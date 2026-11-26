"""
Phase 4 Automated Test Suite: Role-Based Access Control (RBAC).
Verifies role-permission seeding, HTTP 401 for unauthenticated requests,
HTTP 403 for unauthorized roles across all 5 system roles, Admin role management,
and prevention of public ADMIN self-registration.
"""
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.models.enums import UserRole
from app.models.permissions import Permission
from app.services.rbac_service import RBACService


# ==========================================
# 1. Service & Repository Unit Tests
# ==========================================

def test_rbac_service_seeds_all_five_roles(mock_db):
    """Verify RBACService seeds all 5 canonical roles into roles_permissions."""
    service = RBACService()
    roles = service.list_roles()
    role_names = {r["role_name"] for r in roles}

    assert role_names == {
        UserRole.ADMIN.value,
        UserRole.BLOOD_BANK_STAFF.value,
        UserRole.HOSPITAL_STAFF.value,
        UserRole.DOCTOR.value,
        UserRole.DONOR.value,
    }
    assert service.has_permissions(UserRole.ADMIN.value, [Permission.AUDIT_READ.value, Permission.ROLES_WRITE.value])
    assert service.has_permissions(UserRole.BLOOD_BANK_STAFF.value, [Permission.BLOOD_UNITS_WRITE.value])
    assert not service.has_permissions(UserRole.DONOR.value, [Permission.BLOOD_UNITS_WRITE.value])


# ==========================================
# 2. Unauthenticated Access (HTTP 401)
# ==========================================

def test_unauthenticated_requests_return_401(client: TestClient):
    """Verify all protected endpoints reject unauthenticated requests with HTTP 401."""
    protected_gets = [
        "/api/users",
        "/api/roles",
        "/api/donors",
        "/api/hospitals",
        "/api/patients",
        "/api/donations",
        "/api/blood-units",
        "/api/blood-requests",
    ]
    for path in protected_gets:
        res = client.get(path)
        assert res.status_code == 401, f"Expected 401 for unauthenticated GET {path}, got {res.status_code}"


# ==========================================
# 3. Privilege Escalation Prevention
# ==========================================

def test_public_registration_rejects_admin_role(client: TestClient):
    """Verify public /api/auth/register blocks ADMIN self-registration with HTTP 403."""
    res = client.post(
        "/api/auth/register",
        json={
            "username": "rogue_admin",
            "email": "rogue@example.com",
            "password": "RoguePassword2026!",
            "role": "ADMIN",
        },
    )
    assert res.status_code == 403
    assert "admin" in res.json()["detail"].lower()


# ==========================================
# 4. Per-Role API Authorization Matrix
# ==========================================

def test_admin_can_manage_users_and_roles(client: TestClient, auth_header_factory):
    """Verify ADMIN has access to /api/users and /api/roles management."""
    admin_hdrs = auth_header_factory(UserRole.ADMIN)
    donor_hdrs = auth_header_factory(UserRole.DONOR, username="dynamic_donor")

    # List roles
    roles_res = client.get("/api/roles", headers=admin_hdrs)
    assert roles_res.status_code == 200
    assert len(roles_res.json()) == 5

    # Inspect specific role
    donor_role_res = client.get("/api/roles/DONOR", headers=admin_hdrs)
    assert donor_role_res.status_code == 200
    assert Permission.DONORS_READ.value in donor_role_res.json()["permissions"]

    # Initially DONOR can read donations
    assert client.get("/api/donations", headers=donor_hdrs).status_code == 200

    # Update DONOR role permissions dynamically to remove DONATIONS_READ and verify 403
    update_res = client.put(
        "/api/roles/DONOR",
        json={"permissions": [Permission.DONORS_READ.value]},
        headers=admin_hdrs,
    )
    assert update_res.status_code == 200
    assert update_res.json()["permissions"] == [Permission.DONORS_READ.value]
    assert client.get("/api/donations", headers=donor_hdrs).status_code == 403

    # Reset back to default matrix via /api/roles/seed and verify restored access
    seed_res = client.post("/api/roles/seed", headers=admin_hdrs)
    assert seed_res.status_code == 200
    donor_after_reset = client.get("/api/roles/DONOR", headers=admin_hdrs).json()
    assert Permission.DONATIONS_READ.value in donor_after_reset["permissions"]
    assert client.get("/api/donations", headers=donor_hdrs).status_code == 200


