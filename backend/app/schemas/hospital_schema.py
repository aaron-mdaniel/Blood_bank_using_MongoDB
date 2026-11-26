"""
Pydantic schemas for Hospital entity.
Includes GeoJSON Point schema for geospatial MongoDB indexing and spatial queries.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from app.models.enums import HospitalVerificationStatus
from app.schemas.common_schema import MongoBaseModel


class GeoPoint(BaseModel):
    type: str = Field(default="Point", description="GeoJSON type")
    coordinates: List[float] = Field(..., description="[longitude, latitude]")

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, v: List[float]) -> List[float]:
        if len(v) != 2:
            raise ValueError("Coordinates must be a list of two floats: [longitude, latitude]")
        lon, lat = v[0], v[1]
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(f"Longitude {lon} out of range [-180, 180]")
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"Latitude {lat} out of range [-90, 90]")
        return v


class HospitalCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    license_number: str = Field(..., description="Unique government regulatory license number")
    location: GeoPoint = Field(..., description="Geographical location coordinates")
    address: str = Field(..., description="Physical street address")
    emergency_helpline: str = Field(..., description="24/7 emergency dispatch helpline")
    verification_status: HospitalVerificationStatus = Field(default=HospitalVerificationStatus.VERIFIED)


class HospitalUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[GeoPoint] = None
    address: Optional[str] = None
    emergency_helpline: Optional[str] = None
    verification_status: Optional[HospitalVerificationStatus] = None


class HospitalResponse(MongoBaseModel):
    id: str = Field(..., alias="_id")
    name: str
    license_number: str
    location: GeoPoint
    address: Optional[str] = None
    emergency_helpline: Optional[str] = None
    address_encrypted: Optional[str] = None
    emergency_helpline_encrypted: Optional[str] = None
    verification_status: HospitalVerificationStatus
    created_at: datetime
