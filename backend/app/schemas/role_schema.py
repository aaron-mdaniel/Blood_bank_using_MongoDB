"""
Pydantic schemas for Role-Based Access Control (roles_permissions collection).
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from app.models.enums import UserRole
from app.models.permissions import Permission
from app.schemas.common_schema import MongoBaseModel


class RolePermissionUpdate(BaseModel):
    description: Optional[str] = Field(default=None, max_length=300)
    permissions: List[Permission] = Field(..., description="Updated list of granted permissions for this role")


class RolePermissionResponse(MongoBaseModel):
    id: str = Field(..., alias="_id")
    role_name: UserRole
    description: str
    permissions: List[str]
    created_at: datetime
    updated_at: datetime
