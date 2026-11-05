"""
Repository-Level Unit Tests for Phase 2 Core Database Implementation.
Tests CRUD operations, unique constraints, atomic conditional updates, and queries
across Users, Donors, Hospitals, Patients, Donations, Blood Units, and Blood Requests.
"""
from datetime import datetime, timezone, timedelta
import pytest

from app.models.enums import (
    UserRole,
    BloodGroup,
    RhFactor,
    BloodComponent,
    DonorEligibility,
    BloodUnitStatus,
    RequestPriority,
    RequestStatus,
    HospitalVerificationStatus,
    Gender,
)
from app.repositories.user_repository import UserRepository
from app.repositories.donor_repository import DonorRepository
from app.repositories.hospital_repository import HospitalRepository
from app.repositories.patient_repository import PatientRepository
from app.repositories.donation_repository import DonationRepository
from app.repositories.blood_unit_repository import BloodUnitRepository
from app.repositories.blood_request_repository import BloodRequestRepository


def test_user_repository_crud(mock_db):
    """Test User creation, retrieval, failed-login tracking, and update."""
    repo = UserRepository()
    user_data = {
        "username": "dr_smith",
        "email_hash": "hash_dr_smith@hospital.org",
        "password_hash": "$argon2id$mocked_hash",
        "role": UserRole.DOCTOR.value,
        "is_active": True,
        "failed_login_attempts": 0,
        "lockout_until": None,
    }
    created = repo.create(user_data)
    assert created["_id"] is not None
    user_id = created["_id"]

    # Retrieve by username
    found = repo.get_by_username("dr_smith")
    assert found is not None
    assert found["_id"] == user_id
    assert found["role"] == UserRole.DOCTOR.value

    # Increment failed attempts
    updated_failed = repo.increment_failed_attempts(user_id, max_attempts=3)
    assert updated_failed["failed_login_attempts"] == 1

    # Reset failed attempts
    reset_user = repo.reset_failed_attempts(user_id)
    assert reset_user["failed_login_attempts"] == 0

    # Update role
    updated_role = repo.update(user_id, {"role": UserRole.ADMIN.value})
    assert updated_role["role"] == UserRole.ADMIN.value


def test_donor_repository_crud(mock_db):
    """Test Donor creation, card lookup, eligibility search, and dates update."""
    repo = DonorRepository()
    donor_data = {
        "user_id": "usr_9901",
        "donor_card_number": "DNR-2026-001",
        "first_name": "Alice",
        "last_name": "Walker",
        "date_of_birth": "1995-04-12",
        "gender": Gender.FEMALE.value,
        "blood_group": BloodGroup.O.value,
        "rh_factor": RhFactor.NEGATIVE.value,
        "contact_phone_encrypted": "enc_phone",
        "address_encrypted": "enc_address",
        "eligibility_status": DonorEligibility.ELIGIBLE.value,
    }
    created = repo.create(donor_data)
    assert created["_id"] is not None
    donor_id = created["_id"]

    # Card lookup
    found = repo.get_by_card_number("DNR-2026-001")
    assert found is not None
    assert found["first_name"] == "Alice"

    # Eligible query
    eligible_o_neg = repo.find_eligible_by_blood_group("O", "NEGATIVE")
    assert len(eligible_o_neg) == 1
    assert eligible_o_neg[0]["donor_card_number"] == "DNR-2026-001"

    # Update donation dates
    now = datetime.now(timezone.utc)
    next_date = now + timedelta(days=90)
    updated = repo.update_donation_dates(donor_id, now, next_date)
    assert updated["last_donation_date"] is not None
    assert updated["next_eligible_date"] is not None


def test_hospital_repository_crud(mock_db):
    """Test Hospital registration and license retrieval."""
    repo = HospitalRepository()
    hosp_data = {
        "name": "Apollo Central Hospital",
        "license_number": "LIC-BLR-2026-99",
        "location": {"type": "Point", "coordinates": [77.5946, 12.9716]},
        "address_encrypted": "enc_address",
        "emergency_helpline_encrypted": "enc_helpline",
        "verification_status": HospitalVerificationStatus.VERIFIED.value,
    }
    created = repo.create(hosp_data)
    assert created["_id"] is not None

    found = repo.get_by_license("LIC-BLR-2026-99")
    assert found is not None
    assert found["name"] == "Apollo Central Hospital"


def test_patient_repository_crud(mock_db):
    """Test Patient creation and retrieval by MRN."""
    repo = PatientRepository()
    patient_data = {
        "hospital_id": "hosp_100",
        "attending_doctor_id": "doc_200",
        "mrn": "MRN-55441",
        "full_name": "Robert Vance",
        "blood_group": BloodGroup.A.value,
        "rh_factor": RhFactor.POSITIVE.value,
        "clinical_indication": "Cardiothoracic bypass",
        "medical_notes_encrypted": "enc_notes",
    }
    created = repo.create(patient_data)
    assert created["_id"] is not None

    found = repo.get_by_hospital_mrn("hosp_100", "MRN-55441")
    assert found is not None
    assert found["full_name"] == "Robert Vance"

    by_doc = repo.find_by_doctor("doc_200")
    assert len(by_doc) == 1


