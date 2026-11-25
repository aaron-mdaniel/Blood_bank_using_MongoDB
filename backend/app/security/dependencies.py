"""
FastAPI Security Dependencies: Bearer token extraction, user authentication, and active status checks.
"""
from typing import Any, Dict, Tuple
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.security.jwt_handler import decode_access_token
from app.repositories.user_repository import UserRepository

# HTTPBearer security scheme
oauth2_scheme = HTTPBearer(auto_error=True)
user_repo = UserRepository()


async def get_current_token_and_payload(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
) -> Tuple[str, Dict[str, Any]]:
    """
    Validates Bearer token and returns (raw_token, decoded_payload).
    Raises HTTP 401 if token is expired, invalid, or malformed.
    """
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        return token, payload
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or revoked access token: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    token_and_payload: Tuple[str, Dict[str, Any]] = Depends(get_current_token_and_payload),
) -> Dict[str, Any]:
    """
    FastAPI dependency that validates the active JWT and returns the current user document.
    Enforces active account verification (rejects deactivated accounts with HTTP 403).
    """
    _, payload = token_and_payload
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identification subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated. Contact system administrator.",
        )

    return user
