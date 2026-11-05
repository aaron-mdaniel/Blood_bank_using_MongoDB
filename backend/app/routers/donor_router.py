"""
Donor CRUD REST API Router.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.repositories.donor_repository import DonorRepository
from app.schemas.donor_schema import DonorCreate, DonorUpdate, DonorResponse

router = APIRouter(prefix="/donors", tags=["Donors"])
donor_repo = DonorRepository()


@router.post("", response_model=DonorResponse, status_code=status.HTTP_201_CREATED)
async def create_donor(payload: DonorCreate):
    """Registers a new blood donor record."""
    if donor_repo.get_by_card_number(payload.donor_card_number):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Donor card number '{payload.donor_card_number}' already exists."
        )

    donor_dict = payload.model_dump()
    # In Phase 2, placeholder encrypted fields; Phase 6 introduces full AES-256-GCM cipher service
    donor_dict["contact_phone_encrypted"] = f"enc_{donor_dict.pop('contact_phone')}"
    donor_dict["address_encrypted"] = f"enc_{donor_dict.pop('address')}"
    if donor_dict.get("emergency_contact"):
        donor_dict["emergency_contact_encrypted"] = f"enc_{donor_dict.pop('emergency_contact')}"
    if donor_dict.get("medical_screening_notes"):
        donor_dict["medical_screening_notes_encrypted"] = f"enc_{donor_dict.pop('medical_screening_notes')}"

    try:
        created = donor_repo.create(donor_dict)
        return created
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A donor with this user_id or donor_card_number already exists."
        )


@router.get("", response_model=List[DonorResponse])
async def list_donors(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    blood_group: Optional[str] = None,
    rh_factor: Optional[str] = None,
    eligibility_status: Optional[str] = None
):
    """Retrieves list of donors with optional blood group and eligibility filtering."""
    query = {}
    if blood_group:
        query["blood_group"] = blood_group
    if rh_factor:
        query["rh_factor"] = rh_factor
    if eligibility_status:
        query["eligibility_status"] = eligibility_status
    return donor_repo.find_many(query, skip=skip, limit=limit)


@router.get("/{donor_id}", response_model=DonorResponse)
async def get_donor(donor_id: str):
    """Retrieves single donor by ID."""
    donor = donor_repo.get_by_id(donor_id)
    if not donor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor not found.")
    return donor


@router.put("/{donor_id}", response_model=DonorResponse)
async def update_donor(donor_id: str, payload: DonorUpdate):
    """Updates donor eligibility or contact details."""
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update.")

    updated = donor_repo.update(donor_id, update_data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor not found.")
    return updated


@router.delete("/{donor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_donor(donor_id: str):
    """Deletes donor record."""
    deleted = donor_repo.delete(donor_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor not found.")
    return None
