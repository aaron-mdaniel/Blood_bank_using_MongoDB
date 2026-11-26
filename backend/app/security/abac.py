"""
Attribute-Based / Resource-Level Access Control (ABAC) Policies.
Enforces record ownership and facility-level scope isolation on top of RBAC:
- DONOR: Restricted to own donor profile and own donation records.
- HOSPITAL_STAFF: Restricted to own hospital's patients and blood requests.
- DOCTOR: Restricted to assigned patients, own blood requests, and permitted hospital scope.
- BLOOD_BANK_STAFF: Restricted to assigned blood bank's donations and inventory units.
- ADMIN: Global administrative scope across all resources.
"""
from typing import Any, Dict, Optional
from fastapi import HTTPException, status

from app.models.enums import BloodUnitStatus, UserRole
from app.repositories.donor_repository import DonorRepository
from app.repositories.patient_repository import PatientRepository

# Fields on DonorUpdate reserved for Blood Bank Staff / Admin clinical review
DONOR_CLINICAL_FIELDS = frozenset({
    "eligibility_status",
    "last_donation_date",
    "next_eligible_date",
    "medical_screening_notes",
})


def _deny(detail: str) -> None:
    """Raises HTTP 403 Forbidden for resource-level authorization violations."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
    )


def _user_id(current_user: Dict[str, Any]) -> str:
    return str(current_user.get("_id", ""))


def _require_scope_value(current_user: Dict[str, Any], field: str, label: str) -> str:
    val = current_user.get(field)
    if not val:
        _deny(f"Access denied. Account is missing assigned {label} scope.")
    return str(val)


def _enforce_filter_scope(
    query: Dict[str, Any],
    filter_key: str,
    expected_value: str,
    label: str,
) -> None:
    """
    Validates an optional caller-supplied filter against the actor's allowed scope,
    and pins the query to that scope.
    """
    requested = query.get(filter_key)
    if requested is not None and str(requested) != str(expected_value):
        _deny(f"Access denied. Cannot query {label} outside your assigned scope.")
    query[filter_key] = str(expected_value)


# ==========================================
# 1. Donor Resource Policies
# ==========================================

def authorize_donor_create(current_user: Dict[str, Any], payload_user_id: str) -> None:
    role = current_user.get("role")
    if role == UserRole.DONOR.value and str(payload_user_id) != _user_id(current_user):
        _deny("Access denied. Donors can only register a donor profile for themselves.")


def scope_donor_query(current_user: Dict[str, Any], query: Dict[str, Any]) -> Dict[str, Any]:
    if current_user.get("role") == UserRole.DONOR.value:
        query["user_id"] = _user_id(current_user)
    return query


def authorize_donor_access(current_user: Dict[str, Any], donor_doc: Dict[str, Any]) -> None:
    if current_user.get("role") == UserRole.DONOR.value:
        if str(donor_doc.get("user_id")) != _user_id(current_user):
            _deny("Access denied. You can only access your own donor profile.")


def authorize_donor_update(
    current_user: Dict[str, Any],
    donor_doc: Dict[str, Any],
    update_fields: Dict[str, Any],
) -> None:
    authorize_donor_access(current_user, donor_doc)
    if current_user.get("role") == UserRole.DONOR.value:
        forbidden = set(update_fields.keys()) & DONOR_CLINICAL_FIELDS
        if forbidden:
            _deny(
                "Access denied. Donors cannot modify clinical eligibility or screening fields: "
                f"{', '.join(sorted(forbidden))}."
            )


# ==========================================
# 2. Donation Resource Policies
# ==========================================

def authorize_donation_create(current_user: Dict[str, Any], payload_blood_bank_id: str) -> None:
    if current_user.get("role") == UserRole.BLOOD_BANK_STAFF.value:
        assigned_bb = _require_scope_value(current_user, "blood_bank_id", "blood bank")
        if str(payload_blood_bank_id) != assigned_bb:
            _deny("Access denied. Cannot record donations for another blood bank.")


def scope_donation_query(
    current_user: Dict[str, Any],
    query: Dict[str, Any],
    donor_repo: DonorRepository,
) -> Optional[Dict[str, Any]]:
    """
    Applies scope filters to donation queries.
    Returns None when a DONOR has no donor profile yet (caller should return empty list).
    """
    role = current_user.get("role")
    if role == UserRole.DONOR.value:
        donor_profile = donor_repo.get_by_user_id(_user_id(current_user))
        if not donor_profile:
            if query.get("donor_id"):
                _deny("Access denied. You can only view your own donation records.")
            return None
        _enforce_filter_scope(query, "donor_id", str(donor_profile["_id"]), "donor")
    elif role == UserRole.BLOOD_BANK_STAFF.value:
        assigned_bb = _require_scope_value(current_user, "blood_bank_id", "blood bank")
        _enforce_filter_scope(query, "blood_bank_id", assigned_bb, "blood bank")
    return query


def authorize_donation_access(
    current_user: Dict[str, Any],
    donation_doc: Dict[str, Any],
    donor_repo: DonorRepository,
) -> None:
    role = current_user.get("role")
    if role == UserRole.DONOR.value:
        donor_profile = donor_repo.get_by_user_id(_user_id(current_user))
        if not donor_profile or str(donation_doc.get("donor_id")) != str(donor_profile["_id"]):
            _deny("Access denied. You can only view your own donation records.")
    elif role == UserRole.BLOOD_BANK_STAFF.value:
        assigned_bb = _require_scope_value(current_user, "blood_bank_id", "blood bank")
        if str(donation_doc.get("blood_bank_id")) != assigned_bb:
            _deny("Access denied. Cannot access donation records from another blood bank.")


# ==========================================
# 3. Patient Resource Policies
# ==========================================

def authorize_patient_create(
    current_user: Dict[str, Any],
    payload_hospital_id: str,
    payload_doctor_id: str,
) -> None:
    role = current_user.get("role")
    if role == UserRole.HOSPITAL_STAFF.value:
        assigned_hosp = _require_scope_value(current_user, "hospital_id", "hospital")
        if str(payload_hospital_id) != assigned_hosp:
            _deny("Access denied. Cannot register patients for another hospital.")
    elif role == UserRole.DOCTOR.value:
        if current_user.get("hospital_id") and str(payload_hospital_id) != str(current_user["hospital_id"]):
            _deny("Access denied. Cannot register patients outside your assigned hospital.")
        if str(payload_doctor_id) != _user_id(current_user):
            _deny("Access denied. Doctors can only register patients assigned to themselves.")


def scope_patient_query(current_user: Dict[str, Any], query: Dict[str, Any]) -> Dict[str, Any]:
    role = current_user.get("role")
    if role == UserRole.HOSPITAL_STAFF.value:
        assigned_hosp = _require_scope_value(current_user, "hospital_id", "hospital")
        _enforce_filter_scope(query, "hospital_id", assigned_hosp, "hospital")
    elif role == UserRole.DOCTOR.value:
        if current_user.get("hospital_id"):
            _enforce_filter_scope(query, "hospital_id", str(current_user["hospital_id"]), "hospital")
        _enforce_filter_scope(query, "attending_doctor_id", _user_id(current_user), "attending doctor")
    return query


def authorize_patient_access(current_user: Dict[str, Any], patient_doc: Dict[str, Any]) -> None:
    role = current_user.get("role")
    if role == UserRole.HOSPITAL_STAFF.value:
        assigned_hosp = _require_scope_value(current_user, "hospital_id", "hospital")
        if str(patient_doc.get("hospital_id")) != assigned_hosp:
            _deny("Access denied. Cannot access patients from another hospital.")
    elif role == UserRole.DOCTOR.value:
        if current_user.get("hospital_id") and str(patient_doc.get("hospital_id")) != str(current_user["hospital_id"]):
            _deny("Access denied. Cannot access patients outside your assigned hospital.")
        if str(patient_doc.get("attending_doctor_id")) != _user_id(current_user):
            _deny("Access denied. You can only access patients assigned to you.")


# ==========================================
# 4. Blood Unit / Inventory Resource Policies
# ==========================================

def authorize_blood_unit_create(current_user: Dict[str, Any], payload_blood_bank_id: str) -> None:
    if current_user.get("role") == UserRole.BLOOD_BANK_STAFF.value:
        assigned_bb = _require_scope_value(current_user, "blood_bank_id", "blood bank")
        if str(payload_blood_bank_id) != assigned_bb:
            _deny("Access denied. Cannot add blood units to another blood bank's inventory.")


def scope_blood_unit_query(current_user: Dict[str, Any], query: Dict[str, Any]) -> Dict[str, Any]:
    role = current_user.get("role")
    if role == UserRole.BLOOD_BANK_STAFF.value:
        assigned_bb = _require_scope_value(current_user, "blood_bank_id", "blood bank")
        _enforce_filter_scope(query, "blood_bank_id", assigned_bb, "blood bank")
    elif role in (UserRole.HOSPITAL_STAFF.value, UserRole.DOCTOR.value):
        requested_status = query.get("status")
        if requested_status is not None and requested_status != BloodUnitStatus.AVAILABLE.value:
            _deny("Access denied. Hospital staff and doctors may only query AVAILABLE blood inventory.")
        query["status"] = BloodUnitStatus.AVAILABLE.value
    return query


def authorize_blood_unit_access(
    current_user: Dict[str, Any],
    unit_doc: Dict[str, Any],
    for_write: bool = False,
) -> None:
    role = current_user.get("role")
    if role == UserRole.BLOOD_BANK_STAFF.value:
        assigned_bb = _require_scope_value(current_user, "blood_bank_id", "blood bank")
        if str(unit_doc.get("blood_bank_id")) != assigned_bb:
            _deny("Access denied. Cannot access or modify blood units from another blood bank.")
    elif not for_write and role in (UserRole.HOSPITAL_STAFF.value, UserRole.DOCTOR.value):
        if unit_doc.get("status") != BloodUnitStatus.AVAILABLE.value:
            _deny("Access denied. You may only view AVAILABLE blood units.")


# ==========================================
# 5. Blood Request Resource Policies
# ==========================================

def authorize_blood_request_create(
    current_user: Dict[str, Any],
    payload_hospital_id: str,
    payload_doctor_id: str,
    payload_patient_id: str,
    patient_repo: Optional[PatientRepository] = None,
) -> None:
    role = current_user.get("role")
    if role == UserRole.HOSPITAL_STAFF.value:
        assigned_hosp = _require_scope_value(current_user, "hospital_id", "hospital")
        if str(payload_hospital_id) != assigned_hosp:
            _deny("Access denied. Cannot create blood requests for another hospital.")
    elif role == UserRole.DOCTOR.value:
        if current_user.get("hospital_id") and str(payload_hospital_id) != str(current_user["hospital_id"]):
            _deny("Access denied. Cannot create blood requests for another hospital.")
        if str(payload_doctor_id) != _user_id(current_user):
            _deny("Access denied. Doctors can only submit blood requests under their own physician ID.")
        if patient_repo is not None:
            patient = None
            try:
                patient = patient_repo.get_by_id(payload_patient_id)
            except ValueError:
                patient = None
            if patient and str(patient.get("attending_doctor_id")) != _user_id(current_user):
                _deny("Access denied. Cannot create a blood request for an unassigned patient.")


def scope_blood_request_query(current_user: Dict[str, Any], query: Dict[str, Any]) -> Dict[str, Any]:
    role = current_user.get("role")
    if role == UserRole.HOSPITAL_STAFF.value:
        assigned_hosp = _require_scope_value(current_user, "hospital_id", "hospital")
        _enforce_filter_scope(query, "hospital_id", assigned_hosp, "hospital")
    elif role == UserRole.DOCTOR.value:
        if current_user.get("hospital_id"):
            _enforce_filter_scope(query, "hospital_id", str(current_user["hospital_id"]), "hospital")
        query["doctor_id"] = _user_id(current_user)
    return query


def authorize_blood_request_access(current_user: Dict[str, Any], request_doc: Dict[str, Any]) -> None:
    role = current_user.get("role")
    if role == UserRole.HOSPITAL_STAFF.value:
        assigned_hosp = _require_scope_value(current_user, "hospital_id", "hospital")
        if str(request_doc.get("hospital_id")) != assigned_hosp:
            _deny("Access denied. Cannot view blood requests belonging to another hospital.")
    elif role == UserRole.DOCTOR.value:
        if current_user.get("hospital_id") and str(request_doc.get("hospital_id")) != str(current_user["hospital_id"]):
            _deny("Access denied. Cannot view blood requests belonging to another hospital.")
        if str(request_doc.get("doctor_id")) != _user_id(current_user):
            _deny("Access denied. You can only view your own patient blood requests.")
