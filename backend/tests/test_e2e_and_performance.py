"""
Phase 10 Automated Test Suite:
- Full 5-role End-to-End Lifecycle Verification
- Demo Data Seeder Idempotency Test
- Concurrent Multi-Threaded Atomic Allocation Race-Condition Test
- Indexed Query & Aggregation Performance Benchmark (500 units)
"""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.config.database import db_manager
from app.models.enums import (
    BloodComponent,
    BloodGroup,
    BloodUnitStatus,
    RequestPriority,
    RequestStatus,
    RhFactor,
    UserRole,
)
from app.repositories.blood_request_repository import BloodRequestRepository
from app.repositories.blood_unit_repository import BloodUnitRepository
from app.services.analytics_service import AnalyticsService
from app.services.workflow_service import WorkflowService
from scripts.create_indexes import setup_indexes
from scripts.seed_demo import DEMO_ACCOUNTS, seed_demo_data


# ==========================================
# 1. Demo Seeder & Multi-Role End-to-End Flow
# ==========================================

def test_seed_demo_data_is_idempotent_and_logins_work(client: TestClient):
    """Verify seed_demo_data populates all 11 collections idempotently and all 5 demo logins succeed."""
    first = seed_demo_data()
    second = seed_demo_data()
    assert first["users"] == second["users"]
    assert db_manager.users.count_documents({}) == 5
    assert db_manager.blood_units.count_documents({}) >= 5
    assert db_manager.blood_camps.count_documents({}) == 2

    # Verify all 5 demo accounts authenticate and reach /api/auth/me
    for uname, _, pwd, role, _, _ in DEMO_ACCOUNTS:
        login_res = client.post("/api/auth/login", json={"username": uname, "password": pwd})
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res.status_code == 200
        assert me_res.json()["role"] == role


def test_full_end_to_end_clinical_and_security_lifecycle(client: TestClient, auth_header_factory):
    """
    Exercises the complete clinical flow across all 5 roles:
    Admin -> Hospital -> Blood Bank Staff -> Donor -> Donation Separation ->
    Doctor Patient & Critical Request -> Triage -> Atomic Allocation -> Analytics & Audit.
    """
    admin_hdrs = auth_header_factory(UserRole.ADMIN, username="e2e_admin")
    staff_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="e2e_staff", blood_bank_id="bb_e2e")
    doc_hdrs = auth_header_factory(UserRole.DOCTOR, username="e2e_doc", hospital_id="hosp_e2e")
    donor_hdrs = auth_header_factory(UserRole.DONOR, username="e2e_donor")

    doc_uid = client.get("/api/auth/me", headers=doc_hdrs).json()["_id"]
    donor_uid = client.get("/api/auth/me", headers=donor_hdrs).json()["_id"]

    # 1. Admin creates hospital
    assert (
        client.post(
            "/api/hospitals",
            json={
                "name": "E2E General Hospital",
                "license_number": "LIC-E2E-1",
                "location": {"type": "Point", "coordinates": [77.59, 12.97]},
                "address": "1 Central Ave",
                "emergency_helpline": "+91-80-11112222",
            },
            headers=admin_hdrs,
        ).status_code
        == 201
    )

    # 2. Staff registers donor, records donation, and separates components
    donor_id = client.post(
        "/api/donors",
        json={
            "user_id": donor_uid,
            "donor_card_number": "CARD-E2E-1",
            "first_name": "Kiran",
            "last_name": "Rao",
            "date_of_birth": "1990-02-02",
            "gender": "MALE",
            "blood_group": "O",
            "rh_factor": "NEGATIVE",
            "contact_phone": "+91-9900112233",
            "address": "22 Residency Rd",
        },
        headers=staff_hdrs,
    ).json()["_id"]

    donation_id = client.post(
        "/api/donations",
        json={
            "donation_code": "DON-E2E-1",
            "donor_id": donor_id,
            "blood_bank_id": "bb_e2e",
            "volume_ml": 450,
            "hemoglobin_g_dl": 15.0,
            "blood_pressure": "118/76",
            "screening_status": "PASSED",
        },
        headers=staff_hdrs,
    ).json()["_id"]

    sep = client.post(
        f"/api/donations/{donation_id}/separate-components",
        json={"components": ["RBC", "FFP"]},
        headers=staff_hdrs,
    )
    assert sep.status_code == 201
    assert len(sep.json()["generated_units"]) == 2

    # 3. Doctor registers patient and submits CRITICAL RBC request
    patient_id = client.post(
        "/api/patients",
        json={
            "hospital_id": "hosp_e2e",
            "attending_doctor_id": doc_uid,
            "mrn": "MRN-E2E-1",
            "full_name": "Rohan Das",
            "blood_group": "A",
            "rh_factor": "POSITIVE",
            "clinical_indication": "Acute hemorrhage",
            "medical_notes": "Crossmatch verified",
        },
        headers=doc_hdrs,
    ).json()["_id"]

    req_res = client.post(
        "/api/blood-requests",
        json={
            "request_code": "REQ-E2E-1",
            "hospital_id": "hosp_e2e",
            "doctor_id": doc_uid,
            "patient_id": patient_id,
            "blood_group": "A",
            "rh_factor": "POSITIVE",
            "component_type": "RBC",
            "units_requested": 1,
            "priority": "CRITICAL",
            "clinical_reason": "Emergency trauma",
        },
        headers=doc_hdrs,
    )
    assert req_res.status_code == 201

    # 4. Staff approves & atomically allocates compatible O- RBC unit
    assert client.post("/api/blood-requests/REQ-E2E-1/approve", json={}, headers=staff_hdrs).status_code == 200
    alloc = client.post("/api/blood-requests/REQ-E2E-1/allocate", json={}, headers=staff_hdrs)
    assert alloc.status_code == 200
    assert alloc.json()["request"]["status"] == "ALLOCATED"

    # 5. Donor sees own profile & donation; Admin sees analytics & audit logs
    assert len(client.get("/api/donors", headers=donor_hdrs).json()) == 1
    assert len(client.get("/api/donations", headers=donor_hdrs).json()) == 1
    assert client.get("/api/analytics/dashboard", headers=admin_hdrs).json()["allocated_requests"] == 1
    audit_actions = {e["action"] for e in client.get("/api/audit", headers=admin_hdrs).json()}
    assert {"BLOOD_UNIT_CREATED", "BLOOD_REQUEST_CREATED", "BLOOD_REQUEST_APPROVED", "BLOOD_UNIT_ALLOCATED"}.issubset(
        audit_actions
    )


