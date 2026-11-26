"""
Hospital CRUD REST API Router (RBAC protected).
Supports geospatial query endpoints for locating nearby registered medical centers.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.models.permissions import Permission
from app.repositories.hospital_repository import HospitalRepository
from app.schemas.hospital_schema import HospitalCreate, HospitalUpdate, HospitalResponse
from app.security.dependencies import require_permissions
from app.security.encryption import (
    HOSPITAL_ENCRYPTED_FIELDS,
    decrypt_fields,
    encrypt_fields,
)

router = APIRouter(prefix="/hospitals", tags=["Hospitals"])
hospital_repo = HospitalRepository()


@router.post("", response_model=HospitalResponse, status_code=status.HTTP_201_CREATED)
async def create_hospital(
    payload: HospitalCreate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.HOSPITALS_WRITE)),
):
    """Registers a hospital facility with geospatial coordinates (Admin only)."""
    if hospital_repo.get_by_license(payload.license_number):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"License number '{payload.license_number}' is already registered."
        )

    hosp_dict = encrypt_fields(payload.model_dump(), HOSPITAL_ENCRYPTED_FIELDS, context="hospitals")

    try:
        created = hospital_repo.create(hosp_dict)
        return decrypt_fields(created, HOSPITAL_ENCRYPTED_FIELDS, context="hospitals")
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A hospital with this license number already exists."
        )


@router.get("/nearby", response_model=List[HospitalResponse])
async def find_nearby_hospitals(
    longitude: float = Query(..., ge=-180.0, le=180.0),
    latitude: float = Query(..., ge=-90.0, le=90.0),
    radius_km: float = Query(50.0, ge=1.0, le=500.0),
    limit: int = Query(10, ge=1, le=50),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.HOSPITALS_READ)),
):
    """Finds hospitals within proximity radius (km) using MongoDB geospatial index."""
    max_meters = int(radius_km * 1000)
    docs = hospital_repo.find_nearby(longitude, latitude, max_distance_meters=max_meters, limit=limit)
    return [decrypt_fields(doc, HOSPITAL_ENCRYPTED_FIELDS, context="hospitals") for doc in docs]


@router.get("", response_model=List[HospitalResponse])
async def list_hospitals(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.HOSPITALS_READ)),
):
    """Retrieves paginated list of registered hospitals."""
    docs = hospital_repo.find_many({}, skip=skip, limit=limit)
    return [decrypt_fields(doc, HOSPITAL_ENCRYPTED_FIELDS, context="hospitals") for doc in docs]


@router.get("/{hospital_id}", response_model=HospitalResponse)
async def get_hospital(
    hospital_id: str,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.HOSPITALS_READ)),
):
    """Retrieves single hospital record."""
    hosp = hospital_repo.get_by_id(hospital_id)
    if not hosp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found.")
    return decrypt_fields(hosp, HOSPITAL_ENCRYPTED_FIELDS, context="hospitals")


@router.put("/{hospital_id}", response_model=HospitalResponse)
async def update_hospital(
    hospital_id: str,
    payload: HospitalUpdate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.HOSPITALS_WRITE)),
):
    """Updates hospital profile (Admin only)."""
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update.")

    encrypted_update = encrypt_fields(update_data, HOSPITAL_ENCRYPTED_FIELDS, context="hospitals")
    updated = hospital_repo.update(hospital_id, encrypted_update)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found.")
    return decrypt_fields(updated, HOSPITAL_ENCRYPTED_FIELDS, context="hospitals")
