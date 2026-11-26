"""
BloodUnit repository for managing individual blood units.
Implements atomic conditional updates for safe, race-condition-free inventory allocation.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from bson import ObjectId
from pymongo import ReturnDocument

from app.config.database import db_manager, Collections
from app.repositories.base_repository import BaseRepository


class BloodUnitRepository(BaseRepository):
    """
    Data access repository for blood_units collection.
    """

    def __init__(self, collection=None):
        col = collection if collection is not None else Collections.BLOOD_UNITS
        super().__init__(col)

    def get_by_unit_id(self, unit_id: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"unit_id": unit_id})

    def find_available_units(
        self,
        blood_group: str,
        rh_factor: str,
        component_type: str,
        blood_bank_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Finds unexpired, AVAILABLE blood units ordered by earliest expiry (FIFO principle).
        """
        query: Dict[str, Any] = {
            "blood_group": blood_group,
            "rh_factor": rh_factor,
            "component_type": component_type,
            "status": "AVAILABLE",
            "expiry_date": {"$gt": datetime.now(timezone.utc)},
        }
        if blood_bank_id:
            query["blood_bank_id"] = str(blood_bank_id)

        cursor = self.collection.find(query).sort([("expiry_date", 1)]).limit(limit)
        return [self.serialize_doc(doc) for doc in cursor]

    def allocate_unit_atomic(
        self, unit_id: Union[str, ObjectId], request_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically allocates a blood unit.
        Guarantees that two concurrent requests cannot allocate the exact same unit.
        """
        try:
            oid = self.to_object_id(unit_id)
            query = {"_id": oid}
        except ValueError:
            query = {"unit_id": str(unit_id)}

        query.update({
            "status": "AVAILABLE",
            "expiry_date": {"$gt": datetime.now(timezone.utc)}
        })

        now = datetime.now(timezone.utc)
        updated_doc = self.collection.find_one_and_update(
            filter=query,
            update={
                "$set": {
                    "status": "ALLOCATED",
                    "reserved_for_request_id": str(request_id),
                    "allocated_at": now,
                    "updated_at": now,
                },
                "$inc": {"version": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.serialize_doc(updated_doc)

    def find_expiring_units(
        self,
        within_days: int = 7,
        blood_bank_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Finds AVAILABLE blood units expiring within `within_days` from now."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=within_days)
        query: Dict[str, Any] = {
            "status": "AVAILABLE",
            "expiry_date": {"$gt": now, "$lte": cutoff},
        }
        if blood_bank_id:
            query["blood_bank_id"] = str(blood_bank_id)
        cursor = self.collection.find(query).sort([("expiry_date", 1)])
        return [self.serialize_doc(doc) for doc in cursor]

    def mark_expired_units(self, blood_bank_id: Optional[str] = None) -> int:
        """Transitions past-expiry AVAILABLE units to EXPIRED and returns modified count."""
        now = datetime.now(timezone.utc)
        query: Dict[str, Any] = {
            "status": "AVAILABLE",
            "expiry_date": {"$lte": now},
        }
        if blood_bank_id:
            query["blood_bank_id"] = str(blood_bank_id)
        result = self.collection.update_many(
            query,
            {"$set": {"status": "EXPIRED", "updated_at": now}, "$inc": {"version": 1}},
        )
        return result.modified_count
