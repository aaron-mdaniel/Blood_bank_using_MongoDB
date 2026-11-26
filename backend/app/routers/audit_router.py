"""
Security Audit Logs REST API Router (Admin-only).
Provides centralized compliance visibility into authentication, authorization denials,
and critical clinical/administrative operations.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query

from app.models.permissions import Permission
from app.schemas.audit_schema import AuditLogResponse, AuditStatus
from app.security.dependencies import require_permissions
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["Security Audit"])
audit_service = AuditService()


@router.get("", response_model=List[AuditLogResponse])
async def list_audit_logs(
    action: Optional[str] = None,
    audit_status: Optional[AuditStatus] = Query(None, alias="status"),
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.AUDIT_READ)),
):
    """Retrieves paginated security audit logs with multi-field filtering (Admin only)."""
    return audit_service.list_audit_logs(
        action=action,
        audit_status=audit_status.value if audit_status else None,
        user_id=user_id,
        resource_type=resource_type,
        start_time=start_time,
        end_time=end_time,
        skip=skip,
        limit=limit,
    )


@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    log_id: str,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.AUDIT_READ)),
):
    """Retrieves a single audit log entry by event_id or _id (Admin only)."""
    return audit_service.get_audit_log(log_id)
