"""
Pytest configuration and shared test fixtures.
Provides isolated test clients, in-memory MongoDB fixtures (via mongomock),
and clean database teardown.
"""
import os
import sys
from pathlib import Path
import pytest
import mongomock
from fastapi.testclient import TestClient

# Ensure backend root is on Python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Force testing environment
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_NAME"] = "test_secure_blood_bank"

from app.config.settings import get_settings
from app.config.database import db_manager, Collections
from app.main import app


@pytest.fixture(scope="session")
def test_settings():
    """Returns application test settings."""
    settings = get_settings()
    return settings


@pytest.fixture(scope="function")
def mock_db():
    """
    Provides an isolated in-memory MongoDB database instance per test function using mongomock.
    Guarantees that tests run deterministically and without requiring an external MongoDB server.
    """
    mock_client = mongomock.MongoClient()
    db_manager.connect(client=mock_client)
    yield db_manager.db
    # Teardown
    db_manager.disconnect()


@pytest.fixture(scope="function")
def client(mock_db):
    """
    TestClient fixture equipped with the in-memory mock database.
    """
    with TestClient(app) as test_client:
        yield test_client
