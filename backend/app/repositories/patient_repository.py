"""
Patient repository for managing patients collection documents.
"""
from typing import Any, Dict, List, Optional
from app.config.database import db_manager, Collections
from app.repositories.base_repository import BaseRepository


class PatientRepository(BaseRepository):
    """
    Data access repository for patients collection.
    """

    def __init__(self, collection=None):
        col = collection if collection is not None else Collections.PATIENTS
        super().__init__(col)

    def get_by_hospital_mrn(self, hospital_id: str, mrn: str) -> Optional[Dict[str, Any]]:
        return self.find_one({"hospital_id": hospital_id, "mrn": mrn})

    def find_by_hospital(self, hospital_id: str, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        return self.find_many({"hospital_id": hospital_id}, skip=skip, limit=limit)

    def find_by_doctor(self, doctor_id: str, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        return self.find_many({"attending_doctor_id": doctor_id}, skip=skip, limit=limit)
