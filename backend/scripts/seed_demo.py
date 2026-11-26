"""
Idempotent Academic Demo Data Seeder.
Populates all 11 MongoDB collections with sample users (across all 5 roles),
hospitals, donors, patients, donations, blood_units, blood_requests,
blood_camps, notifications, and audit_logs for interactive evaluation.
"""
import hashlib
import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config.database import db_manager
from app.config.settings import get_settings
from app.models.enums import (
    BloodComponent,
    BloodGroup,
    BloodUnitStatus,
    DonorEligibility,
    Gender,
    HospitalVerificationStatus,
    RequestPriority,
    RequestStatus,
    RhFactor,
    UserRole,
)
from app.repositories.blood_camp_repository import BloodCampRepository
from app.repositories.blood_request_repository import BloodRequestRepository
from app.repositories.blood_unit_repository import BloodUnitRepository
from app.repositories.donation_repository import DonationRepository
from app.repositories.donor_repository import DonorRepository
from app.repositories.hospital_repository import HospitalRepository
from app.repositories.patient_repository import PatientRepository
from app.repositories.user_repository import UserRepository
from app.schemas.notification_schema import NotificationType
from app.security.encryption import (
    DONOR_ENCRYPTED_FIELDS,
    HOSPITAL_ENCRYPTED_FIELDS,
    PATIENT_ENCRYPTED_FIELDS,
    USER_ENCRYPTED_FIELDS,
    encrypt_fields,
)
from app.security.hashing import hash_password
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.rbac_service import RBACService
from scripts.create_indexes import setup_indexes

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("secure_blood_bank.seed_demo")

DEMO_ACCOUNTS = [
    ("admin_demo", "admin@bloodbank.edu", "AdminDemo2026!", UserRole.ADMIN.value, None, None),
    ("staff_demo", "staff@bloodbank.edu", "StaffDemo2026!", UserRole.BLOOD_BANK_STAFF.value, None, "bb_central"),
    ("hospital_demo", "hospital@citymed.edu", "HospitalDemo2026!", UserRole.HOSPITAL_STAFF.value, "hosp_city_01", None),
    ("doctor_demo", "doctor@citymed.edu", "DoctorDemo2026!", UserRole.DOCTOR.value, "hosp_city_01", None),
    ("donor_demo", "donor@example.edu", "DonorDemo2026!", UserRole.DONOR.value, None, None),
]


