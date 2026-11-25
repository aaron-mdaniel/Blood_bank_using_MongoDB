"""
Argon2id password hashing and verification module.
Uses argon2-cffi configured with parameters from application settings.
"""
import logging
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from app.config.settings import get_settings

logger = logging.getLogger("secure_blood_bank.security.hashing")


def _get_hasher() -> PasswordHasher:
    """Instantiates Argon2id PasswordHasher configured with parameters from Settings."""
    settings = get_settings()
    return PasswordHasher(
        time_cost=settings.ARGON2_TIME_COST,
        memory_cost=settings.ARGON2_MEMORY_COST,
        parallelism=settings.ARGON2_PARALLELISM,
        hash_len=32,
        salt_len=16,
    )


# Module-level hasher instance
_hasher: PasswordHasher = _get_hasher()


def hash_password(plain_password: str) -> str:
    """
    Hashes a plaintext password using Argon2id.
    Never stores or logs the plaintext password.
    """
    if not plain_password:
        raise ValueError("Password cannot be empty.")
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plaintext password against an Argon2id hash.
    Resistant to timing attacks. Returns False on mismatch or corrupted hash.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception as exc:
        logger.error(f"Unexpected error during password verification: {exc}")
        return False


def check_needs_rehash(hashed_password: str) -> bool:
    """Checks whether the password hash needs to be upgraded to newer Argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(hashed_password)
    except Exception:
        return True
