"""
User CRUD REST API Router.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.repositories.user_repository import UserRepository
from app.schemas.user_schema import UserCreate, UserUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["Users"])
user_repo = UserRepository()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate):
    """Creates a new system user."""
    # Check for existing username
    if user_repo.get_by_username(payload.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' is already registered."
        )

    # In Phase 2, store with mock password hash (Argon2id integration occurs in Phase 3)
    user_dict = payload.model_dump()
    raw_password = user_dict.pop("password")
    user_dict["password_hash"] = f"hashed_{raw_password}"
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
    role: Optional[str] = None
):
    """Retrieves paginated list of users."""
    query = {}
    if role:
        query["role"] = role
    return user_repo.find_many(query, skip=skip, limit=limit)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    """Retrieves a single user by ID."""
    user = user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, payload: UserUpdate):
    """Updates user role or active status."""
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update.")

    updated = user_repo.update(user_id, update_data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return updated


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str):
    """Deletes a user account."""
    deleted = user_repo.delete(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return None
