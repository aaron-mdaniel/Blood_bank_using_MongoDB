"""
Role & Permission Management REST API Router (Admin-only RBAC Administration).
"""
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status

from app.models.enums import UserRole
from app.models.permissions import Permission
from app.schemas.role_schema import RolePermissionResponse, RolePermissionUpdate
from app.security.dependencies import require_permissions
from app.services.rbac_service import RBACService

router = APIRouter(prefix="/roles", tags=["Roles & Permissions"])
rbac_service = RBACService()


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
    return rbac_service.update_role_permissions(role_name.value, payload)


@router.post("/seed", response_model=List[RolePermissionResponse], status_code=status.HTTP_200_OK)
async def reset_default_roles(
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.ROLES_WRITE)),
):
    """Resets all 5 roles in roles_permissions to the canonical default matrix (Admin only)."""
    return rbac_service.reset_defaults()
