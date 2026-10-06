"""AI feedback service (ChatBot5400 P2A).

Business logic for Like / Dislike / Report on AI chat answers. Routers stay
thin and call into here (see api/AGENTS.md: routes -> services -> models).

Security / privacy invariants enforced here, never trusted from the client:

- The caller must own the chat session (same rule as the chat routers — a
  session is private to its owner, even from an admin). See `_owned_session`.
- The question text, answer text, username and display name stored on a
  feedback row are SERVER-SIDE snapshots read from the real LangGraph
  checkpoint, never taken from the request body.
- Admin reads only these snapshots; there is no path here (or anywhere) that
  lets an admin browse another user's live chat history.

One row per (user, session, AI message), keyed by the deterministic composite
record id `ai_feedback:[user_id, session_id, message_id]`, so repeat actions
UPSERT in place and never duplicate (migration 30).
"""

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from langchain_core.runnables import RunnableConfig

from api.auth import TokenUser, auth_disabled
from api.routers._chat_shared import get_session_or_404
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import ChatSession, Notebook, Source
from open_notebook.domain.user import User
from open_notebook.graphs.chat import graph as chat_graph
from open_notebook.graphs.source_chat import source_chat_graph
from open_notebook.utils.text_utils import extract_text_content

# Client-side temporary ids (optimistic/streaming) never correspond to a
# persisted message and must never be accepted.
_TEMP_ID_PREFIXES = ("temp-", "ai-")

REPORT_REASON_MAX = 2000

# Admin list: only these columns/directions may reach the ORDER BY clause.
_SORT_COLUMNS = {
    "created",
    "reaction",
    "reported",
    "username_snapshot",
    "context_type",
}
_SORT_DIRS = {"asc": "ASC", "desc": "DESC"}

# Shared composite-id selector; every statement targets exactly one row.
_ID = "type::thing('ai_feedback', [$uid, $sid, $mid])"

_UPSERT_SNAPSHOT = """
SET user_id = $user,
    username_snapshot = $uname,
    user_name_snapshot = $name,
    session_id = $sid,
    message_id = $mid,
    context_type = $ct,
    context_id = $cid,
    context_title_snapshot = $ctitle,
    question_snapshot = $q,
    answer_snapshot = $a
"""


# --- ownership & helpers --------------------------------------------------
def _owned_session(session: ChatSession, current: TokenUser) -> ChatSession:
    """Owner-only, mirroring the chat routers. 404 (not 403) so a non-owner
    cannot even learn the session exists. Skipped in single-user mode."""
    if auth_disabled():
        return session
    owner = getattr(session, "user_id", None)
    if owner is None or str(owner) != str(current.id):
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _msg_content(msg: Any) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    try:
        return extract_text_content(content)
    except Exception:  # noqa: BLE001 - defensive: snapshot must not crash feedback
        return str(content)


async def _resolve_context(full_session_id: str):
    """Return (context_type, context_id, graph) from the session's refers_to
    target. Both notebook and source chat sessions use the `refers_to` relation;
    the target's table prefix disambiguates which graph owns the history."""
    rel = await repo_query(
        "SELECT out FROM refers_to WHERE in = $sid",
        {"sid": ensure_record_id(full_session_id)},
    )
    out = str(rel[0]["out"]) if rel and rel[0].get("out") is not None else ""
    if out.startswith("notebook:"):
        return "notebook", out, chat_graph
    if out.startswith("source:"):
        return "source", out, source_chat_graph
    raise HTTPException(status_code=404, detail="Session context not found")


async def _context_title(context_type: str, context_id: str) -> Optional[str]:
    try:
        if context_type == "notebook":
            nb = await Notebook.get(context_id)
            return getattr(nb, "name", None)
        src = await Source.get(context_id)
        return getattr(src, "title", None)
    except Exception:  # noqa: BLE001 - title is best-effort snapshot
        return None


async def _display_name(user_id: str) -> Optional[str]:
    try:
        user = await User.get(user_id)
        return getattr(user, "name", None)
    except Exception:  # noqa: BLE001 - name snapshot is best-effort (e.g. dev user)
        return None


async def _ai_question_answer(full_session_id: str, message_id: str, graph) -> tuple[str, str]:
    """Read the real LangGraph checkpoint, locate the AI message by id, and
    return (nearest preceding human question, that AI answer). Rejects a
    message that is missing, not an AI message, or has no question before it."""
    state = await asyncio.to_thread(
        graph.get_state,
        config=RunnableConfig(configurable={"thread_id": full_session_id}),
    )
    messages: List[Any] = []
    if state and state.values and "messages" in state.values:
        messages = state.values["messages"]

    target_idx = None
    for i, msg in enumerate(messages):
        if str(getattr(msg, "id", "") or "") == message_id:
            target_idx = i
            break
    if target_idx is None:
        raise HTTPException(status_code=404, detail="Message not found in session")

    target = messages[target_idx]
    if getattr(target, "type", None) != "ai":
        raise HTTPException(
            status_code=400, detail="Feedback is only allowed on AI answers"
        )

    question = None
    for j in range(target_idx - 1, -1, -1):
        if getattr(messages[j], "type", None) == "human":
            question = _msg_content(messages[j])
            break
    if question is None:
        raise HTTPException(
            status_code=400, detail="No question found for this answer"
        )

    return question, _msg_content(target)


