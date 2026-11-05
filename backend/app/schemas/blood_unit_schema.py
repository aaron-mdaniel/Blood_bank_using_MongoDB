"""
Pydantic schemas for BloodUnit entity.
Models individual, independently tracked blood unit documents.
"""
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
from app.models.enums import BloodGroup, RhFactor, BloodComponent, BloodUnitStatus
from app.schemas.common_schema import MongoBaseModel


class StorageLocation(BaseModel):
    refrigerator_id: str = Field(..., description="Refrigerator or storage freezer ID")
    shelf: str = Field(..., description="Shelf identifier")
    slot: Optional[str] = Field(default=None, description="Specific rack/tray/slot")


class BloodUnitCreate(BaseModel):
    unit_id: str = Field(..., description="Unique barcoded unit identifier")
    source_donation_id: str = Field(..., description="Source donation identifier")
    blood_bank_id: str = Field(..., description="Blood bank facility identifier")
    blood_group: BloodGroup
    rh_factor: RhFactor
    component_type: BloodComponent
    volume_ml: int = Field(..., ge=50, le=500)
    collection_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expiry_date: datetime = Field(..., description="Calculated expiration timestamp")
    storage_location: StorageLocation
    status: BloodUnitStatus = Field(default=BloodUnitStatus.AVAILABLE)


class BloodUnitUpdate(BaseModel):
    status: Optional[BloodUnitStatus] = None
    storage_location: Optional[StorageLocation] = None
    reserved_for_request_id: Optional[str] = None


class BloodUnitFilter(BaseModel):
    blood_group: Optional[BloodGroup] = None
    rh_factor: Optional[RhFactor] = None
    component_type: Optional[BloodComponent] = None
    status: Optional[BloodUnitStatus] = None
    blood_bank_id: Optional[str] = None


class BloodUnitResponse(MongoBaseModel):
    id: str = Field(..., alias="_id")
    unit_id: str
    source_donation_id: str
    blood_bank_id: str
    blood_group: BloodGroup
    rh_factor: RhFactor
    component_type: BloodComponent
    volume_ml: int
    collection_date: datetime
    expiry_date: datetime
    storage_location: StorageLocation
    status: BloodUnitStatus
    reserved_for_request_id: Optional[str] = None
    allocated_at: Optional[datetime] = None
    version: int = 1
    created_at: datetime
