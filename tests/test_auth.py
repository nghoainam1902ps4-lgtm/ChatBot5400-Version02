"""Tests for JWT authentication, the auth middleware, and RBAC dependencies."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Request
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from api.auth import (
    JWTAuthMiddleware,
    TokenUser,
    auth_disabled,
    create_access_token,
    decode_token,
    get_current_user,
    require_admin,
    _jwt_secret,
)
from open_notebook.exceptions import AuthenticationError, AuthorizationError

# A fixed secret keeps token signing/verification deterministic across the
# process regardless of the ambient encryption key.
FIXED_SECRET = "test-secret-key"


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch):
    """Enforce auth (off the suite-wide disable) with a fixed JWT secret."""
    monkeypatch.setenv("OPEN_NOTEBOOK_JWT_SECRET", FIXED_SECRET)
    monkeypatch.delenv("OPEN_NOTEBOOK_DISABLE_AUTH", raising=False)


async def _unused_app(_: Scope, __: Receive, ___: Send) -> None:
    raise AssertionError("dispatch should use the supplied call_next")


def _make_request(path: str, token: str | None = None, method: str = "GET") -> Request:
    headers = []
    if token is not None:
        headers.append((b"authorization", b"Bearer " + token.encode()))
    scope: Scope = {"type": "http", "method": method, "path": path, "headers": headers}
    return Request(scope)


async def _dispatch(request: Request) -> Response:
    captured: dict = {}

    async def call_next(req: Request) -> Response:
        captured["user"] = getattr(req.state, "user", None)
        return Response(status_code=200)

    middleware = JWTAuthMiddleware(_unused_app)
    response = await middleware.dispatch(request, call_next)
    response._captured_user = captured.get("user")  # type: ignore[attr-defined]
    return response


class TestTokenRoundTrip:
    def test_encode_decode_preserves_identity(self):
        token = create_access_token("user:abc", "alice", "admin")
        user = decode_token(token)
        assert isinstance(user, TokenUser)
        assert user.id == "user:abc"
        assert user.username == "alice"
        assert user.role == "admin"
        assert user.is_admin is True

    def test_regular_user_not_admin(self):
        user = decode_token(create_access_token("user:x", "bob", "user"))
        assert user.is_admin is False

    def test_garbage_token_rejected(self):
        with pytest.raises(AuthenticationError):
            decode_token("not.a.jwt")

    def test_wrong_signature_rejected(self):
        forged = jwt.encode(
            {"sub": "user:x", "username": "bob", "role": "admin"},
            "some-other-secret",
            algorithm="HS256",
        )
        with pytest.raises(AuthenticationError):
            decode_token(forged)

    def test_expired_token_rejected(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        expired = jwt.encode(
            {"sub": "user:x", "username": "bob", "role": "user", "exp": past},
            _jwt_secret(),
            algorithm="HS256",
        )
        with pytest.raises(AuthenticationError):
            decode_token(expired)

    def test_missing_claims_rejected(self):
        bad = jwt.encode({"role": "user"}, _jwt_secret(), algorithm="HS256")
        with pytest.raises(AuthenticationError):
            decode_token(bad)


class TestJWTAuthMiddleware:
    @pytest.mark.asyncio
    async def test_excluded_path_allows_without_token(self):
        resp = await _dispatch(_make_request("/api/auth/login", method="POST"))
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_missing_token_rejected(self):
        resp = await _dispatch(_make_request("/api/notebooks"))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self):
        resp = await _dispatch(_make_request("/api/notebooks", token="garbage"))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_allows_and_sets_user(self):
        token = create_access_token("user:abc", "alice", "admin")
        resp = await _dispatch(_make_request("/api/notebooks", token=token))
        assert resp.status_code == 200
        user = resp._captured_user  # type: ignore[attr-defined]
        assert isinstance(user, TokenUser)
        assert user.username == "alice"

    @pytest.mark.asyncio
    async def test_options_preflight_skipped(self):
        resp = await _dispatch(_make_request("/api/notebooks", method="OPTIONS"))
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_disabled_auth_injects_dev_admin(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("OPEN_NOTEBOOK_DISABLE_AUTH", "true")
        resp = await _dispatch(_make_request("/api/notebooks"))
        assert resp.status_code == 200
        user = resp._captured_user  # type: ignore[attr-defined]
        assert user is not None and user.is_admin


class TestRbacDependencies:
    def test_get_current_user_from_state(self):
        req = _make_request("/api/notebooks")
        req.state.user = TokenUser(id="user:1", username="bob", role="user")
        assert get_current_user(req).username == "bob"

    def test_get_current_user_no_auth_raises(self):
        with pytest.raises(AuthenticationError):
            get_current_user(_make_request("/api/notebooks"))

    def test_require_admin_allows_admin(self):
        req = _make_request("/api/users")
        req.state.user = TokenUser(id="user:1", username="root", role="admin")
        assert require_admin(req).is_admin

    def test_require_admin_blocks_regular_user(self):
        req = _make_request("/api/users")
        req.state.user = TokenUser(id="user:1", username="bob", role="user")
        with pytest.raises(AuthorizationError):
            require_admin(req)


class TestAuthDisabledFlag:
    def test_default_enforced(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPEN_NOTEBOOK_DISABLE_AUTH", raising=False)
        assert auth_disabled() is False

    @pytest.mark.parametrize("value", ["true", "1", "yes", "on", "TRUE"])
    def test_truthy_values_disable(self, monkeypatch: pytest.MonkeyPatch, value: str):
        monkeypatch.setenv("OPEN_NOTEBOOK_DISABLE_AUTH", value)
        assert auth_disabled() is True

    @pytest.mark.parametrize("value", ["false", "0", "no", ""])
    def test_falsy_values_keep_enforced(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ):
        monkeypatch.setenv("OPEN_NOTEBOOK_DISABLE_AUTH", value)
        assert auth_disabled() is False
