"""
Core Blood Bank Workflow Service (Phase 8):
- Donation recording with donor eligibility & interval updates
- Blood component separation from screened donations
- Blood request triage, approval, rejection, and atomic FIFO compatible allocation
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status

from app.models.enums import (
    BloodUnitStatus,
    DonorEligibility,
    RequestPriority,
    RequestStatus,
    UserRole,
)
from app.repositories.blood_request_repository import BloodRequestRepository
from app.repositories.blood_unit_repository import BloodUnitRepository
from app.repositories.donation_repository import DonationRepository
from app.repositories.donor_repository import DonorRepository
from app.schemas.audit_schema import AuditStatus
from app.schemas.blood_request_schema import BloodRequestCreate
from app.schemas.donation_schema import DonationCreate
from app.schemas.notification_schema import NotificationType
from app.schemas.workflow_schema import (
    AllocationRequestPayload,
    ComponentSeparationRequest,
)
from app.security import abac
from app.services.audit_service import AuditService
from app.services.compatibility import (
    ACADEMIC_DISCLAIMER,
    COMPONENT_SPECS,
    get_compatible_donor_types,
)
from app.services.notification_service import NotificationService


class WorkflowService:
    """
    Orchestrates clinical blood bank workflows across donations, inventory,
    blood requests, atomic allocation, audit trails, and notifications.
    """

    def __init__(
        self,
        donor_repo: DonorRepository = None,
        donation_repo: DonationRepository = None,
        unit_repo: BloodUnitRepository = None,
        request_repo: BloodRequestRepository = None,
        audit_service: AuditService = None,
        notification_service: NotificationService = None,
    ):
        self.donor_repo = donor_repo or DonorRepository()
        self.donation_repo = donation_repo or DonationRepository()
        self.unit_repo = unit_repo or BloodUnitRepository()
        self.request_repo = request_repo or BloodRequestRepository()
        self.audit_service = audit_service or AuditService()
        self.notification_service = notification_service or NotificationService(unit_repo=self.unit_repo)

    # ==========================================
    # 1. Donation Recording & Component Separation
    # ==========================================

    def record_donation(self, payload: DonationCreate, current_user: Dict[str, Any]) -> Dict[str, Any]:
        abac.authorize_donation_create(current_user, payload.blood_bank_id)
        if self.donation_repo.get_by_code(payload.donation_code):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Donation code '{payload.donation_code}' has already been processed.",
            )

        # If donor exists in DB, validate eligibility (cannot accept PERMANENT_DEFERRED)
        donor_doc = None
        try:
            donor_doc = self.donor_repo.get_by_id(payload.donor_id)
        except ValueError:
            donor_doc = None

        if donor_doc and donor_doc.get("eligibility_status") == DonorEligibility.PERMANENT_DEFERRED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot record donation for a permanently deferred donor.",
            )

        donation_dict = payload.model_dump()
        donation_dict["components_separated"] = False
        created = self.donation_repo.create(donation_dict)

        if donor_doc:
            donation_dt = payload.donation_date
            if donation_dt.tzinfo is None:
                donation_dt = donation_dt.replace(tzinfo=timezone.utc)
            self.donor_repo.update_donation_dates(
                donor_doc["_id"],
                last_date=donation_dt,
                next_eligible=donation_dt + timedelta(days=56),
            )

        self.audit_service.log_event(
            action="DONATION_RECORDED",
            resource_type="donations",
            resource_id=created["_id"],
            status=AuditStatus.SUCCESS.value,
            actor=current_user,
            metadata={
                "donation_code": created["donation_code"],
                "blood_bank_id": created["blood_bank_id"],
                "screening_status": created["screening_status"],
            },
        )
        return created

    def separate_donation_components(
        self,
        donation_id: str,
        payload: ComponentSeparationRequest,
        current_user: Dict[str, Any],
    ) -> Dict[str, Any]:
        donation = self.donation_repo.get_by_code(donation_id)
        if not donation:
            try:
                donation = self.donation_repo.get_by_id(donation_id)
            except ValueError:
                donation = None
        if not donation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Donation record not found.")

        abac.authorize_donation_access(current_user, donation, self.donor_repo)

        if donation.get("screening_status") != "PASSED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot separate components for donation with screening_status='{donation.get('screening_status')}'.",
            )
        if donation.get("components_separated"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Components have already been separated for donation '{donation['donation_code']}'.",
            )

        # Resolve blood group & Rh from donor record or explicit fallback
        donor_doc = None
        try:
            donor_doc = self.donor_repo.get_by_id(donation["donor_id"])
        except ValueError:
            donor_doc = None

        blood_group = donor_doc["blood_group"] if donor_doc else (payload.blood_group.value if payload.blood_group else None)
        rh_factor = donor_doc["rh_factor"] if donor_doc else (payload.rh_factor.value if payload.rh_factor else None)
        if not blood_group or not rh_factor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Donor blood_group and rh_factor could not be resolved; provide them in payload or link a valid donor.",
            )

        collection_dt = donation.get("donation_date") or datetime.now(timezone.utc)
        if isinstance(collection_dt, datetime) and collection_dt.tzinfo is None:
            collection_dt = collection_dt.replace(tzinfo=timezone.utc)

        generated_units: List[Dict[str, Any]] = []
        unique_comps = list(dict.fromkeys([c.value for c in payload.components]))
        for comp_name in unique_comps:
            shelf_days, default_vol = COMPONENT_SPECS.get(comp_name, (35, 250))
            unit_code = f"UNIT-{donation['donation_code']}-{comp_name[:3]}-{uuid.uuid4().hex[:4].upper()}"
            unit_doc = {
                "unit_id": unit_code,
                "source_donation_id": donation["donation_code"],
                "blood_bank_id": donation["blood_bank_id"],
                "blood_group": blood_group,
                "rh_factor": rh_factor,
                "component_type": comp_name,
                "volume_ml": default_vol,
                "collection_date": collection_dt,
                "expiry_date": collection_dt + timedelta(days=shelf_days),
                "storage_location": payload.storage_location.model_dump(),
                "status": BloodUnitStatus.AVAILABLE.value,
                "reserved_for_request_id": None,
                "allocated_at": None,
                "version": 1,
            }
            created_unit = self.unit_repo.create(unit_doc)
            generated_units.append(created_unit)
            self.audit_service.log_event(
                action="BLOOD_UNIT_CREATED",
                resource_type="blood_units",
                resource_id=created_unit["_id"],
                status=AuditStatus.SUCCESS.value,
                actor=current_user,
                metadata={
                    "unit_id": created_unit["unit_id"],
                    "blood_group": blood_group,
                    "rh_factor": rh_factor,
                    "component_type": comp_name,
                    "source_donation_id": donation["donation_code"],
                },
            )

        self.donation_repo.update(donation["_id"], {"components_separated": True})
        self.audit_service.log_event(
            action="DONATION_COMPONENTS_SEPARATED",
            resource_type="donations",
            resource_id=donation["_id"],
            status=AuditStatus.SUCCESS.value,
            actor=current_user,
            metadata={"donation_code": donation["donation_code"], "units_created": len(generated_units)},
        )

        return {
            "donation_id": str(donation["_id"]),
            "donation_code": donation["donation_code"],
            "components_separated": True,
            "generated_units": generated_units,
        }

    # ==========================================
    # 2. Blood Request Submission, Triage, Decision & Atomic Allocation
    # ==========================================

    def submit_blood_request(
        self,
        payload: BloodRequestCreate,
        current_user: Dict[str, Any],
        patient_repo=None,
    ) -> Dict[str, Any]:
        abac.authorize_blood_request_create(
            current_user,
            payload.hospital_id,
            payload.doctor_id,
            payload.patient_id,
            patient_repo=patient_repo,
        )
        if self.request_repo.get_by_code(payload.request_code):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Request code '{payload.request_code}' already exists.",
            )

        req_dict = payload.model_dump()
        req_dict["status"] = RequestStatus.PENDING.value
        req_dict["allocated_units"] = []
        created = self.request_repo.create(req_dict)

        self.audit_service.log_event(
            action="BLOOD_REQUEST_CREATED",
            resource_type="blood_requests",
            resource_id=created["_id"],
            status=AuditStatus.SUCCESS.value,
            actor=current_user,
            metadata={
                "request_code": created["request_code"],
                "hospital_id": created["hospital_id"],
                "blood_group": created["blood_group"],
                "rh_factor": created["rh_factor"],
                "priority": created["priority"],
            },
        )

        if created.get("priority") == RequestPriority.CRITICAL.value:
            self.notification_service.notify_roles(
                roles=[UserRole.ADMIN.value, UserRole.BLOOD_BANK_STAFF.value],
                notification_type=NotificationType.EMERGENCY_REQUEST,
                title=f"CRITICAL Blood Request: {created['request_code']}",
                message=(
                    f"Urgent {created['units_requested']} unit(s) of "
                    f"{created['blood_group']} {created['rh_factor']} {created['component_type']} "
                    f"requested by hospital '{created['hospital_id']}'."
                ),
                resource_type="blood_requests",
                resource_id=created["_id"],
                metadata={"request_code": created["request_code"], "priority": created["priority"]},
            )

        return created

    def _resolve_request(self, request_id: str) -> Dict[str, Any]:
        req = self.request_repo.get_by_code(request_id)
        if not req:
            try:
                req = self.request_repo.get_by_id(request_id)
            except ValueError:
                req = None
        if not req:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blood request not found.")
        return req

    def decide_request(
        self,
        request_id: str,
        approve: bool,
        reason: Optional[str],
        current_user: Dict[str, Any],
    ) -> Dict[str, Any]:
        target = self._resolve_request(request_id)
        current_status = target.get("status")

        if current_status in (RequestStatus.ALLOCATED.value, RequestStatus.REJECTED.value, RequestStatus.CANCELLED.value):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot modify request in terminal status '{current_status}'.",
            )
        if approve and current_status != RequestStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Only PENDING requests can be approved (current status: '{current_status}').",
            )

        new_status = RequestStatus.APPROVED.value if approve else RequestStatus.REJECTED.value
        update_fields: Dict[str, Any] = {"status": new_status}
        if reason:
            update_fields["decision_reason"] = reason

        updated = self.request_repo.update(target["_id"], update_fields)
        action = "BLOOD_REQUEST_APPROVED" if approve else "BLOOD_REQUEST_REJECTED"

        self.audit_service.log_event(
            action=action,
            resource_type="blood_requests",
            resource_id=target["_id"],
            status=AuditStatus.SUCCESS.value,
            actor=current_user,
            metadata={"request_code": target["request_code"], "new_status": new_status, "reason": reason},
        )

        self.notification_service.notify_request_stakeholders(
            request_doc=updated,
            notification_type=NotificationType.REQUEST_STATUS,
            title=f"Request {target['request_code']} {new_status}",
            message=f"Blood request {target['request_code']} has been {new_status.lower()}."
            + (f" Note: {reason}" if reason else ""),
        )
        return updated

    def allocate_request_units(
        self,
        request_id: str,
        payload: AllocationRequestPayload,
        current_user: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Finds compatible unexpired units (FIFO by earliest expiry) and allocates them
        using conditional atomic updates (`allocate_unit_atomic`) to prevent duplicate allocation.
        """
        target = self._resolve_request(request_id)
        current_status = target.get("status")
        if current_status not in (
            RequestStatus.PENDING.value,
            RequestStatus.APPROVED.value,
            RequestStatus.PARTIALLY_ALLOCATED.value,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot allocate units for request in status '{current_status}'.",
            )

        # Enforce blood bank scope for BLOOD_BANK_STAFF
        target_bb = payload.blood_bank_id
        if current_user.get("role") == UserRole.BLOOD_BANK_STAFF.value:
            assigned_bb = current_user.get("blood_bank_id")
            if not assigned_bb:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. Blood bank staff account lacks assigned blood_bank_id.",
                )
            if target_bb and str(target_bb) != str(assigned_bb):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. Cannot allocate units from another blood bank.",
                )
            target_bb = str(assigned_bb)

        existing_allocated = list(target.get("allocated_units", []))
        remaining_needed = max(0, int(target["units_requested"]) - len(existing_allocated))
        if remaining_needed == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Blood request already has all requested units allocated.",
            )

        compatible_pairs: List[Tuple[str, str]] = get_compatible_donor_types(
            recipient_group=target["blood_group"],
            recipient_rh=target["rh_factor"],
            component_type=target["component_type"],
            allow_substitutes=payload.allow_compatible_substitutes,
        )

        newly_allocated_docs: List[Dict[str, Any]] = []
        for donor_grp, donor_rh in compatible_pairs:
            if remaining_needed <= 0:
                break
            candidates = self.unit_repo.find_available_units(
                blood_group=donor_grp,
                rh_factor=donor_rh,
                component_type=target["component_type"],
                blood_bank_id=target_bb,
                limit=remaining_needed + 10,
            )
            for candidate in candidates:
                if remaining_needed <= 0:
                    break
                allocated_doc = self.unit_repo.allocate_unit_atomic(
                    unit_id=candidate["_id"],
                    request_id=str(target["_id"]),
                )
                if not allocated_doc:
                    # Another concurrent request won this unit; continue to next FIFO candidate
                    continue
                newly_allocated_docs.append(allocated_doc)
                remaining_needed -= 1
                self.audit_service.log_event(
                    action="BLOOD_UNIT_ALLOCATED",
                    resource_type="blood_units",
                    resource_id=allocated_doc["_id"],
                    status=AuditStatus.SUCCESS.value,
                    actor=current_user,
                    metadata={
                        "unit_id": allocated_doc["unit_id"],
                        "request_code": target["request_code"],
                        "request_id": str(target["_id"]),
                    },
                )

        if not newly_allocated_docs:
            self.notification_service.notify_roles(
                roles=[UserRole.ADMIN.value, UserRole.BLOOD_BANK_STAFF.value],
                notification_type=NotificationType.INVENTORY_ALERT,
                title=f"Insufficient Stock for {target['request_code']}",
                message=(
                    f"No compatible unexpired {target['blood_group']} {target['rh_factor']} "
                    f"{target['component_type']} units available."
                ),
                blood_bank_id=target_bb,
                resource_type="blood_requests",
                resource_id=target["_id"],
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No compatible unexpired blood units are currently available for allocation.",
            )

        all_allocated_ids = existing_allocated + [u["unit_id"] for u in newly_allocated_docs]
        final_status = (
            RequestStatus.ALLOCATED.value
            if remaining_needed == 0
            else RequestStatus.PARTIALLY_ALLOCATED.value
        )
        updated_req = self.request_repo.attach_allocated_units(
            target["_id"],
            unit_ids=all_allocated_ids,
            new_status=final_status,
        )

        self.audit_service.log_event(
            action="BLOOD_REQUEST_ALLOCATED",
            resource_type="blood_requests",
            resource_id=target["_id"],
            status=AuditStatus.SUCCESS.value,
            actor=current_user,
            metadata={
                "request_code": target["request_code"],
                "newly_allocated": [u["unit_id"] for u in newly_allocated_docs],
                "new_status": final_status,
            },
        )

        self.notification_service.notify_request_stakeholders(
            request_doc=updated_req,
            notification_type=NotificationType.REQUEST_STATUS,
            title=f"Blood Units Allocated ({target['request_code']})",
            message=(
                f"{len(newly_allocated_docs)} unit(s) allocated to request {target['request_code']} "
                f"(status: {final_status})."
            ),
        )

        return {
            "request": updated_req,
            "allocated_units": newly_allocated_docs,
            "newly_allocated_count": len(newly_allocated_docs),
            "remaining_units_needed": remaining_needed,
            "compatibility_disclaimer": ACADEMIC_DISCLAIMER,
        }
