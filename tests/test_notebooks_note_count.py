"""Tests for per-user Notebook Card note counts.

Notes are per-user data (each user only sees their own notes), so the note
count returned for a notebook must be scoped to the current user. Source
counts stay global because sources are shared data added by admins. These
tests assert the SurrealQL the notebooks router builds for the count:

- auth enforced   -> count(<-artifact<-note[WHERE user_id = $user]) + "user" param
- single-user mode -> count(<-artifact.in), no "user" param

The source count expression (count(<-reference.in)) is unchanged in both.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def _nb_row(source_count: int, note_count: int) -> dict:
    return {
        "id": "notebook:nb1",
        "name": "NB1",
        "description": "",
        "archived": False,
        "created": "2026-01-01T00:00:00",
        "updated": "2026-01-02T00:00:00",
        "source_count": source_count,
        "note_count": note_count,
    }


class TestNotebookNoteCountScoping:
    @patch("api.routers.notebooks.repo_query", new_callable=AsyncMock)
    @patch("api.routers.notebooks.auth_disabled", return_value=False)
    def test_list_note_count_scoped_to_current_user(
        self, _mock_auth_disabled, mock_repo_query, client
    ):
        """With auth enforced, GET /notebooks counts only the caller's notes."""
        mock_repo_query.return_value = [_nb_row(source_count=2, note_count=2)]

        resp = client.get("/api/notebooks")

        assert resp.status_code == 200
        assert resp.json()[0]["note_count"] == 2
        assert resp.json()[0]["source_count"] == 2

        sql, params = mock_repo_query.await_args.args
        # Note count walks the artifact edge to the note node and filters on
        # the note's owner.
        assert "count(<-artifact<-note[WHERE user_id = $user]) as note_count" in sql
        assert "user" in params
        # Source count stays global (shared data).
        assert "count(<-reference.in) as source_count" in sql

    @patch("api.routers.notebooks.repo_query", new_callable=AsyncMock)
    @patch("api.routers.notebooks.auth_disabled", return_value=True)
    def test_list_note_count_global_in_single_user_mode(
        self, _mock_auth_disabled, mock_repo_query, client
    ):
        """With auth disabled there is no owner to scope by: count all notes."""
        mock_repo_query.return_value = [_nb_row(source_count=2, note_count=4)]

        resp = client.get("/api/notebooks")

        assert resp.status_code == 200
        assert resp.json()[0]["note_count"] == 4

        sql, params = mock_repo_query.await_args.args
        assert "count(<-artifact.in) as note_count" in sql
        assert "user" not in params

    @patch("api.routers.notebooks.stamp_view", new_callable=AsyncMock)
    @patch("api.routers.notebooks.repo_query", new_callable=AsyncMock)
    @patch("api.routers.notebooks.auth_disabled", return_value=False)
    def test_get_by_id_note_count_scoped_to_current_user(
        self, _mock_auth_disabled, mock_repo_query, _mock_stamp, client
    ):
        """GET /notebooks/{id} applies the same per-user note-count scoping."""
        mock_repo_query.return_value = [_nb_row(source_count=2, note_count=2)]

        resp = client.get("/api/notebooks/notebook:nb1")

        assert resp.status_code == 200
        assert resp.json()["note_count"] == 2

        sql, params = mock_repo_query.await_args.args
        assert "count(<-artifact<-note[WHERE user_id = $user]) as note_count" in sql
        assert "user" in params
        assert "notebook_id" in params
