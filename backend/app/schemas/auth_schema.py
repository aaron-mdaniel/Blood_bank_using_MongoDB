"""
Pydantic schemas for Authentication workflows (Registration, Login, Token Response).
"""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.models.enums import UserRole
from app.schemas.common_schema import MongoBaseModel


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username or handle")
    password: str = Field(..., min_length=1, description="Account password")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(..., min_length=8, description="Password (minimum 8 characters)")
    role: UserRole = Field(default=UserRole.DONOR, description="Assigned role (DONOR, HOSPITAL_STAFF, DOCTOR, etc.)")
    hospital_id: Optional[str] = Field(default=None, description="Associated hospital ID if hospital staff/doctor")
    blood_bank_id: Optional[str] = Field(default=None, description="Associated blood bank ID if blood bank staff")


class UserSummary(MongoBaseModel):
    id: str = Field(..., alias="_id")
    username: str
    email_masked: Optional[str] = None
    role: UserRole
    is_active: bool
    hospital_id: Optional[str] = None
    blood_bank_id: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token lifespan in seconds")
    user: UserSummary


class LogoutResponse(BaseModel):
    message: str = "Successfully logged out."
    status: str = "success"
