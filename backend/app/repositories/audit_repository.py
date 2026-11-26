"""
Audit Log repository for append-only persistence and querying of audit_logs collection.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config.database import Collections
from app.repositories.base_repository import BaseRepository


class AuditRepository(BaseRepository):
    """
    Data access repository for centralized security audit_logs.
    """

    def __init__(self, collection=None):
        col = collection if collection is not None else Collections.AUDIT_LOGS
        super().__init__(col)

    def get_by_event_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"event_id": event_id})

    def query_logs(
        self,
        action: Optional[str] = None,
        audit_status: Optional[str] = None,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Queries audit records using indexed fields (timestamp, actor.user_id, action, status, resource_type).
        """
        query: Dict[str, Any] = {}
        if action:
            query["action"] = action
        if audit_status:
            query["status"] = audit_status
        if user_id:
            query["actor.user_id"] = user_id
        if resource_type:
            query["resource_type"] = resource_type
        if start_time or end_time:
            ts_filter: Dict[str, Any] = {}
            if start_time:
                ts_filter["$gte"] = start_time
            if end_time:
                ts_filter["$lte"] = end_time
            query["timestamp"] = ts_filter

        return self.find_many(
            query,
            skip=skip,
            limit=limit,
            sort=[("timestamp", -1)],
        )
