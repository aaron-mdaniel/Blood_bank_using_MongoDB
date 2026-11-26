"""
Pydantic schemas for In-App Notifications & Inventory Alerts (notifications collection).
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.common_schema import MongoBaseModel


class NotificationType(str, Enum):
    REQUEST_STATUS = "REQUEST_STATUS"
    EMERGENCY_REQUEST = "EMERGENCY_REQUEST"
    EXPIRY_ALERT = "EXPIRY_ALERT"
    INVENTORY_ALERT = "INVENTORY_ALERT"


class NotificationResponse(MongoBaseModel):
    id: str = Field(..., alias="_id")
    user_id: str
    notification_type: NotificationType
    title: str
    message: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    is_read: bool = False
    read_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class InventoryAlertScanRequest(BaseModel):
    expiry_days_threshold: int = Field(default=7, ge=1, le=90, description="Flag units expiring within N days")
    min_units_threshold: int = Field(default=2, ge=1, le=50, description="Flag blood groups below N available units")


class InventoryAlertScanResponse(BaseModel):
    expired_units_marked: int
    expiring_soon_count: int
    low_stock_groups: List[Dict[str, Any]]
    notifications_dispatched: int
