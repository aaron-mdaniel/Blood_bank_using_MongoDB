"""
Notifications & Inventory Alert REST API Router.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query

from app.models.enums import UserRole
from app.models.permissions import Permission
from app.schemas.notification_schema import (
    InventoryAlertScanRequest,
    InventoryAlertScanResponse,
    NotificationResponse,
)
from app.security.dependencies import require_permissions
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])
notification_service = NotificationService()


@router.get("", response_model=List[NotificationResponse])
async def list_my_notifications(
    is_read: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.NOTIFICATIONS_READ)),
):
    """Lists in-app notifications belonging to the currently authenticated user."""
    return notification_service.list_my_notifications(
        current_user=current_user,
        is_read=is_read,
        skip=skip,
        limit=limit,
    )


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: str,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.NOTIFICATIONS_READ)),
):
    """Marks a single notification as read (owner-only)."""
    return notification_service.mark_notification_read(notification_id, current_user)


@router.post("/read-all")
async def mark_all_notifications_read(
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.NOTIFICATIONS_READ)),
):
    """Marks all unread notifications for the authenticated user as read."""
    modified = notification_service.mark_all_read(current_user)
    return {"marked_read": modified}


@router.post("/scan-alerts", response_model=InventoryAlertScanResponse)
async def scan_expiry_and_low_stock(
    payload: InventoryAlertScanRequest = InventoryAlertScanRequest(),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.NOTIFICATIONS_WRITE)),
):
    """
    Scans blood inventory for expired/soon-to-expire units and low RBC stock,
    updating expired units and dispatching alerts to Admin / Blood Bank Staff.
    """
    bb_scope = (
        current_user.get("blood_bank_id")
        if current_user.get("role") == UserRole.BLOOD_BANK_STAFF.value
        else None
    )
    return notification_service.scan_expiring_and_low_inventory(
        expiry_days_threshold=payload.expiry_days_threshold,
        min_units_threshold=payload.min_units_threshold,
        blood_bank_id=bb_scope,
    )
