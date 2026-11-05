"""
Base repository providing generic MongoDB CRUD operations via PyMongo.
Handles ObjectId conversions, timestamps, and query pagination.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from bson import ObjectId
from pymongo.collection import Collection
from pymongo import ReturnDocument


class BaseRepository:
    """
    Abstract base repository encapsulating common PyMongo document interactions.
    """

    def __init__(self, collection_or_name: Union[Collection, str]):
        if isinstance(collection_or_name, str):
            self.collection_name = collection_or_name
            self._collection = None
        else:
            self._collection = collection_or_name
            self.collection_name = collection_or_name.name

    @property
    def collection(self) -> Collection:
        if self._collection is not None:
            return self._collection
        from app.config.database import db_manager
        return db_manager.get_collection(self.collection_name)

    @staticmethod
    def to_object_id(id_val: Union[str, ObjectId]) -> ObjectId:
        """Converts string or ObjectId to ObjectId."""
        if isinstance(id_val, ObjectId):
            return id_val
        if isinstance(id_val, str) and ObjectId.is_valid(id_val):
            return ObjectId(id_val)
        raise ValueError(f"Invalid ObjectId format: '{id_val}'")

    @staticmethod
    def serialize_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Converts internal ObjectId instances to string representations."""
        if not doc:
            return None
        doc_copy = dict(doc)
        if "_id" in doc_copy and isinstance(doc_copy["_id"], ObjectId):
            doc_copy["_id"] = str(doc_copy["_id"])
        return doc_copy

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inserts a new document with automated timestamp tracking.
        """
        document = dict(data)
        now = datetime.now(timezone.utc)
        if "created_at" not in document:
            document["created_at"] = now
        if "updated_at" not in document:
            document["updated_at"] = now

        result = self.collection.insert_one(document)
        document["_id"] = str(result.inserted_id)
        return document

    def get_by_id(self, doc_id: Union[str, ObjectId]) -> Optional[Dict[str, Any]]:
        """
        Retrieves single document by primary key _id.
        """
        try:
            oid = self.to_object_id(doc_id)
        except ValueError:
            return None
        doc = self.collection.find_one({"_id": oid})
        return self.serialize_doc(doc)

    def find_one(self, filter_query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Retrieves first document matching query filter.
        """
        doc = self.collection.find_one(filter_query)
        return self.serialize_doc(doc)

    def find_many(
        self,
        filter_query: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 50,
        sort: Optional[List] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves multiple documents matching query with pagination and sorting.
        """
        query = filter_query or {}
        cursor = self.collection.find(query).skip(skip).limit(limit)
        if sort:
            cursor = cursor.sort(sort)
        return [self.serialize_doc(d) for d in cursor]

    def count(self, filter_query: Optional[Dict[str, Any]] = None) -> int:
        """Counts total documents matching query."""
        return self.collection.count_documents(filter_query or {})

    def update(
        self, doc_id: Union[str, ObjectId], update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Updates document by _id using $set and updates 'updated_at' timestamp.
        """
        try:
            oid = self.to_object_id(doc_id)
        except ValueError:
            return None

        clean_update = dict(update_data)
        clean_update["updated_at"] = datetime.now(timezone.utc)

        updated_doc = self.collection.find_one_and_update(
            {"_id": oid},
            {"$set": clean_update},
            return_document=ReturnDocument.AFTER,
        )
        return self.serialize_doc(updated_doc)

    def delete(self, doc_id: Union[str, ObjectId]) -> bool:
        """
        Deletes document by _id.
        """
        try:
            oid = self.to_object_id(doc_id)
        except ValueError:
            return False
        result = self.collection.delete_one({"_id": oid})
        return result.deleted_count > 0
