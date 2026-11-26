"""
BloodRequest CRUD REST API Router (RBAC + ABAC protected).
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.models.enums import RequestStatus, RequestPriority
from app.models.permissions import Permission
from app.repositories.blood_request_repository import BloodRequestRepository
from app.repositories.patient_repository import PatientRepository
from app.schemas.blood_request_schema import (
    BloodRequestCreate,
    BloodRequestUpdate,
    BloodRequestResponse,
)
from app.schemas.workflow_schema import (
    AllocationRequestPayload,
    AllocationResponse,
    RequestDecisionPayload,
)
from app.security import abac
from app.security.dependencies import require_permissions
from app.services.audit_service import AuditService
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/blood-requests", tags=["Blood Requests"])
request_repo = BloodRequestRepository()
patient_repo = PatientRepository()
audit_service = AuditService()
workflow_service = WorkflowService(request_repo=request_repo, audit_service=audit_service)


@router.post("", response_model=BloodRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_blood_request(
    payload: BloodRequestCreate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.BLOOD_REQUESTS_WRITE)),
):
    """Submits a new hospital blood transfusion request (triggers emergency alert if CRITICAL)."""
    try:
        return workflow_service.submit_blood_request(payload, current_user, patient_repo=patient_repo)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A request with this code already exists."
        )


@router.get("/triage", response_model=List[BloodRequestResponse])
async def get_triage_queue(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.BLOOD_REQUESTS_READ)),
):
    """Retrieves active requests prioritized by clinical urgency (CRITICAL -> URGENT -> ROUTINE)."""
    query: Dict[str, Any] = {
        "status": {"$in": [RequestStatus.PENDING.value, RequestStatus.APPROVED.value, RequestStatus.PARTIALLY_ALLOCATED.value]}
    }
    abac.scope_blood_request_query(current_user, query)
    return request_repo.find_many(
        query,
        skip=skip,
        limit=limit,
        sort=[("priority_weight", 1), ("created_at", 1)],
    )


@router.get("", response_model=List[BloodRequestResponse])
async def list_blood_requests(
    hospital_id: Optional[str] = None,
    req_status: Optional[RequestStatus] = Query(None, alias="status"),
    priority: Optional[RequestPriority] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.BLOOD_REQUESTS_READ)),
):
    """Retrieves blood requests with triage filtering."""
    query = {}
    if hospital_id:
        query["hospital_id"] = hospital_id
    if req_status:
        query["status"] = req_status.value
    if priority:
        query["priority"] = priority.value

    abac.scope_blood_request_query(current_user, query)
    return request_repo.find_many(
        query, skip=skip, limit=limit, sort=[("priority", -1), ("created_at", 1)]
    )


@router.get("/{request_id}", response_model=BloodRequestResponse)
async def get_blood_request(
    request_id: str,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.BLOOD_REQUESTS_READ)),
):
    """Retrieves single blood request by request_code or _id."""
    req = request_repo.get_by_code(request_id) or request_repo.get_by_id(request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
    abac.authorize_blood_request_access(current_user, req)
    return req


@router.put("/{request_id}", response_model=BloodRequestResponse)
async def update_blood_request(
    request_id: str,
    payload: BloodRequestUpdate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.BLOOD_REQUESTS_APPROVE)),
):
    """Updates blood request status (approve/reject/allocate) or allocation details."""
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update.")

    target = request_repo.get_by_code(request_id) or request_repo.get_by_id(request_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")

    updated = request_repo.update(target["_id"], update_data)
    new_status = updated.get("status")
    status_action_map = {
        RequestStatus.APPROVED.value: "BLOOD_REQUEST_APPROVED",
        RequestStatus.REJECTED.value: "BLOOD_REQUEST_REJECTED",
        RequestStatus.ALLOCATED.value: "BLOOD_REQUEST_ALLOCATED",
        RequestStatus.PARTIALLY_ALLOCATED.value: "BLOOD_REQUEST_ALLOCATED",
    }
    audit_service.log_event(
        action=status_action_map.get(new_status, "BLOOD_REQUEST_UPDATED"),
        resource_type="blood_requests",
        resource_id=target["_id"],
        actor=current_user,
        metadata={
            "request_code": target.get("request_code"),
            "previous_status": target.get("status"),
            "new_status": new_status,
        },
    )
    return updated


@router.post("/{request_id}/approve", response_model=BloodRequestResponse)
async def approve_blood_request(
    request_id: str,
    payload: RequestDecisionPayload = RequestDecisionPayload(),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.BLOOD_REQUESTS_APPROVE)),
):
    """Approves a PENDING blood request and notifies the requesting facility."""
    return workflow_service.decide_request(
        request_id=request_id,
        approve=True,
        reason=payload.reason,
        current_user=current_user,
    )


@router.post("/{request_id}/reject", response_model=BloodRequestResponse)
async def reject_blood_request(
    request_id: str,
    payload: RequestDecisionPayload = RequestDecisionPayload(),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.BLOOD_REQUESTS_APPROVE)),
):
    """Rejects a PENDING or APPROVED blood request and notifies the requesting facility."""
    return workflow_service.decide_request(
        request_id=request_id,
        approve=False,
        reason=payload.reason,
        current_user=current_user,
    )


@router.post("/{request_id}/allocate", response_model=AllocationResponse)
async def allocate_blood_request(
    request_id: str,
    payload: AllocationRequestPayload = AllocationRequestPayload(),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.BLOOD_REQUESTS_APPROVE)),
):
    """
    Atomically allocates compatible unexpired blood units (FIFO by earliest expiry)
    to satisfy the blood request without duplicate allocation.
    """
    return workflow_service.allocate_request_units(
        request_id=request_id,
        payload=payload,
        current_user=current_user,
    )
