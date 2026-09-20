"""Authentication router for ChatBot5400.

Login / logout / change-password / current-user, plus a public auth-status
endpoint. Uses JWT (see api/auth.py) and the User domain model.
"""

from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel, Field

from api.auth import (
    TokenUser,
    auth_disabled,
    create_access_token,
    get_current_user,
)
from open_notebook.domain.user import User
from open_notebook.exceptions import AuthenticationError, InvalidInputError

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class UserInfo(BaseModel):
    id: str
    username: str
    role: str
    name: str | None = None
    language: str | None = None
    theme: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=1, description="New password")


class PreferencesRequest(BaseModel):
    language: str | None = Field(None, description="UI language code, e.g. vi-VN")
    theme: str | None = Field(None, description="UI theme: light | dark | system")


def _user_info(user: User) -> "UserInfo":
    return UserInfo(
        id=user.id or "",
        username=user.username,
        role=user.role,
        name=user.name,
        language=user.language,
        theme=user.theme,
    )


@router.get("/status")
async def get_auth_status():
    """Public: report whether authentication is enforced."""
    enabled = not auth_disabled()
    return {
        "auth_enabled": enabled,
        "auth_type": "jwt",
        "message": "Authentication is required"
        if enabled
        else "Authentication is disabled",
    }


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate a user and return a JWT access token."""
    user = await User.authenticate(request.username, request.password)
    if user is None or not user.id:
        raise AuthenticationError("Invalid username or password")

    token = create_access_token(user.id, user.username, user.role)
    logger.info(f"User '{user.username}' logged in")
    return LoginResponse(access_token=token, user=_user_info(user))


@router.post("/logout")
async def logout(current: TokenUser = Depends(get_current_user)):
    """Log out. Tokens are stateless, so the client discards the token."""
    logger.info(f"User '{current.username}' logged out")
    return {"success": True, "message": "Logged out successfully"}


@router.get("/me", response_model=UserInfo)
async def get_me(current: TokenUser = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    user = await User.get_by_username(current.username)
    if user is None or not user.id:
        raise AuthenticationError("User no longer exists")
    return _user_info(user)


@router.put("/preferences", response_model=UserInfo)
async def update_preferences(
    request: PreferencesRequest,
    current: TokenUser = Depends(get_current_user),
):
    """Persist the current user's UI preferences (language and/or theme)."""
    user = await User.get_by_username(current.username)
    if user is None:
        raise AuthenticationError("User no longer exists")
    if request.language is not None:
        user.language = request.language
    if request.theme is not None:
        user.theme = request.theme
    await user.save()
    return _user_info(user)


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current: TokenUser = Depends(get_current_user),
):
    """Change the current user's own password."""
    user = await User.get_by_username(current.username)
    if user is None:
        raise AuthenticationError("User no longer exists")
    if not user.check_password(request.current_password):
        raise AuthenticationError("Current password is incorrect")
    if not request.new_password:
        raise InvalidInputError("New password cannot be empty")

    await user.set_password(request.new_password)
    logger.info(f"User '{user.username}' changed their password")
    return {"success": True, "message": "Password changed successfully"}
