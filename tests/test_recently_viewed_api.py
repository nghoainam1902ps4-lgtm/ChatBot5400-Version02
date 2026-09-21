"""Tests for per-user recently viewed notebooks and sources.

View history is stored per (user, item) in the `recently_viewed` table, so one
user never sees another's history. The read endpoint filters by the current
user; the notebook/source GET endpoints stamp a view for the current user via
``api.recently_viewed.stamp_view`` (which uses its own module-level
``repo_query`` reference — patched separately from the routers').
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from open_notebook.domain.notebook import Source


@pytest.fixture
def client():
    """Create test client after environment variables have been cleared by conftest."""
    from api.main import app

    return TestClient(app)


class TestRecentlyViewedApi:
    @patch("api.routers.notebooks.repo_query", new_callable=AsyncMock)
    def test_recently_viewed_returns_current_user_items_newest_first(
        self, mock_repo_query, client
    ):
        # Rows come back already ordered by the DB (last_viewed_at DESC), with
        # the linked item FETCH-ed inline.
        mock_repo_query.return_value = [
            {
                "item": {"id": "source:new", "title": "Newer Source"},
                "item_type": "source",
                "last_viewed_at": "2026-06-27T10:00:00Z",
            },
            {
                "item": {"id": "notebook:old", "name": "Older Notebook"},
                "item_type": "notebook",
                "last_viewed_at": "2026-06-26T10:00:00Z",
            },
        ]

        response = client.get("/api/recently-viewed")

        assert response.status_code == 200
        assert response.json() == [
            {
                "type": "source",
                "id": "source:new",
                "title": "Newer Source",
                "last_viewed_at": "2026-06-27T10:00:00Z",
            },
            {
                "type": "notebook",
                "id": "notebook:old",
                "title": "Older Notebook",
                "last_viewed_at": "2026-06-26T10:00:00Z",
            },
        ]
        # A single query, scoped to the current user.
        assert mock_repo_query.await_count == 1
        sql, params = mock_repo_query.await_args.args
        assert "recently_viewed" in sql
        assert "WHERE user = $user" in sql
        assert "user" in params

    @patch("api.routers.notebooks.repo_query", new_callable=AsyncMock)
    def test_recently_viewed_honors_limit(self, mock_repo_query, client):
        mock_repo_query.return_value = []

        response = client.get("/api/recently-viewed?limit=2")

        assert response.status_code == 200
        assert mock_repo_query.await_args.args[1]["limit"] == 2

    @patch("api.routers.notebooks.repo_query", new_callable=AsyncMock)
    def test_recently_viewed_empty_when_no_view_history(self, mock_repo_query, client):
        mock_repo_query.return_value = []

        response = client.get("/api/recently-viewed")

        assert response.status_code == 200
        assert response.json() == []

    @patch("api.routers.notebooks.repo_query", new_callable=AsyncMock)
    def test_recently_viewed_skips_deleted_items(self, mock_repo_query, client):
        # A dangling link (target notebook/source deleted) FETCHes to None and
        # must be dropped rather than surfaced as a broken row.
        mock_repo_query.return_value = [
            {
                "item": None,
                "item_type": "notebook",
                "last_viewed_at": "2026-06-27T11:00:00Z",
            },
            {
                "item": {"id": "source:1", "title": "Source"},
                "item_type": "source",
                "last_viewed_at": "2026-06-27T10:00:00Z",
            },
        ]

        response = client.get("/api/recently-viewed")

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == ["source:1"]

    @patch("api.recently_viewed.repo_query", new_callable=AsyncMock)
    @patch("api.routers.notebooks.repo_query", new_callable=AsyncMock)
    def test_get_notebook_stamps_view_for_current_user(
        self, mock_nb_query, mock_stamp_query, client
    ):
        mock_nb_query.return_value = [
            {
                "id": "notebook:1",
                "name": "Notebook",
                "description": "",
                "archived": False,
                "created": "2026-06-27T09:00:00Z",
                "updated": "2026-06-27T09:00:00Z",
                "source_count": 0,
                "note_count": 0,
            }
        ]

        response = client.get("/api/notebooks/notebook:1")

        assert response.status_code == 200
        # View recorded once in the per-user recently_viewed table.
        assert mock_stamp_query.await_count == 1
        stamp_sql = mock_stamp_query.await_args.args[0]
        assert "recently_viewed" in stamp_sql
        assert "type::thing('recently_viewed'" in stamp_sql
        stamp_params = mock_stamp_query.await_args.args[1]
        assert stamp_params["item_type"] == "notebook"

    @patch("api.recently_viewed.repo_query", new_callable=AsyncMock)
    @patch("api.routers.sources.Source.get_embedded_chunks", new_callable=AsyncMock)
    @patch("api.routers.sources.Source.get", new_callable=AsyncMock)
    @patch("api.routers.sources.repo_query", new_callable=AsyncMock)
    def test_get_source_stamps_view_for_current_user(
        self, mock_src_query, mock_get_source, mock_chunks, mock_stamp_query, client
    ):
        mock_get_source.return_value = Source(
            id="source:1",
            title="Source",
            topics=[],
            full_text="Source text",
            created="2026-06-27T09:00:00Z",
            updated="2026-06-27T09:00:00Z",
        )
        mock_chunks.return_value = 0
        mock_src_query.return_value = []

        response = client.get("/api/sources/source:1")

        assert response.status_code == 200
        assert mock_stamp_query.await_count == 1
        stamp_sql = mock_stamp_query.await_args.args[0]
        assert "recently_viewed" in stamp_sql
        assert mock_stamp_query.await_args.args[1]["item_type"] == "source"
