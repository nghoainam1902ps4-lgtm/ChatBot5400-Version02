"""Approval-workflow helpers for ChatBot5400.

Centralises the scope logic shared by the sources, notebooks and approvals
routers: what an approver is allowed to review/manage, and how pending-source
rows map to the API response. Admins have global scope; approvers are limited
to the categories (and their sub-notebooks) an admin assigned to them.
"""

from typing import Any, Dict, List, Optional

from api.auth import TokenUser
from api.models import ApprovalItemResponse, ApprovalNotebookRef
from open_notebook.domain.notebook import Notebook, Source
from open_notebook.exceptions import AuthorizationError


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


async def list_pending(user: TokenUser) -> List[ApprovalItemResponse]:
    """Pending sources awaiting this reviewer's action."""
    scope = await scope_ids_for(user)
    if scope is not None and not scope:
        return []
    rows = await Source.get_pending(scope)
    return [_map_pending_row(row) for row in rows]


async def count_pending(user: TokenUser) -> int:
    """Number of pending sources awaiting this reviewer's action."""
    scope = await scope_ids_for(user)
    if scope is not None and not scope:
        return 0
    return await Source.count_pending(scope)


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
