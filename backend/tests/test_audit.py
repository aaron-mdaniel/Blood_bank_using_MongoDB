"""
Phase 7 Automated Test Suite: Centralized Security Audit Logging.
Tests audit log generation for authentication events, user/role changes,
blood unit and request lifecycle actions, HTTP 403 ACCESS_DENIED capture,
sensitive-data redaction, and Admin-only /api/audit access controls.
"""
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.config.database import db_manager
from app.models.enums import UserRole
from app.models.permissions import Permission
from app.services.audit_service import AuditService, sanitize_metadata


# ==========================================
# 1. Metadata Sanitization Unit Tests
# ==========================================

def test_audit_metadata_sanitizes_secrets_and_pii():
    """Verify passwords, JWT secrets, encryption keys, and PII are never stored in audit_logs."""
    raw_metadata = {
        "username": "alice",
        "password": "PlainPassword123!",
        "jwt_secret_key": "super_secret_jwt",
        "encryption_secret_key": "super_secret_aes",
        "email": "alice@example.org",
        "nested": {
            "contact_phone": "+91-9999999999",
            "access_token": "eyJhbGciOi...",
            "safe_note": "ok",
        },
    }
    clean = sanitize_metadata(raw_metadata)
    assert clean["username"] == "alice"
    assert clean["password"] == "[REDACTED]"
    assert clean["jwt_secret_key"] == "[REDACTED]"
    assert clean["encryption_secret_key"] == "[REDACTED]"
    assert clean["email"] == "[REDACTED]"
    assert clean["nested"]["contact_phone"] == "[REDACTED]"
    assert clean["nested"]["access_token"] == "[REDACTED]"
    assert clean["nested"]["safe_note"] == "ok"


def test_audit_service_persists_structured_event(mock_db):
    """Verify AuditService writes required event fields and redacts sensitive metadata."""
    service = AuditService()
    created = service.log_event(
        action="USER_CREATED",
        resource_type="users",
        resource_id="usr_42",
        status="SUCCESS",
        actor={"_id": "adm_1", "username": "sysadmin", "role": "ADMIN"},
        metadata={"password": "leak", "target_role": "DOCTOR"},
    )
    assert created is not None
    assert created["event_id"].startswith("EVT-")
    assert created["actor"]["user_id"] == "adm_1"
    assert created["actor"]["role"] == "ADMIN"
    assert created["metadata"]["password"] == "[REDACTED]"
    assert created["metadata"]["target_role"] == "DOCTOR"


# ==========================================
# 2. Authentication & User/Role Lifecycle Audits
# ==========================================

def test_auth_events_generate_audit_logs(client: TestClient, auth_header_factory):
    """Verify registration, successful login, failed login, and logout are recorded in audit_logs."""
    admin_hdrs = auth_header_factory(UserRole.ADMIN)

    # Register
    reg_res = client.post(
        "/api/auth/register",
        json={
            "username": "audit_donor",
            "email": "audit.donor@example.com",
            "password": "AuditPassword2026!",
            "role": "DONOR",
        },
    )
    assert reg_res.status_code == 201

    # Failed login
    fail_res = client.post(
        "/api/auth/login",
        json={"username": "audit_donor", "password": "WrongPassword!"},
    )
    assert fail_res.status_code == 401

    # Successful login
    ok_res = client.post(
        "/api/auth/login",
        json={"username": "audit_donor", "password": "AuditPassword2026!"},
    )
    assert ok_res.status_code == 200
    token = ok_res.json()["access_token"]

    # Logout
    logout_res = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_res.status_code == 200

    # Admin inspects /api/audit
    logs_res = client.get("/api/audit", headers=admin_hdrs)
    assert logs_res.status_code == 200
    actions = {entry["action"] for entry in logs_res.json()}
    assert {"USER_CREATED", "LOGIN_FAILED", "LOGIN_SUCCESS", "LOGOUT"}.issubset(actions)

    # Confirm no plaintext email or password leaked anywhere in audit_logs
    raw_logs = list(db_manager.audit_logs.find({}))
    serialized_dump = str(raw_logs)
    assert "AuditPassword2026!" not in serialized_dump
    assert "WrongPassword!" not in serialized_dump
    assert "audit.donor@example.com" not in serialized_dump


def test_user_role_change_and_permission_update_audited(client: TestClient, auth_header_factory):
    """Verify Admin user creation, role change, and role permission updates generate audit logs."""
    admin_hdrs = auth_header_factory(UserRole.ADMIN)

    u_res = client.post(
        "/api/users",
        json={
            "username": "promoted_staff",
            "email": "promoted@bloodbank.org",
            "password": "StaffPassword2026!",
            "role": "DONOR",
        },
        headers=admin_hdrs,
    )
    assert u_res.status_code == 201
    uid = u_res.json()["_id"]

    # Role change
    upd_res = client.put(
        f"/api/users/{uid}",
        json={"role": "BLOOD_BANK_STAFF"},
        headers=admin_hdrs,
    )
    assert upd_res.status_code == 200

    # Role permission update
    perm_res = client.put(
        "/api/roles/DONOR",
        json={"permissions": [Permission.DONORS_READ.value, Permission.DONATIONS_READ.value]},
        headers=admin_hdrs,
    )
    assert perm_res.status_code == 200

    role_change_logs = client.get("/api/audit?action=USER_ROLE_CHANGED", headers=admin_hdrs).json()
    assert len(role_change_logs) == 1
    assert role_change_logs[0]["resource_id"] == uid
    assert role_change_logs[0]["metadata"]["old_role"] == "DONOR"
    assert role_change_logs[0]["metadata"]["new_role"] == "BLOOD_BANK_STAFF"

    perm_logs = client.get("/api/audit?action=ROLE_PERMISSIONS_UPDATED", headers=admin_hdrs).json()
    assert len(perm_logs) == 1
    assert perm_logs[0]["resource_id"] == "DONOR"


