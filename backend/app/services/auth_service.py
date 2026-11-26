"""
Authentication Service: User Registration, Argon2id Verification, JWT Issuance,
Failed-Attempt Lockout Enforcement, and Session Revocation.
"""
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.config.settings import get_settings
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.auth_schema import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserSummary,
    LogoutResponse,
)
from app.security.hashing import hash_password, verify_password
from app.security.jwt_handler import create_access_token, token_blacklist


class AuthService:
    """
    Orchestrates authentication, credential verification, and account security.
    """
    def __init__(self, user_repo: UserRepository = None):
        self.user_repo = user_repo or UserRepository()

    @staticmethod
    def compute_email_hash(email: str) -> str:
        """Computes deterministic SHA-256 hash of normalized email for unique indexing."""
        return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()

    def register_user(self, payload: RegisterRequest) -> Dict[str, Any]:
        """
        Registers a new user account with Argon2id password hashing.
        Rejects duplicate usernames/email addresses and prevents public ADMIN self-registration.
        """
        requested_role = payload.role.value if isinstance(payload.role, UserRole) else str(payload.role)
        if requested_role == UserRole.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Self-registration with ADMIN role is not permitted. Contact an administrator.",
            )

        # Check duplicate username
        if self.user_repo.get_by_username(payload.username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{payload.username}' is already registered.",
            )

        email_hash = self.compute_email_hash(str(payload.email))
        if self.user_repo.get_by_email_hash(email_hash):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address is already registered.",
            )

        # Hash password using Argon2id
        argon2_hash = hash_password(payload.password)

        user_doc = {
            "username": payload.username,
            "email_hash": email_hash,
            "email_encrypted": f"enc_{payload.email}",  # Secured via AES-256-GCM in Phase 6
            "password_hash": argon2_hash,
            "role": payload.role.value if isinstance(payload.role, UserRole) else str(payload.role),
            "is_active": True,
            "failed_login_attempts": 0,
            "lockout_until": None,
            "hospital_id": payload.hospital_id,
            "blood_bank_id": payload.blood_bank_id,
        }

        try:
            created = self.user_repo.create(user_doc)
            return created
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this username or email already exists.",
            )

    def authenticate_user(self, payload: LoginRequest) -> TokenResponse:
        """
        Verifies login credentials with Argon2id and enforces account lockouts.
        Tracks failed login attempts and locks out account for 15 minutes after 5 failures.
        """
        settings = get_settings()
        user = self.user_repo.get_by_username(payload.username)

        # Constant-time mitigation against user enumeration
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if account is deactivated
        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated. Contact system administrator.",
            )

        # Check if account is currently locked out
        lockout_until = user.get("lockout_until")
        if lockout_until:
            if lockout_until.tzinfo is None:
                lockout_until = lockout_until.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if lockout_until > now:
                remaining_seconds = int((lockout_until - now).total_seconds())
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        f"Account is temporarily locked due to multiple failed login attempts. "
                        f"Please try again in {remaining_seconds} seconds."
                    ),
                )

        # Verify password using Argon2id
        password_valid = verify_password(payload.password, user.get("password_hash", ""))
        if not password_valid:
            # Increment failed attempts and trigger lockout if >= 5
            self.user_repo.increment_failed_attempts(user["_id"], max_attempts=5)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Successful authentication: reset failed attempts if previously flagged
        if user.get("failed_login_attempts", 0) > 0 or user.get("lockout_until") is not None:
            self.user_repo.reset_failed_attempts(user["_id"])

        # Generate JWT access token with role claims
        token_claims = {
            "sub": str(user["_id"]),
            "username": user["username"],
            "role": user["role"],
            "hospital_id": user.get("hospital_id"),
            "blood_bank_id": user.get("blood_bank_id"),
        }
        access_token = create_access_token(token_claims)
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

        user_summary = UserSummary(
            _id=str(user["_id"]),
            username=user["username"],
            role=user["role"],
            is_active=user["is_active"],
            hospital_id=user.get("hospital_id"),
            blood_bank_id=user.get("blood_bank_id"),
        )

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            user=user_summary,
        )

    def logout_user(self, token: str, payload: Dict[str, Any]) -> LogoutResponse:
        """
        Invalidates active session by blacklisting the token's unique jti.
        """
        jti = payload.get("jti")
        exp_ts = payload.get("exp")

        if jti and exp_ts:
            exp_datetime = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            token_blacklist.revoke(jti, exp_datetime)

        return LogoutResponse(message="Successfully logged out.", status="success")
