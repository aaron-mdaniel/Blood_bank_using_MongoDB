"""
RBAC Service: Role-Permission resolution, seeding, and administrative updates.
"""
from typing import Any, Dict, List, Set
from fastapi import HTTPException, status

from app.models.enums import UserRole
from app.models.permissions import DEFAULT_ROLE_DEFINITIONS, get_default_permissions
from app.repositories.role_repository import RoleRepository
from app.schemas.role_schema import RolePermissionUpdate


class RBACService:
    """
    Orchestrates role definitions and permission verification against MongoDB.
    """

    def __init__(self, role_repo: RoleRepository = None):
        self.role_repo = role_repo or RoleRepository()

    def ensure_seeded(self) -> List[Dict[str, Any]]:
        """Ensures default role-permission definitions exist in MongoDB."""
        return self.role_repo.seed_defaults(force=False)

    def reset_defaults(self) -> List[Dict[str, Any]]:
        """Resets all 5 roles in MongoDB back to the canonical permission matrix."""
        return self.role_repo.seed_defaults(force=True)

    def list_roles(self) -> List[Dict[str, Any]]:
        """Lists all role definitions, seeding defaults if collection is empty."""
        self.ensure_seeded()
        return self.role_repo.find_many({}, limit=50, sort=[("role_name", 1)])

    def get_role(self, role_name: str) -> Dict[str, Any]:
        """Retrieves a single role definition by role_name."""
        self.ensure_seeded()
        role_doc = self.role_repo.get_by_role_name(role_name)
        if not role_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role '{role_name}' not found.",
            )
        return role_doc

    def get_permissions_for_role(self, role_name: str) -> Set[str]:
        """
        Resolves the active permission set for a user role from MongoDB,
        seeding defaults automatically on first lookup if needed.
        """
        self.ensure_seeded()
        role_doc = self.role_repo.get_by_role_name(role_name)
        if role_doc:
            return set(role_doc.get("permissions", []))
        return set(get_default_permissions(role_name))

    def has_permissions(self, role_name: str, required_permissions: List[str]) -> bool:
        """Returns True if the role holds all required permissions."""
        granted = self.get_permissions_for_role(role_name)
        return all(perm in granted for perm in required_permissions)

    def update_role_permissions(
        self, role_name: str, payload: RolePermissionUpdate
    ) -> Dict[str, Any]:
        """Updates permissions (and optional description) for a valid system role."""
        valid_roles = {r.value for r in UserRole}
        if role_name not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role '{role_name}' is not a valid system role.",
            )

        self.ensure_seeded()
        existing = self.role_repo.get_by_role_name(role_name)
        description = payload.description
        if description is None:
            description = (
                existing.get("description")
                if existing
                else str(DEFAULT_ROLE_DEFINITIONS[role_name]["description"])
            )

        perm_values = [p.value for p in payload.permissions]
        return self.role_repo.upsert_role(
            role_name=role_name,
            permissions=perm_values,
            description=description,
        )
