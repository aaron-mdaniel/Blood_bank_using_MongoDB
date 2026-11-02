"""
Phase 1 Automated Verification Tests:
Tests settings loading, database manager connectivity, 11 collection handles,
index definitions, and FastAPI health endpoints.
"""
from fastapi.testclient import TestClient
from pymongo import IndexModel

from app.config.settings import get_settings
from app.config.database import db_manager, Collections
from scripts.create_indexes import get_index_definitions, setup_indexes


def test_settings_loading():
    """Verify settings are loaded with required cryptographic and database attributes."""
    settings = get_settings()
    assert settings.PROJECT_NAME is not None
    assert settings.DATABASE_NAME is not None
    assert settings.MONGODB_URL is not None
    assert settings.JWT_SECRET_KEY is not None
    assert settings.ENCRYPTION_SECRET_KEY is not None
    assert isinstance(settings.CORS_ORIGINS, list)
    assert len(settings.CORS_ORIGINS) > 0


def test_collection_constants_completeness():
    """Verify that all 11 required collections are present in Collections constants."""
    expected_collections = {
        "users",
        "roles_permissions",
        "donors",
        "hospitals",
        "patients",
        "donations",
        "blood_units",
        "blood_requests",
        "blood_camps",
        "notifications",
        "audit_logs",
    }
    actual_collections = set(Collections.ALL_COLLECTIONS)
    assert expected_collections == actual_collections


def test_database_manager_collection_handles(mock_db):
    """Verify that DatabaseManager exposes dedicated properties for all 11 collections."""
    assert db_manager.users.name == Collections.USERS
    assert db_manager.roles_permissions.name == Collections.ROLES_PERMISSIONS
    assert db_manager.donors.name == Collections.DONORS
    assert db_manager.hospitals.name == Collections.HOSPITALS
    assert db_manager.patients.name == Collections.PATIENTS
    assert db_manager.donations.name == Collections.DONATIONS
    assert db_manager.blood_units.name == Collections.BLOOD_UNITS
    assert db_manager.blood_requests.name == Collections.BLOOD_REQUESTS
    assert db_manager.blood_camps.name == Collections.BLOOD_CAMPS
    assert db_manager.notifications.name == Collections.NOTIFICATIONS
    assert db_manager.audit_logs.name == Collections.AUDIT_LOGS


def test_database_basic_crud(mock_db):
    """Verify basic document write and read across collections."""
    sample_unit = {
        "unit_id": "UNIT-TEST-001",
        "blood_group": "O",
        "rh_factor": "NEGATIVE",
        "component_type": "RBC",
        "status": "AVAILABLE",
    }
    insert_result = db_manager.blood_units.insert_one(sample_unit)
    assert insert_result.inserted_id is not None

    retrieved = db_manager.blood_units.find_one({"unit_id": "UNIT-TEST-001"})
    assert retrieved is not None
    assert retrieved["blood_group"] == "O"
    assert retrieved["rh_factor"] == "NEGATIVE"
    assert retrieved["status"] == "AVAILABLE"


def test_index_definitions_structure():
    """Verify all 11 collections have properly configured index definitions."""
    definitions = get_index_definitions()
    assert len(definitions) == 11

    for col in Collections.ALL_COLLECTIONS:
        assert col in definitions
        assert len(definitions[col]) > 0
        for index_model in definitions[col]:
            assert isinstance(index_model, IndexModel)

    # Verify specific key indexes
    user_indexes = {idx.document["name"]: idx for idx in definitions[Collections.USERS]}
    assert "idx_users_username_unique" in user_indexes
    assert user_indexes["idx_users_username_unique"].document.get("unique") is True

    unit_indexes = {idx.document["name"]: idx for idx in definitions[Collections.BLOOD_UNITS]}
    assert "idx_units_allocation_search" in unit_indexes
    assert "idx_units_unit_id_unique" in unit_indexes

    notif_indexes = {idx.document["name"]: idx for idx in definitions[Collections.NOTIFICATIONS]}
    assert "idx_notif_ttl_30d" in notif_indexes
    assert notif_indexes["idx_notif_ttl_30d"].document.get("expireAfterSeconds") == 2592000

    hospital_indexes = {idx.document["name"]: idx for idx in definitions[Collections.HOSPITALS]}
    assert "idx_hospitals_location_2dsphere" in hospital_indexes


def test_root_endpoint(client: TestClient):
    """Verify root API endpoint responds with valid identification payload."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "Secure Centralized Blood Bank Management System" in data["system"]
    assert "docs_url" in data


def test_health_endpoint(client: TestClient):
    """Verify liveness probe endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" in data


def test_database_health_endpoint(client: TestClient):
    """Verify deep database health endpoint."""
    response = client.get("/api/health/db")
    assert response.status_code in (200, 503)
    data = response.json()
    assert data["component"] == "MongoDB"
    assert "diagnostics" in data
