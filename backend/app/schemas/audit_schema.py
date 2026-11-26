"""
Pydantic schemas for Centralized Security Audit Logging (audit_logs collection).
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from app.schemas.common_schema import MongoBaseModel


class AuditStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    DENIED = "DENIED"


class AuditActor(BaseModel):
    user_id: Optional[str] = None
    username: Optional[str] = None
    role: Optional[str] = None


class AuditLogResponse(MongoBaseModel):
    id: str = Field(..., alias="_id")
    event_id: str
    timestamp: datetime
    actor: AuditActor
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    status: AuditStatus
    metadata: Dict[str, Any] = Field(default_factory=dict)
