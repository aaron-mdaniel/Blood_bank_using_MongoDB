"""
BloodRequest repository for managing transfusion requests.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from bson import ObjectId
from pymongo import ReturnDocument

from app.config.database import db_manager, Collections
from app.models.enums import PRIORITY_WEIGHTS, RequestPriority
from app.repositories.base_repository import BaseRepository


class BloodRequestRepository(BaseRepository):
    """
    Data access repository for blood_requests collection.
    """

    def __init__(self, collection=None):
        col = collection if collection is not None else Collections.BLOOD_REQUESTS
        super().__init__(col)

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures priority_weight is computed for accurate clinical triage sorting."""
        doc_data = dict(data)
        priority_val = doc_data.get("priority")
        if isinstance(priority_val, RequestPriority):
            priority_val = priority_val.value
        doc_data["priority_weight"] = PRIORITY_WEIGHTS.get(priority_val, 3)
        return super().create(doc_data)

    def get_by_code(self, request_code: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"request_code": request_code})

    def find_by_hospital(
        self, hospital_id: str, skip: int = 0, limit: int = 50
    ) -> List[Dict[str, Any]]:
        return self.find_many(
            {"hospital_id": str(hospital_id)},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)],
        )

    def find_pending_triage(self, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieves pending requests prioritized by urgency (CRITICAL first, then URGENT, then ROUTINE).
        """
        cursor = self.collection.find({"status": "PENDING"}).sort(
            [("priority_weight", 1), ("created_at", 1)]
        ).skip(skip).limit(limit)
        return [self.serialize_doc(d) for d in cursor]

    def attach_allocated_units(
        self, request_id: Union[str, ObjectId], unit_ids: List[str]
    ) -> Optional[Dict[str, Any]]:
        oid = self.to_object_id(request_id)
        now = datetime.now(timezone.utc)
        updated = self.collection.find_one_and_update(
            {"_id": oid},
            {
                "$set": {
                    "allocated_units": unit_ids,
                    "status": "ALLOCATED",
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.serialize_doc(updated)
