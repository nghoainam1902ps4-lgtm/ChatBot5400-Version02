from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from api.auth import TokenUser, auth_disabled, get_current_user, require_admin
from api.models import (
    NotebookCreate,
    NotebookDeletePreview,
    NotebookDeleteResponse,
    NotebookResponse,
    NotebookUpdate,
    RecentlyViewedResponse,
)
from api.recently_viewed import stamp_view
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import Notebook, Source
from open_notebook.exceptions import (
    InvalidInputError,
    NotFoundError,
    OpenNotebookError,
)

router = APIRouter()


def _note_count_scope(current_user: TokenUser) -> tuple[str, dict]:
    """Build the SurrealQL note-count expression scoped to the caller.

    Notes are per-user data (each user only ever sees their own notes), so the
    Notebook Card's note count must be scoped to the current user - otherwise
    it shows the sum of *every* user's notes. The count walks the artifact edge
    to the note node and filters on ``note.user_id``:
    ``count(<-artifact<-note[WHERE user_id = $user])``.

    Source counts stay global (``count(<-reference.in)``) because sources are
    shared data added by admins - every user sees the same source count.

    In single-user mode (auth enforcement disabled) there is no owner to scope
    by, so all notes are counted, matching the behaviour in ``notes.py``.

    Returns the count expression and the query params it needs (empty when
    unscoped).
    """
    if auth_disabled():
        return "count(<-artifact.in)", {}
    return (
        "count(<-artifact<-note[WHERE user_id = $user])",
        {"user": ensure_record_id(current_user.id)},
    )


def _recently_viewed_row(row: dict) -> Optional[RecentlyViewedResponse]:
    """Map a FETCH-ed recently_viewed row to a response, or None if the target
    notebook/source has since been deleted (dangling record link)."""
    item = row.get("item")
    if not isinstance(item, dict):
        # Link no longer resolves (item deleted) -> drop it from the list.
        return None
    item_type = row.get("item_type")
    if item_type not in ("notebook", "source"):
        return None
    title = item.get("name") or item.get("title") or "Untitled"
    return RecentlyViewedResponse(
        type=item_type,
        id=str(item.get("id", "")),
        title=title,
        last_viewed_at=str(row.get("last_viewed_at", "")),
    )


@router.get("/notebooks", response_model=List[NotebookResponse])
async def get_notebooks(
    archived: Optional[bool] = Query(None, description="Filter by archived status"),
    order_by: str = Query("updated desc", description="Order by field and direction"),
    current_user: TokenUser = Depends(get_current_user),
):
    """Get all notebooks with optional filtering and ordering."""
    try:
        # Validate order_by against allowlist to prevent SurrealQL injection
        allowed_fields = {"name", "created", "updated"}
        allowed_directions = {"asc", "desc"}

        parts = order_by.strip().lower().split()
        if len(parts) == 1:
            if parts[0] not in allowed_fields:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid order_by field: '{order_by}'. Allowed fields: {', '.join(sorted(allowed_fields))}",
                )
            validated_order_by = parts[0]
        elif len(parts) == 2:
            if parts[0] not in allowed_fields or parts[1] not in allowed_directions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid order_by: '{order_by}'. Allowed fields: {', '.join(sorted(allowed_fields))}. Allowed directions: asc, desc",
                )
            validated_order_by = f"{parts[0]} {parts[1]}"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid order_by format: '{order_by}'. Expected 'field' or 'field direction'",
            )

        # Build the query with counts. Note count is scoped to the current user
        # (per-user data); source count stays global (shared data).
        note_count_expr, count_params = _note_count_scope(current_user)
        query = f"""
            SELECT *,
            count(<-reference.in) as source_count,
            {note_count_expr} as note_count
            FROM notebook
            ORDER BY {validated_order_by}
        """

        result = await repo_query(query, count_params)

        # Filter by archived status if specified
        if archived is not None:
            result = [nb for nb in result if nb.get("archived") == archived]

        return [
            NotebookResponse(
                id=str(nb.get("id", "")),
                name=nb.get("name", ""),
                description=nb.get("description", ""),
                archived=nb.get("archived", False),
                created=str(nb.get("created", "")),
                updated=str(nb.get("updated", "")),
                source_count=nb.get("source_count", 0),
                note_count=nb.get("note_count", 0),
            )
            for nb in result
        ]
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error fetching notebooks: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching notebooks: {str(e)}"
        )


