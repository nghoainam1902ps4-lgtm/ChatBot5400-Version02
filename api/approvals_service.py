"""Approval-workflow helpers for ChatBot5400.

Centralises the scope logic shared by the sources, notebooks and approvals
routers: what an approver is allowed to review/manage, and how pending-source
rows map to the API response. Admins have global scope; approvers are limited
to the categories (and their sub-notebooks) an admin assigned to them.
"""

from typing import Any, Dict, List, Optional

from api.auth import TokenUser, auth_disabled
from api.models import ApprovalItemResponse, ApprovalNotebookRef, ReviewerResponse
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import Notebook, Source
from open_notebook.exceptions import AuthorizationError, NotFoundError


async def scope_ids_for(user: TokenUser) -> Optional[List[str]]:
    """Notebook-id scope for a reviewer.

    Returns ``None`` for an admin (global scope), the managed notebook ids for
    an approver, or ``[]`` for anyone else (no review scope).
    """
    if user.is_admin:
        return None
    if user.is_approver:
        return await Notebook.managed_scope_ids(user.id)
    return []


def _derive_type(asset: Optional[Dict[str, Any]]) -> str:
    if not asset:
        return "text"
    if asset.get("url"):
        return "link"
    if asset.get("file_path"):
        return "upload"
    return "text"


def _map_pending_row(row: Dict[str, Any]) -> ApprovalItemResponse:
    submitter = row.get("submitted_by")
    submitter_id = None
    submitter_name = None
    if isinstance(submitter, dict):
        submitter_id = str(submitter.get("id")) if submitter.get("id") else None
        submitter_name = submitter.get("name") or submitter.get("username")
    elif submitter:
        submitter_id = str(submitter)

    notebooks = []
    for nb in row.get("notebooks") or []:
        if isinstance(nb, dict) and nb.get("id"):
            notebooks.append(
                ApprovalNotebookRef(
                    id=str(nb.get("id")), name=nb.get("name") or "Untitled"
                )
            )

    submitted_at = row.get("submitted_at")
    return ApprovalItemResponse(
        id=str(row.get("id")),
        title=row.get("title"),
        type=_derive_type(row.get("asset")),
        approval_status=row.get("approval_status") or "pending",
        submitted_by_id=submitter_id,
        submitted_by_name=submitter_name,
        submitted_at=str(submitted_at) if submitted_at else None,
        notebooks=notebooks,
    )


def _reviewer_id_for(user: TokenUser) -> Optional[str]:
    """The approver id to match directed submissions against (None for admin)."""
    return None if user.is_admin else user.id


async def list_pending(user: TokenUser) -> List[ApprovalItemResponse]:
    """Pending sources awaiting this reviewer's action."""
    scope = await scope_ids_for(user)
    reviewer_id = _reviewer_id_for(user)
    if scope is not None and not scope and not reviewer_id:
        return []
    rows = await Source.get_pending(scope, reviewer_id)
    return [_map_pending_row(row) for row in rows]


async def count_pending(user: TokenUser) -> int:
    """Number of pending sources awaiting this reviewer's action."""
    scope = await scope_ids_for(user)
    reviewer_id = _reviewer_id_for(user)
    if scope is not None and not scope and not reviewer_id:
        return 0
    return await Source.count_pending(scope, reviewer_id)


async def eligible_reviewers(notebook_ids: List[str]) -> List[ReviewerResponse]:
    """Approvers a contributor may route a submission to: those managing the
    category (top-level notebook) of any selected notebook.

    An empty ``notebook_ids`` returns every approver (the submission has no
    notebook scope yet, so any approver is a valid target).
    """
    try:
        category_ids: set[str] = set()
        if notebook_ids:
            rows = await repo_query(
                "SELECT id, parent FROM notebook WHERE id IN $ids",
                {"ids": [ensure_record_id(x) for x in notebook_ids]},
            )
            for row in rows or []:
                parent = row.get("parent")
                # A sub-notebook inherits its category (parent); a top-level
                # notebook is its own category.
                category_ids.add(str(parent) if parent else str(row.get("id")))

        if category_ids:
            manager_rows = await repo_query(
                "SELECT VALUE managers FROM notebook WHERE id IN $ids",
                {"ids": [ensure_record_id(x) for x in category_ids]},
            )
            user_ids: set[str] = set()
            for managers in manager_rows or []:
                for m in managers or []:
                    user_ids.add(str(m))
            if not user_ids:
                return []
            users = await repo_query(
                "SELECT id, name, username FROM user "
                "WHERE id IN $ids AND role = 'approver' ORDER BY username ASC",
                {"ids": [ensure_record_id(u) for u in user_ids]},
            )
        else:
            # No notebook scope yet: any approver is eligible.
            users = await repo_query(
                "SELECT id, name, username FROM user "
                "WHERE role = 'approver' ORDER BY username ASC"
            )

        return [
            ReviewerResponse(
                id=str(u.get("id")),
                username=u.get("username") or "",
                name=u.get("name"),
            )
            for u in (users or [])
        ]
    except Exception:
        # Reviewer picking is best-effort; never block the add-source flow.
        return []


async def assert_can_review_source(user: TokenUser, source: Source) -> None:
    """Raise AuthorizationError unless the caller may review this source."""
    if user.is_admin:
        return
    if not user.is_approver:
        raise AuthorizationError("Approver privileges required")
    scope = await Notebook.managed_scope_ids(user.id)
    if not scope:
        raise AuthorizationError("This source is outside your managed categories")
    referenced = set(await source.referenced_notebook_ids())
    if referenced.isdisjoint(set(scope)):
        raise AuthorizationError("This source is outside your managed categories")


async def assert_can_view_source(user: TokenUser, source: Source) -> None:
    """Hide a source that is still awaiting approval from callers who may not
    see it.

    Approved sources are visible to everyone. A pending source is visible only
    to an admin, its submitter, the approver it was routed to, and approvers
    managing one of its notebooks. Everyone else gets NotFoundError (404) so the
    endpoint does not reveal that the document exists.
    """
    if (source.approval_status or "approved") == "approved":
        return
    if auth_disabled() or user.is_admin:
        return
    if source.submitted_by and str(source.submitted_by) == user.id:
        return
    if user.is_approver:
        if source.assigned_approver and str(source.assigned_approver) == user.id:
            return
        try:
            await assert_can_review_source(user, source)
            return
        except AuthorizationError:
            pass
    raise NotFoundError("Source not found")


async def assert_can_manage_notebook(user: TokenUser, notebook_id: str) -> None:
    """Raise AuthorizationError unless the caller manages this notebook.

    Used to gate approver actions scoped to a category/sub-notebook (creating a
    sub-notebook under it, linking an existing source into it without review).
    Admins always pass.
    """
    if user.is_admin:
        return
    if not user.is_approver:
        raise AuthorizationError("Approver privileges required")
    scope = await Notebook.managed_scope_ids(user.id)
    if str(notebook_id) not in set(scope):
        raise AuthorizationError(
            "This notebook is outside your managed categories"
        )
