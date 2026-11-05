"""
BloodUnit CRUD REST API Router.
Tracks individual blood unit documents for granular inventory state and shelf life.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.models.enums import BloodGroup, RhFactor, BloodComponent, BloodUnitStatus
from app.repositories.blood_unit_repository import BloodUnitRepository
from app.schemas.blood_unit_schema import BloodUnitCreate, BloodUnitUpdate, BloodUnitResponse

router = APIRouter(prefix="/blood-units", tags=["Blood Units"])
unit_repo = BloodUnitRepository()


@router.post("", response_model=BloodUnitResponse, status_code=status.HTTP_201_CREATED)
async def create_blood_unit(payload: BloodUnitCreate):
    """Adds a new individual blood unit document into inventory."""
    if unit_repo.get_by_unit_id(payload.unit_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Blood unit ID '{payload.unit_id}' already exists in inventory."
        )

    unit_dict = payload.model_dump()
    unit_dict["version"] = 1
    unit_dict["reserved_for_request_id"] = None
    unit_dict["allocated_at"] = None

    try:
        created = unit_repo.create(unit_dict)
        return created
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A blood unit with this unit_id already exists."
        )


@router.get("", response_model=List[BloodUnitResponse])
async def list_blood_units(
    blood_group: Optional[BloodGroup] = None,
    rh_factor: Optional[RhFactor] = None,
    component_type: Optional[BloodComponent] = None,
    unit_status: Optional[BloodUnitStatus] = Query(None, alias="status"),
    blood_bank_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Retrieves blood units with flexible multi-field filtering."""
    query = {}
    if blood_group:
        query["blood_group"] = blood_group.value
    if rh_factor:
        query["rh_factor"] = rh_factor.value
    if component_type:
        query["component_type"] = component_type.value
    if unit_status:
        query["status"] = unit_status.value
    if blood_bank_id:
        query["blood_bank_id"] = blood_bank_id

    return unit_repo.find_many(query, skip=skip, limit=limit, sort=[("expiry_date", 1)])


@router.get("/{unit_id}", response_model=BloodUnitResponse)
async def get_blood_unit(unit_id: str):
    """Retrieves single blood unit by unit_id or _id."""
    unit = unit_repo.get_by_unit_id(unit_id) or unit_repo.get_by_id(unit_id)
    if not unit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood unit not found.")
    return unit


@router.put("/{unit_id}", response_model=BloodUnitResponse)
async def update_blood_unit(unit_id: str, payload: BloodUnitUpdate):
    """Updates unit status (e.g. DISCARDED, TRANSFUSED) or storage location."""
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update.")

    target = unit_repo.get_by_unit_id(unit_id) or unit_repo.get_by_id(unit_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood unit not found.")

    updated = unit_repo.update(target["_id"], update_data)
    return updated
