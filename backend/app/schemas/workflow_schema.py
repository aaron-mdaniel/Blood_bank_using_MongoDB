"""
Pydantic schemas for Phase 8 Blood Bank Workflows:
- Component Separation from Donations
- Request Approval / Rejection / Atomic Allocation
"""
from typing import List, Optional
from pydantic import BaseModel, Field

from app.models.enums import BloodComponent, BloodGroup, RhFactor
from app.schemas.blood_request_schema import BloodRequestResponse
from app.schemas.blood_unit_schema import BloodUnitResponse, StorageLocation


class ComponentSeparationRequest(BaseModel):
    components: List[BloodComponent] = Field(
        default=[BloodComponent.RBC, BloodComponent.FFP, BloodComponent.PLATELETS],
        min_length=1,
        description="Blood components to derive from the screened donation",
    )
    storage_location: StorageLocation = Field(
        default_factory=lambda: StorageLocation(refrigerator_id="REF-MAIN-01", shelf="A1", slot="AUTO"),
        description="Initial cold-chain storage location for generated units",
    )
    blood_group: Optional[BloodGroup] = Field(
        default=None,
        description="Optional override if donor record is external; normally derived from donor profile",
    )
    rh_factor: Optional[RhFactor] = Field(
        default=None,
        description="Optional override if donor record is external; normally derived from donor profile",
    )


class ComponentSeparationResponse(BaseModel):
    donation_id: str
    donation_code: str
    components_separated: bool
    generated_units: List[BloodUnitResponse]


class RequestDecisionPayload(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=300, description="Clinical or operational decision note")


class AllocationRequestPayload(BaseModel):
    blood_bank_id: Optional[str] = Field(default=None, description="Optional blood bank scope filter")
    allow_compatible_substitutes: bool = Field(
        default=True,
        description="Use ABO/Rh academic compatibility substitution if exact match stock is exhausted",
    )


class AllocationResponse(BaseModel):
    request: BloodRequestResponse
    allocated_units: List[BloodUnitResponse]
    newly_allocated_count: int
    remaining_units_needed: int
    compatibility_disclaimer: str
