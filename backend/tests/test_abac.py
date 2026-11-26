"""
Phase 5 Automated Test Suite: Resource-Level Access Control (ABAC).
Tests ownership and facility-scope enforcement across Donors, Donations,
Patients, Blood Units, and Blood Requests, verifying HTTP 403 on cross-owner
and cross-tenant access attempts.
"""
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.models.enums import UserRole


def _get_user_id(client: TestClient, headers: dict) -> str:
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 200
    return res.json()["_id"]


# ==========================================
# 1. Donor & Donation Ownership Tests
# ==========================================

def test_donor_cannot_access_or_modify_other_donor_profile(client: TestClient, auth_header_factory):
    """Donor A can manage own profile, but gets HTTP 403 on Donor B's profile and clinical fields."""
    donor_a_hdrs = auth_header_factory(UserRole.DONOR, username="donor_alice")
    donor_b_hdrs = auth_header_factory(UserRole.DONOR, username="donor_bob")
    alice_uid = _get_user_id(client, donor_a_hdrs)
    bob_uid = _get_user_id(client, donor_b_hdrs)

    base_profile = {
        "date_of_birth": "1994-03-15",
        "gender": "FEMALE",
        "blood_group": "O",
        "rh_factor": "POSITIVE",
        "contact_phone": "+91-9000011111",
        "address": "10 Main St",
    }

    # Alice cannot register profile for Bob
    forged_res = client.post(
        "/api/donors",
        json={**base_profile, "user_id": bob_uid, "donor_card_number": "CARD-FORGE", "first_name": "Bob", "last_name": "B"},
        headers=donor_a_hdrs,
    )
    assert forged_res.status_code == 403

    # Alice & Bob create their own profiles
    alice_res = client.post(
        "/api/donors",
        json={**base_profile, "user_id": alice_uid, "donor_card_number": "CARD-ALICE", "first_name": "Alice", "last_name": "A"},
        headers=donor_a_hdrs,
    )
    assert alice_res.status_code == 201
    alice_donor_id = alice_res.json()["_id"]

    bob_res = client.post(
        "/api/donors",
        json={**base_profile, "user_id": bob_uid, "donor_card_number": "CARD-BOB", "first_name": "Bob", "last_name": "B"},
        headers=donor_b_hdrs,
    )
    assert bob_res.status_code == 201
    bob_donor_id = bob_res.json()["_id"]

    # Listing /api/donors as Alice returns only Alice
    list_res = client.get("/api/donors", headers=donor_a_hdrs)
    assert list_res.status_code == 200
    assert [d["_id"] for d in list_res.json()] == [alice_donor_id]

    # Alice can view & update own non-clinical fields
    assert client.get(f"/api/donors/{alice_donor_id}", headers=donor_a_hdrs).status_code == 200
    assert client.put(f"/api/donors/{alice_donor_id}", json={"address": "22 New Ave"}, headers=donor_a_hdrs).status_code == 200

    # Alice cannot alter clinical eligibility_status on own profile
    clinical_res = client.put(
        f"/api/donors/{alice_donor_id}",
        json={"eligibility_status": "ELIGIBLE"},
        headers=donor_a_hdrs,
    )
    assert clinical_res.status_code == 403

    # Alice cannot view or update Bob's profile
    assert client.get(f"/api/donors/{bob_donor_id}", headers=donor_a_hdrs).status_code == 403
    assert client.put(f"/api/donors/{bob_donor_id}", json={"address": "Hacked"}, headers=donor_a_hdrs).status_code == 403


