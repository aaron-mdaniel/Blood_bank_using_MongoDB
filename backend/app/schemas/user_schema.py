"""
Pydantic schemas for User entity.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.models.enums import UserRole
from app.schemas.common_schema import MongoBaseModel


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Unique alphanumeric username")
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Plaintext password to be hashed using Argon2id")
    role: UserRole = Field(default=UserRole.DONOR, description="System role")
    hospital_id: Optional[str] = Field(default=None, description="Associated hospital ID if hospital staff/doctor")
    blood_bank_id: Optional[str] = Field(default=None, description="Associated blood bank ID if staff")


class UserUpdate(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    hospital_id: Optional[str] = None
    blood_bank_id: Optional[str] = None


class UserResponse(MongoBaseModel):
    id: str = Field(..., alias="_id")
    username: str
    email: Optional[str] = None
    email_encrypted: Optional[str] = None
    role: UserRole
    is_active: bool
    failed_login_attempts: int = 0
    lockout_until: Optional[datetime] = None
    hospital_id: Optional[str] = None
    blood_bank_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
