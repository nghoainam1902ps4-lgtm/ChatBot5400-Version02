"""Tests for the per-user preferences endpoint (PUT /api/auth/preferences)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from open_notebook.domain.user import User


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def _user():
    return User(
        id="user:dev",
        username="dev",
        password_hash="x",
        role="admin",
        name="Dev",
    )


class TestPreferences:
    def test_update_language_and_theme(self, client):
        user = _user()
        with patch.object(User, "get_by_username", new=AsyncMock(return_value=user)):
            with patch.object(User, "save", new=AsyncMock()):
                resp = client.put(
                    "/api/auth/preferences",
                    json={"language": "vi-VN", "theme": "dark"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] == "vi-VN"
        assert data["theme"] == "dark"

    def test_partial_update_theme_only(self, client):
        user = _user()
        user.language = "en-US"
        with patch.object(User, "get_by_username", new=AsyncMock(return_value=user)):
            with patch.object(User, "save", new=AsyncMock()):
                resp = client.put("/api/auth/preferences", json={"theme": "light"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["theme"] == "light"
        # language left untouched
        assert data["language"] == "en-US"

    def test_me_returns_preferences(self, client):
        user = _user()
        user.language = "vi-VN"
        user.theme = "system"
        with patch.object(User, "get_by_username", new=AsyncMock(return_value=user)):
            resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] == "vi-VN"
        assert data["theme"] == "system"
