"""
Phase 8 Automated Test Suite: Core Blood Bank Workflows & Atomic Allocation.
Tests academic ABO/Rh compatibility, donation component separation,
request triage & approval/rejection, FIFO atomic allocation without duplicates,
expiry/low-stock scanning, and user-scoped notifications.
"""
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.config.database import db_manager
from app.models.enums import BloodComponent, BloodGroup, RhFactor, UserRole
from app.services.compatibility import (
    ACADEMIC_DISCLAIMER,
    get_compatible_donor_types,
    is_unit_compatible,
)


def _get_user_id(client: TestClient, headers: dict) -> str:
    return client.get("/api/auth/me", headers=headers).json()["_id"]


# ==========================================
# 1. Academic Compatibility Rules Unit Tests
# ==========================================

def test_academic_blood_compatibility_rules():
    """Verify RBC and FFP academic ABO/Rh compatibility order and component matching."""
    # Exact match always comes first
    rbc_a_pos = get_compatible_donor_types(BloodGroup.A.value, RhFactor.POSITIVE.value, BloodComponent.RBC.value)
    assert rbc_a_pos[0] == (BloodGroup.A.value, RhFactor.POSITIVE.value)
    assert (BloodGroup.O.value, RhFactor.NEGATIVE.value) in rbc_a_pos
    assert (BloodGroup.B.value, RhFactor.POSITIVE.value) not in rbc_a_pos

    # O- recipient can only receive O- RBC
    rbc_o_neg = get_compatible_donor_types(BloodGroup.O.value, RhFactor.NEGATIVE.value, BloodComponent.RBC.value)
    assert rbc_o_neg == [(BloodGroup.O.value, RhFactor.NEGATIVE.value)]

    # Reverse ABO for FFP (AB plasma is universal for FFP)
    assert is_unit_compatible("AB", "POSITIVE", "FFP", "O", "NEGATIVE", "FFP") is True
    assert is_unit_compatible("O", "NEGATIVE", "RBC", "A", "POSITIVE", "FFP") is False


# ==========================================
# 2. Donation & Component Separation Workflow
# ==========================================

def test_donation_recording_and_component_separation(client: TestClient, auth_header_factory):
    """Verify donation updates donor dates and separates into individual BloodUnit documents."""
    staff_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="wf_bb_staff", blood_bank_id="bb_wf")
    donor_hdrs = auth_header_factory(UserRole.DONOR, username="wf_donor")
    donor_uid = _get_user_id(client, donor_hdrs)

    donor_res = client.post(
        "/api/donors",
        json={
            "user_id": donor_uid,
            "donor_card_number": "CARD-WF-001",
            "first_name": "Maya",
            "last_name": "Lin",
            "date_of_birth": "1995-04-10",
            "gender": "FEMALE",
            "blood_group": "O",
            "rh_factor": "NEGATIVE",
            "contact_phone": "+91-9811122233",
            "address": "15 Indiranagar",
        },
        headers=staff_hdrs,
    )
    assert donor_res.status_code == 201
    donor_id = donor_res.json()["_id"]

    # Record PASSED donation
    don_res = client.post(
        "/api/donations",
        json={
            "donation_code": "DON-WF-100",
            "donor_id": donor_id,
            "blood_bank_id": "bb_wf",
            "volume_ml": 450,
            "hemoglobin_g_dl": 13.8,
            "blood_pressure": "120/80",
            "screening_status": "PASSED",
        },
        headers=staff_hdrs,
    )
    assert don_res.status_code == 201
    donation_id = don_res.json()["_id"]

    # Donor eligibility dates updated (+56 days)
    updated_donor = client.get(f"/api/donors/{donor_id}", headers=staff_hdrs).json()
    assert updated_donor["last_donation_date"] is not None
    assert updated_donor["next_eligible_date"] is not None

    # Separate into RBC, FFP, PLATELETS
    sep_res = client.post(
        f"/api/donations/{donation_id}/separate-components",
        json={
            "components": ["RBC", "FFP", "PLATELETS"],
            "storage_location": {"refrigerator_id": "REF-WF-1", "shelf": "S2", "slot": "B4"},
        },
        headers=staff_hdrs,
    )
    assert sep_res.status_code == 201
    sep_data = sep_res.json()
    assert sep_data["components_separated"] is True
    assert len(sep_data["generated_units"]) == 3
    assert {u["component_type"] for u in sep_data["generated_units"]} == {"RBC", "FFP", "PLATELETS"}
    assert all(u["blood_group"] == "O" and u["rh_factor"] == "NEGATIVE" for u in sep_data["generated_units"])

    # Duplicate separation blocked with 409
    dup_sep = client.post(
        f"/api/donations/{donation_id}/separate-components",
        json={"components": ["RBC"]},
        headers=staff_hdrs,
    )
    assert dup_sep.status_code == 409


