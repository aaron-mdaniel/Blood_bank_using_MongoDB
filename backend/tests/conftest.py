"""
Pytest configuration and shared test fixtures.
Provides isolated test clients, in-memory MongoDB fixtures (via mongomock),
and clean database teardown.
"""
import os
import sys
from pathlib import Path
import pytest
import mongomock
from fastapi.testclient import TestClient

# Ensure backend root is on Python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Force testing environment
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_NAME"] = "test_secure_blood_bank"

from app.config.settings import get_settings
from app.config.database import db_manager, Collections
from app.main import app
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository
from app.security.encryption import USER_ENCRYPTED_FIELDS, encrypt_fields
from app.security.hashing import hash_password
from app.security.jwt_handler import create_access_token, token_blacklist


@pytest.fixture(scope="session")
def test_settings():
    """Returns application test settings."""
    settings = get_settings()
    return settings


@pytest.fixture(scope="function")
def mock_db():
    """
    Provides an isolated in-memory MongoDB database instance per test function using mongomock.
    Guarantees that tests run deterministically and without requiring an external MongoDB server.
    """
    mock_client = mongomock.MongoClient()
    db_manager.connect(client=mock_client)
    token_blacklist.clear()
    yield db_manager.db
    # Teardown
    token_blacklist.clear()
    db_manager.disconnect()


@pytest.fixture(scope="function")
def client(mock_db):
    """
    TestClient fixture equipped with the in-memory mock database.
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def auth_header_factory(mock_db):
    """
    Factory fixture that creates a user in mock_db for a given role and returns Bearer auth headers.
    """
    user_repo = UserRepository()

    def _make_headers(
        role: UserRole = UserRole.ADMIN,
        username: str = None,
        hospital_id: str = None,
        blood_bank_id: str = None,
    ):
        role_val = role.value if isinstance(role, UserRole) else str(role)
        uname = username or f"test_{role_val.lower()}"
        existing = user_repo.get_by_username(uname)
        if not existing:
            user_doc = encrypt_fields(
                {
                    "username": uname,
                    "email_hash": f"hash_{uname}@test.local",
                    "email": f"{uname}@test.local",
                    "password_hash": hash_password("TestPassword2026!"),
                    "role": role_val,
                    "is_active": True,
                    "failed_login_attempts": 0,
                    "lockout_until": None,
                    "hospital_id": hospital_id,
                    "blood_bank_id": blood_bank_id,
                },
                USER_ENCRYPTED_FIELDS,
                context="users",
            )
            existing = user_repo.create(user_doc)
        token = create_access_token({
            "sub": str(existing["_id"]),
            "username": existing["username"],
            "role": existing["role"],
            "hospital_id": existing.get("hospital_id"),
            "blood_bank_id": existing.get("blood_bank_id"),
        })
        return {"Authorization": f"Bearer {token}"}

    return _make_headers


@pytest.fixture(scope="function")
def admin_headers(auth_header_factory):
    """Returns Bearer authorization headers for an ADMIN user."""
    return auth_header_factory(role=UserRole.ADMIN, username="fixture_admin")
