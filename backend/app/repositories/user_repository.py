"""
User repository for managing users collection documents.
"""
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Union
from bson import ObjectId
from pymongo import ReturnDocument

from app.config.database import db_manager, Collections
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository):
    """
    Data access repository for users collection.
    """

    def __init__(self, collection=None):
        col = collection if collection is not None else Collections.USERS
        super().__init__(col)

    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"username": username})

    def get_by_email_hash(self, email_hash: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"email_hash": email_hash})

    def increment_failed_attempts(self, user_id: Union[str, ObjectId], max_attempts: int = 5) -> Optional[Dict[str, Any]]:
        oid = self.to_object_id(user_id)
        user = self.get_by_id(oid)
        if not user:
            return None

        new_count = user.get("failed_login_attempts", 0) + 1
        now = datetime.now(timezone.utc)
        update_fields: Dict[str, Any] = {
            "failed_login_attempts": new_count,
            "updated_at": now
        }

        if new_count >= max_attempts:
            # Lock out for 15 minutes
            update_fields["lockout_until"] = now + timedelta(minutes=15)

        updated = self.collection.find_one_and_update(
            {"_id": oid},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER
        )
        return self.serialize_doc(updated)

    def reset_failed_attempts(self, user_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        oid = self.to_object_id(user_id)
        now = datetime.now(timezone.utc)
        updated = self.collection.find_one_and_update(
            {"_id": oid},
            {"$set": {"failed_login_attempts": 0, "lockout_until": None, "updated_at": now}},
            return_document=ReturnDocument.AFTER
        )
        return self.serialize_doc(updated)
