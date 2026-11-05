"""
Pydantic schemas for BloodRequest entity.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.models.enums import BloodGroup, RhFactor, BloodComponent, RequestPriority, RequestStatus
from app.schemas.common_schema import MongoBaseModel


class BloodRequestCreate(BaseModel):
    request_code: str = Field(..., description="Unique requisition tracking number")
    hospital_id: str = Field(..., description="Ordering hospital identifier")
    doctor_id: str = Field(..., description="Prescribing physician identifier")
    patient_id: str = Field(..., description="Recipient patient identifier")
    blood_group: BloodGroup
    rh_factor: RhFactor
    component_type: BloodComponent
    units_requested: int = Field(default=1, ge=1, le=20)
    priority: RequestPriority = Field(default=RequestPriority.ROUTINE)
    clinical_reason: str = Field(..., min_length=3, max_length=500)


class BloodRequestUpdate(BaseModel):
    status: Optional[RequestStatus] = None
    priority: Optional[RequestPriority] = None
    allocated_units: Optional[List[str]] = None


class BloodRequestResponse(MongoBaseModel):
    id: str = Field(..., alias="_id")
    request_code: str
    hospital_id: str
    doctor_id: str
    patient_id: str
    blood_group: BloodGroup
    rh_factor: RhFactor
    component_type: BloodComponent
    units_requested: int
    priority: RequestPriority
    clinical_reason: str
    status: RequestStatus
    allocated_units: List[str] = []
    created_at: datetime
    updated_at: datetime
