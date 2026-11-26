"""
Notification repository for managing the notifications MongoDB collection
(with 30-day TTL auto-expiration configured via idx_notif_ttl_30d).
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from bson import ObjectId
from pymongo import ReturnDocument

from app.config.database import Collections
from app.repositories.base_repository import BaseRepository


class NotificationRepository(BaseRepository):
    """
    Data access repository for in-app notifications.
    """

    def __init__(self, collection=None):
        col = collection if collection is not None else Collections.NOTIFICATIONS
        super().__init__(col)

    def find_for_user(
        self,
        user_id: str,
        is_read: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"user_id": str(user_id)}
        if is_read is not None:
            query["is_read"] = is_read
        return self.find_many(query, skip=skip, limit=limit, sort=[("created_at", -1)])

    def mark_as_read(self, notification_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        oid = self.to_object_id(notification_id)
        now = datetime.now(timezone.utc)
        updated = self.collection.find_one_and_update(
            {"_id": oid},
            {"$set": {"is_read": True, "read_at": now, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return self.serialize_doc(updated)

    def mark_all_read(self, user_id: str) -> int:
        now = datetime.now(timezone.utc)
        result = self.collection.update_many(
            {"user_id": str(user_id), "is_read": False},
            {"$set": {"is_read": True, "read_at": now, "updated_at": now}},
        )
        return result.modified_count
