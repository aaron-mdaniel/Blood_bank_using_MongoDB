"""
JWT Token Management: Creation, Decoding, Verification, and Revocation (Blacklisting).
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Set
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.config.settings import get_settings


class TokenBlacklist:
    """
    Manages revoked JWT tokens (by jti or token signature).
    Prunes expired entries to avoid memory growth.
    """
    def __init__(self):
        # Maps jti -> expiry timestamp
        self._revoked_tokens: Dict[str, datetime] = {}

    def revoke(self, jti: str, exp: datetime) -> None:
        self._prune()
        self._revoked_tokens[jti] = exp

    def is_revoked(self, jti: str) -> bool:
        self._prune()
        return jti in self._revoked_tokens

    def _prune(self) -> None:
        now = datetime.now(timezone.utc)
        expired_keys = [k for k, exp in self._revoked_tokens.items() if exp <= now]
        for k in expired_keys:
            del self._revoked_tokens[k]

    def clear(self) -> None:
        """Clears blacklist (primarily for test teardowns)."""
        self._revoked_tokens.clear()


# Global blacklist singleton
token_blacklist = TokenBlacklist()


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Generates a cryptographically signed JWT access token.
    Embeds sub, username, role, optional hospital_id/blood_bank_id, jti, iat, and exp.
    """
    settings = get_settings()
    to_encode = dict(data)
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT access token.
    Raises ExpiredSignatureError if expired, InvalidTokenError if signature invalid or revoked.
    """
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["exp", "iat", "sub"]},
    )

    # Check if revoked/blacklisted
    jti = payload.get("jti")
    if jti and token_blacklist.is_revoked(jti):
        raise InvalidTokenError("Token has been revoked/logged out.")

    return payload
