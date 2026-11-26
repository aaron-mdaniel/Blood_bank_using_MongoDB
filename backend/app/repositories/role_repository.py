"""
Role repository for managing the roles_permissions MongoDB collection.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pymongo import ReturnDocument

from app.config.database import Collections
from app.models.permissions import DEFAULT_ROLE_DEFINITIONS
from app.repositories.base_repository import BaseRepository


class RoleRepository(BaseRepository):
    """
    Data access repository for roles_permissions collection.
    """

    def __init__(self, collection=None):
        col = collection if collection is not None else Collections.ROLES_PERMISSIONS
        super().__init__(col)

    def get_by_role_name(self, role_name: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"role_name": role_name})

    def upsert_role(
        self,
        role_name: str,
        permissions: List[str],
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates or updates a role's permission definition."""
        now = datetime.now(timezone.utc)
        set_fields: Dict[str, Any] = {
            "permissions": list(dict.fromkeys(permissions)),
            "updated_at": now,
        }
        if description is not None:
            set_fields["description"] = description

        updated = self.collection.find_one_and_update(
            {"role_name": role_name},
            {
                "$set": set_fields,
                "$setOnInsert": {
                    "role_name": role_name,
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return self.serialize_doc(updated)

    def seed_defaults(self, force: bool = False) -> List[Dict[str, Any]]:
        """
        Seeds the default 5 roles into roles_permissions.
        When force=False, only seeds if the collection is currently empty.
        """
        if not force and self.collection.count_documents({}) > 0:
            return self.find_many({}, limit=20)

        results: List[Dict[str, Any]] = []
        for role_name, definition in DEFAULT_ROLE_DEFINITIONS.items():
            existing = self.get_by_role_name(role_name)
            if existing and not force:
                results.append(existing)
                continue
            doc = self.upsert_role(
                role_name=role_name,
                permissions=list(definition["permissions"]),
                description=str(definition["description"]),
            )
            if doc:
                results.append(doc)
        return results
