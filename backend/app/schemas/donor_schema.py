"""
Pydantic schemas for Donor entity.
"""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.models.enums import BloodGroup, RhFactor, DonorEligibility, Gender
from app.schemas.common_schema import MongoBaseModel


class DonorCreate(BaseModel):
    user_id: str = Field(..., description="Referenced User ID")
    donor_card_number: str = Field(..., description="Unique donor identifier card number")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: str = Field(..., description="Date of birth YYYY-MM-DD")
    gender: Gender = Field(default=Gender.MALE)
    blood_group: BloodGroup
    rh_factor: RhFactor
    contact_phone: str = Field(..., description="Phone number to be stored encrypted")
    address: str = Field(..., description="Residential address to be stored encrypted")
    emergency_contact: Optional[str] = Field(default=None, description="Emergency contact to be stored encrypted")
    medical_screening_notes: Optional[str] = Field(default=None, description="Medical notes to be stored encrypted")
    eligibility_status: DonorEligibility = Field(default=DonorEligibility.ELIGIBLE)


class DonorUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    eligibility_status: Optional[DonorEligibility] = None
    last_donation_date: Optional[datetime] = None
    next_eligible_date: Optional[datetime] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    medical_screening_notes: Optional[str] = None


class DonorResponse(MongoBaseModel):
    id: str = Field(..., alias="_id")
    user_id: str
    donor_card_number: str
    first_name: str
    last_name: str
    date_of_birth: str
    gender: Gender
    blood_group: BloodGroup
    rh_factor: RhFactor
    eligibility_status: DonorEligibility
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    medical_screening_notes: Optional[str] = None
    contact_phone_encrypted: Optional[str] = None
    address_encrypted: Optional[str] = None
    emergency_contact_encrypted: Optional[str] = None
    medical_screening_notes_encrypted: Optional[str] = None
    last_donation_date: Optional[datetime] = None
    next_eligible_date: Optional[datetime] = None
    created_at: datetime