# ==========================================
# 3. Triage, Approval, Rejection & Emergency Alerts
# ==========================================

def test_request_triage_approval_rejection_and_notifications(client: TestClient, auth_header_factory):
    """Verify CRITICAL alerts, triage ordering, approval/rejection transitions, and notifications."""
    staff_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="triage_staff", blood_bank_id="bb_triage")
    hosp_hdrs = auth_header_factory(UserRole.HOSPITAL_STAFF, username="triage_hosp", hospital_id="hosp_triage")
    doc_hdrs = auth_header_factory(UserRole.DOCTOR, username="triage_doc", hospital_id="hosp_triage")
    doc_uid = _get_user_id(client, doc_hdrs)

    # Submit ROUTINE then CRITICAL request
    r_routine = client.post(
        "/api/blood-requests",
        json={
            "request_code": "REQ-TR-ROUTINE",
            "hospital_id": "hosp_triage",
            "doctor_id": doc_uid,
            "patient_id": "pat_tr_1",
            "blood_group": "A",
            "rh_factor": "POSITIVE",
            "component_type": "RBC",
            "units_requested": 1,
            "priority": "ROUTINE",
            "clinical_reason": "Elective anemia support",
        },
        headers=doc_hdrs,
    )
    assert r_routine.status_code == 201

    r_crit = client.post(
        "/api/blood-requests",
        json={
            "request_code": "REQ-TR-CRIT",
            "hospital_id": "hosp_triage",
            "doctor_id": doc_uid,
            "patient_id": "pat_tr_2",
            "blood_group": "O",
            "rh_factor": "NEGATIVE",
            "component_type": "RBC",
            "units_requested": 2,
            "priority": "CRITICAL",
            "clinical_reason": "Massive trauma",
        },
        headers=doc_hdrs,
    )
    assert r_crit.status_code == 201

    # Emergency notification dispatched to blood bank staff
    staff_notifs = client.get("/api/notifications?is_read=false", headers=staff_hdrs).json()
    assert any(n["notification_type"] == "EMERGENCY_REQUEST" for n in staff_notifs)

    # Triage queue places CRITICAL before ROUTINE
    triage_list = client.get("/api/blood-requests/triage", headers=staff_hdrs).json()
    codes = [r["request_code"] for r in triage_list]
    assert codes.index("REQ-TR-CRIT") < codes.index("REQ-TR-ROUTINE")

    # Approve critical request & reject routine request
    app_res = client.post(
        "/api/blood-requests/REQ-TR-CRIT/approve",
        json={"reason": "Confirmed emergency priority"},
        headers=staff_hdrs,
    )
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "APPROVED"

    rej_res = client.post(
        "/api/blood-requests/REQ-TR-ROUTINE/reject",
        json={"reason": "Deferred pending hemoglobin recheck"},
        headers=staff_hdrs,
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "REJECTED"

    # Re-approving a rejected request returns 409
    assert client.post("/api/blood-requests/REQ-TR-ROUTINE/approve", json={}, headers=staff_hdrs).status_code == 409

    # Doctor and hospital staff received REQUEST_STATUS notifications; donor cannot mark them read (403)
    doc_notifs = client.get("/api/notifications", headers=doc_hdrs).json()
    assert len(doc_notifs) >= 2
    assert any(n["notification_type"] == "REQUEST_STATUS" for n in doc_notifs)

    notif_id = doc_notifs[0]["_id"]
    assert client.patch(f"/api/notifications/{notif_id}/read", headers=hosp_hdrs).status_code == 403
    mark_res = client.patch(f"/api/notifications/{notif_id}/read", headers=doc_hdrs)
    assert mark_res.status_code == 200
    assert mark_res.json()["is_read"] is True


# ==========================================
# 4. Atomic FIFO Compatible Allocation & No Duplicate Allocation
# ==========================================

def test_atomic_fifo_compatible_allocation_and_no_duplicates(client: TestClient, auth_header_factory):
    """
    Verify FIFO earliest-expiry selection, ignoring expired units, compatible O- substitution
    for A+ request, partial allocation, and rejection of duplicate allocation.
    """
    staff_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="alloc_staff", blood_bank_id="bb_alloc")
    hosp_hdrs = auth_header_factory(UserRole.HOSPITAL_STAFF, username="alloc_hosp", hospital_id="hosp_alloc")
    now = datetime.now(timezone.utc)

    # Seed: 1 expired A+ unit (ignored), 1 later-expiring O- unit, 1 earlier-expiring O- unit
    units = [
        ("UNIT-EXPIRED", "A", "POSITIVE", now - timedelta(days=1)),
        ("UNIT-LATE-O-NEG", "O", "NEGATIVE", now + timedelta(days=25)),
        ("UNIT-EARLY-O-NEG", "O", "NEGATIVE", now + timedelta(days=5)),
    ]
    for uid, grp, rh, exp in units:
        res = client.post(
            "/api/blood-units",
            json={
                "unit_id": uid,
                "source_donation_id": "DON-ALLOC-1",
                "blood_bank_id": "bb_alloc",
                "blood_group": grp,
                "rh_factor": rh,
                "component_type": "RBC",
                "volume_ml": 250,
                "expiry_date": exp.isoformat(),
                "storage_location": {"refrigerator_id": "REF-1", "shelf": "S1"},
            },
            headers=staff_hdrs,
        )
        assert res.status_code == 201

    # Request 1 asks for 1 A+ RBC -> gets earliest O- unit (compatible substitute)
    req1 = client.post(
        "/api/blood-requests",
        json={
            "request_code": "REQ-AL-1",
            "hospital_id": "hosp_alloc",
            "doctor_id": "doc_al",
            "patient_id": "pat_al_1",
            "blood_group": "A",
            "rh_factor": "POSITIVE",
            "component_type": "RBC",
            "units_requested": 1,
            "priority": "URGENT",
            "clinical_reason": "GI bleed",
        },
        headers=hosp_hdrs,
    )
    assert req1.status_code == 201

    alloc1 = client.post("/api/blood-requests/REQ-AL-1/allocate", json={}, headers=staff_hdrs)
    assert alloc1.status_code == 200
    body1 = alloc1.json()
    assert body1["newly_allocated_count"] == 1
    assert body1["remaining_units_needed"] == 0
    assert body1["request"]["status"] == "ALLOCATED"
    assert body1["allocated_units"][0]["unit_id"] == "UNIT-EARLY-O-NEG"
    assert body1["compatibility_disclaimer"] == ACADEMIC_DISCLAIMER

    # Request 2 asks for 2 O- RBC -> only UNIT-LATE-O-NEG remains -> PARTIALLY_ALLOCATED (1 of 2)
    req2 = client.post(
        "/api/blood-requests",
        json={
            "request_code": "REQ-AL-2",
            "hospital_id": "hosp_alloc",
            "doctor_id": "doc_al",
            "patient_id": "pat_al_2",
            "blood_group": "O",
            "rh_factor": "NEGATIVE",
            "component_type": "RBC",
            "units_requested": 2,
            "priority": "CRITICAL",
            "clinical_reason": "Emergency surgery",
        },
        headers=hosp_hdrs,
    )
    assert req2.status_code == 201

    alloc2 = client.post("/api/blood-requests/REQ-AL-2/allocate", json={}, headers=staff_hdrs)
    assert alloc2.status_code == 200
    body2 = alloc2.json()
    assert body2["newly_allocated_count"] == 1
    assert body2["remaining_units_needed"] == 1
    assert body2["request"]["status"] == "PARTIALLY_ALLOCATED"
    assert body2["allocated_units"][0]["unit_id"] == "UNIT-LATE-O-NEG"

    # Request 3 asks for O- RBC when none left (expired unit excluded, previous units already allocated) -> 409
    client.post(
        "/api/blood-requests",
        json={
            "request_code": "REQ-AL-3",
            "hospital_id": "hosp_alloc",
            "doctor_id": "doc_al",
            "patient_id": "pat_al_3",
            "blood_group": "O",
            "rh_factor": "NEGATIVE",
            "component_type": "RBC",
            "units_requested": 1,
            "priority": "ROUTINE",
            "clinical_reason": "Elective",
        },
        headers=hosp_hdrs,
    )
    alloc3 = client.post("/api/blood-requests/REQ-AL-3/allocate", json={}, headers=staff_hdrs)
    assert alloc3.status_code == 409


