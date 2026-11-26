"""
FastAPI Security Dependencies: Bearer token extraction, user authentication,
active status checks, and Role-Based Access Control (RBAC) guards.
"""
from typing import Any, Callable, Dict, Tuple, Union
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.models.enums import UserRole
from app.models.permissions import Permission
from app.security.jwt_handler import decode_access_token
from app.repositories.user_repository import UserRepository
from app.services.rbac_service import RBACService

# HTTPBearer with auto_error=False so missing credentials consistently return HTTP 401
oauth2_scheme = HTTPBearer(auto_error=False)
user_repo = UserRepository()
rbac_service = RBACService()


async def get_current_token_and_payload(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
) -> Tuple[str, Dict[str, Any]]:
    """
    Validates Bearer token and returns (raw_token, decoded_payload).
    Raises HTTP 401 if token is missing, expired, invalid, or revoked.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

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


def require_roles(*allowed_roles: Union[UserRole, str]) -> Callable:
    """
    FastAPI dependency factory enforcing that the authenticated user holds one of the allowed roles.
    Raises HTTP 401 if unauthenticated and HTTP 403 if role is not permitted.
    """
    allowed = {r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles}

    async def role_dependency(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        user_role = current_user.get("role")
        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Role '{user_role}' is not authorized for this operation.",
            )
        return current_user

    return role_dependency


def require_permissions(*required_permissions: Union[Permission, str]) -> Callable:
    """
    FastAPI dependency factory enforcing that the authenticated user's role possesses
    all specified permissions in the roles_permissions collection.
    Raises HTTP 401 if unauthenticated and HTTP 403 if any permission is missing.
    """
    needed = [p.value if isinstance(p, Permission) else str(p) for p in required_permissions]

    async def permission_dependency(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        user_role = current_user.get("role", "")
        if not rbac_service.has_permissions(user_role, needed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied. Role '{user_role}' lacks required permission(s): "
                    f"{', '.join(needed)}."
                ),
            )
        return current_user

    return permission_dependency