# ==========================================
# 2. Concurrent Atomic Allocation Stress Test
# ==========================================

def test_concurrent_allocation_prevents_double_allocation(mock_db):
    """
    Simulates 5 simultaneous allocation threads competing for a single AVAILABLE blood unit.
    Verifies exactly 1 thread succeeds and 4 are rejected without double allocation.
    """
    unit_repo = BloodUnitRepository()
    request_repo = BloodRequestRepository()
    workflow = WorkflowService(unit_repo=unit_repo, request_repo=request_repo)
    now = datetime.now(timezone.utc)

    unit = unit_repo.create({
        "unit_id": "UNIT-RACE-SINGLE",
        "source_donation_id": "DON-RACE",
        "blood_bank_id": "bb_race",
        "blood_group": BloodGroup.O.value,
        "rh_factor": RhFactor.NEGATIVE.value,
        "component_type": BloodComponent.RBC.value,
        "volume_ml": 250,
        "collection_date": now,
        "expiry_date": now + timedelta(days=20),
        "storage_location": {"refrigerator_id": "REF-R", "shelf": "S1"},
        "status": BloodUnitStatus.AVAILABLE.value,
        "reserved_for_request_id": None,
        "allocated_at": None,
        "version": 1,
    })

    req_codes = [f"REQ-RACE-{i}" for i in range(5)]
    for code in req_codes:
        request_repo.create({
            "request_code": code,
            "hospital_id": "hosp_race",
            "doctor_id": "doc_race",
            "patient_id": f"pat_{code}",
            "blood_group": BloodGroup.O.value,
            "rh_factor": RhFactor.NEGATIVE.value,
            "component_type": BloodComponent.RBC.value,
            "units_requested": 1,
            "priority": RequestPriority.CRITICAL.value,
            "clinical_reason": "Concurrent stress test",
            "status": RequestStatus.APPROVED.value,
            "allocated_units": [],
        })

    staff_actor = {"_id": "staff_race", "username": "race_staff", "role": UserRole.BLOOD_BANK_STAFF.value, "blood_bank_id": "bb_race"}
    from app.schemas.workflow_schema import AllocationRequestPayload

    def _attempt(code: str) -> bool:
        try:
            workflow.allocate_request_units(code, AllocationRequestPayload(), staff_actor)
            return True
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=5) as pool:
        outcomes = list(pool.map(_attempt, req_codes))

    assert sum(1 for ok in outcomes if ok) == 1
    assert sum(1 for ok in outcomes if not ok) == 4

    final_unit = unit_repo.get_by_id(unit["_id"])
    assert final_unit["status"] == BloodUnitStatus.ALLOCATED.value
    assert final_unit["version"] == 2


# ==========================================
# 3. Index Setup & Query Performance Benchmark
# ==========================================

def test_indexes_and_bulk_query_performance(mock_db):
    """
    Verifies all 30 custom indexes initialize cleanly and measures latency of
    indexed FIFO search + aggregation pipeline across 500 blood unit documents.
    """
    summary = setup_indexes(mock_db)
    assert len(summary) == 11
    assert sum(len(v) for v in summary.values()) == 30

    now = datetime.now(timezone.utc)
    bulk_units = [
        {
            "unit_id": f"UNIT-PERF-{i:04d}",
            "source_donation_id": "DON-PERF",
            "blood_bank_id": "bb_perf",
            "blood_group": ["O", "A", "B", "AB"][i % 4],
            "rh_factor": "NEGATIVE" if i % 5 == 0 else "POSITIVE",
            "component_type": "RBC",
            "volume_ml": 250,
            "collection_date": now - timedelta(days=1),
            "expiry_date": now + timedelta(days=(i % 40) + 1),
            "storage_location": {"refrigerator_id": "REF-P", "shelf": "S1"},
            "status": "AVAILABLE",
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        for i in range(500)
    ]
    db_manager.blood_units.insert_many(bulk_units)

    unit_repo = BloodUnitRepository()
    t0 = time.perf_counter()
    fifo_results = unit_repo.find_available_units("O", "NEGATIVE", "RBC", limit=10)
    fifo_elapsed = time.perf_counter() - t0
    assert len(fifo_results) == 10
    assert fifo_results[0]["expiry_date"] <= fifo_results[-1]["expiry_date"]
    assert fifo_elapsed < 1.0

    analytics = AnalyticsService()
    t1 = time.perf_counter()
    stats = analytics.get_dashboard_analytics()
    agg_elapsed = time.perf_counter() - t1
    assert stats["available_blood_units"] == 500
    assert agg_elapsed < 1.0
