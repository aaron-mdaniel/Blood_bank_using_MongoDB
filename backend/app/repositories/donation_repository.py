"""
Donation repository for managing donations collection documents.
"""
from typing import Any, Dict, List, Optional
from app.config.database import db_manager, Collections
from app.repositories.base_repository import BaseRepository


class DonationRepository(BaseRepository):
    """
    Data access repository for donations collection.
    """

    def __init__(self, collection=None):
        col = collection if collection is not None else Collections.DONATIONS
        super().__init__(col)

    def get_by_code(self, donation_code: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"donation_code": donation_code})

    def find_by_donor(self, donor_id: str, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        return self.find_many(
            {"donor_id": str(donor_id)},
            skip=skip,
            limit=limit,
            sort=[("donation_date", -1)],
        )
