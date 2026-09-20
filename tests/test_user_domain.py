"""Tests for the User domain model, authentication, and admin seeding."""

from unittest.mock import AsyncMock, patch

import pytest

from open_notebook.domain.user import User, seed_default_admin
from open_notebook.exceptions import InvalidInputError
from open_notebook.utils.passwords import hash_password


def _user_row(username="alice", role="user", password="pw"):
    return {
        "id": f"user:{username}",
        "username": username,
        "password_hash": hash_password(password),
        "role": role,
        "name": None,
    }


class TestGetByUsername:
    @pytest.mark.asyncio
    async def test_found(self):
        with patch(
            "open_notebook.domain.user.repo_query",
            new=AsyncMock(return_value=[_user_row("alice")]),
        ):
            user = await User.get_by_username("alice")
        assert user is not None
        assert user.username == "alice"
        assert user.role == "user"

    @pytest.mark.asyncio
    async def test_not_found(self):
        with patch(
            "open_notebook.domain.user.repo_query", new=AsyncMock(return_value=[])
        ):
            assert await User.get_by_username("ghost") is None

    @pytest.mark.asyncio
    async def test_empty_username_short_circuits(self):
        mock = AsyncMock(return_value=[])
        with patch("open_notebook.domain.user.repo_query", new=mock):
            assert await User.get_by_username("") is None
        mock.assert_not_called()


class TestAuthenticate:
    @pytest.mark.asyncio
    async def test_valid_credentials(self):
        user = User(username="alice", password_hash=hash_password("correct"), role="user")
        with patch.object(User, "get_by_username", new=AsyncMock(return_value=user)):
            result = await User.authenticate("alice", "correct")
        assert result is user

    @pytest.mark.asyncio
    async def test_wrong_password(self):
        user = User(username="alice", password_hash=hash_password("correct"), role="user")
        with patch.object(User, "get_by_username", new=AsyncMock(return_value=user)):
            assert await User.authenticate("alice", "wrong") is None

    @pytest.mark.asyncio
    async def test_unknown_user(self):
        with patch.object(User, "get_by_username", new=AsyncMock(return_value=None)):
            assert await User.authenticate("ghost", "x") is None


class TestCreate:
    @pytest.mark.asyncio
    async def test_creates_with_hashed_password(self):
        with patch.object(User, "get_by_username", new=AsyncMock(return_value=None)):
            with patch.object(User, "save", new=AsyncMock()) as save:
                user = await User.create("bob", "s3cret", role="admin", name="Bob")
        assert user.username == "bob"
        assert user.role == "admin"
        assert user.password_hash != "s3cret"
        assert user.check_password("s3cret") is True
        save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_username_rejected(self):
        existing = User(username="bob", password_hash="x", role="user")
        with patch.object(User, "get_by_username", new=AsyncMock(return_value=existing)):
            with pytest.raises(InvalidInputError):
                await User.create("bob", "pw")

    @pytest.mark.asyncio
    async def test_empty_username_rejected(self):
        with pytest.raises(InvalidInputError):
            await User.create("  ", "pw")

    @pytest.mark.asyncio
    async def test_empty_password_rejected(self):
        with patch.object(User, "get_by_username", new=AsyncMock(return_value=None)):
            with pytest.raises(InvalidInputError):
                await User.create("bob", "")


class TestSeedDefaultAdmin:
    @pytest.mark.asyncio
    async def test_seeds_when_empty(self):
        with patch.object(User, "count", new=AsyncMock(return_value=0)):
            with patch.object(User, "create", new=AsyncMock()) as create:
                await seed_default_admin()
        create.assert_awaited_once()
        kwargs = create.await_args.kwargs
        assert kwargs["username"] == "admin"
        assert kwargs["password"] == "admin"
        assert kwargs["role"] == "admin"

    @pytest.mark.asyncio
    async def test_noop_when_users_exist(self):
        with patch.object(User, "count", new=AsyncMock(return_value=3)):
            with patch.object(User, "create", new=AsyncMock()) as create:
                await seed_default_admin()
        create.assert_not_called()