def test_donation_repository_crud(mock_db):
    """Test Donation intake recording and query by donor."""
    repo = DonationRepository()
    donation_data = {
        "donation_code": "DON-2026-881",
        "donor_id": "donor_001",
        "blood_bank_id": "bb_central",
        "donation_date": datetime.now(timezone.utc),
        "volume_ml": 450,
        "donation_type": BloodComponent.WHOLE_BLOOD.value,
        "hemoglobin_g_dl": 14.5,
        "blood_pressure": "120/80",
        "screening_status": "PASSED",
        "components_separated": False,
    }
    created = repo.create(donation_data)
    assert created["_id"] is not None

    found = repo.get_by_code("DON-2026-881")
    assert found is not None
    assert found["volume_ml"] == 450

    donor_donations = repo.find_by_donor("donor_001")
    assert len(donor_donations) == 1


def test_blood_unit_atomic_allocation(mock_db):
    """
    Test BloodUnit creation and atomic conditional allocation.
    Verifies that AVAILABLE units can be allocated, and already ALLOCATED units cannot be re-allocated.
    """
    repo = BloodUnitRepository()
    unit_data = {
        "unit_id": "UNIT-O-NEG-001",
        "source_donation_id": "DON-2026-881",
        "blood_bank_id": "bb_central",
        "blood_group": BloodGroup.O.value,
        "rh_factor": RhFactor.NEGATIVE.value,
        "component_type": BloodComponent.RBC.value,
        "volume_ml": 250,
        "collection_date": datetime.now(timezone.utc),
        "expiry_date": datetime.now(timezone.utc) + timedelta(days=35),
        "storage_location": {"refrigerator_id": "FRIDGE-1", "shelf": "S2", "slot": "A4"},
        "status": BloodUnitStatus.AVAILABLE.value,
        "version": 1,
    }
    created = repo.create(unit_data)
    assert created["_id"] is not None

    # Find available units
    available = repo.find_available_units("O", "NEGATIVE", "RBC")
    assert len(available) == 1
    assert available[0]["unit_id"] == "UNIT-O-NEG-001"

    # First allocation should succeed
    alloc_result_1 = repo.allocate_unit_atomic("UNIT-O-NEG-001", request_id="REQ-9901")
    assert alloc_result_1 is not None
    assert alloc_result_1["status"] == "ALLOCATED"
    assert alloc_result_1["reserved_for_request_id"] == "REQ-9901"
    assert alloc_result_1["version"] == 2

    # Second concurrent attempt to allocate the SAME unit must FAIL (returns None)
    alloc_result_2 = repo.allocate_unit_atomic("UNIT-O-NEG-001", request_id="REQ-9902")
    assert alloc_result_2 is None

    # Available count should now be 0
    available_now = repo.find_available_units("O", "NEGATIVE", "RBC")
    assert len(available_now) == 0


def test_blood_request_triage_queue(mock_db):
    """Test BloodRequest submission, priority sorting (CRITICAL first), and unit attachment."""
    repo = BloodRequestRepository()

    # Create Routine request
    routine_req = {
        "request_code": "REQ-ROUTINE-1",
        "hospital_id": "hosp_1",
        "doctor_id": "doc_1",
        "patient_id": "pat_1",
        "blood_group": BloodGroup.B.value,
        "rh_factor": RhFactor.POSITIVE.value,
        "component_type": BloodComponent.RBC.value,
        "units_requested": 1,
        "priority": RequestPriority.ROUTINE.value,
        "clinical_reason": "Elective surgery",
        "status": RequestStatus.PENDING.value,
        "allocated_units": [],
    }
    repo.create(routine_req)

    # Create Critical emergency request
    critical_req = {
        "request_code": "REQ-CRITICAL-1",
        "hospital_id": "hosp_1",
        "doctor_id": "doc_2",
        "patient_id": "pat_2",
        "blood_group": BloodGroup.O.value,
        "rh_factor": RhFactor.NEGATIVE.value,
        "component_type": BloodComponent.RBC.value,
        "units_requested": 2,
        "priority": RequestPriority.CRITICAL.value,
        "clinical_reason": "Trauma acute hemorrhage",
        "status": RequestStatus.PENDING.value,
        "allocated_units": [],
    }
    repo.create(critical_req)

    # Check triage queue ordering
    triage = repo.find_pending_triage()
    assert len(triage) == 2
    # CRITICAL request must be at the head of the queue
    assert triage[0]["request_code"] == "REQ-CRITICAL-1"
    assert triage[0]["priority"] == "CRITICAL"

    # Attach allocated units
    attached = repo.attach_allocated_units(triage[0]["_id"], ["UNIT-O-NEG-001", "UNIT-O-NEG-002"])
    assert attached["status"] == "ALLOCATED"
    assert len(attached["allocated_units"]) == 2