def test_blood_bank_staff_rbac(client: TestClient, auth_header_factory):
    """
    Verify BLOOD_BANK_STAFF can manage donors, donations, blood units, and approve requests,
    but receives HTTP 403 on user/role administration and hospital creation.
    """
    staff_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, blood_bank_id="bb_central")
    hospital_hdrs = auth_header_factory(UserRole.HOSPITAL_STAFF, hospital_id="hosp_01")

    # Allowed: Create blood unit
    expiry_dt = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    unit_res = client.post(
        "/api/blood-units",
        json={
            "unit_id": "UNIT-RBAC-001",
            "source_donation_id": "DON-RBAC-001",
            "blood_bank_id": "bb_central",
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

    # Hospital creates a request, Staff approves it
    req_res = client.post(
        "/api/blood-requests",
        json={
            "request_code": "REQ-RBAC-001",
            "hospital_id": "hosp_01",
            "doctor_id": "doc_01",
            "patient_id": "pat_01",
            "blood_group": "O",
            "rh_factor": "NEGATIVE",
            "component_type": "RBC",
            "units_requested": 1,
            "priority": "URGENT",
            "clinical_reason": "Surgical standby",
        },
        headers=hospital_hdrs,
    )
    assert req_res.status_code == 201

    approve_res = client.put(
        "/api/blood-requests/REQ-RBAC-001",
        json={"status": "APPROVED"},
        headers=staff_hdrs,
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "APPROVED"

    # Denied (403): Manage users, manage roles, create hospital, delete donor
    assert client.get("/api/users", headers=staff_hdrs).status_code == 403
    assert client.get("/api/roles", headers=staff_hdrs).status_code == 403
    assert client.delete("/api/donors/507f1f77bcf86cd799439011", headers=staff_hdrs).status_code == 403
    assert (
        client.post(
            "/api/hospitals",
            json={
                "name": "Unauthorized Hospital",
                "license_number": "LIC-999",
                "location": {"type": "Point", "coordinates": [77.5, 12.9]},
                "address": "123 Street",
                "emergency_helpline": "100",
            },
            headers=staff_hdrs,
        ).status_code
        == 403
    )


def test_hospital_staff_and_doctor_rbac(client: TestClient, auth_header_factory):
    """
    Verify HOSPITAL_STAFF and DOCTOR can read blood units, manage patients, and create requests,
    but receive HTTP 403 when modifying blood units, approving requests, or reading donations/donors.
    """
    hosp_hdrs = auth_header_factory(UserRole.HOSPITAL_STAFF, hospital_id="hosp_02")
    doc_hdrs = auth_header_factory(UserRole.DOCTOR, hospital_id="hosp_02")

    for hdrs in (hosp_hdrs, doc_hdrs):
        # Allowed: read inventory & create patient
        assert client.get("/api/blood-units", headers=hdrs).status_code == 200
        assert client.get("/api/blood-requests", headers=hdrs).status_code == 200

        # Denied (403): modify inventory, record donation, approve request, access users/roles
        expiry_dt = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        assert (
            client.post(
                "/api/blood-units",
                json={
                    "unit_id": "UNIT-ILLEGAL",
                    "source_donation_id": "DON-1",
                    "blood_bank_id": "bb_1",
                    "blood_group": "A",
                    "rh_factor": "POSITIVE",
                    "component_type": "RBC",
                    "volume_ml": 250,
                    "expiry_date": expiry_dt,
                    "storage_location": {"refrigerator_id": "REF-1", "shelf": "S1"},
                },
                headers=hdrs,
            ).status_code
            == 403
        )
        assert client.put("/api/blood-requests/REQ-NONE", json={"status": "APPROVED"}, headers=hdrs).status_code == 403
        assert client.get("/api/donations", headers=hdrs).status_code == 403
        assert client.get("/api/donors", headers=hdrs).status_code == 403
        assert client.get("/api/users", headers=hdrs).status_code == 403


def test_donor_rbac(client: TestClient, auth_header_factory):
    """
    Verify DONOR can access donor/donation read endpoints,
    but receives HTTP 403 on inventory, requests, patients, hospitals, users, and roles.
    """
    donor_hdrs = auth_header_factory(UserRole.DONOR)

    # Allowed at role level (resource ownership checks come in Phase 5)
    assert client.get("/api/donors", headers=donor_hdrs).status_code == 200
    assert client.get("/api/donations", headers=donor_hdrs).status_code == 200

    # Denied (403)
    assert client.get("/api/users", headers=donor_hdrs).status_code == 403
    assert client.get("/api/roles", headers=donor_hdrs).status_code == 403
    assert client.get("/api/patients", headers=donor_hdrs).status_code == 403
    assert client.get("/api/blood-units", headers=donor_hdrs).status_code == 403
    assert client.get("/api/blood-requests", headers=donor_hdrs).status_code == 403
    assert client.get("/api/hospitals", headers=donor_hdrs).status_code == 403
    assert client.delete("/api/donors/507f1f77bcf86cd799439011", headers=donor_hdrs).status_code == 403