@router.post(
    "/notebooks",
    response_model=NotebookResponse,
    dependencies=[Depends(require_admin)],
)
async def create_notebook(notebook: NotebookCreate):
    """Create a new notebook."""
    try:
        new_notebook = Notebook(
            name=notebook.name,
            description=notebook.description,
        )
        await new_notebook.save()

        return NotebookResponse(
            id=new_notebook.id or "",
            name=new_notebook.name,
            description=new_notebook.description,
            archived=new_notebook.archived or False,
            created=str(new_notebook.created),
            updated=str(new_notebook.updated),
            source_count=0,  # New notebook has no sources
            note_count=0,  # New notebook has no notes
        )
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error creating notebook: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error creating notebook: {str(e)}"
        )


@router.get("/recently-viewed", response_model=List[RecentlyViewedResponse])
async def get_recently_viewed(
    limit: int = Query(12, ge=1, le=50, description="Number of items to return"),
    current_user: TokenUser = Depends(get_current_user),
):
    """Get the CURRENT user's recently viewed notebooks and sources, newest
    first. View history is per-user (see api/recently_viewed.py), so one user
    never sees another's history."""
    try:
        rows = await repo_query(
            """
            SELECT item, item_type, last_viewed_at
            FROM recently_viewed
            WHERE user = $user
            ORDER BY last_viewed_at DESC
            LIMIT $limit
            FETCH item
            """,
            {"user": ensure_record_id(current_user.id), "limit": limit},
        )

        items = [
            mapped
            for row in rows
            if (mapped := _recently_viewed_row(row)) is not None
        ]
        return items[:limit]
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        # Log full context server-side; return a generic message so internal
        # details are not leaked to clients.
        logger.exception(f"Error fetching recently viewed items: {e}")
        raise HTTPException(
            status_code=500, detail="Error fetching recently viewed items"
        )


@router.get(
    "/notebooks/{notebook_id}/delete-preview", response_model=NotebookDeletePreview
)
async def get_notebook_delete_preview(notebook_id: str):
    """Get a preview of what will be deleted when this notebook is deleted."""
    try:
        notebook = await Notebook.get(notebook_id)

        preview = await notebook.get_delete_preview()

        return NotebookDeletePreview(
            notebook_id=str(notebook.id),
            notebook_name=notebook.name,
            note_count=preview["note_count"],
            exclusive_source_count=preview["exclusive_source_count"],
            shared_source_count=preview["shared_source_count"],
        )
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error getting delete preview for notebook {notebook_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching notebook deletion preview: {str(e)}",
        )


@router.get("/notebooks/{notebook_id}", response_model=NotebookResponse)
async def get_notebook(
    notebook_id: str,
    current_user: TokenUser = Depends(get_current_user),
):
    """Get a specific notebook by ID."""
    try:
        # Query with counts for single notebook. Note count is scoped to the
        # current user (per-user data); source count stays global (shared data).
        note_count_expr, count_params = _note_count_scope(current_user)
        query = f"""
            SELECT *,
            count(<-reference.in) as source_count,
            {note_count_expr} as note_count
            FROM $notebook_id
        """
        result = await repo_query(
            query,
            {"notebook_id": ensure_record_id(notebook_id), **count_params},
        )

        if not result:
            raise HTTPException(status_code=404, detail="Notebook not found")

        await stamp_view(current_user.id, notebook_id, "notebook")

        nb = result[0]
        return NotebookResponse(
            id=str(nb.get("id", "")),
            name=nb.get("name", ""),
            description=nb.get("description", ""),
            archived=nb.get("archived", False),
            created=str(nb.get("created", "")),
            updated=str(nb.get("updated", "")),
            source_count=nb.get("source_count", 0),
            note_count=nb.get("note_count", 0),
        )
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error fetching notebook {notebook_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching notebook: {str(e)}"
        )


