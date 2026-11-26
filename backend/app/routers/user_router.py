"""
User CRUD REST API Router (Admin-protected via RBAC).
"""
import hashlib
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.models.permissions import Permission
from app.repositories.user_repository import UserRepository
from app.schemas.user_schema import UserCreate, UserUpdate, UserResponse
from app.security.dependencies import require_permissions
from app.security.hashing import hash_password

router = APIRouter(prefix="/users", tags=["Users"])
user_repo = UserRepository()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.USERS_WRITE)),
):
    """Creates a new system user with Argon2id password hashing (Admin only)."""
    # Check for existing username
    if user_repo.get_by_username(payload.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' is already registered."
        )

    email_hash = hashlib.sha256(payload.email.strip().lower().encode("utf-8")).hexdigest()
    if user_repo.get_by_email_hash(email_hash):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address is already registered."
        )

    user_dict = payload.model_dump()
    raw_password = user_dict.pop("password")
    user_dict["password_hash"] = hash_password(raw_password)
    user_dict["email_hash"] = email_hash
    user_dict["email_encrypted"] = f"enc_{payload.email}"
    user_dict["is_active"] = True
    user_dict["failed_login_attempts"] = 0
    user_dict["lockout_until"] = None

    try:
        created = user_repo.create(user_dict)
        return created
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this username or email already exists."
        )


@router.get("", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    role: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.USERS_READ)),
):
    """Retrieves paginated list of users (Admin only)."""
    query = {}
    if role:
        query["role"] = role
    return user_repo.find_many(query, skip=skip, limit=limit)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.USERS_READ)),
):
    """Retrieves a single user by ID (Admin only)."""
    user = user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.USERS_WRITE)),
):
    """Updates user role or active status (Admin only)."""
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update.")

    updated = user_repo.update(user_id, update_data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return updated


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.USERS_DELETE)),
):
    """Deletes a user account (Admin only)."""
    deleted = user_repo.delete(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return None
