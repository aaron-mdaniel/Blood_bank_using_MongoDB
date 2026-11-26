"""
Donation CRUD REST API Router (RBAC + ABAC protected).
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.models.permissions import Permission
from app.repositories.donation_repository import DonationRepository
from app.repositories.donor_repository import DonorRepository
from app.schemas.donation_schema import DonationCreate, DonationUpdate, DonationResponse
from app.security import abac
from app.security.dependencies import require_permissions

router = APIRouter(prefix="/donations", tags=["Donations"])
donation_repo = DonationRepository()
donor_repo = DonorRepository()


@router.post("", response_model=DonationResponse, status_code=status.HTTP_201_CREATED)
async def record_donation(
    payload: DonationCreate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.DONATIONS_WRITE)),
):
    """Logs a new blood donation event."""
    abac.authorize_donation_create(current_user, payload.blood_bank_id)
    if donation_repo.get_by_code(payload.donation_code):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Donation code '{payload.donation_code}' has already been processed."
        )

    donation_dict = payload.model_dump()
    donation_dict["components_separated"] = False

    try:
        created = donation_repo.create(donation_dict)
        return created
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Donation code already exists."
        )


@router.get("", response_model=List[DonationResponse])
async def list_donations(
    donor_id: Optional[str] = None,
    blood_bank_id: Optional[str] = None,
    screening_status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.DONATIONS_READ)),
):
    """Retrieves donation history with optional donor and facility filters."""
    query = {}
    if donor_id:
        query["donor_id"] = donor_id
    if blood_bank_id:
        query["blood_bank_id"] = blood_bank_id
    if screening_status:
        query["screening_status"] = screening_status
    scoped = abac.scope_donation_query(current_user, query, donor_repo)
    if scoped is None:
        return []
    return donation_repo.find_many(scoped, skip=skip, limit=limit, sort=[("donation_date", -1)])


@router.get("/{donation_id}", response_model=DonationResponse)
async def get_donation(
    donation_id: str,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.DONATIONS_READ)),
):
    """Retrieves single donation record."""
    donation = donation_repo.get_by_id(donation_id)
    if not donation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donation record not found.")
    abac.authorize_donation_access(current_user, donation, donor_repo)
    return donation


@router.put("/{donation_id}", response_model=DonationResponse)
async def update_donation(
    donation_id: str,
    payload: DonationUpdate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.DONATIONS_WRITE)),
):
    """Updates screening status or component separation flag."""
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update.")

    existing = donation_repo.get_by_id(donation_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donation record not found.")
    abac.authorize_donation_access(current_user, existing, donor_repo)

    updated = donation_repo.update(donation_id, update_data)
    return updated
