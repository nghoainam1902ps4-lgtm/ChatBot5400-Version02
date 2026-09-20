"""Authentication & authorization for ChatBot5400.

JWT-based auth layered on the User table (see open_notebook/domain/user.py).

- ``JWTAuthMiddleware`` enforces a valid Bearer token on every ``/api`` request
  except a small allowlist (login, auth status, config, health/docs). It stores
  the decoded identity on ``request.state`` — this is the app-wide ``requireAuth``.
- ``get_current_user`` is a FastAPI dependency that returns the caller's identity
  (from ``request.state``) — use it in handlers that need the user id/role.
- ``require_admin`` is a dependency that additionally enforces ``role == 'admin'``
  — attach it to admin-only endpoints (Notebook/Source management, user CRUD).

Tokens are stateless; ``logout`` is a client-side token discard (the endpoint
exists for symmetry and future revocation support).
"""

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from open_notebook.exceptions import AuthenticationError, AuthorizationError
from open_notebook.utils.encryption import get_secret_from_env

JWT_ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = 720  # 12 hours


def _jwt_secret() -> str:
    """Resolve the signing secret.

    Prefers OPEN_NOTEBOOK_JWT_SECRET; otherwise derives a stable secret from the
    required OPEN_NOTEBOOK_ENCRYPTION_KEY so no extra configuration is needed.
    """
    explicit = get_secret_from_env("OPEN_NOTEBOOK_JWT_SECRET")
    if explicit:
        return explicit
    enc = get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEY")
    if enc:
        return hashlib.sha256(f"chatbot5400-jwt::{enc}".encode("utf-8")).hexdigest()
    # Last resort: warn loudly. Tokens won't survive a restart / multiple workers.
    logger.warning(
        "Neither OPEN_NOTEBOOK_JWT_SECRET nor OPEN_NOTEBOOK_ENCRYPTION_KEY is set; "
        "using an ephemeral JWT secret. Set one of these for stable sessions."
    )
    return "chatbot5400-insecure-dev-secret"


def _expire_minutes() -> int:
    raw = os.getenv("OPEN_NOTEBOOK_JWT_EXPIRE_MINUTES")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_EXPIRE_MINUTES


@dataclass
class TokenUser:
    """Caller identity decoded from a JWT."""

    id: str
    username: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def create_access_token(user_id: str, username: str, role: str) -> str:
    """Mint a signed JWT for a user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=_expire_minutes()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> TokenUser:
    """Decode/validate a JWT, returning the identity. Raises AuthenticationError."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise AuthenticationError("Token has expired") from e
    except jwt.InvalidTokenError as e:
        raise AuthenticationError("Invalid token") from e

    user_id = payload.get("sub")
    username = payload.get("username")
    role = payload.get("role", "user")
    if not user_id or not username:
        raise AuthenticationError("Malformed token payload")
    return TokenUser(id=str(user_id), username=str(username), role=str(role))


def _extract_bearer(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    try:
        scheme, credentials = auth_header.split(" ", 1)
    except ValueError:
        return None
    if scheme.lower() != "bearer":
        return None
    return credentials.strip()


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Require a valid JWT on every request except the excluded allowlist."""

    def __init__(
        self, app: ASGIApp, excluded_paths: Optional[list[str]] = None
    ) -> None:
        super().__init__(app)
        self.excluded_paths: list[str] = excluded_paths or [
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/api/auth/status",
            "/api/auth/login",
            "/api/config",
        ]

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if request.method == "OPTIONS" or path in self.excluded_paths:
            return await call_next(request)

        token = _extract_bearer(request)
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            user = decode_token(token)
        except AuthenticationError as e:
            return JSONResponse(
                status_code=401,
                content={"detail": str(e)},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Expose identity to downstream dependencies/handlers.
        request.state.user = user
        return await call_next(request)


# --- FastAPI dependencies -------------------------------------------------
def get_current_user(request: Request) -> TokenUser:
    """Dependency: return the authenticated caller (requireAuth).

    Relies on JWTAuthMiddleware having populated request.state.user. Falls back
    to decoding the header directly so it still works if used on an excluded
    path or in tests without the middleware.
    """
    user = getattr(request.state, "user", None)
    if isinstance(user, TokenUser):
        return user
    token = _extract_bearer(request)
    if not token:
        raise AuthenticationError("Not authenticated")
    return decode_token(token)


def require_admin(request: Request) -> TokenUser:
    """Dependency: require the caller to be an admin (requireAdmin)."""
    user = get_current_user(request)
    if not user.is_admin:
        raise AuthorizationError("Administrator privileges required")
    return user
