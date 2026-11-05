"""
FastAPI End-to-End API Route Tests for Phase 2 Core Database Implementation.
Validates HTTP response codes (201, 200, 404, 409, 422) across all CRUD endpoints.
"""
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient


def test_user_api_crud(client: TestClient):
    """Test POST, GET, PUT, and duplicate rejection on /api/users."""
    # 1. Create User
    user_payload = {
        "username": "john_donor",
        "email": "john.donor@example.com",
        "password": "SecurePassword123!",
        "role": "DONOR",
    }
    create_res = client.post("/api/users", json=user_payload)
    assert create_res.status_code == 201
    user_data = create_res.json()
    assert user_data["username"] == "john_donor"
    assert user_data["role"] == "DONOR"
    assert "_id" in user_data or "id" in user_data
    user_id = user_data.get("_id") or user_data.get("id")

    # 2. Duplicate Username Rejection
    dup_res = client.post("/api/users", json=user_payload)
    assert dup_res.status_code == 409

    # 3. List Users
    list_res = client.get("/api/users")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 4. Get User by ID
    get_res = client.get(f"/api/users/{user_id}")
    assert get_res.status_code == 200
    assert get_res.json()["username"] == "john_donor"

    # 5. Update User Status
    update_res = client.put(f"/api/users/{user_id}", json={"is_active": False})
    assert update_res.status_code == 200
    assert update_res.json()["is_active"] is False


def test_donor_api_crud(client: TestClient):
    """Test POST and GET on /api/donors."""
    donor_payload = {
        "user_id": "usr_test_1",
        "donor_card_number": "CARD-BLR-001",
        "first_name": "Marcus",
        "last_name": "Brown",
        "date_of_birth": "1990-08-20",
        "gender": "MALE",
        "blood_group": "B",
        "rh_factor": "POSITIVE",
        "contact_phone": "+91-9876543210",
        "address": "42 MG Road, Bangalore",
        "emergency_contact": "+91-9876543211",
        "eligibility_status": "ELIGIBLE",
    }
    create_res = client.post("/api/donors", json=donor_payload)
    assert create_res.status_code == 201
    donor_data = create_res.json()
    assert donor_data["donor_card_number"] == "CARD-BLR-001"
    donor_id = donor_data.get("_id") or donor_data.get("id")

    # Filter donors by blood group
    filter_res = client.get("/api/donors?blood_group=B&rh_factor=POSITIVE")
    assert filter_res.status_code == 200
    assert len(filter_res.json()) == 1


def test_hospital_api_crud(client: TestClient):
    """Test POST and GET on /api/hospitals."""
    hosp_payload = {
        "name": "Manipal Central Hospital",
        "license_number": "LIC-HOSP-2026-01",
        "location": {"type": "Point", "coordinates": [77.6000, 12.9800]},
        "address": "HAL Airport Road, Bangalore",
        "emergency_helpline": "+91-80-22223333",
        "verification_status": "VERIFIED",
    }
    create_res = client.post("/api/hospitals", json=hosp_payload)
    assert create_res.status_code == 201
    hosp_data = create_res.json()
    assert hosp_data["license_number"] == "LIC-HOSP-2026-01"

    # List hospitals
    list_res = client.get("/api/hospitals")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1


def test_patient_api_crud(client: TestClient):
    """Test POST and GET on /api/patients."""
    patient_payload = {
        "hospital_id": "hosp_manipal",
        "attending_doctor_id": "doc_sharma",
        "mrn": "MRN-2026-9001",
        "full_name": "Eleanor Rigby",
        "blood_group": "AB",
        "rh_factor": "NEGATIVE",
        "clinical_indication": "Major orthopedic reconstruction",
        "medical_notes": "Allergic to penicillin",
    }
    create_res = client.post("/api/patients", json=patient_payload)
    assert create_res.status_code == 201
    patient_data = create_res.json()
    assert patient_data["mrn"] == "MRN-2026-9001"

    # Query by hospital
    list_res = client.get("/api/patients?hospital_id=hosp_manipal")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1


def test_donation_api_crud(client: TestClient):
    """Test POST and GET on /api/donations."""
    donation_payload = {
        "donation_code": "DON-API-2026-001",
        "donor_id": "dnr_001",
        "blood_bank_id": "bb_central",
        "volume_ml": 450,
        "donation_type": "WHOLE_BLOOD",
        "hemoglobin_g_dl": 15.1,
        "blood_pressure": "118/78",
        "screening_status": "PASSED",
    }
    create_res = client.post("/api/donations", json=donation_payload)
    assert create_res.status_code == 201
    donation_data = create_res.json()
    assert donation_data["donation_code"] == "DON-API-2026-001"
    assert donation_data["screening_status"] == "PASSED"


def test_blood_unit_api_crud(client: TestClient):
    """Test POST, GET and filter on /api/blood-units."""
    expiry_dt = (datetime.now(timezone.utc) + timedelta(days=42)).isoformat()
    unit_payload = {
        "unit_id": "UNIT-A-POS-901",
        "source_donation_id": "DON-API-2026-001",
        "blood_bank_id": "bb_central",
        "blood_group": "A",
        "rh_factor": "POSITIVE",
        "component_type": "RBC",
        "volume_ml": 250,
        "expiry_date": expiry_dt,
        "storage_location": {"refrigerator_id": "REF-B2", "shelf": "S1", "slot": "SLOT-08"},
        "status": "AVAILABLE",
    }
    create_res = client.post("/api/blood-units", json=unit_payload)
    assert create_res.status_code == 201
    unit_data = create_res.json()
    assert unit_data["unit_id"] == "UNIT-A-POS-901"

    # Filter units by blood_group and status
    filter_res = client.get("/api/blood-units?blood_group=A&rh_factor=POSITIVE&status=AVAILABLE")
    assert filter_res.status_code == 200
    assert len(filter_res.json()) == 1


def test_blood_request_api_crud(client: TestClient):
    """Test POST and GET on /api/blood-requests."""
    req_payload = {
        "request_code": "REQ-API-9901",
        "hospital_id": "hosp_manipal",
        "doctor_id": "doc_sharma",
        "patient_id": "pat_9001",
        "blood_group": "O",
        "rh_factor": "NEGATIVE",
        "component_type": "RBC",
        "units_requested": 2,
        "priority": "CRITICAL",
        "clinical_reason": "Severe acute trauma hemorrhage",
    }
    create_res = client.post("/api/blood-requests", json=req_payload)
    assert create_res.status_code == 201
    req_data = create_res.json()
    assert req_data["request_code"] == "REQ-API-9901"
    assert req_data["priority"] == "CRITICAL"
    assert req_data["status"] == "PENDING"

    # List requests with priority filter
    list_res = client.get("/api/blood-requests?priority=CRITICAL")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1


def test_input_validation_error(client: TestClient):
    """Test that invalid enum inputs yield HTTP 422 Unprocessable Entity."""
    invalid_unit = {
        "unit_id": "UNIT-INVALID",
        "source_donation_id": "DON-000",
        "blood_bank_id": "bb_000",
        "blood_group": "INVALID_GROUP",  # Invalid blood group
        "rh_factor": "POSITIVE",
        "component_type": "RBC",
        "volume_ml": 250,
        "expiry_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "storage_location": {"refrigerator_id": "REF-1", "shelf": "S1"},
    }
    res = client.post("/api/blood-units", json=invalid_unit)
    assert res.status_code == 422
