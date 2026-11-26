"""
Routers package export.
"""
from app.routers.auth_router import router as auth_router
from app.routers.user_router import router as user_router
from app.routers.role_router import router as role_router
from app.routers.donor_router import router as donor_router
from app.routers.hospital_router import router as hospital_router
from app.routers.patient_router import router as patient_router
from app.routers.donation_router import router as donation_router
from app.routers.blood_unit_router import router as blood_unit_router
from app.routers.blood_request_router import router as blood_request_router
from app.routers.audit_router import router as audit_router
from app.routers.notification_router import router as notification_router
from app.routers.blood_camp_router import router as blood_camp_router
from app.routers.analytics_router import router as analytics_router

__all__ = [
    "auth_router",
    "user_router",
    "role_router",
    "donor_router",
    "hospital_router",
    "patient_router",
    "donation_router",
    "blood_unit_router",
    "blood_request_router",
    "audit_router",
    "notification_router",
    "blood_camp_router",
    "analytics_router",
]
