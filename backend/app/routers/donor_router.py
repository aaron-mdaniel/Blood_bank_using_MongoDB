"""
Donor CRUD REST API Router (RBAC + ABAC protected).
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.models.permissions import Permission
from app.repositories.donor_repository import DonorRepository
from app.schemas.donor_schema import DonorCreate, DonorUpdate, DonorResponse
from app.security import abac
from app.security.dependencies import require_permissions
from app.security.encryption import (
    DONOR_ENCRYPTED_FIELDS,
    decrypt_fields,
    encrypt_fields,
)

router = APIRouter(prefix="/donors", tags=["Donors"])
donor_repo = DonorRepository()


@router.post("", response_model=DonorResponse, status_code=status.HTTP_201_CREATED)
async def create_donor(
    payload: DonorCreate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.DONORS_WRITE)),
):
    """Registers a new blood donor record."""
    abac.authorize_donor_create(current_user, payload.user_id)
    if donor_repo.get_by_card_number(payload.donor_card_number):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Donor card number '{payload.donor_card_number}' already exists."
        )

    donor_dict = encrypt_fields(payload.model_dump(), DONOR_ENCRYPTED_FIELDS, context="donors")

    try:
        created = donor_repo.create(donor_dict)
        return decrypt_fields(created, DONOR_ENCRYPTED_FIELDS, context="donors")
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
    eligibility_status: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.DONORS_READ)),
):
    """Retrieves list of donors with optional blood group and eligibility filtering."""
    query = {}
    if blood_group:
        query["blood_group"] = blood_group
    if rh_factor:
        query["rh_factor"] = rh_factor
    if eligibility_status:
        query["eligibility_status"] = eligibility_status
    abac.scope_donor_query(current_user, query)
    docs = donor_repo.find_many(query, skip=skip, limit=limit)
    return [decrypt_fields(doc, DONOR_ENCRYPTED_FIELDS, context="donors") for doc in docs]


@router.get("/{donor_id}", response_model=DonorResponse)
async def get_donor(
    donor_id: str,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.DONORS_READ)),
):
    """Retrieves single donor by ID."""
    donor = donor_repo.get_by_id(donor_id)
    if not donor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor not found.")
    abac.authorize_donor_access(current_user, donor)
    return decrypt_fields(donor, DONOR_ENCRYPTED_FIELDS, context="donors")


@router.put("/{donor_id}", response_model=DonorResponse)
async def update_donor(
    donor_id: str,
    payload: DonorUpdate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.DONORS_WRITE)),
):
    """Updates donor eligibility or contact details."""
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update.")

    existing = donor_repo.get_by_id(donor_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor not found.")
    abac.authorize_donor_update(current_user, existing, update_data)

    encrypted_update = encrypt_fields(update_data, DONOR_ENCRYPTED_FIELDS, context="donors")
    updated = donor_repo.update(donor_id, encrypted_update)
    return decrypt_fields(updated, DONOR_ENCRYPTED_FIELDS, context="donors")


@router.delete("/{donor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_donor(
    donor_id: str,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.DONORS_DELETE)),
):
    """Deletes donor record (Admin only)."""
    deleted = donor_repo.delete(donor_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donor not found.")
    return None
