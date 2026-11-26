"""
MongoDB Aggregation Analytics & Change Stream REST API Router.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Query

from app.models.enums import UserRole
from app.models.permissions import Permission
from app.schemas.analytics_schema import ChangeStreamStatusResponse, DashboardAnalyticsResponse
from app.security.dependencies import require_permissions
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics & Aggregations"])
analytics_service = AnalyticsService()


@router.get("/dashboard", response_model=DashboardAnalyticsResponse)
async def get_dashboard_analytics(
    expiry_days: int = Query(7, ge=1, le=90),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.REPORTS_READ)),
):
    """
    Executes MongoDB aggregation pipelines for Admin and Blood Bank Staff dashboards.
    Blood Bank Staff metrics are scoped to their assigned blood_bank_id.
    """
    bb_scope = (
        current_user.get("blood_bank_id")
        if current_user.get("role") == UserRole.BLOOD_BANK_STAFF.value
        else None
    )
    return analytics_service.get_dashboard_analytics(
        blood_bank_id=bb_scope,
        expiry_days=expiry_days,
    )


@router.get("/inventory-distribution")
async def get_inventory_distribution(
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.BLOOD_UNITS_READ)),
) -> List[Dict[str, Any]]:
    """
    Aggregates AVAILABLE unexpired blood units by blood group, Rh factor, and component type.
    Accessible to Admin, Blood Bank Staff, Hospital Staff, and Doctors.
    """
    return analytics_service.get_available_inventory_distribution()


@router.get("/change-streams/status", response_model=ChangeStreamStatusResponse)
async def get_change_stream_status(
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.REPORTS_READ)),
):
    """Reports MongoDB Change Streams replica-set readiness and recent inventory/request events."""
    return analytics_service.get_change_stream_status()
