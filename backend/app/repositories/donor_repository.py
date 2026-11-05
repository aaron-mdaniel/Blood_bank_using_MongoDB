"""
Donor repository for managing donors collection documents.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from bson import ObjectId
from pymongo import ReturnDocument

from app.config.database import db_manager, Collections
from app.repositories.base_repository import BaseRepository


class DonorRepository(BaseRepository):
    """
    Data access repository for donors collection.
    """

    def __init__(self, collection=None):
        col = collection if collection is not None else Collections.DONORS
        super().__init__(col)

    def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"user_id": str(user_id)})

    def get_by_card_number(self, donor_card_number: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"donor_card_number": donor_card_number})

    def find_eligible_by_blood_group(
        self, blood_group: str, rh_factor: str, skip: int = 0, limit: int = 50
    ) -> List[Dict[str, Any]]:
        query = {
            "blood_group": blood_group,
            "rh_factor": rh_factor,
            "eligibility_status": "ELIGIBLE",
        }
        return self.find_many(query, skip=skip, limit=limit)

    def update_donation_dates(
        self, donor_id: Union[str, ObjectId], last_date: datetime, next_eligible: datetime
    ) -> Optional[Dict[str, Any]]:
        oid = self.to_object_id(donor_id)
        updated = self.collection.find_one_and_update(
            {"_id": oid},
            {
                "$set": {
                    "last_donation_date": last_date,
                    "next_eligible_date": next_eligible,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self.serialize_doc(updated)
