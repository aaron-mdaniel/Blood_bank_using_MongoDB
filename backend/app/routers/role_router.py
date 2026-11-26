"""
Role & Permission Management REST API Router (Admin-only RBAC Administration).
"""
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status

from app.models.enums import UserRole
from app.models.permissions import Permission
from app.schemas.role_schema import RolePermissionResponse, RolePermissionUpdate
from app.security.dependencies import require_permissions
from app.services.audit_service import AuditService
from app.services.rbac_service import RBACService

router = APIRouter(prefix="/roles", tags=["Roles & Permissions"])
rbac_service = RBACService()
audit_service = AuditService()


@router.get("", response_model=List[RolePermissionResponse])
async def list_roles(
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.ROLES_READ)),
):
    """Lists all system roles and their assigned permissions (Admin only)."""
    return rbac_service.list_roles()


@router.get("/{role_name}", response_model=RolePermissionResponse)
async def get_role(
    role_name: UserRole,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.ROLES_READ)),
):
    """Retrieves permissions for a specific system role (Admin only)."""
    return rbac_service.get_role(role_name.value)


@router.put("/{role_name}", response_model=RolePermissionResponse)
async def update_role_permissions(
    role_name: UserRole,
    payload: RolePermissionUpdate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.ROLES_WRITE)),
):
    """Updates the permission list for a system role (Admin only)."""
    updated = rbac_service.update_role_permissions(role_name.value, payload)
    audit_service.log_event(
        action="ROLE_PERMISSIONS_UPDATED",
        resource_type="roles_permissions",
        resource_id=role_name.value,
        actor=current_user,
        metadata={"permissions_count": len(payload.permissions)},
    )
    return updated


@router.post("/seed", response_model=List[RolePermissionResponse], status_code=status.HTTP_200_OK)
async def reset_default_roles(
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.ROLES_WRITE)),
):
    """Resets all 5 roles in roles_permissions to the canonical default matrix (Admin only)."""
    seeded = rbac_service.reset_defaults()
    audit_service.log_event(
        action="ROLES_SEEDED",
        resource_type="roles_permissions",
        actor=current_user,
        metadata={"roles_count": len(seeded)},
    )
    return seeded
