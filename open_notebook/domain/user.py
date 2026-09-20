"""User domain model for authentication and RBAC (ChatBot5400)."""

from typing import ClassVar, Literal, Optional

from loguru import logger
from pydantic import field_validator

from open_notebook.database.repository import repo_query
from open_notebook.domain.base import ObjectModel
from open_notebook.exceptions import InvalidInputError
from open_notebook.utils.passwords import hash_password, verify_password

Role = Literal["admin", "user"]


class User(ObjectModel):
    """An application user account.

    `password_hash` stores a bcrypt hash — never the plaintext password. Use
    `create()` / `set_password()` so hashing is applied consistently, and
    `authenticate()` to check credentials.
    """

    table_name: ClassVar[str] = "user"

    username: str
    password_hash: str
    role: Role = "user"
    name: Optional[str] = None

    @field_validator("username")
    @classmethod
    def _username_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise InvalidInputError("Username cannot be empty")
        return v.strip()

    # --- Queries -----------------------------------------------------------
    @classmethod
    async def get_by_username(cls, username: str) -> Optional["User"]:
        """Return the user with this username, or None."""
        if not username or not username.strip():
            return None
        result = await repo_query(
            "SELECT * FROM user WHERE username = $username LIMIT 1",
            {"username": username.strip()},
        )
        if result:
            return cls(**result[0])
        return None

    @classmethod
    async def count(cls) -> int:
        """Total number of user accounts."""
        result = await repo_query("SELECT count() FROM user GROUP ALL")
        if result and isinstance(result[0], dict):
            return int(result[0].get("count", 0))
        return 0

    # --- Mutations ---------------------------------------------------------
    @classmethod
    async def create(
        cls,
        username: str,
        password: str,
        role: Role = "user",
        name: Optional[str] = None,
    ) -> "User":
        """Create a new user, hashing the plaintext password."""
        username = (username or "").strip()
        if not username:
            raise InvalidInputError("Username cannot be empty")
        if not password:
            raise InvalidInputError("Password cannot be empty")
        if await cls.get_by_username(username) is not None:
            raise InvalidInputError(f"Username '{username}' already exists")

        user = cls(
            username=username,
            password_hash=hash_password(password),
            role=role,
            name=name,
        )
        await user.save()
        return user

    async def set_password(self, password: str) -> None:
        """Hash and persist a new password for this user."""
        if not password:
            raise InvalidInputError("Password cannot be empty")
        self.password_hash = hash_password(password)
        await self.save()

    def check_password(self, password: str) -> bool:
        """Verify a plaintext password against this user's stored hash."""
        return verify_password(password, self.password_hash)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    # --- Auth --------------------------------------------------------------
    @classmethod
    async def authenticate(cls, username: str, password: str) -> Optional["User"]:
        """Return the user if the username/password pair is valid, else None."""
        user = await cls.get_by_username(username)
        if user is None:
            # Run a dummy hash comparison to keep timing roughly constant
            # whether or not the username exists.
            verify_password(password, "$2b$12$" + "x" * 53)
            return None
        if not user.check_password(password):
            return None
        return user


async def seed_default_admin() -> None:
    """Seed a default admin (admin/admin) when there are no users yet.

    Called on API startup after migrations. Idempotent: does nothing once any
    user exists.
    """
    try:
        if await User.count() > 0:
            return
        await User.create(
            username="admin",
            password="admin",
            role="admin",
            name="Administrator",
        )
        logger.warning(
            "Seeded default admin account (username='admin', password='admin'). "
            "Change this password immediately after first login."
        )
    except Exception as e:  # pragma: no cover - defensive: never block startup
        logger.error(f"Failed to seed default admin account: {e}")
