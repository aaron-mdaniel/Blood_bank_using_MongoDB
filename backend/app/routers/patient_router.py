"""
Patient CRUD REST API Router (RBAC + ABAC protected).
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.models.permissions import Permission
from app.repositories.patient_repository import PatientRepository
from app.schemas.patient_schema import PatientCreate, PatientUpdate, PatientResponse
from app.security import abac
from app.security.dependencies import require_permissions
from app.security.encryption import (
    PATIENT_ENCRYPTED_FIELDS,
    decrypt_fields,
    encrypt_fields,
)

router = APIRouter(prefix="/patients", tags=["Patients"])
patient_repo = PatientRepository()


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    payload: PatientCreate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.PATIENTS_WRITE)),
):
    """Registers patient record under a specific hospital and attending physician."""
    abac.authorize_patient_create(current_user, payload.hospital_id, payload.attending_doctor_id)
    if patient_repo.get_by_hospital_mrn(payload.hospital_id, payload.mrn):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Patient MRN '{payload.mrn}' already exists for this hospital."
        )

    patient_dict = encrypt_fields(payload.model_dump(), PATIENT_ENCRYPTED_FIELDS, context="patients")

    try:
        created = patient_repo.create(patient_dict)
        return decrypt_fields(created, PATIENT_ENCRYPTED_FIELDS, context="patients")
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A patient with this MRN already exists under this hospital."
        )


@router.get("", response_model=List[PatientResponse])
async def list_patients(
    hospital_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.PATIENTS_READ)),
):
    """Retrieves list of patients with hospital or doctor filters."""
    query = {}
    if hospital_id:
        query["hospital_id"] = hospital_id
    if doctor_id:
        query["attending_doctor_id"] = doctor_id
    abac.scope_patient_query(current_user, query)
    docs = patient_repo.find_many(query, skip=skip, limit=limit)
    return [decrypt_fields(doc, PATIENT_ENCRYPTED_FIELDS, context="patients") for doc in docs]


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: str,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.PATIENTS_READ)),
):
    """Retrieves single patient record."""
    patient = patient_repo.get_by_id(patient_id)
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    abac.authorize_patient_access(current_user, patient)
    return decrypt_fields(patient, PATIENT_ENCRYPTED_FIELDS, context="patients")


@router.put("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: str,
    payload: PatientUpdate,
    current_user: Dict[str, Any] = Depends(require_permissions(Permission.PATIENTS_WRITE)),
):
    """Updates clinical indication or notes."""
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update.")

    existing = patient_repo.get_by_id(patient_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    abac.authorize_patient_access(current_user, existing)

    encrypted_update = encrypt_fields(update_data, PATIENT_ENCRYPTED_FIELDS, context="patients")
    updated = patient_repo.update(patient_id, encrypted_update)
    return decrypt_fields(updated, PATIENT_ENCRYPTED_FIELDS, context="patients")
