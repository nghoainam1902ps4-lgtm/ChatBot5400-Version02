"""Tests for the AI feedback feature (ChatBot5400 P2A).

Two layers:
- Service-level tests run against a REAL embedded SurrealDB (`mem://`) with the
  actual migration-30 schema applied, so idempotency / delete-empty / switch /
  stats / pagination are verified against real SurrealQL. Only `repo_query` is
  redirected to the in-memory connection; the chat session lookup and LangGraph
  state are mocked following tests/test_chat_routers_characterization.py.
- HTTP-level tests exercise routing, request validation and the admin guard
  through the FastAPI TestClient.

conftest.py disables auth for the suite (dev admin); tests that need real
ownership / admin enforcement re-enable it explicitly.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from api import feedback_service as fs
from open_notebook.database.repository import parse_record_ids


# --- helpers --------------------------------------------------------------
class _Msg:
    def __init__(self, id, type, content):
        self.id = id
        self.type = type
        self.content = content


def _state(messages):
    return SimpleNamespace(values={"messages": messages})


def _session(user_id="user:dev", sid="chat_session:s1"):
    return SimpleNamespace(id=sid, user_id=user_id, title="S", created="c", updated="u")


def _user(current_id="user:dev", username="dev", role="admin"):
    return fs.TokenUser(id=current_id, username=username, role=role)


@pytest_asyncio.fixture
async def embedded():
    """A real embedded SurrealDB with migration-30 schema + a seeded user and a
    notebook `refers_to` relation for chat_session:s1. Yields a bound
    `repo_query` patched into the service."""
    from pathlib import Path

    from surrealdb import AsyncSurreal

    conn = AsyncSurreal("mem://")
    await conn.use("test", "test")
    await conn.query(
        "DEFINE TABLE user SCHEMALESS; CREATE user:dev SET username='dev', name='Dev';"
    )
    await conn.query("DEFINE TABLE chat_session SCHEMALESS; CREATE chat_session:s1 SET title='S';")
    await conn.query("DEFINE TABLE notebook SCHEMALESS; CREATE notebook:n1 SET name='NB';")
    await conn.query("RELATE chat_session:s1->refers_to->notebook:n1;")
    schema = (
        Path(__file__).parent.parent
        / "open_notebook/database/migrations/30.surrealql"
    ).read_text()
    await conn.query(schema)

    async def fake_repo_query(q, vars=None):
        res = parse_record_ids(await conn.query(q, vars or {}))
        if isinstance(res, str):
            raise RuntimeError(res)
        return res

    with patch.object(fs, "repo_query", fake_repo_query):
        yield fake_repo_query


def _patch_common(messages):
    """Patch session lookup + both graphs so the service resolves an AI message
    with id 'ai-uuid-1' and preceding human question."""
    return patch.multiple(
        fs,
        get_session_or_404=AsyncMock(return_value=("chat_session:s1", _session())),
        chat_graph=MagicMock(get_state=MagicMock(return_value=_state(messages))),
        source_chat_graph=MagicMock(get_state=MagicMock(return_value=_state(messages))),
        Notebook=MagicMock(get=AsyncMock(return_value=SimpleNamespace(name="NB"))),
        Source=MagicMock(get=AsyncMock(return_value=SimpleNamespace(title="SRC"))),
        User=MagicMock(get=AsyncMock(return_value=SimpleNamespace(name="Dev"))),
    )


AI_ID = "11111111-1111-1111-1111-111111111111"
MESSAGES = [
    _Msg("h1", "human", "What is X?"),
    _Msg(AI_ID, "ai", "X is Y."),
]


# --- reaction lifecycle (real SQL) ----------------------------------------
@pytest.mark.asyncio
async def test_like_create_then_idempotent_then_remove(embedded):
    with _patch_common(MESSAGES):
        r = await fs.set_reaction("chat_session:s1", AI_ID, "like", _user())
        assert r == {"message_id": AI_ID, "reaction": "like", "reported": False}
        # idempotent: second identical call keeps a single row
        await fs.set_reaction("chat_session:s1", AI_ID, "like", _user())
        rows = await embedded("SELECT count() FROM ai_feedback GROUP ALL")
        assert rows[0]["count"] == 1
        # snapshots are server-side (from graph state), never from the client
        row = (await embedded("SELECT * FROM ai_feedback"))[0]
        assert row["question_snapshot"] == "What is X?"
        assert row["answer_snapshot"] == "X is Y."
        assert row["username_snapshot"] == "dev"
        assert row["context_type"] == "notebook"
        # remove reaction with no report -> row deleted entirely
        r = await fs.set_reaction("chat_session:s1", AI_ID, None, _user())
        assert r["reaction"] is None and r["reported"] is False
        rows = await embedded("SELECT count() FROM ai_feedback GROUP ALL")
        assert (rows[0]["count"] if rows else 0) == 0


@pytest.mark.asyncio
async def test_like_to_dislike_and_back(embedded):
    with _patch_common(MESSAGES):
        await fs.set_reaction("chat_session:s1", AI_ID, "like", _user())
        await fs.set_reaction("chat_session:s1", AI_ID, "dislike", _user())
        row = (await embedded("SELECT * FROM ai_feedback"))[0]
        assert row["reaction"] == "dislike"
        await fs.set_reaction("chat_session:s1", AI_ID, "like", _user())
        rows = await embedded("SELECT reaction FROM ai_feedback")
        assert len(rows) == 1 and rows[0]["reaction"] == "like"


@pytest.mark.asyncio
async def test_invalid_reaction_rejected(embedded):
    with _patch_common(MESSAGES):
        with pytest.raises(Exception) as exc:
            await fs.set_reaction("chat_session:s1", AI_ID, "love", _user())
        assert getattr(exc.value, "status_code", None) == 422


# --- report lifecycle -----------------------------------------------------
@pytest.mark.asyncio
async def test_report_requires_reason(embedded):
    with _patch_common(MESSAGES):
        for bad in ("", "   ", None):
            with pytest.raises(Exception) as exc:
                await fs.set_report("chat_session:s1", AI_ID, bad, _user())
            assert getattr(exc.value, "status_code", None) == 422


@pytest.mark.asyncio
async def test_report_too_long_rejected(embedded):
    with _patch_common(MESSAGES):
        with pytest.raises(Exception) as exc:
            await fs.set_report("chat_session:s1", AI_ID, "x" * 2001, _user())
        assert getattr(exc.value, "status_code", None) == 422


@pytest.mark.asyncio
async def test_report_persisted_and_idempotent(embedded):
    with _patch_common(MESSAGES):
        await fs.set_report("chat_session:s1", AI_ID, "  offensive  ", _user())
        await fs.set_report("chat_session:s1", AI_ID, "offensive again", _user())
        rows = await embedded("SELECT * FROM ai_feedback")
        assert len(rows) == 1
        assert rows[0]["reported"] is True
        assert rows[0]["report_reason"] == "offensive again"  # trimmed, updated in place


@pytest.mark.asyncio
async def test_report_and_dislike_coexist_and_clear_keeps_reported(embedded):
    with _patch_common(MESSAGES):
        await fs.set_reaction("chat_session:s1", AI_ID, "dislike", _user())
        await fs.set_report("chat_session:s1", AI_ID, "bad", _user())
        row = (await embedded("SELECT * FROM ai_feedback"))[0]
        assert row["reaction"] == "dislike" and row["reported"] is True
        # clearing the reaction while reported must KEEP the row
        r = await fs.set_reaction("chat_session:s1", AI_ID, None, _user())
        assert r["reported"] is True and r["reaction"] is None
        rows = await embedded("SELECT * FROM ai_feedback")
        assert len(rows) == 1 and rows[0]["reported"] is True


# --- message identity / validation ---------------------------------------
@pytest.mark.asyncio
async def test_temporary_id_rejected(embedded):
    with _patch_common(MESSAGES):
        for temp in ("temp-123", "ai-456"):
            with pytest.raises(Exception) as exc:
                await fs.set_reaction("chat_session:s1", temp, "like", _user())
            assert getattr(exc.value, "status_code", None) == 400


@pytest.mark.asyncio
async def test_nonexistent_message_rejected(embedded):
    with _patch_common(MESSAGES):
        with pytest.raises(Exception) as exc:
            await fs.set_reaction("chat_session:s1", "does-not-exist", "like", _user())
        assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_human_message_rejected(embedded):
    with _patch_common(MESSAGES):
        with pytest.raises(Exception) as exc:
            await fs.set_reaction("chat_session:s1", "h1", "like", _user())
        assert getattr(exc.value, "status_code", None) == 400


@pytest.mark.asyncio
async def test_ai_without_preceding_human_rejected(embedded):
    only_ai = [_Msg(AI_ID, "ai", "orphan answer")]
    with _patch_common(only_ai):
        with pytest.raises(Exception) as exc:
            await fs.set_reaction("chat_session:s1", AI_ID, "like", _user())
        assert getattr(exc.value, "status_code", None) == 400


@pytest.mark.asyncio
async def test_qa_snapshot_not_taken_from_client(embedded):
    """The question/answer stored come from graph state, not any client input."""
    with _patch_common(MESSAGES):
        await fs.set_reaction("chat_session:s1", AI_ID, "like", _user())
        row = (await embedded("SELECT * FROM ai_feedback"))[0]
        assert row["question_snapshot"] == "What is X?"  # from _Msg, not request
        assert row["answer_snapshot"] == "X is Y."


# --- ownership / privacy --------------------------------------------------
@pytest.mark.asyncio
async def test_cross_user_rejected(embedded):
    other = _session(user_id="user:alice")
    with patch.object(fs, "auth_disabled", lambda: False), patch.multiple(
        fs,
        get_session_or_404=AsyncMock(return_value=("chat_session:s1", other)),
        chat_graph=MagicMock(get_state=MagicMock(return_value=_state(MESSAGES))),
        source_chat_graph=MagicMock(get_state=MagicMock(return_value=_state(MESSAGES))),
        Notebook=MagicMock(get=AsyncMock(return_value=SimpleNamespace(name="NB"))),
        Source=MagicMock(get=AsyncMock(return_value=SimpleNamespace(title="S"))),
        User=MagicMock(get=AsyncMock(return_value=SimpleNamespace(name="Bob"))),
    ):
        with pytest.raises(Exception) as exc:
            await fs.set_reaction("chat_session:s1", AI_ID, "like", _user(current_id="user:bob"))
        assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_session_batch_only_owner_rows(embedded):
    with _patch_common(MESSAGES):
        await fs.set_reaction("chat_session:s1", AI_ID, "like", _user())
    # a row owned by someone else in the same session must not leak
    await embedded(
        "UPSERT type::thing('ai_feedback', ['user:alice','chat_session:s1','m-alice']) "
        "SET user_id=user:alice, username_snapshot='alice', session_id='chat_session:s1', "
        "message_id='m-alice', context_type='notebook', question_snapshot='q', "
        "answer_snapshot='a', reaction='like'"
    )
    with patch.object(fs, "auth_disabled", lambda: False), patch.object(
        fs, "get_session_or_404", AsyncMock(return_value=("chat_session:s1", _session()))
    ):
        rows = await fs.get_session_feedback("chat_session:s1", _user(current_id="user:dev"))
    ids = {r["message_id"] for r in rows}
    assert ids == {AI_ID}  # alice's row excluded


# --- admin stats / list ---------------------------------------------------
@pytest.mark.asyncio
async def test_admin_stats_overlap(embedded):
    with _patch_common(MESSAGES):
        await fs.set_reaction("chat_session:s1", AI_ID, "dislike", _user())
        await fs.set_report("chat_session:s1", AI_ID, "bad", _user())
    stats = await fs.admin_stats()
    # one row that is both dislike and report
    assert stats == {"total": 1, "likes": 0, "dislikes": 1, "reports": 1}


@pytest.mark.asyncio
async def test_admin_pagination_and_filter(embedded):
    # seed 5 likes directly
    for i in range(5):
        await embedded(
            "UPSERT type::thing('ai_feedback', ['user:dev','chat_session:s1',$m]) "
            "SET user_id=user:dev, username_snapshot='dev', session_id='chat_session:s1', "
            "message_id=$m, context_type='notebook', question_snapshot='q', "
            "answer_snapshot='a', reaction='like'",
            {"m": f"m{i}"},
        )
    page1 = await fs.admin_list(page=1, page_size=2)
    assert page1["total"] == 5 and page1["total_pages"] == 3 and len(page1["items"]) == 2
    page3 = await fs.admin_list(page=3, page_size=2)
    assert len(page3["items"]) == 1
    only_likes = await fs.admin_list(type_filter="like")
    assert only_likes["total"] == 5
    none_reports = await fs.admin_list(type_filter="report")
    assert none_reports["total"] == 0


@pytest.mark.asyncio
async def test_admin_search_and_sort_allowlist(embedded):
    await embedded(
        "UPSERT type::thing('ai_feedback', ['user:dev','chat_session:s1','m1']) "
        "SET user_id=user:dev, username_snapshot='Alice', session_id='chat_session:s1', "
        "message_id='m1', context_type='notebook', question_snapshot='Weather today', "
        "answer_snapshot='Sunny', reaction='like'"
    )
    await embedded(
        "UPSERT type::thing('ai_feedback', ['user:dev','chat_session:s1','m2']) "
        "SET user_id=user:dev, username_snapshot='Bob', session_id='chat_session:s1', "
        "message_id='m2', context_type='source', question_snapshot='Stocks', "
        "answer_snapshot='Up', reported=true, report_reason='spam content'"
    )
    found = await fs.admin_list(q="spam")
    assert found["total"] == 1 and found["items"][0]["username_snapshot"] == "Bob"
    # unknown sort column falls back to 'created' (allowlist), does not error/inject
    safe = await fs.admin_list(sort="password_hash; DROP", direction="asc")
    assert safe["total"] == 2


@pytest.mark.asyncio
async def test_snapshot_survives_session_and_user_deletion(embedded):
    with _patch_common(MESSAGES):
        await fs.set_report("chat_session:s1", AI_ID, "bad", _user())
    # delete the underlying chat session and user records
    await embedded("DELETE chat_session:s1")
    await embedded("DELETE user:dev")
    # feedback snapshot remains fully readable for admin statistics
    listing = await fs.admin_list()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["username_snapshot"] == "dev"  # survives user deletion
    assert item["question_snapshot"] == "What is X?"
    assert item["answer_snapshot"] == "X is Y."
    assert item["reported"] is True


# --- HTTP layer: routing, validation, admin guard -------------------------
@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def test_reaction_http_validation_rejects_bad_enum(client):
    # Pydantic Literal rejects an invalid reaction at the API boundary (422)
    resp = client.put(
        f"/api/feedback/messages/{AI_ID}/reaction",
        json={"session_id": "chat_session:s1", "reaction": "love"},
    )
    assert resp.status_code == 422


def test_report_http_requires_reason_field(client):
    resp = client.post(
        f"/api/feedback/messages/{AI_ID}/report",
        json={"session_id": "chat_session:s1"},
    )
    assert resp.status_code == 422


def test_admin_endpoints_require_admin(client, monkeypatch):
    """With auth enforced, a non-admin token is rejected by require_admin."""

    from api.auth import create_access_token

    monkeypatch.setenv("OPEN_NOTEBOOK_DISABLE_AUTH", "false")
    token = create_access_token("user:bob", "bob", "user")
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/feedback/admin/stats", headers=headers).status_code == 403
    assert client.get("/api/feedback/admin", headers=headers).status_code == 403
