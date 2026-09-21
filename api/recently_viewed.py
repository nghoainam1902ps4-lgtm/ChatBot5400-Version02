"""Per-user "recently viewed" tracking.

Notebooks and sources are shared, admin-managed resources. Recording the last
view as a single ``last_viewed_at`` field on the notebook/source row therefore
leaked one user's browsing history to every other user. Instead we keep a
``recently_viewed`` row per ``(user, item)`` pair (see migration 29) so each
user only ever sees their own history.
"""

from typing import Literal

from loguru import logger

from open_notebook.database.repository import ensure_record_id, repo_query

ItemType = Literal["notebook", "source"]


async def stamp_view(user_id: str, item_id: str, item_type: ItemType) -> None:
    """Best-effort record that ``user_id`` viewed ``item_id`` just now.

    Uses a deterministic composite record id (``recently_viewed:[user, item]``)
    so repeat views upsert the same row instead of piling up duplicates.
    Recording a view must never turn a successful read into an error, so any
    failure is logged and swallowed.
    """
    if not user_id or not item_id:
        return
    try:
        # UPSERT (not UPDATE): on SurrealDB 2.x, UPDATE on a record id that does
        # not exist yet is a no-op and creates nothing, so the very first view of
        # any (user, item) pair would never be recorded. UPSERT creates the row
        # if missing and overwrites it on repeat views.
        await repo_query(
            """
            UPSERT type::thing('recently_viewed', [$uid, $iid]) SET
                user = $user,
                item = $item,
                item_type = $item_type,
                last_viewed_at = time::now();
            """,
            {
                "uid": user_id,
                "iid": item_id,
                "user": ensure_record_id(user_id),
                "item": ensure_record_id(item_id),
                "item_type": item_type,
            },
        )
    except Exception as e:  # noqa: BLE001 - best-effort, never fail the read
        logger.warning(f"Failed to stamp view for {item_type} {item_id}: {e}")