# ==========================================
# 3. Clinical Inventory & Request Audits
# ==========================================

def test_blood_unit_and_request_lifecycle_audited(client: TestClient, auth_header_factory):
    """Verify blood unit creation/allocation and blood request creation/approval/rejection are audited."""
    admin_hdrs = auth_header_factory(UserRole.ADMIN)
    staff_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="audit_bb_staff", blood_bank_id="bb_audit")
    hosp_hdrs = auth_header_factory(UserRole.HOSPITAL_STAFF, username="audit_hosp_staff", hospital_id="hosp_audit")

    # Blood unit create & allocate update
    expiry_dt = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    unit_res = client.post(
        "/api/blood-units",
        json={
            "unit_id": "UNIT-AUD-001",
            "source_donation_id": "DON-AUD-001",
            "blood_bank_id": "bb_audit",
            "blood_group": "O",
            "rh_factor": "NEGATIVE",
            "component_type": "RBC",
            "volume_ml": 250,
            "expiry_date": expiry_dt,
            "storage_location": {"refrigerator_id": "REF-1", "shelf": "S1"},
        },
        headers=staff_hdrs,
    )
    assert unit_res.status_code == 201
    assert (
        client.put(
            "/api/blood-units/UNIT-AUD-001",
            json={"status": "ALLOCATED", "reserved_for_request_id": "REQ-AUD-1"},
            headers=staff_hdrs,
        ).status_code
        == 200
    )

    # Blood request create, approve, and reject
    req_base = {
        "hospital_id": "hosp_audit",
        "doctor_id": "doc_1",
        "patient_id": "pat_1",
        "blood_group": "O",
        "rh_factor": "NEGATIVE",
        "component_type": "RBC",
        "units_requested": 1,
        "priority": "CRITICAL",
        "clinical_reason": "Emergency transfusion",
    }
    assert client.post("/api/blood-requests", json={**req_base, "request_code": "REQ-AUD-1"}, headers=hosp_hdrs).status_code == 201
    assert client.post("/api/blood-requests", json={**req_base, "request_code": "REQ-AUD-2"}, headers=hosp_hdrs).status_code == 201
    assert client.put("/api/blood-requests/REQ-AUD-1", json={"status": "APPROVED"}, headers=staff_hdrs).status_code == 200
    assert client.put("/api/blood-requests/REQ-AUD-2", json={"status": "REJECTED"}, headers=staff_hdrs).status_code == 200

    logs = client.get("/api/audit", headers=admin_hdrs).json()
    actions = {entry["action"] for entry in logs}
    assert {
        "BLOOD_UNIT_CREATED",
        "BLOOD_UNIT_ALLOCATED",
        "BLOOD_REQUEST_CREATED",
        "BLOOD_REQUEST_APPROVED",
        "BLOOD_REQUEST_REJECTED",
    }.issubset(actions)


# ==========================================
# 4. Unauthorized 403 Denial Audits & Admin-Only /api/audit
# ==========================================

def test_unauthorized_attempts_logged_and_audit_endpoint_restricted(client: TestClient, auth_header_factory):
    """
    Verify non-admin roles receive HTTP 403 on /api/audit and that HTTP 403 denials
    are centrally recorded as ACCESS_DENIED in audit_logs.
    """
    admin_hdrs = auth_header_factory(UserRole.ADMIN)
    donor_hdrs = auth_header_factory(UserRole.DONOR, username="audit_intruder_donor")
    staff_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="audit_intruder_staff", blood_bank_id="bb_1")

    # Non-admin attempts to read audit logs -> 403
    assert client.get("/api/audit", headers=donor_hdrs).status_code == 403
    assert client.get("/api/audit", headers=staff_hdrs).status_code == 403

    # Donor attempts unauthorized inventory write -> 403
    expiry_dt = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    assert (
        client.post(
            "/api/blood-units",
            json={
                "unit_id": "UNIT-DENIED",
                "source_donation_id": "DON-1",
                "blood_bank_id": "bb_1",
                "blood_group": "A",
                "rh_factor": "POSITIVE",
                "component_type": "RBC",
                "volume_ml": 250,
                "expiry_date": expiry_dt,
                "storage_location": {"refrigerator_id": "REF-1", "shelf": "S1"},
            },
            headers=donor_hdrs,
        ).status_code
        == 403
    )

    # Admin filters DENIED events and inspects single event by event_id
    denied_res = client.get("/api/audit?action=ACCESS_DENIED&status=DENIED", headers=admin_hdrs)
    assert denied_res.status_code == 200
    denied_logs = denied_res.json()
    assert len(denied_logs) >= 3
    assert all(entry["status"] == "DENIED" for entry in denied_logs)
    assert any(entry["actor"]["username"] == "audit_intruder_donor" for entry in denied_logs)

    event_id = denied_logs[0]["event_id"]
    single_res = client.get(f"/api/audit/{event_id}", headers=admin_hdrs)
    assert single_res.status_code == 200
    assert single_res.json()["event_id"] == event_id