def test_donor_can_only_view_own_donations(client: TestClient, auth_header_factory):
    """Donor sees only own donations and receives HTTP 403 when querying another donor's donations."""
    staff_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="bb_staff_don", blood_bank_id="bb_1")
    donor_a_hdrs = auth_header_factory(UserRole.DONOR, username="donor_one")
    donor_b_hdrs = auth_header_factory(UserRole.DONOR, username="donor_two")
    uid_a = _get_user_id(client, donor_a_hdrs)
    uid_b = _get_user_id(client, donor_b_hdrs)

    profile_base = {
        "date_of_birth": "1992-01-10",
        "gender": "MALE",
        "blood_group": "A",
        "rh_factor": "POSITIVE",
        "contact_phone": "+91-9000022222",
        "address": "12 Park Rd",
    }
    donor_a_id = client.post(
        "/api/donors",
        json={**profile_base, "user_id": uid_a, "donor_card_number": "CARD-D1", "first_name": "One", "last_name": "D"},
        headers=donor_a_hdrs,
    ).json()["_id"]
    donor_b_id = client.post(
        "/api/donors",
        json={**profile_base, "user_id": uid_b, "donor_card_number": "CARD-D2", "first_name": "Two", "last_name": "D"},
        headers=donor_b_hdrs,
    ).json()["_id"]

    don_a = client.post(
        "/api/donations",
        json={
            "donation_code": "DON-OWN-A",
            "donor_id": donor_a_id,
            "blood_bank_id": "bb_1",
            "volume_ml": 450,
            "hemoglobin_g_dl": 14.2,
            "blood_pressure": "120/80",
        },
        headers=staff_hdrs,
    ).json()
    don_b = client.post(
        "/api/donations",
        json={
            "donation_code": "DON-OWN-B",
            "donor_id": donor_b_id,
            "blood_bank_id": "bb_1",
            "volume_ml": 450,
            "hemoglobin_g_dl": 14.5,
            "blood_pressure": "118/76",
        },
        headers=staff_hdrs,
    ).json()

    # Donor A lists donations -> sees only DON-OWN-A
    list_a = client.get("/api/donations", headers=donor_a_hdrs)
    assert list_a.status_code == 200
    assert [d["_id"] for d in list_a.json()] == [don_a["_id"]]

    # Donor A can fetch own donation, gets 403 for Donor B's donation or filter
    assert client.get(f"/api/donations/{don_a['_id']}", headers=donor_a_hdrs).status_code == 200
    assert client.get(f"/api/donations/{don_b['_id']}", headers=donor_a_hdrs).status_code == 403
    assert client.get(f"/api/donations?donor_id={donor_b_id}", headers=donor_a_hdrs).status_code == 403


# ==========================================
# 2. Hospital & Doctor Ownership Tests
# ==========================================

def test_hospital_staff_scoped_to_own_hospital_requests(client: TestClient, auth_header_factory):
    """Hospital A cannot view, query, or create blood requests for Hospital B."""
    hosp_a_hdrs = auth_header_factory(UserRole.HOSPITAL_STAFF, username="staff_hosp_a", hospital_id="hosp_A")
    hosp_b_hdrs = auth_header_factory(UserRole.HOSPITAL_STAFF, username="staff_hosp_b", hospital_id="hosp_B")

    req_base = {
        "doctor_id": "doc_generic",
        "patient_id": "pat_generic",
        "blood_group": "B",
        "rh_factor": "POSITIVE",
        "component_type": "RBC",
        "units_requested": 2,
        "priority": "URGENT",
        "clinical_reason": "Pre-op standby",
    }

    # Hospital A cannot submit a request under Hospital B
    assert (
        client.post(
            "/api/blood-requests",
            json={**req_base, "request_code": "REQ-FORGE-B", "hospital_id": "hosp_B"},
            headers=hosp_a_hdrs,
        ).status_code
        == 403
    )

    req_a = client.post(
        "/api/blood-requests",
        json={**req_base, "request_code": "REQ-HOSP-A1", "hospital_id": "hosp_A"},
        headers=hosp_a_hdrs,
    ).json()
    req_b = client.post(
        "/api/blood-requests",
        json={**req_base, "request_code": "REQ-HOSP-B1", "hospital_id": "hosp_B"},
        headers=hosp_b_hdrs,
    ).json()

    # Hospital A list returns only Hospital A's requests
    list_a = client.get("/api/blood-requests", headers=hosp_a_hdrs)
    assert list_a.status_code == 200
    assert [r["request_code"] for r in list_a.json()] == ["REQ-HOSP-A1"]

    # Hospital A cannot query ?hospital_id=hosp_B or fetch req_b directly
    assert client.get("/api/blood-requests?hospital_id=hosp_B", headers=hosp_a_hdrs).status_code == 403
    assert client.get(f"/api/blood-requests/{req_b['_id']}", headers=hosp_a_hdrs).status_code == 403
    assert client.get(f"/api/blood-requests/{req_a['_id']}", headers=hosp_a_hdrs).status_code == 200


