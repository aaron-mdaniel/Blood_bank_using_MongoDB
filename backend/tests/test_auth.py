"""
Phase 3 Automated Test Suite: User Authentication & Security.
Tests Argon2id hashing, JWT token lifecycle, registration, login, failed-attempt lockout,
deactivated account handling, logout token revocation, and protected identity retrieval.
"""
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.security.hashing import hash_password, verify_password
from app.security.jwt_handler import (
    create_access_token,
    decode_access_token,
    token_blacklist,
)
from app.repositories.user_repository import UserRepository


# ==========================================
# 1. Cryptographic Hashing Unit Tests
# ==========================================

def test_argon2_hashing_and_verification():
    """Verify Argon2id generates valid hashes and verifies correct/incorrect passwords."""
    plain = "SuperSecretPassword2026!"
    hashed = hash_password(plain)

    # Must start with standard Argon2id identifier
    assert hashed.startswith("$argon2id$")
    assert hashed != plain

    # Successful verification
    assert verify_password(plain, hashed) is True

    # Failed verification on incorrect password
    assert verify_password("WrongPassword123!", hashed) is False

    # Graceful handling of corrupted hash
    assert verify_password(plain, "corrupted_hash_string") is False
    assert verify_password("", hashed) is False


# ==========================================
# 2. JWT Generation & Verification Unit Tests
# ==========================================

def test_jwt_generation_and_decoding():
    """Verify JWT access token contains required claims and valid signature."""
    claims = {
        "sub": "user_id_12345",
        "username": "tester_admin",
        "role": "ADMIN",
        "hospital_id": "hosp_99",
    }
    token = create_access_token(claims, expires_delta=timedelta(minutes=15))
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload["sub"] == "user_id_12345"
    assert payload["username"] == "tester_admin"
    assert payload["role"] == "ADMIN"
    assert payload["hospital_id"] == "hosp_99"
    assert "exp" in payload
    assert "iat" in payload
    assert "jti" in payload


def test_jwt_expiration_handling():
    """Verify expired tokens are rejected."""
    claims = {"sub": "user_expired", "username": "expired_user", "role": "DONOR"}
    expired_token = create_access_token(claims, expires_delta=timedelta(seconds=-10))

    with pytest.raises(ExpiredSignatureError):
        decode_access_token(expired_token)


def test_jwt_tampered_signature_rejection():
    """Verify tampered token signatures are rejected."""
    claims = {"sub": "user_tamper", "username": "legit_user", "role": "DONOR"}
    token = create_access_token(claims)

    # Tamper with the token string
    tampered_token = token[:-5] + "XXXXX"
    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered_token)


# ==========================================
# 3. Authentication REST API Endpoints Tests
# ==========================================