def seed_demo_data() -> dict:
    """Seeds roles, demo accounts, and clinical/geospatial sample records idempotently."""
    RBACService().ensure_seeded()

    user_repo = UserRepository()
    hosp_repo = HospitalRepository()
    donor_repo = DonorRepository()
    patient_repo = PatientRepository()
    donation_repo = DonationRepository()
    unit_repo = BloodUnitRepository()
    request_repo = BloodRequestRepository()
    camp_repo = BloodCampRepository()
    notif_service = NotificationService(user_repo=user_repo, unit_repo=unit_repo)
    audit_service = AuditService()

    # 1. Users (all 5 roles)
    users_by_name = {}
    for uname, email, pwd, role, hosp_id, bb_id in DEMO_ACCOUNTS:
        existing = user_repo.get_by_username(uname)
        if not existing:
            email_hash = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
            doc = encrypt_fields(
                {
                    "username": uname,
                    "email_hash": email_hash,
                    "email": email,
                    "password_hash": hash_password(pwd),
                    "role": role,
                    "is_active": True,
                    "failed_login_attempts": 0,
                    "lockout_until": None,
                    "hospital_id": hosp_id,
                    "blood_bank_id": bb_id,
                },
                USER_ENCRYPTED_FIELDS,
                context="users",
            )
            existing = user_repo.create(doc)
        users_by_name[uname] = existing

    # 2. Hospital
    hospital = hosp_repo.get_by_license("LIC-DEMO-2026")
    if not hospital:
        hospital = hosp_repo.create(
            encrypt_fields(
                {
                    "name": "City Central Medical Hospital",
                    "license_number": "LIC-DEMO-2026",
                    "location": {"type": "Point", "coordinates": [77.5946, 12.9716]},
                    "address": "100 MG Road, Bengaluru",
                    "emergency_helpline": "+91-80-22224444",
                    "verification_status": HospitalVerificationStatus.VERIFIED.value,
                },
                HOSPITAL_ENCRYPTED_FIELDS,
                context="hospitals",
            )
        )

    # 3. Donor linked to donor_demo
    donor_uid = str(users_by_name["donor_demo"]["_id"])
    donor = donor_repo.get_by_user_id(donor_uid)
    if not donor:
        donor = donor_repo.create(
            encrypt_fields(
                {
                    "user_id": donor_uid,
                    "donor_card_number": "CARD-DEMO-001",
                    "first_name": "Aarav",
                    "last_name": "Mehta",
                    "date_of_birth": "1994-07-15",
                    "gender": Gender.MALE.value,
                    "blood_group": BloodGroup.O.value,
                    "rh_factor": RhFactor.NEGATIVE.value,
                    "contact_phone": "+91-9876501234",
                    "address": "42 Indiranagar 2nd Stage, Bengaluru",
                    "emergency_contact": "+91-9876509999",
                    "medical_screening_notes": "Cleared routine health screening",
                    "eligibility_status": DonorEligibility.ELIGIBLE.value,
                },
                DONOR_ENCRYPTED_FIELDS,
                context="donors",
            )
        )

    # 4. Patient assigned to doctor_demo
    doctor_uid = str(users_by_name["doctor_demo"]["_id"])
    patient = patient_repo.get_by_hospital_mrn("hosp_city_01", "MRN-DEMO-001")
    if not patient:
        patient = patient_repo.create(
            encrypt_fields(
                {
                    "hospital_id": "hosp_city_01",
                    "attending_doctor_id": doctor_uid,
                    "mrn": "MRN-DEMO-001",
                    "full_name": "Meera Nair",
                    "blood_group": BloodGroup.A.value,
                    "rh_factor": RhFactor.POSITIVE.value,
                    "clinical_indication": "Orthopedic surgical support",
                    "medical_notes": "No prior transfusion reaction",
                },
                PATIENT_ENCRYPTED_FIELDS,
                context="patients",
            )
        )

    now = datetime.now(timezone.utc)

    # 5. Donation
    donation = donation_repo.get_by_code("DON-DEMO-001")
    if not donation:
        donation = donation_repo.create({
            "donation_code": "DON-DEMO-001",
            "donor_id": str(donor["_id"]),
            "blood_bank_id": "bb_central",
            "donation_date": now - timedelta(days=3),
            "volume_ml": 450,
            "donation_type": BloodComponent.WHOLE_BLOOD.value,
            "hemoglobin_g_dl": 14.8,
            "blood_pressure": "120/78",
            "screening_status": "PASSED",
            "components_separated": True,
        })

    # 6. Blood Units across types & expiry windows
    sample_units = [
        ("UNIT-DEMO-O-NEG-1", BloodGroup.O.value, RhFactor.NEGATIVE.value, BloodComponent.RBC.value, 4),
        ("UNIT-DEMO-A-POS-1", BloodGroup.A.value, RhFactor.POSITIVE.value, BloodComponent.RBC.value, 25),
        ("UNIT-DEMO-B-POS-1", BloodGroup.B.value, RhFactor.POSITIVE.value, BloodComponent.RBC.value, 30),
        ("UNIT-DEMO-AB-POS-FFP", BloodGroup.AB.value, RhFactor.POSITIVE.value, BloodComponent.FFP.value, 180),
        ("UNIT-DEMO-O-NEG-PLT", BloodGroup.O.value, RhFactor.NEGATIVE.value, BloodComponent.PLATELETS.value, 3),
    ]
    for uid, grp, rh, comp, exp_days in sample_units:
        if not unit_repo.get_by_unit_id(uid):
            unit_repo.create({
                "unit_id": uid,
                "source_donation_id": "DON-DEMO-001",
                "blood_bank_id": "bb_central",
                "blood_group": grp,
                "rh_factor": rh,
                "component_type": comp,
                "volume_ml": 250,
                "collection_date": now - timedelta(days=2),
                "expiry_date": now + timedelta(days=exp_days),
                "storage_location": {"refrigerator_id": "REF-DEMO-1", "shelf": "A1", "slot": "01"},
                "status": BloodUnitStatus.AVAILABLE.value,
                "reserved_for_request_id": None,
                "allocated_at": None,
                "version": 1,
            })

    # 7. Sample Blood Requests
    if not request_repo.get_by_code("REQ-DEMO-CRIT"):
        req = request_repo.create({
            "request_code": "REQ-DEMO-CRIT",
            "hospital_id": "hosp_city_01",
            "doctor_id": doctor_uid,
            "patient_id": str(patient["_id"]),
            "blood_group": BloodGroup.A.value,
            "rh_factor": RhFactor.POSITIVE.value,
            "component_type": BloodComponent.RBC.value,
            "units_requested": 1,
            "priority": RequestPriority.CRITICAL.value,
            "clinical_reason": "Emergency trauma surgery",
            "status": RequestStatus.PENDING.value,
            "allocated_units": [],
        })
        notif_service.notify_roles(
            roles=[UserRole.ADMIN.value, UserRole.BLOOD_BANK_STAFF.value],
            notification_type=NotificationType.EMERGENCY_REQUEST,
            title="CRITICAL Blood Request: REQ-DEMO-CRIT",
            message="1 unit of A POSITIVE RBC requested by hosp_city_01.",
            resource_type="blood_requests",
            resource_id=req["_id"],
        )

    # 8. Sample Geospatial Blood Camps
    camps = [
        ("CAMP-DEMO-BLR", "Cubbon Park Mega Blood Drive", [77.5946, 12.9716], "Cubbon Park, Bengaluru"),
        ("CAMP-DEMO-ECITY", "Electronic City Tech Drive", [77.6602, 12.8452], "Electronic City Phase 1, Bengaluru"),
    ]
    for code, title, coords, addr in camps:
        if not camp_repo.get_by_code(code):
            camp_repo.create({
                "camp_code": code,
                "title": title,
                "organizer_blood_bank_id": "bb_central",
                "location": {"type": "Point", "coordinates": coords},
                "address": addr,
                "start_time": now + timedelta(days=3),
                "end_time": now + timedelta(days=3, hours=6),
                "capacity_donors": 200,
                "status": "UPCOMING",
            })

    audit_service.log_event(
        action="DEMO_DATA_SEEDED",
        resource_type="system",
        actor=users_by_name["admin_demo"],
        metadata={"users_seeded": len(users_by_name)},
    )

    return {
        "users": list(users_by_name.keys()),
        "hospital_id": str(hospital["_id"]),
        "donor_id": str(donor["_id"]),
        "patient_id": str(patient["_id"]),
    }


def main():
    settings = get_settings()
    logger.info(f"Seeding demo dataset into {settings.DATABASE_NAME}...")
    if not db_manager.connect():
        logger.error("Could not connect to MongoDB.")
        sys.exit(1)
    try:
        setup_indexes(db_manager.db)
        summary = seed_demo_data()
        logger.info(f"Demo data ready: {summary}")
    finally:
        db_manager.disconnect()


if __name__ == "__main__":
    main()
