"""
Pydantic schemas for Donation entity.
"""
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
from app.models.enums import BloodComponent
from app.schemas.common_schema import MongoBaseModel


class DonationCreate(BaseModel):
    donation_code: str = Field(..., description="Unique barcode / code identifier")
    donor_id: str = Field(..., description="Referenced Donor ID")
    blood_bank_id: str = Field(..., description="Referenced Blood Bank ID")
    donation_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    volume_ml: int = Field(default=450, ge=200, le=600, description="Volume collected in mL")
    donation_type: BloodComponent = Field(default=BloodComponent.WHOLE_BLOOD)
    hemoglobin_g_dl: float = Field(..., ge=10.0, le=20.0, description="Hemoglobin screening in g/dL")
    blood_pressure: str = Field(..., description="Systolic/Diastolic BP string (e.g. 120/80)")
    screening_status: str = Field(default="PASSED", description="PASSED, PENDING, or REJECTED")


class DonationUpdate(BaseModel):
    screening_status: Optional[str] = None
    components_separated: Optional[bool] = None


class DonationResponse(MongoBaseModel):
    id: str = Field(..., alias="_id")
    donation_code: str
    donor_id: str
    blood_bank_id: str
    donation_date: datetime
    volume_ml: int
    donation_type: BloodComponent
    hemoglobin_g_dl: float
    blood_pressure: str
    screening_status: str
    components_separated: bool = False
    created_at: datetime