@router.put(
    "/notebooks/{notebook_id}",
    response_model=NotebookResponse,
    dependencies=[Depends(require_admin)],
)
async def update_notebook(
    notebook_id: str,
    notebook_update: NotebookUpdate,
    current_user: TokenUser = Depends(get_current_user),
):
    """Update a notebook."""
    try:
        notebook = await Notebook.get(notebook_id)

        # Update only provided fields
        if notebook_update.name is not None:
            notebook.name = notebook_update.name
        if notebook_update.description is not None:
            notebook.description = notebook_update.description
        if notebook_update.archived is not None:
            notebook.archived = notebook_update.archived

        await notebook.save()

        # Query with counts after update. Note count is scoped to the current
        # user (per-user data); source count stays global (shared data).
        note_count_expr, count_params = _note_count_scope(current_user)
        query = f"""
            SELECT *,
            count(<-reference.in) as source_count,
            {note_count_expr} as note_count
            FROM $notebook_id
        """
        result = await repo_query(
            query,
            {"notebook_id": ensure_record_id(notebook_id), **count_params},
        )

        if result:
            nb = result[0]
            return NotebookResponse(
                id=str(nb.get("id", "")),
                name=nb.get("name", ""),
                description=nb.get("description", ""),
                archived=nb.get("archived", False),
                created=str(nb.get("created", "")),
                updated=str(nb.get("updated", "")),
                source_count=nb.get("source_count", 0),
                note_count=nb.get("note_count", 0),
            )

        # Fallback if query fails
        return NotebookResponse(
            id=notebook.id or "",
            name=notebook.name,
            description=notebook.description,
            archived=notebook.archived or False,
            created=str(notebook.created),
            updated=str(notebook.updated),
            source_count=0,
            note_count=0,
        )
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error updating notebook {notebook_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating notebook: {str(e)}"
        )


@router.post(
    "/notebooks/{notebook_id}/sources/{source_id}",
    dependencies=[Depends(require_admin)],
)
async def add_source_to_notebook(notebook_id: str, source_id: str):
    """Add an existing source to a notebook (create the reference)."""
    try:
        # Verify the notebook and source exist (raises NotFoundError -> 404)
        await Notebook.get(notebook_id)
        await Source.get(source_id)

        # Check if reference already exists (idempotency)
        existing_ref = await repo_query(
            "SELECT * FROM reference WHERE out = $source_id AND in = $notebook_id",
            {
                "notebook_id": ensure_record_id(notebook_id),
                "source_id": ensure_record_id(source_id),
            },
        )

        # If reference doesn't exist, create it
        if not existing_ref:
            await repo_query(
                "RELATE $source_id->reference->$notebook_id",
                {
                    "notebook_id": ensure_record_id(notebook_id),
                    "source_id": ensure_record_id(source_id),
                },
            )

        return {"message": "Source linked to notebook successfully"}
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook or source not found")
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(
            f"Error linking source {source_id} to notebook {notebook_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Error linking source to notebook: {str(e)}"
        )


@router.delete(
    "/notebooks/{notebook_id}/sources/{source_id}",
    dependencies=[Depends(require_admin)],
)
async def remove_source_from_notebook(notebook_id: str, source_id: str):
    """Remove a source from a notebook (delete the reference)."""
    try:
        # Verify the notebook exists (raises NotFoundError -> 404)
        await Notebook.get(notebook_id)

        # Delete the reference record linking source to notebook
        await repo_query(
            "DELETE FROM reference WHERE out = $notebook_id AND in = $source_id",
            {
                "notebook_id": ensure_record_id(notebook_id),
                "source_id": ensure_record_id(source_id),
            },
        )

        return {"message": "Source removed from notebook successfully"}
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(
            f"Error removing source {source_id} from notebook {notebook_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Error removing source from notebook: {str(e)}"
        )


@router.delete(
    "/notebooks/{notebook_id}",
    response_model=NotebookDeleteResponse,
    dependencies=[Depends(require_admin)],
)
async def delete_notebook(
    notebook_id: str,
    delete_exclusive_sources: bool = Query(
        False,
        description="Whether to delete sources that belong only to this notebook",
    ),
):
    """
    Delete a notebook with cascade deletion.

    Always deletes all notes associated with the notebook.
    If delete_exclusive_sources is True, also deletes sources that belong only
    to this notebook (not linked to any other notebooks).
    """
    try:
        notebook = await Notebook.get(notebook_id)

        result = await notebook.delete(
            delete_exclusive_sources=delete_exclusive_sources
        )

        return NotebookDeleteResponse(
            message="Notebook deleted successfully",
            deleted_notes=result["deleted_notes"],
            deleted_sources=result["deleted_sources"],
            unlinked_sources=result["unlinked_sources"],
            deleted_chat_sessions=result["deleted_chat_sessions"],
        )
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error deleting notebook {notebook_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error deleting notebook: {str(e)}"
        )
