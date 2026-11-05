"""
Pydantic schemas for Patient entity.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.models.enums import BloodGroup, RhFactor
from app.schemas.common_schema import MongoBaseModel


class PatientCreate(BaseModel):
    hospital_id: str = Field(..., description="Hospital ID managing the patient")
    attending_doctor_id: str = Field(..., description="Doctor ID treating the patient")
    mrn: str = Field(..., description="Medical Record Number unique within hospital")
    full_name: str = Field(..., min_length=1, max_length=150)
    blood_group: BloodGroup
    rh_factor: RhFactor
    clinical_indication: str = Field(..., description="Diagnosis or reason for transfusion")
    medical_notes: Optional[str] = Field(default=None, description="Confidential medical notes")


class PatientUpdate(BaseModel):
    attending_doctor_id: Optional[str] = None
    clinical_indication: Optional[str] = None
    medical_notes: Optional[str] = None


class PatientResponse(MongoBaseModel):
    id: str = Field(..., alias="_id")
    hospital_id: str
    attending_doctor_id: str
    mrn: str
    full_name: str
    blood_group: BloodGroup
    rh_factor: RhFactor
    clinical_indication: str
    medical_notes_encrypted: Optional[str] = None
    created_at: datetime
