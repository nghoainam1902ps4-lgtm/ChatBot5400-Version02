"""Password hashing helpers for authentication (ChatBot5400).

Uses bcrypt directly. bcrypt has a hard 72-byte limit on the input, so the
password is truncated to 72 bytes before hashing/verifying (the standard,
documented behaviour) to avoid a ValueError on long inputs.
"""

import bcrypt

_BCRYPT_MAX_BYTES = 72


def _normalize(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Return a bcrypt hash (utf-8 string) for the given plaintext password."""
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string")
    return bcrypt.hashpw(_normalize(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time check of a plaintext password against a stored bcrypt hash."""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(_normalize(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
