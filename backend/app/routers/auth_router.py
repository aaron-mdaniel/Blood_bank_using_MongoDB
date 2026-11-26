"""
Authentication REST API Router: Registration, Login, Logout, and Identity Inspection.
"""
from typing import Any, Dict, Tuple
from fastapi import APIRouter, Depends, status

from app.schemas.auth_schema import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserSummary,
    LogoutResponse,
)
from app.schemas.user_schema import UserResponse
from app.services.auth_service import AuthService
from app.security.dependencies import (
    get_current_user,
    get_current_token_and_payload,
)
from app.security.encryption import USER_ENCRYPTED_FIELDS, decrypt_fields

router = APIRouter(prefix="/auth", tags=["Authentication"])
auth_service = AuthService()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user account",
)
async def register(payload: RegisterRequest):
    """
    Registers a new system user with Argon2id password hashing and unique email/username checks.
    """
    created_user = auth_service.register_user(payload)
    return created_user


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User login and JWT issuance",
)
async def login(payload: LoginRequest):
    """
    Authenticates user credentials using Argon2id, verifies account state,
    enforces 5-attempt lockout security, and issues signed JWT access token.
    """
    token_response = auth_service.authenticate_user(payload)
    return token_response


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout and revoke active JWT session",
)
async def logout(
    token_and_payload: Tuple[str, Dict[str, Any]] = Depends(get_current_token_and_payload),
):
    """
    Revokes the current JWT access token and invalidates the session context.
    """
    token, payload = token_and_payload
    return auth_service.logout_user(token, payload)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve current authenticated user",
)
async def get_me(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Returns the profile and role details of the currently authenticated session actor.
    """
    return decrypt_fields(current_user, USER_ENCRYPTED_FIELDS, context="users")
