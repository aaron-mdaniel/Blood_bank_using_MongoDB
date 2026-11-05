"""
BloodRequest CRUD REST API Router.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.models.enums import RequestStatus, RequestPriority
from app.repositories.blood_request_repository import BloodRequestRepository
from app.schemas.blood_request_schema import (
    BloodRequestCreate,
    BloodRequestUpdate,
    BloodRequestResponse,
)

router = APIRouter(prefix="/blood-requests", tags=["Blood Requests"])
request_repo = BloodRequestRepository()


@router.post("", response_model=BloodRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_blood_request(payload: BloodRequestCreate):
    """Submits a new hospital blood transfusion request."""
    if request_repo.get_by_code(payload.request_code):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request code '{payload.request_code}' already exists."
        )

    req_dict = payload.model_dump()
    req_dict["status"] = RequestStatus.PENDING.value
    req_dict["allocated_units"] = []

    try:
        created = request_repo.create(req_dict)
        return created
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A request with this code already exists."
        )


@router.get("", response_model=List[BloodRequestResponse])
async def list_blood_requests(
    hospital_id: Optional[str] = None,
    req_status: Optional[RequestStatus] = Query(None, alias="status"),
    priority: Optional[RequestPriority] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Retrieves blood requests with triage filtering."""
    query = {}
    if hospital_id:
        query["hospital_id"] = hospital_id
    if req_status:
        query["status"] = req_status.value
    if priority:
        query["priority"] = priority.value

    return request_repo.find_many(
        query, skip=skip, limit=limit, sort=[("priority", -1), ("created_at", 1)]
    )


@router.get("/{request_id}", response_model=BloodRequestResponse)
async def get_blood_request(request_id: str):
    """Retrieves single blood request by request_code or _id."""
    req = request_repo.get_by_code(request_id) or request_repo.get_by_id(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    return req


@router.put("/{request_id}", response_model=BloodRequestResponse)
async def update_blood_request(request_id: str, payload: BloodRequestUpdate):
    """Updates blood request status or allocation details."""
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update.")

    target = request_repo.get_by_code(request_id) or request_repo.get_by_id(request_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")

    updated = request_repo.update(target["_id"], update_data)
    return updated