def test_doctor_and_hospital_patient_access_restrictions(client: TestClient, auth_header_factory):
    """
    Doctor 1 can only access own patients and create requests for own patients;
    Hospital A staff sees Hospital A patients only and cannot access Hospital B patients.
    """
    doc1_hdrs = auth_header_factory(UserRole.DOCTOR, username="doc_one", hospital_id="hosp_A")
    doc2_hdrs = auth_header_factory(UserRole.DOCTOR, username="doc_two", hospital_id="hosp_A")
    hosp_a_hdrs = auth_header_factory(UserRole.HOSPITAL_STAFF, username="hosp_a_mgr", hospital_id="hosp_A")
    hosp_b_hdrs = auth_header_factory(UserRole.HOSPITAL_STAFF, username="hosp_b_mgr", hospital_id="hosp_B")

    doc1_uid = _get_user_id(client, doc1_hdrs)
    doc2_uid = _get_user_id(client, doc2_hdrs)

    # Doc 1 cannot register a patient assigned to Doc 2
    assert (
        client.post(
            "/api/patients",
            json={
                "hospital_id": "hosp_A",
                "attending_doctor_id": doc2_uid,
                "mrn": "MRN-FORGE",
                "full_name": "Forged Patient",
                "blood_group": "A",
                "rh_factor": "POSITIVE",
                "clinical_indication": "Anemia",
            },
            headers=doc1_hdrs,
        ).status_code
        == 403
    )

    p1 = client.post(
        "/api/patients",
        json={
            "hospital_id": "hosp_A",
            "attending_doctor_id": doc1_uid,
            "mrn": "MRN-A-101",
            "full_name": "Patient One",
            "blood_group": "A",
            "rh_factor": "POSITIVE",
            "clinical_indication": "Surgery",
        },
        headers=doc1_hdrs,
    ).json()

    p2 = client.post(
        "/api/patients",
        json={
            "hospital_id": "hosp_A",
            "attending_doctor_id": doc2_uid,
            "mrn": "MRN-A-102",
            "full_name": "Patient Two",
            "blood_group": "O",
            "rh_factor": "NEGATIVE",
            "clinical_indication": "Trauma",
        },
        headers=doc2_hdrs,
    ).json()

    p_other_hosp = client.post(
        "/api/patients",
        json={
            "hospital_id": "hosp_B",
            "attending_doctor_id": "doc_b1",
            "mrn": "MRN-B-201",
            "full_name": "Hospital B Patient",
            "blood_group": "AB",
            "rh_factor": "POSITIVE",
            "clinical_indication": "Oncology",
        },
        headers=hosp_b_hdrs,
    ).json()

    # Doc 1 sees only p1, gets 403 on p2 and p_other_hosp
    doc1_list = client.get("/api/patients", headers=doc1_hdrs)
    assert doc1_list.status_code == 200
    assert [p["_id"] for p in doc1_list.json()] == [p1["_id"]]
    assert client.get(f"/api/patients/{p2['_id']}", headers=doc1_hdrs).status_code == 403
    assert client.put(f"/api/patients/{p2['_id']}", json={"clinical_indication": "Tampered"}, headers=doc1_hdrs).status_code == 403

    # Doc 1 cannot submit a blood request for Doc 2's patient
    assert (
        client.post(
            "/api/blood-requests",
            json={
                "request_code": "REQ-DOC-CROSS",
                "hospital_id": "hosp_A",
                "doctor_id": doc1_uid,
                "patient_id": p2["_id"],
                "blood_group": "O",
                "rh_factor": "NEGATIVE",
                "component_type": "RBC",
                "units_requested": 1,
                "priority": "URGENT",
                "clinical_reason": "Cross-patient attempt",
            },
            headers=doc1_hdrs,
        ).status_code
        == 403
    )

    # Hospital A staff sees both p1 & p2, but gets 403 on Hospital B patient
    hosp_a_patients = client.get("/api/patients", headers=hosp_a_hdrs)
    assert hosp_a_patients.status_code == 200
    assert {p["_id"] for p in hosp_a_patients.json()} == {p1["_id"], p2["_id"]}
    assert client.get(f"/api/patients/{p_other_hosp['_id']}", headers=hosp_a_hdrs).status_code == 403