async def _build_snapshot(
    session_id: str, message_id: str, current: TokenUser
) -> Dict[str, Any]:
    """Validate ownership + message identity and assemble the server-side
    snapshot. Raises HTTPException on any invalid state."""
    if message_id.startswith(_TEMP_ID_PREFIXES):
        raise HTTPException(
            status_code=400, detail="Feedback is not allowed on unsaved messages"
        )
    full_session_id, session = await get_session_or_404(session_id)
    _owned_session(session, current)
    context_type, context_id, graph = await _resolve_context(full_session_id)
    question, answer = await _ai_question_answer(full_session_id, message_id, graph)
    return {
        "full_session_id": full_session_id,
        "uid": str(current.id),
        "user_rid": ensure_record_id(current.id),
        "username": current.username,
        "name": await _display_name(current.id),
        "context_type": context_type,
        "context_id": context_id,
        "context_title": await _context_title(context_type, context_id),
        "question": question,
        "answer": answer,
    }


def _snapshot_params(snap: Dict[str, Any], message_id: str) -> Dict[str, Any]:
    return {
        "uid": snap["uid"],
        "sid": snap["full_session_id"],
        "mid": message_id,
        "user": snap["user_rid"],
        "uname": snap["username"],
        "name": snap["name"],
        "ct": snap["context_type"],
        "cid": snap["context_id"],
        "ctitle": snap["context_title"],
        "q": snap["question"],
        "a": snap["answer"],
    }


# --- user operations ------------------------------------------------------
async def get_session_feedback(
    session_id: str, current: TokenUser
) -> List[Dict[str, Any]]:
    """Batch feedback state for every AI message in a session (owner only).

    One query, no N+1. Returns only the caller's own rows.
    """
    full_session_id, session = await get_session_or_404(session_id)
    _owned_session(session, current)

    if auth_disabled():
        rows = await repo_query(
            "SELECT message_id, reaction, reported FROM ai_feedback "
            "WHERE session_id = $sid",
            {"sid": str(full_session_id)},
        )
    else:
        rows = await repo_query(
            "SELECT message_id, reaction, reported FROM ai_feedback "
            "WHERE session_id = $sid AND user_id = $user",
            {"sid": str(full_session_id), "user": ensure_record_id(current.id)},
        )
    return [
        {
            "message_id": r.get("message_id"),
            "reaction": r.get("reaction"),
            "reported": bool(r.get("reported")),
        }
        for r in rows
    ]


async def set_reaction(
    session_id: str, message_id: str, reaction: Optional[str], current: TokenUser
) -> Dict[str, Any]:
    """Idempotent upsert of a like/dislike, or clear it.

    - reaction in {like, dislike}: upsert the row (snapshot refreshed).
    - reaction is None: remove the reaction. If the row carries no report, the
      whole row is DELETED (so 'Total feedback' never counts undone reactions);
      if it is reported, the row stays and only `reaction` is cleared.
    """
    if reaction is not None and reaction not in ("like", "dislike"):
        raise HTTPException(status_code=422, detail="Invalid reaction")

    snap = await _build_snapshot(session_id, message_id, current)
    id_params = {
        "uid": snap["uid"],
        "sid": snap["full_session_id"],
        "mid": message_id,
    }

    if reaction is None:
        existing = await repo_query(
            f"SELECT reported FROM {_ID}", id_params
        )
        reported = bool(existing[0]["reported"]) if existing else False
        if reported:
            await repo_query(f"UPDATE {_ID} SET reaction = NONE", id_params)
            return {"message_id": message_id, "reaction": None, "reported": True}
        await repo_query(f"DELETE {_ID}", id_params)
        return {"message_id": message_id, "reaction": None, "reported": False}

    params = _snapshot_params(snap, message_id)
    params["reaction"] = reaction
    rows = await repo_query(
        f"UPSERT {_ID} {_UPSERT_SNAPSHOT}, reaction = $reaction",
        params,
    )
    row = rows[0] if rows else {}
    return {
        "message_id": message_id,
        "reaction": row.get("reaction", reaction),
        "reported": bool(row.get("reported")),
    }


