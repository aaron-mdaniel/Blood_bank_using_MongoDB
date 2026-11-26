"""
Role-Based Access Control (RBAC) permission constants and default role-permission matrix.
Maps the 5 core system roles to granular resource-action permissions.
"""
from enum import Enum
from typing import Dict, List

from app.models.enums import UserRole


class Permission(str, Enum):
    """Granular API and domain permissions."""
    # User & Role Administration
    USERS_READ = "users:read"
    USERS_WRITE = "users:write"
    USERS_DELETE = "users:delete"
    ROLES_READ = "roles:read"
    ROLES_WRITE = "roles:write"

    # Donors
    DONORS_READ = "donors:read"
    DONORS_WRITE = "donors:write"
    DONORS_DELETE = "donors:delete"

    # Hospitals
    HOSPITALS_READ = "hospitals:read"
    HOSPITALS_WRITE = "hospitals:write"

    # Patients
    PATIENTS_READ = "patients:read"
    PATIENTS_WRITE = "patients:write"

    # Donations
    DONATIONS_READ = "donations:read"
    DONATIONS_WRITE = "donations:write"

    # Blood Units / Inventory
    BLOOD_UNITS_READ = "blood_units:read"
    BLOOD_UNITS_WRITE = "blood_units:write"

    # Blood Requests
    BLOOD_REQUESTS_READ = "blood_requests:read"
    BLOOD_REQUESTS_WRITE = "blood_requests:write"
    BLOOD_REQUESTS_APPROVE = "blood_requests:approve"

    # Reports & Security Audit
    REPORTS_READ = "reports:read"
    AUDIT_READ = "audit:read"

    # Notifications & Alerts
    NOTIFICATIONS_READ = "notifications:read"
    NOTIFICATIONS_WRITE = "notifications:write"

    # Blood Camps
    CAMPS_READ = "camps:read"
    CAMPS_WRITE = "camps:write"


DEFAULT_ROLE_DEFINITIONS: Dict[str, Dict[str, object]] = {
    UserRole.ADMIN.value: {
        "description": "Full system administrator with user, role, inventory, request, report, and audit management access.",
        "permissions": [p.value for p in Permission],
    },
    UserRole.BLOOD_BANK_STAFF.value: {
        "description": "Blood bank staff managing donors, donations, blood units, inventory, and hospital request fulfillment.",
        "permissions": [
            Permission.DONORS_READ.value,
            Permission.DONORS_WRITE.value,
            Permission.HOSPITALS_READ.value,
            Permission.DONATIONS_READ.value,
            Permission.DONATIONS_WRITE.value,
            Permission.BLOOD_UNITS_READ.value,
            Permission.BLOOD_UNITS_WRITE.value,
            Permission.BLOOD_REQUESTS_READ.value,
            Permission.BLOOD_REQUESTS_APPROVE.value,
            Permission.REPORTS_READ.value,
            Permission.NOTIFICATIONS_READ.value,
            Permission.NOTIFICATIONS_WRITE.value,
            Permission.CAMPS_READ.value,
            Permission.CAMPS_WRITE.value,
        ],
    },
    UserRole.HOSPITAL_STAFF.value: {
        "description": "Hospital staff registering hospital blood requests, managing hospital patients, and viewing permitted inventory.",
        "permissions": [
            Permission.HOSPITALS_READ.value,
            Permission.PATIENTS_READ.value,
            Permission.PATIENTS_WRITE.value,
            Permission.BLOOD_UNITS_READ.value,
            Permission.BLOOD_REQUESTS_READ.value,
            Permission.BLOOD_REQUESTS_WRITE.value,
            Permission.NOTIFICATIONS_READ.value,
            Permission.CAMPS_READ.value,
        ],
    },
    UserRole.DOCTOR.value: {
        "description": "Clinician managing patient records, creating patient-related blood requests, and viewing permitted blood inventory.",
        "permissions": [
            Permission.HOSPITALS_READ.value,
            Permission.PATIENTS_READ.value,
            Permission.PATIENTS_WRITE.value,
            Permission.BLOOD_UNITS_READ.value,
            Permission.BLOOD_REQUESTS_READ.value,
            Permission.BLOOD_REQUESTS_WRITE.value,
            Permission.NOTIFICATIONS_READ.value,
            Permission.CAMPS_READ.value,
        ],
    },
    UserRole.DONOR.value: {
        "description": "Registered blood donor managing own profile and viewing own donation history.",
        "permissions": [
            Permission.DONORS_READ.value,
            Permission.DONORS_WRITE.value,
            Permission.DONATIONS_READ.value,
            Permission.NOTIFICATIONS_READ.value,
            Permission.CAMPS_READ.value,
        ],
    },
}


def get_default_permissions(role_name: str) -> List[str]:
    """Returns default permission list for a given role name."""
    definition = DEFAULT_ROLE_DEFINITIONS.get(role_name)
    if not definition:
        return []
    return list(definition["permissions"])
