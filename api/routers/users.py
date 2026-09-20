"""User management router for ChatBot5400 (admin only).

Every endpoint here requires an admin caller (require_admin dependency). Regular
users manage only their own password via /api/auth/change-password.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel, Field

from api.auth import TokenUser, require_admin
from open_notebook.domain.user import User
from open_notebook.exceptions import InvalidInputError

# require_admin is attached to the whole router: it runs before every handler.
router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    name: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    role: str = Field("user", pattern="^(admin|user)$")
    name: Optional[str] = None


class UserUpdateRequest(BaseModel):
    username: Optional[str] = Field(None, min_length=1)
    role: Optional[str] = Field(None, pattern="^(admin|user)$")
    name: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=1)


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id or "",
        username=user.username,
        role=user.role,
        name=user.name,
        created=str(user.created) if user.created else None,
        updated=str(user.updated) if user.updated else None,
    )


async def _count_admins() -> int:
    return len([u for u in await User.get_all() if u.role == "admin"])


@router.get("", response_model=List[UserResponse])
async def list_users():
    """List all user accounts."""
    users = await User.get_all(order_by="username asc")
    return [_to_response(u) for u in users]


@router.post("", response_model=UserResponse)
async def create_user(request: UserCreateRequest):
    """Create a new user account."""
    user = await User.create(
        username=request.username,
        password=request.password,
        role=request.role,  # type: ignore[arg-type]
        name=request.name,
    )
    logger.info(f"Admin created user '{user.username}' (role={user.role})")
    return _to_response(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    """Get a single user by id."""
    user = await User.get(user_id)
    return _to_response(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, request: UserUpdateRequest):
    """Update a user's username, role, or display name."""
    user = await User.get(user_id)

    # Guard: never demote the last remaining admin (would lock everyone out).
    if (
        request.role is not None
        and user.role == "admin"
        and request.role != "admin"
        and await _count_admins() <= 1
    ):
        raise InvalidInputError("Cannot demote the last remaining admin")

    if request.username is not None and request.username.strip() != user.username:
        existing = await User.get_by_username(request.username)
        if existing is not None and existing.id != user.id:
            raise InvalidInputError(
                f"Username '{request.username}' already exists"
            )
        user.username = request.username.strip()
    if request.role is not None:
        user.role = request.role  # type: ignore[assignment]
    if request.name is not None:
        user.name = request.name

    await user.save()
    logger.info(f"Admin updated user '{user.username}'")
    return _to_response(user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: str, admin: TokenUser = Depends(require_admin)
):
    """Delete a user account."""
    user = await User.get(user_id)

    if user.id == admin.id:
        raise InvalidInputError("You cannot delete your own account")
    if user.role == "admin" and await _count_admins() <= 1:
        raise InvalidInputError("Cannot delete the last remaining admin")

    await user.delete()
    logger.info(f"Admin deleted user '{user.username}'")
    return {"success": True, "message": "User deleted successfully"}


@router.post("/{user_id}/reset-password")
async def reset_password(user_id: str, request: ResetPasswordRequest):
    """Admin resets another user's password."""
    user = await User.get(user_id)
    if not request.new_password:
        raise InvalidInputError("New password cannot be empty")
    await user.set_password(request.new_password)
    logger.info(f"Admin reset password for user '{user.username}'")
    return {"success": True, "message": "Password reset successfully"}
