"""
BloodCamps REST API Router (Geospatial 2dsphere queries + RBAC/ABAC).
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.models.enums import UserRole
from app.models.permissions import Permission
from app.repositories.blood_camp_repository import BloodCampRepository
from app.schemas.audit_schema import AuditStatus
from app.schemas.blood_camp_schema import BloodCampCreate, BloodCampResponse, BloodCampUpdate, CampStatus
from app.security.dependencies import require_permissions
from app.services.audit_service import AuditService

router = APIRouter(prefix="/blood-camps", tags=["Blood Camps"])
camp_repo = BloodCampRepository()
audit_service = AuditService()


def _enforce_camp_bb_scope(current_user: Dict[str, Any], organizer_bb_id: str) -> None:
    if current_user.get("role") == UserRole.BLOOD_BANK_STAFF.value:
        assigned = current_user.get("blood_bank_id")
        if not assigned or str(organizer_bb_id) != str(assigned):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Cannot manage blood camps outside your assigned blood bank.",
            )


@router.post("", response_model=BloodCampResponse, status_code=status.HTTP_201_CREATED)
async def create_blood_camp(
    payload: BloodCampCreate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.CAMPS_WRITE)),
):
    """Creates a community blood donation camp with GeoJSON coordinates."""
    _enforce_camp_bb_scope(current_user, payload.organizer_blood_bank_id)
    if payload.end_time <= payload.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Camp end_time must be after start_time.",
        )
    if camp_repo.get_by_code(payload.camp_code):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Blood camp code '{payload.camp_code}' already exists.",
        )

    try:
        created = camp_repo.create(payload.model_dump())
        audit_service.log_event(
            action="BLOOD_CAMP_CREATED",
            resource_type="blood_camps",
            resource_id=created["_id"],
            status=AuditStatus.SUCCESS.value,
            actor=current_user,
            metadata={"camp_code": created["camp_code"], "organizer_blood_bank_id": created["organizer_blood_bank_id"]},
        )
        return created
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Blood camp code already exists.")


@router.get("/nearby", response_model=List[BloodCampResponse])
async def find_nearby_camps(
    longitude: float = Query(..., ge=-180.0, le=180.0),
    latitude: float = Query(..., ge=-90.0, le=90.0),
    radius_km: float = Query(50.0, ge=1.0, le=500.0),
    camp_status: Optional[CampStatus] = Query(None, alias="status"),
    limit: int = Query(10, ge=1, le=50),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.CAMPS_READ)),
):
    """Finds blood camps within radius_km using MongoDB 2dsphere geospatial indexing."""
    return camp_repo.find_nearby(
        longitude=longitude,
        latitude=latitude,
        max_distance_meters=int(radius_km * 1000),
        status_filter=camp_status.value if camp_status else None,
        limit=limit,
    )


@router.get("", response_model=List[BloodCampResponse])
async def list_blood_camps(
    camp_status: Optional[CampStatus] = Query(None, alias="status"),
    organizer_blood_bank_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.CAMPS_READ)),
):
    """Lists blood camps sorted by start_time."""
    query: Dict[str, Any] = {}
    if camp_status:
        query["status"] = camp_status.value
    if organizer_blood_bank_id:
        query["organizer_blood_bank_id"] = organizer_blood_bank_id
    return camp_repo.find_many(query, skip=skip, limit=limit, sort=[("start_time", 1)])


@router.get("/{camp_id}", response_model=BloodCampResponse)
async def get_blood_camp(
    camp_id: str,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.CAMPS_READ)),
):
    """Retrieves a single blood camp by camp_code or _id."""
    camp = camp_repo.get_by_code(camp_id)
    if not camp:
        try:
            camp = camp_repo.get_by_id(camp_id)
        except ValueError:
            camp = None
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood camp not found.")
    return camp


@router.put("/{camp_id}", response_model=BloodCampResponse)
async def update_blood_camp(
    camp_id: str,
    payload: BloodCampUpdate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.CAMPS_WRITE)),
):
    """Updates blood camp schedule, capacity, or status."""
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update.")

    target = camp_repo.get_by_code(camp_id)
    if not target:
        try:
            target = camp_repo.get_by_id(camp_id)
        except ValueError:
            target = None
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood camp not found.")

    _enforce_camp_bb_scope(current_user, target["organizer_blood_bank_id"])
    return camp_repo.update(target["_id"], update_data)