async def set_report(
    session_id: str, message_id: str, reason: Optional[str], current: TokenUser
) -> Dict[str, Any]:
    """Idempotent report. Independent of the reaction (a row may be
    reported and liked/disliked at once). Reason is required, trimmed,
    1..2000 chars. Re-reporting the same answer updates the same row."""
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="Report reason is required")
    if len(reason) > REPORT_REASON_MAX:
        raise HTTPException(
            status_code=422,
            detail=f"Report reason must be at most {REPORT_REASON_MAX} characters",
        )

    snap = await _build_snapshot(session_id, message_id, current)
    params = _snapshot_params(snap, message_id)
    params["reason"] = reason
    rows = await repo_query(
        f"UPSERT {_ID} {_UPSERT_SNAPSHOT}, "
        "reported = true, report_reason = $reason, reported_at = time::now()",
        params,
    )
    row = rows[0] if rows else {}
    return {
        "message_id": message_id,
        "reaction": row.get("reaction"),
        "reported": True,
    }


# --- admin operations -----------------------------------------------------
async def _count(query: str, params: Optional[Dict[str, Any]] = None) -> int:
    rows = await repo_query(query, params or {})
    if rows and isinstance(rows[0], dict):
        return int(rows[0].get("count", 0))
    return 0


async def admin_stats() -> Dict[str, int]:
    """Aggregate counts. Numbers overlap on purpose (one row can be both a
    dislike and a report), so likes + dislikes + reports != total."""
    return {
        "total": await _count("SELECT count() FROM ai_feedback GROUP ALL"),
        "likes": await _count(
            "SELECT count() FROM ai_feedback WHERE reaction = 'like' GROUP ALL"
        ),
        "dislikes": await _count(
            "SELECT count() FROM ai_feedback WHERE reaction = 'dislike' GROUP ALL"
        ),
        "reports": await _count(
            "SELECT count() FROM ai_feedback WHERE reported = true GROUP ALL"
        ),
    }


async def admin_list(
    page: int = 1,
    page_size: int = 30,
    q: Optional[str] = None,
    type_filter: Optional[str] = None,
    context: Optional[str] = None,
    sort: str = "created",
    direction: str = "desc",
) -> Dict[str, Any]:
    """Server-side paginated/filtered/sorted admin listing.

    Security: `q` is always a bound parameter; `type_filter`, `context`, the
    sort column and direction are matched against fixed allowlists before they
    reach the query string, so none of them is interpolated raw.
    """
    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    where: List[str] = []
    params: Dict[str, Any] = {}

    if type_filter == "like":
        where.append("reaction = 'like'")
    elif type_filter == "dislike":
        where.append("reaction = 'dislike'")
    elif type_filter == "report":
        where.append("reported = true")

    if context in ("notebook", "source"):
        where.append("context_type = $ctx")
        params["ctx"] = context

    if q and q.strip():
        params["q"] = q.strip().lower()
        where.append(
            "(string::lowercase(username_snapshot) CONTAINS $q "
            "OR string::lowercase(question_snapshot) CONTAINS $q "
            "OR string::lowercase(answer_snapshot) CONTAINS $q "
            "OR string::lowercase(report_reason ?? '') CONTAINS $q)"
        )

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    sort_col = sort if sort in _SORT_COLUMNS else "created"
    sort_dir = _SORT_DIRS.get((direction or "desc").lower(), "DESC")

    total = await _count(
        f"SELECT count() FROM ai_feedback{clause} GROUP ALL", params
    )
    total_pages = (total + page_size - 1) // page_size if total else 0
    start = (page - 1) * page_size

    rows = await repo_query(
        f"SELECT * FROM ai_feedback{clause} "
        f"ORDER BY {sort_col} {sort_dir} LIMIT {page_size} START {start}",
        params,
    )

    items = [_serialize_row(r) for r in rows]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _serialize_row(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(r.get("id")) if r.get("id") is not None else "",
        "username_snapshot": r.get("username_snapshot") or "",
        "user_name_snapshot": r.get("user_name_snapshot"),
        "session_id": str(r.get("session_id")) if r.get("session_id") else "",
        "message_id": r.get("message_id") or "",
        "context_type": r.get("context_type") or "",
        "context_id": str(r.get("context_id")) if r.get("context_id") else None,
        "context_title_snapshot": r.get("context_title_snapshot"),
        "question_snapshot": r.get("question_snapshot") or "",
        "answer_snapshot": r.get("answer_snapshot") or "",
        "reaction": r.get("reaction"),
        "reported": bool(r.get("reported")),
        "report_reason": r.get("report_reason"),
        "reported_at": str(r.get("reported_at")) if r.get("reported_at") else None,
        "created": str(r.get("created")) if r.get("created") else None,
        "updated": str(r.get("updated")) if r.get("updated") else None,
    }
