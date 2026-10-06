"""AI feedback router (ChatBot5400 P2A).

Thin HTTP layer over `api.feedback_service`. User endpoints are owner-scoped;
admin endpoints require an admin caller and only ever read server-side
snapshots (never live chat history of other users).
"""

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger
from pydantic import BaseModel, Field

from api import feedback_service
from api.auth import TokenUser, get_current_user, require_admin
from open_notebook.exceptions import OpenNotebookError

router = APIRouter()


# --- request / response models -------------------------------------------
class ReactionRequest(BaseModel):
    session_id: str = Field(..., description="Chat session id that owns the message")
    # Enum (and the null-to-clear case) is enforced here at the API layer; the
    # DB column is an open option<string> on purpose (see migration 30).
    reaction: Optional[Literal["like", "dislike"]] = Field(
        None, description="New reaction, or null to clear it"
    )


class ReportRequest(BaseModel):
    session_id: str = Field(..., description="Chat session id that owns the message")
    reason: str = Field(..., description="Report reason (1..2000 chars, trimmed)")


class FeedbackStateResponse(BaseModel):
    message_id: str
    reaction: Optional[str] = None
    reported: bool = False


class AdminStatsResponse(BaseModel):
    total: int
    likes: int
    dislikes: int
    reports: int


class AdminFeedbackItem(BaseModel):
    id: str
    username_snapshot: str
    user_name_snapshot: Optional[str] = None
    session_id: str
    message_id: str
    context_type: str
    context_id: Optional[str] = None
    context_title_snapshot: Optional[str] = None
    question_snapshot: str
    answer_snapshot: str
    reaction: Optional[str] = None
    reported: bool
    report_reason: Optional[str] = None
    reported_at: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None


class AdminListResponse(BaseModel):
    items: List[AdminFeedbackItem]
    page: int
    page_size: int
    total: int
    total_pages: int


# --- user endpoints -------------------------------------------------------
@router.get(
    "/feedback/sessions/{session_id}", response_model=List[FeedbackStateResponse]
)
async def get_session_feedback(
    session_id: str, current: TokenUser = Depends(get_current_user)
):
    """Batch feedback state for every AI message in a session (owner only)."""
    try:
        return await feedback_service.get_session_feedback(session_id, current)
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error loading session feedback: {e}")
        raise


@router.put(
    "/feedback/messages/{message_id}/reaction",
    response_model=FeedbackStateResponse,
)
async def set_reaction(
    message_id: str,
    request: ReactionRequest,
    current: TokenUser = Depends(get_current_user),
):
    """Set or clear a like/dislike on an AI answer (idempotent, owner only)."""
    try:
        return await feedback_service.set_reaction(
            request.session_id, message_id, request.reaction, current
        )
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error setting reaction: {e}")
        raise


@router.post(
    "/feedback/messages/{message_id}/report",
    response_model=FeedbackStateResponse,
)
async def report_message(
    message_id: str,
    request: ReportRequest,
    current: TokenUser = Depends(get_current_user),
):
    """Report an AI answer (idempotent, owner only)."""
    try:
        return await feedback_service.set_report(
            request.session_id, message_id, request.reason, current
        )
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error reporting message: {e}")
        raise


# --- admin endpoints ------------------------------------------------------
@router.get("/feedback/admin/stats", response_model=AdminStatsResponse)
async def feedback_admin_stats(_admin: TokenUser = Depends(require_admin)):
    """Aggregate stats (admin only). Counts overlap; they do not sum to total."""
    return await feedback_service.admin_stats()


@router.get("/feedback/admin", response_model=AdminListResponse)
async def feedback_admin_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    q: Optional[str] = Query(None),
    type: Optional[Literal["like", "dislike", "report"]] = Query(None),
    context: Optional[Literal["notebook", "source"]] = Query(None),
    sort: str = Query("created"),
    direction: Literal["asc", "desc"] = Query("desc"),
    _admin: TokenUser = Depends(require_admin),
):
    """Server-side paginated/filtered/sorted feedback list (admin only)."""
    return await feedback_service.admin_list(
        page=page,
        page_size=page_size,
        q=q,
        type_filter=type,
        context=context,
        sort=sort,
        direction=direction,
    )