# ==========================================
# 5. Expiry & Low Inventory Alert Scan
# ==========================================

def test_expiry_and_low_stock_alert_scan(client: TestClient, auth_header_factory):
    """Verify scan-alerts marks past-expiry units EXPIRED and dispatches EXPIRY_ALERT & INVENTORY_ALERT."""
    staff_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="scan_staff", blood_bank_id="bb_scan")
    now = datetime.now(timezone.utc)

    # Create 1 already-expired unit and 1 unit expiring in 3 days
    for uid, exp in [
        ("UNIT-SCAN-EXP", now - timedelta(hours=2)),
        ("UNIT-SCAN-SOON", now + timedelta(days=3)),
    ]:
        client.post(
            "/api/blood-units",
            json={
                "unit_id": uid,
                "source_donation_id": "DON-SCAN",
                "blood_bank_id": "bb_scan",
                "blood_group": "B",
                "rh_factor": "POSITIVE",
                "component_type": "RBC",
                "volume_ml": 250,
                "expiry_date": exp.isoformat(),
                "storage_location": {"refrigerator_id": "REF-S", "shelf": "S1"},
            },
            headers=staff_hdrs,
        )

    scan_res = client.post(
        "/api/notifications/scan-alerts",
        json={"expiry_days_threshold": 7, "min_units_threshold": 2},
        headers=staff_hdrs,
    )
    assert scan_res.status_code == 200
    scan_data = scan_res.json()
    assert scan_data["expired_units_marked"] == 1
    assert scan_data["expiring_soon_count"] == 1
    assert len(scan_data["low_stock_groups"]) == 8
    assert scan_data["notifications_dispatched"] >= 2

    # Verify DB transitioned UNIT-SCAN-EXP to EXPIRED
    raw_exp = db_manager.blood_units.find_one({"unit_id": "UNIT-SCAN-EXP"})
    assert raw_exp["status"] == "EXPIRED"

    # Verify notifications readable & mark-all-read works
    notifs = client.get("/api/notifications", headers=staff_hdrs).json()
    types = {n["notification_type"] for n in notifs}
    assert {"EXPIRY_ALERT", "INVENTORY_ALERT"}.issubset(types)

    read_all = client.post("/api/notifications/read-all", headers=staff_hdrs)
    assert read_all.status_code == 200
    assert read_all.json()["marked_read"] >= 2
