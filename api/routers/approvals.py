"""Approval-queue router for ChatBot5400.

Lets approvers ("nguoi duyet") and admins review the sources/van ban that
contributors submit. A pending source is invisible to regular users until an
approver in whose managed category it was submitted approves it.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger

from api import approvals_service
from api.auth import TokenUser, require_approver, require_submitter
from api.models import (
    ApprovalItemResponse,
    PendingApprovalCountResponse,
    RejectSourceRequest,
    ReviewActionResponse,
    ReviewerResponse,
)
from open_notebook.domain.notebook import Source
from open_notebook.exceptions import (
    InvalidInputError,
    NotFoundError,
    OpenNotebookError,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("/reviewers", response_model=List[ReviewerResponse])
async def list_reviewers(
    notebook_id: Optional[List[str]] = Query(
        None, description="Notebook id(s) to scope eligible approvers to"
    ),
    _current_user: TokenUser = Depends(require_submitter),
):
    """Approvers a submitter can route a source to (managers of the selected
    notebooks' categories; all approvers when no notebook is selected)."""
    return await approvals_service.eligible_reviewers(notebook_id or [])


@router.get("/pending", response_model=List[ApprovalItemResponse])
async def list_pending_approvals(
    current_user: TokenUser = Depends(require_approver),
):
    """List sources awaiting the caller's review (scoped to managed categories)."""
    return await approvals_service.list_pending(current_user)


@router.get("/count", response_model=PendingApprovalCountResponse)
async def pending_approval_count(
    current_user: TokenUser = Depends(require_approver),
):
    """Badge count: how many sources await the caller's review."""
    count = await approvals_service.count_pending(current_user)
    return PendingApprovalCountResponse(count=count)


@router.post(
    "/sources/{source_id}/approve", response_model=ReviewActionResponse
)
async def approve_source(
    source_id: str,
    current_user: TokenUser = Depends(require_approver),
):
    """Approve a pending source, making it visible and queued for embedding."""
    try:
        source = await Source.get(source_id)
        await approvals_service.assert_can_review_source(current_user, source)
        await source.approve(current_user.id)
        logger.info(f"Source {source_id} approved by '{current_user.username}'")
        return ReviewActionResponse(
            source_id=source_id,
            approval_status="approved",
            message="Source approved",
        )
    except NotFoundError:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error approving source {source_id}: {str(e)}")
        raise


@router.post(
    "/sources/{source_id}/reject", response_model=ReviewActionResponse
)
async def reject_source(
    source_id: str,
    request: RejectSourceRequest,
    current_user: TokenUser = Depends(require_approver),
):
    """Reject a pending source and DELETE it from the system.

    A rejected submission is discarded entirely (record, file, embeddings,
    insights and notebook links) so it does not linger as clutter. The reason is
    logged server-side for audit.
    """
    try:
        source = await Source.get(source_id)
        await approvals_service.assert_can_review_source(current_user, source)
        # Rejecting deletes the document, so it is only allowed while it is
        # still awaiting approval; removing approved content stays admin-only.
        if not source.is_pending:
            raise InvalidInputError(
                "Only a document awaiting approval can be rejected"
            )
        logger.info(
            f"Source {source_id} rejected by '{current_user.username}' "
            f"(reason: {request.reason or '-'}); deleting it"
        )
        await source.delete()
        return ReviewActionResponse(
            source_id=source_id,
            approval_status="rejected",
            message="Source rejected and removed",
        )
    except NotFoundError:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error rejecting source {source_id}: {str(e)}")
        raise
