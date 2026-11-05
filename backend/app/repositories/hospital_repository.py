"""
Hospital repository for managing hospitals collection documents.
Includes geospatial queries via 2dsphere indexing.
"""
from typing import Any, Dict, List, Optional
from app.config.database import db_manager, Collections
from app.repositories.base_repository import BaseRepository


class HospitalRepository(BaseRepository):
    """
    Data access repository for hospitals collection.
    """

    def __init__(self, collection=None):
        col = collection if collection is not None else Collections.HOSPITALS
        super().__init__(col)

    def get_by_license(self, license_number: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"license_number": license_number})

    def find_nearby(
        self, longitude: float, latitude: float, max_distance_meters: int = 50000, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Executes MongoDB $near geospatial query on 2dsphere location index.
        """
        query = {
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
        cursor = self.collection.find(query).limit(limit)
        return [self.serialize_doc(doc) for doc in cursor]