# ==========================================
# 3. Blood Bank Staff Scope & Inventory Visibility
# ==========================================

def test_blood_bank_staff_scoped_to_assigned_blood_bank(client: TestClient, auth_header_factory):
    """Blood bank staff can only create/view/update units and donations within their assigned blood_bank_id."""
    bb_north = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="staff_north", blood_bank_id="bb_north")
    bb_south = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="staff_south", blood_bank_id="bb_south")
    doc_hdrs = auth_header_factory(UserRole.DOCTOR, username="doc_inv", hospital_id="hosp_A")

    expiry_dt = (datetime.now(timezone.utc) + timedelta(days=35)).isoformat()
    unit_template = {
        "source_donation_id": "DON-SCOPE-1",
        "blood_group": "O",
        "rh_factor": "NEGATIVE",
        "component_type": "RBC",
        "volume_ml": 250,
        "expiry_date": expiry_dt,
        "storage_location": {"refrigerator_id": "REF-1", "shelf": "S1"},
    }

    # bb_north cannot add unit to bb_south
    assert (
        client.post(
            "/api/blood-units",
            json={**unit_template, "unit_id": "UNIT-FORGE-S", "blood_bank_id": "bb_south"},
            headers=bb_north,
        ).status_code
        == 403
    )

    u_north = client.post(
        "/api/blood-units",
        json={**unit_template, "unit_id": "UNIT-NORTH-1", "blood_bank_id": "bb_north"},
        headers=bb_north,
    ).json()
    u_south = client.post(
        "/api/blood-units",
        json={**unit_template, "unit_id": "UNIT-SOUTH-1", "blood_bank_id": "bb_south", "status": "DISCARDED"},
        headers=bb_south,
    ).json()

    # bb_north sees only UNIT-NORTH-1 and gets 403 accessing or updating UNIT-SOUTH-1
    north_list = client.get("/api/blood-units", headers=bb_north)
    assert north_list.status_code == 200
    assert [u["unit_id"] for u in north_list.json()] == ["UNIT-NORTH-1"]
    assert client.get("/api/blood-units?blood_bank_id=bb_south", headers=bb_north).status_code == 403
    assert client.get(f"/api/blood-units/{u_south['_id']}", headers=bb_north).status_code == 403
    assert client.put(f"/api/blood-units/{u_south['_id']}", json={"status": "AVAILABLE"}, headers=bb_north).status_code == 403

    # Doctor viewing permitted inventory only sees AVAILABLE units and gets 403 on DISCARDED units
    doc_list = client.get("/api/blood-units", headers=doc_hdrs)
    assert doc_list.status_code == 200
    assert [u["unit_id"] for u in doc_list.json()] == ["UNIT-NORTH-1"]
    assert client.get("/api/blood-units?status=DISCARDED", headers=doc_hdrs).status_code == 403
    assert client.get(f"/api/blood-units/{u_south['_id']}", headers=doc_hdrs).status_code == 403
    assert client.get(f"/api/blood-units/{u_north['_id']}", headers=doc_hdrs).status_code == 200