def test_auth_registration_success_and_duplicates(client: TestClient):
    """Test user registration endpoint with valid data and duplicate rejections."""
    reg_payload = {
        "username": "nurse_sarah",
        "email": "sarah.nurse@cityhospital.org",
        "password": "ClinicalPassword2026!",
        "role": "HOSPITAL_STAFF",
        "hospital_id": "hosp_city_central",
    }

    # 1. Successful Registration
    res = client.post("/api/auth/register", json=reg_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == "nurse_sarah"
    assert data["role"] == "HOSPITAL_STAFF"
    assert data["hospital_id"] == "hosp_city_central"
    assert data["is_active"] is True
    # Password must NEVER be returned in response
    assert "password" not in data
    assert "password_hash" not in data

    # 2. Duplicate Username Rejection (409)
    dup_user_res = client.post(
        "/api/auth/register",
        json={**reg_payload, "email": "different.email@hospital.org"},
    )
    assert dup_user_res.status_code == 409
    assert "already registered" in dup_user_res.json()["detail"].lower()

    # 3. Duplicate Email Rejection (409)
    dup_email_res = client.post(
        "/api/auth/register",
        json={**reg_payload, "username": "different_nurse"},
    )
    assert dup_email_res.status_code == 409
    assert "email" in dup_email_res.json()["detail"].lower()


def test_auth_registration_validation_error(client: TestClient):
    """Verify registration fails if password is too short (< 8 chars)."""
    invalid_payload = {
        "username": "short_pwd_user",
        "email": "short@test.com",
        "password": "123",  # Invalid: < 8 characters
        "role": "DONOR",
    }
    res = client.post("/api/auth/register", json=invalid_payload)
    assert res.status_code == 422


def test_auth_login_success(client: TestClient):
    """Test login with valid credentials returns JWT access token and user profile."""
    # Register
    client.post(
        "/api/auth/register",
        json={
            "username": "dr_watson",
            "email": "watson@bakerstreet.com",
            "password": "Elementary2026!",
            "role": "DOCTOR",
        },
    )

    # Login
    login_res = client.post(
        "/api/auth/login",
        json={"username": "dr_watson", "password": "Elementary2026!"},
    )
    assert login_res.status_code == 200
    data = login_res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert data["user"]["username"] == "dr_watson"
    assert data["user"]["role"] == "DOCTOR"


def test_auth_login_invalid_password(client: TestClient):
    """Test login with incorrect password returns HTTP 401."""
    client.post(
        "/api/auth/register",
        json={
            "username": "donor_bruce",
            "email": "bruce@wayne.com",
            "password": "BatPassword2026!",
            "role": "DONOR",
        },
    )

    # Login with wrong password
    res = client.post(
        "/api/auth/login",
        json={"username": "donor_bruce", "password": "WrongPassword!"},
    )
    assert res.status_code == 401
    assert "Invalid username or password" in res.json()["detail"]


def test_auth_login_nonexistent_user(client: TestClient):
    """Test login with non-existent username returns HTTP 401."""
    res = client.post(
        "/api/auth/login",
        json={"username": "non_existent_ghost", "password": "AnyPassword123!"},
    )
    assert res.status_code == 401
    assert "Invalid username or password" in res.json()["detail"]


def test_auth_failed_login_lockout(client: TestClient):
    """
    Test account lockout security:
    After 5 consecutive failed login attempts, account is locked for 15 minutes.
    """
    client.post(
        "/api/auth/register",
        json={
            "username": "target_victim",
            "email": "victim@security.org",
            "password": "ValidPassword2026!",
            "role": "DONOR",
        },
    )

    # 4 Failed attempts -> HTTP 401
    for _ in range(4):
        res = client.post(
            "/api/auth/login",
            json={"username": "target_victim", "password": "WrongPassword!"},
        )
        assert res.status_code == 401

    # 5th attempt -> triggers lockout
    res_5th = client.post(
        "/api/auth/login",
        json={"username": "target_victim", "password": "WrongPassword!"},
    )
    assert res_5th.status_code == 401

    # 6th attempt (even with CORRECT password) -> must be rejected with HTTP 403 Account Locked
    res_locked = client.post(
        "/api/auth/login",
        json={"username": "target_victim", "password": "ValidPassword2026!"},
    )
    assert res_locked.status_code == 403
    assert "temporarily locked" in res_locked.json()["detail"].lower()


def test_auth_deactivated_account_login(client: TestClient):
    """Test login on deactivated account is rejected with HTTP 403."""
    reg = client.post(
        "/api/auth/register",
        json={
            "username": "deactivated_user",
            "email": "deactivated@example.com",
            "password": "Password2026!",
            "role": "DONOR",
        },
    )
    user_id = reg.json()["_id"]

    # Deactivate account via repository
    user_repo = UserRepository()
    user_repo.update(user_id, {"is_active": False})

    # Attempt login
    login_res = client.post(
        "/api/auth/login",
        json={"username": "deactivated_user", "password": "Password2026!"},
    )
    assert login_res.status_code == 403
    assert "deactivated" in login_res.json()["detail"].lower()


def test_protected_get_me_endpoint(client: TestClient):
    """Test identity inspection endpoint /api/auth/me with valid Bearer token."""
    client.post(
        "/api/auth/register",
        json={
            "username": "staff_alex",
            "email": "alex@bloodbank.org",
            "password": "StaffPassword2026!",
            "role": "BLOOD_BANK_STAFF",
            "blood_bank_id": "bb_central",
        },
    )

    login_res = client.post(
        "/api/auth/login",
        json={"username": "staff_alex", "password": "StaffPassword2026!"},
    )
    token = login_res.json()["access_token"]

    # Call /api/auth/me with Bearer token
    headers = {"Authorization": f"Bearer {token}"}
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["username"] == "staff_alex"
    assert me_data["role"] == "BLOOD_BANK_STAFF"
    assert me_data["blood_bank_id"] == "bb_central"


def test_auth_logout_revocation(client: TestClient):
    """Test token revocation on logout: revoked token is rejected on subsequent calls."""
    client.post(
        "/api/auth/register",
        json={
            "username": "logout_tester",
            "email": "logout@test.com",
            "password": "LogoutPassword2026!",
            "role": "DONOR",
        },
    )

    login_res = client.post(
        "/api/auth/login",
        json={"username": "logout_tester", "password": "LogoutPassword2026!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify token works
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    # Logout
    logout_res = client.post("/api/auth/logout", headers=headers)
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "success"

    # Subsequent access with same token must fail (HTTP 401 Revoked)
    subsequent_res = client.get("/api/auth/me", headers=headers)
    assert subsequent_res.status_code == 401
    assert "revoked" in subsequent_res.json()["detail"].lower()


def test_missing_or_invalid_bearer_token(client: TestClient):
    """Verify accessing protected endpoint without token or with malformed token fails."""
    # 1. Missing Authorization header
    res_missing = client.get("/api/auth/me")
    assert res_missing.status_code in (401, 403)

    # 2. Malformed token
    res_malformed = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
    )
    assert res_malformed.status_code == 401
