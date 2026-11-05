"""
Common schemas, ObjectId validation utilities, and pagination models.
"""
from typing import Any, Generic, List, Optional, TypeVar
from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import core_schema


class PyObjectId(str):
    """
    Custom Pydantic type representing a valid BSON ObjectId serialized as a string.
    """
    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type: Any, _handler: Any) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.chain_schema([
                    core_schema.str_schema(),
                    core_schema.no_info_plain_validator_function(cls.validate),
                ])
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(lambda x: str(x)),
        )

    @classmethod
    def validate(cls, value: Any) -> ObjectId:
        if isinstance(value, ObjectId):
            return value
        if isinstance(value, str) and ObjectId.is_valid(value):
            return ObjectId(value)
        raise ValueError(f"Invalid ObjectId string: {value}")


class MongoBaseModel(BaseModel):
    """
    Base model for MongoDB documents.
    Maps '_id' to 'id' in output serialization and allows population by field name.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic container for paginated query results.
    """
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int
