"""
In-App Notification & Inventory Expiry / Low-Stock Alert Service.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status

from app.models.enums import BloodComponent, BloodGroup, BloodUnitStatus, RhFactor, UserRole
from app.repositories.blood_unit_repository import BloodUnitRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.notification_schema import NotificationType


class NotificationService:
    """
    Dispatches and retrieves role/user-targeted alerts in the notifications collection.
    """

    def __init__(
        self,
        notif_repo: NotificationRepository = None,
        user_repo: UserRepository = None,
        unit_repo: BloodUnitRepository = None,
    ):
        self.notif_repo = notif_repo or NotificationRepository()
        self.user_repo = user_repo or UserRepository()
        self.unit_repo = unit_repo or BloodUnitRepository()

    def notify_user(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        doc = {
            "user_id": str(user_id),
            "notification_type": notification_type.value if isinstance(notification_type, NotificationType) else str(notification_type),
            "title": title,
            "message": message,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id is not None else None,
            "is_read": False,
            "read_at": None,
            "metadata": metadata or {},
        }
        return self.notif_repo.create(doc)

    def notify_roles(
        self,
        roles: List[str],
        notification_type: NotificationType,
        title: str,
        message: str,
        blood_bank_id: Optional[str] = None,
        hospital_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        query: Dict[str, Any] = {"role": {"$in": roles}, "is_active": True}
        if blood_bank_id:
            query["$or"] = [
                {"role": UserRole.ADMIN.value},
                {"blood_bank_id": str(blood_bank_id)},
            ]
        elif hospital_id:
            query["hospital_id"] = str(hospital_id)

        recipients = self.user_repo.find_many(query, limit=200)
        count = 0
        for user in recipients:
            self.notify_user(
                user_id=str(user["_id"]),
                notification_type=notification_type,
                title=title,
                message=message,
                resource_type=resource_type,
                resource_id=resource_id,
                metadata=metadata,
            )
            count += 1
        return count

    def notify_request_stakeholders(
        self,
        request_doc: Dict[str, Any],
        notification_type: NotificationType,
        title: str,
        message: str,
    ) -> int:
        """Notifies the prescribing doctor (if an active user) and hospital staff for the request's hospital."""
        notified_ids = set()
        doctor_id = request_doc.get("doctor_id")
        if doctor_id:
            try:
                doc_user = self.user_repo.get_by_id(str(doctor_id))
            except ValueError:
                doc_user = None
            if doc_user and doc_user.get("is_active", True):
                self.notify_user(
                    user_id=str(doc_user["_id"]),
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    resource_type="blood_requests",
                    resource_id=request_doc.get("_id"),
                    metadata={"request_code": request_doc.get("request_code"), "status": request_doc.get("status")},
                )
                notified_ids.add(str(doc_user["_id"]))

        hosp_id = request_doc.get("hospital_id")
        if hosp_id:
            staff_users = self.user_repo.find_many(
                {"role": UserRole.HOSPITAL_STAFF.value, "hospital_id": str(hosp_id), "is_active": True},
                limit=100,
            )
            for staff in staff_users:
                uid = str(staff["_id"])
                if uid not in notified_ids:
                    self.notify_user(
                        user_id=uid,
                        notification_type=notification_type,
                        title=title,
                        message=message,
                        resource_type="blood_requests",
                        resource_id=request_doc.get("_id"),
                        metadata={"request_code": request_doc.get("request_code"), "status": request_doc.get("status")},
                    )
                    notified_ids.add(uid)
        return len(notified_ids)

    def list_my_notifications(
        self,
        current_user: Dict[str, Any],
        is_read: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return self.notif_repo.find_for_user(
            user_id=str(current_user["_id"]),
            is_read=is_read,
            skip=skip,
            limit=limit,
        )

    def mark_notification_read(
        self,
        notification_id: str,
        current_user: Dict[str, Any],
    ) -> Dict[str, Any]:
        notif = self.notif_repo.get_by_id(notification_id)
        if not notif:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found.",
            )
        if str(notif.get("user_id")) != str(current_user["_id"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You can only modify your own notifications.",
            )
        return self.notif_repo.mark_as_read(notification_id)

    def mark_all_read(self, current_user: Dict[str, Any]) -> int:
        return self.notif_repo.mark_all_read(str(current_user["_id"]))

    def scan_expiring_and_low_inventory(
        self,
        expiry_days_threshold: int = 7,
        min_units_threshold: int = 2,
        blood_bank_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Marks past-expiry AVAILABLE units as EXPIRED, detects soon-to-expire units
        and low-stock RBC blood groups, and dispatches alerts to ADMIN and BLOOD_BANK_STAFF.
        """
        expired_count = self.unit_repo.mark_expired_units(blood_bank_id=blood_bank_id)
        expiring_units = self.unit_repo.find_expiring_units(
            within_days=expiry_days_threshold,
            blood_bank_id=blood_bank_id,
        )

        dispatched = 0
        if expiring_units:
            sample_ids = [u["unit_id"] for u in expiring_units[:5]]
            dispatched += self.notify_roles(
                roles=[UserRole.ADMIN.value, UserRole.BLOOD_BANK_STAFF.value],
                notification_type=NotificationType.EXPIRY_ALERT,
                title=f"Blood Expiry Alert: {len(expiring_units)} unit(s) expiring within {expiry_days_threshold} days",
                message=f"Units nearing expiry: {', '.join(sample_ids)}",
                blood_bank_id=blood_bank_id,
                resource_type="blood_units",
                metadata={"expiring_count": len(expiring_units), "unit_ids": sample_ids},
            )

        # Check RBC availability across standard ABO/Rh combinations
        now = datetime.now(timezone.utc)
        low_stock_groups: List[Dict[str, Any]] = []
        for grp in BloodGroup:
            for rh in RhFactor:
                query: Dict[str, Any] = {
                    "blood_group": grp.value,
                    "rh_factor": rh.value,
                    "component_type": BloodComponent.RBC.value,
                    "status": BloodUnitStatus.AVAILABLE.value,
                    "expiry_date": {"$gt": now},
                }
                if blood_bank_id:
                    query["blood_bank_id"] = str(blood_bank_id)
                available_count = self.unit_repo.count(query)
                if available_count < min_units_threshold:
                    low_stock_groups.append({
                        "blood_group": grp.value,
                        "rh_factor": rh.value,
                        "component_type": BloodComponent.RBC.value,
                        "available_units": available_count,
                    })

        if low_stock_groups:
            summary = ", ".join(f"{g['blood_group']} {g['rh_factor']} ({g['available_units']})" for g in low_stock_groups[:4])
            dispatched += self.notify_roles(
                roles=[UserRole.ADMIN.value, UserRole.BLOOD_BANK_STAFF.value],
                notification_type=NotificationType.INVENTORY_ALERT,
                title=f"Low Inventory Alert: {len(low_stock_groups)} blood group(s) below {min_units_threshold} RBC units",
                message=f"Low RBC stock detected for: {summary}",
                blood_bank_id=blood_bank_id,
                resource_type="blood_units",
                metadata={"low_stock_count": len(low_stock_groups)},
            )

        return {
            "expired_units_marked": expired_count,
            "expiring_soon_count": len(expiring_units),
            "low_stock_groups": low_stock_groups,
            "notifications_dispatched": dispatched,
        }
