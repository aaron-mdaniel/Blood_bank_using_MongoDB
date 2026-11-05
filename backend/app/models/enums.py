"""
Domain enumerations for the Secure Centralized Blood Bank Management System.
Defines strong typing for blood groups, Rh factors, components, roles, and statuses.
"""
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    BLOOD_BANK_STAFF = "BLOOD_BANK_STAFF"
    HOSPITAL_STAFF = "HOSPITAL_STAFF"
    DOCTOR = "DOCTOR"
    DONOR = "DONOR"


class BloodGroup(str, Enum):
    A = "A"
    B = "B"
    AB = "AB"
    O = "O"


class RhFactor(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"


class BloodComponent(str, Enum):
    WHOLE_BLOOD = "WHOLE_BLOOD"
    RBC = "RBC"                     # Red Blood Cells
    PLATELETS = "PLATELETS"         # Platelet Concentrate
    FFP = "FFP"                     # Fresh Frozen Plasma
    CRYOPRECIPITATE = "CRYOPRECIPITATE"


class DonorEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    TEMPORARY_DEFERRED = "TEMPORARY_DEFERRED"
    PERMANENT_DEFERRED = "PERMANENT_DEFERRED"


class BloodUnitStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    ALLOCATED = "ALLOCATED"
    TRANSFUSED = "TRANSFUSED"
    EXPIRED = "EXPIRED"
    DISCARDED = "DISCARDED"


class RequestPriority(str, Enum):
    CRITICAL = "CRITICAL"   # Emergency / Traumatic hemorrhage
    URGENT = "URGENT"       # Scheduled urgent surgery within 24h
    ROUTINE = "ROUTINE"     # Elective transfusion


PRIORITY_WEIGHTS = {
    RequestPriority.CRITICAL.value: 1,  # Highest urgency
    RequestPriority.URGENT.value: 2,
    RequestPriority.ROUTINE.value: 3,    # Lowest urgency
}


class RequestStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PARTIALLY_ALLOCATED = "PARTIALLY_ALLOCATED"
    ALLOCATED = "ALLOCATED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class HospitalVerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    SUSPENDED = "SUSPENDED"


class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"
