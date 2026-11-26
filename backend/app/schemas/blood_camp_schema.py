"""
Pydantic schemas for Community Blood Camps (blood_camps collection) with GeoJSON Point locations.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

from app.schemas.common_schema import MongoBaseModel
from app.schemas.hospital_schema import GeoPoint


class CampStatus(str, Enum):
    UPCOMING = "UPCOMING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class BloodCampCreate(BaseModel):
    camp_code: str = Field(..., min_length=3, max_length=60)
    title: str = Field(..., min_length=3, max_length=200)
    organizer_blood_bank_id: str = Field(..., description="Organizing blood bank ID")
    location: GeoPoint = Field(..., description="GeoJSON Point [longitude, latitude]")
    address: str = Field(..., min_length=3, max_length=300)
    start_time: datetime
    end_time: datetime
    capacity_donors: int = Field(default=100, ge=5, le=5000)
    status: CampStatus = Field(default=CampStatus.UPCOMING)


class BloodCampUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    address: Optional[str] = Field(default=None, min_length=3, max_length=300)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    capacity_donors: Optional[int] = Field(default=None, ge=5, le=5000)
    status: Optional[CampStatus] = None


class BloodCampResponse(MongoBaseModel):
    id: str = Field(..., alias="_id")
    camp_code: str
    title: str
    organizer_blood_bank_id: str
    location: GeoPoint
    address: str
    start_time: datetime
    end_time: datetime
    capacity_donors: int
    status: CampStatus
    distance_km: Optional[float] = None
    created_at: datetime
