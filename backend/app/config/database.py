"""
Database connection management and collection access for MongoDB using PyMongo.
Provides connection pooling, health checks, collection handles, and mock support.
"""
import logging
import time
from typing import Dict, Any, Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from app.config.settings import get_settings

logger = logging.getLogger("secure_blood_bank.database")


class Collections:
    """
    Constant definitions for all 11 application MongoDB collections.
    Ensures zero typo risk across repositories and services.
    """
    USERS = "users"
    ROLES_PERMISSIONS = "roles_permissions"
    DONORS = "donors"
    HOSPITALS = "hospitals"
    PATIENTS = "patients"
    DONATIONS = "donations"
    BLOOD_UNITS = "blood_units"
    BLOOD_REQUESTS = "blood_requests"
    BLOOD_CAMPS = "blood_camps"
    NOTIFICATIONS = "notifications"
    AUDIT_LOGS = "audit_logs"

    ALL_COLLECTIONS = [
        USERS,
        ROLES_PERMISSIONS,
        DONORS,
        HOSPITALS,
        PATIENTS,
        DONATIONS,
        BLOOD_UNITS,
        BLOOD_REQUESTS,
        BLOOD_CAMPS,
        NOTIFICATIONS,
        AUDIT_LOGS,
    ]


class DatabaseManager:
    """
    Manages MongoDB client lifecycle, connection pooling, and collection handles.
    Supports dependency injection of custom clients (e.g., for automated tests).
    """

    def __init__(self):
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None
        self._is_connected: bool = False

    def connect(self, client: Optional[MongoClient] = None) -> bool:
        """
        Establishes connection to MongoDB or adopts an injected client.
        Verifies connectivity via admin ping.
        """
        settings = get_settings()

        if client is not None:
            # Injected client (e.g. mongomock or test fixture)
            self._client = client
            self._db = self._client[settings.DATABASE_NAME]
            self._is_connected = True
            logger.info("DatabaseManager initialized with injected client.")
            return True

        try:
            logger.info(f"Connecting to MongoDB at: {settings.MONGODB_URL}")
            self._client = MongoClient(
                settings.MONGODB_URL,
                serverSelectionTimeoutMS=settings.MONGODB_TIMEOUT_MS,
                connectTimeoutMS=settings.MONGODB_TIMEOUT_MS,
                maxPoolSize=50,
                minPoolSize=5,
            )
            # Verify connectivity
            self._client.admin.command("ping")
            self._db = self._client[settings.DATABASE_NAME]
            self._is_connected = True
            logger.info(f"Successfully connected to MongoDB database: '{settings.DATABASE_NAME}'")
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
            self._is_connected = False
            logger.warning(f"Could not connect to live MongoDB server ({exc}). Operating in disconnected/fallback state.")
            return False
        except Exception as exc:
            self._is_connected = False
            logger.error(f"Unexpected database error: {exc}")
            return False

    def disconnect(self) -> None:
        """Closes the MongoDB client connection pool."""
        if self._client:
            self._client.close()
            self._is_connected = False
            logger.info("MongoDB connection pool closed.")

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def client(self) -> Optional[MongoClient]:
        return self._client

    @property
    def db(self) -> Database:
        if self._db is None:
            # Attempt lazy connection
            self.connect()
        if self._db is None:
            raise RuntimeError("Database is not connected. Verify MongoDB service is running and accessible.")
        return self._db

    def get_collection(self, collection_name: str) -> Collection:
        """Returns handle to a specific collection."""
        return self.db[collection_name]

    # Dedicated collection properties for compile-time clarity and auto-completion
    @property
    def users(self) -> Collection:
        return self.get_collection(Collections.USERS)

    @property
    def roles_permissions(self) -> Collection:
        return self.get_collection(Collections.ROLES_PERMISSIONS)

    @property
    def donors(self) -> Collection:
        return self.get_collection(Collections.DONORS)

    @property
    def hospitals(self) -> Collection:
        return self.get_collection(Collections.HOSPITALS)

    @property
    def patients(self) -> Collection:
        return self.get_collection(Collections.PATIENTS)

    @property
    def donations(self) -> Collection:
        return self.get_collection(Collections.DONATIONS)

    @property
    def blood_units(self) -> Collection:
        return self.get_collection(Collections.BLOOD_UNITS)

    @property
    def blood_requests(self) -> Collection:
        return self.get_collection(Collections.BLOOD_REQUESTS)

    @property
    def blood_camps(self) -> Collection:
        return self.get_collection(Collections.BLOOD_CAMPS)

    @property
    def notifications(self) -> Collection:
        return self.get_collection(Collections.NOTIFICATIONS)

    @property
    def audit_logs(self) -> Collection:
        return self.get_collection(Collections.AUDIT_LOGS)

    def ping(self) -> Dict[str, Any]:
        """
        Executes ping command to verify database liveliness and measure latency.
        """
        if not self._client:
            return {"status": "disconnected", "database": None, "latency_ms": None}

        start_time = time.perf_counter()
        try:
            self._client.admin.command("ping")
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            existing_collections = self.db.list_collection_names()
            return {
                "status": "connected",
                "database": self.db.name,
                "latency_ms": latency_ms,
                "collections_count": len(existing_collections),
                "collections": existing_collections,
            }
        except Exception as exc:
            return {
                "status": "error",
                "database": None,
                "latency_ms": None,
                "error": str(exc),
            }


# Singleton instance across application
db_manager = DatabaseManager()


def get_database() -> Database:
    """Dependency provider returning active Database instance."""
    return db_manager.db
