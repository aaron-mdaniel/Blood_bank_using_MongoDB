"""
BloodCamp repository for managing the blood_camps MongoDB collection.
Supports 2dsphere $near geospatial queries with a Haversine fallback for in-memory mocks.
"""
import math
from typing import Any, Dict, List, Optional
from pymongo.errors import OperationFailure

from app.config.database import Collections
from app.repositories.base_repository import BaseRepository


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


class BloodCampRepository(BaseRepository):
    """
    Data access repository for blood_camps collection.
    """

    def __init__(self, collection=None):
        col = collection if collection is not None else Collections.BLOOD_CAMPS
        super().__init__(col)

    def get_by_code(self, camp_code: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"camp_code": camp_code})

    def find_nearby(
        self,
        longitude: float,
        latitude: float,
        max_distance_meters: int = 50000,
        status_filter: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Executes MongoDB $near query on idx_camps_location_2dsphere, falling back
        to Haversine filtering when running against an in-memory mock engine.
        """
        query: Dict[str, Any] = {
            "location": {
                "$near": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": [longitude, latitude],
                    },
                    "$maxDistance": max_distance_meters,
                }
            }
        }
        if status_filter:
            query["status"] = status_filter

        try:
            docs = [self.serialize_doc(doc) for doc in self.collection.find(query).limit(limit)]
            for doc in docs:
                coords = doc.get("location", {}).get("coordinates", [])
                if len(coords) == 2:
                    doc["distance_km"] = round(_haversine_km(longitude, latitude, coords[0], coords[1]), 2)
            return docs
        except (OperationFailure, NotImplementedError, Exception):
            # Fallback for mongomock or unindexed local testing
            base_query: Dict[str, Any] = {}
            if status_filter:
                base_query["status"] = status_filter
            max_km = max_distance_meters / 1000.0
            candidates = self.find_many(base_query, limit=500)
            within: List[Dict[str, Any]] = []
            for doc in candidates:
                coords = doc.get("location", {}).get("coordinates", [])
                if len(coords) != 2:
                    continue
                dist = _haversine_km(longitude, latitude, coords[0], coords[1])
                if dist <= max_km:
                    doc["distance_km"] = round(dist, 2)
                    within.append(doc)
            within.sort(key=lambda d: d.get("distance_km", 0.0))
            return within[:limit]
