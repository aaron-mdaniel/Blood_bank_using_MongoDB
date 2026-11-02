"""
MongoDB Index Creation Script.
Applies compound, unique, geospatial (2dsphere), and TTL indexes
across all 11 collections of the Secure Centralized Blood Bank Management System.
"""
import sys
import logging
from pathlib import Path
from typing import Dict, List, Any
from pymongo import ASCENDING, DESCENDING, GEOSPHERE, IndexModel
from pymongo.database import Database

# Add backend directory to sys.path to allow absolute imports
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config.settings import get_settings
from app.config.database import db_manager, Collections

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("secure_blood_bank.indexes")


def get_index_definitions() -> Dict[str, List[IndexModel]]:
    """
    Defines all index models for the 11 MongoDB collections.
    """
    return {
        Collections.USERS: [
            IndexModel([("username", ASCENDING)], unique=True, name="idx_users_username_unique"),
            IndexModel([("email_hash", ASCENDING)], unique=True, sparse=True, name="idx_users_email_hash_unique"),
            IndexModel([("role", ASCENDING), ("is_active", ASCENDING)], name="idx_users_role_is_active"),
        ],
        Collections.ROLES_PERMISSIONS: [
            IndexModel([("role_name", ASCENDING)], unique=True, name="idx_roles_role_name_unique"),
        ],
        Collections.DONORS: [
            IndexModel([("user_id", ASCENDING)], unique=True, name="idx_donors_user_id_unique"),
            IndexModel([("donor_card_number", ASCENDING)], unique=True, name="idx_donors_card_number_unique"),
            IndexModel(
                [("blood_group", ASCENDING), ("rh_factor", ASCENDING), ("eligibility_status", ASCENDING)],
                name="idx_donors_group_rh_status"
            ),
        ],
        Collections.HOSPITALS: [
            IndexModel([("license_number", ASCENDING)], unique=True, name="idx_hospitals_license_unique"),
            IndexModel([("location", GEOSPHERE)], name="idx_hospitals_location_2dsphere"),
            IndexModel([("verification_status", ASCENDING)], name="idx_hospitals_verification_status"),
        ],
        Collections.PATIENTS: [
            IndexModel([("hospital_id", ASCENDING), ("mrn", ASCENDING)], unique=True, name="idx_patients_hospital_mrn_unique"),
            IndexModel([("attending_doctor_id", ASCENDING)], name="idx_patients_doctor_id"),
        ],
        Collections.DONATIONS: [
            IndexModel([("donation_code", ASCENDING)], unique=True, name="idx_donations_code_unique"),
            IndexModel([("donor_id", ASCENDING), ("donation_date", DESCENDING)], name="idx_donations_donor_date"),
            IndexModel([("screening_status", ASCENDING)], name="idx_donations_screening_status"),
        ],
        Collections.BLOOD_UNITS: [
            IndexModel([("unit_id", ASCENDING)], unique=True, name="idx_units_unit_id_unique"),
            IndexModel(
                [
                    ("blood_group", ASCENDING),
                    ("rh_factor", ASCENDING),
                    ("component_type", ASCENDING),
                    ("status", ASCENDING),
                    ("expiry_date", ASCENDING),
                ],
                name="idx_units_allocation_search"
            ),
            IndexModel([("expiry_date", ASCENDING), ("status", ASCENDING)], name="idx_units_expiry_status"),
            IndexModel([("status", ASCENDING)], name="idx_units_status"),
        ],
        Collections.BLOOD_REQUESTS: [
            IndexModel([("request_code", ASCENDING)], unique=True, name="idx_requests_code_unique"),
            IndexModel([("hospital_id", ASCENDING), ("status", ASCENDING)], name="idx_requests_hospital_status"),
            IndexModel(
                [("status", ASCENDING), ("priority", DESCENDING), ("created_at", ASCENDING)],
                name="idx_requests_triage_queue"
            ),
        ],
        Collections.BLOOD_CAMPS: [
            IndexModel([("location", GEOSPHERE)], name="idx_camps_location_2dsphere"),
            IndexModel([("start_time", ASCENDING), ("status", ASCENDING)], name="idx_camps_start_status"),
        ],
        Collections.NOTIFICATIONS: [
            IndexModel([("user_id", ASCENDING), ("is_read", ASCENDING), ("created_at", DESCENDING)], name="idx_notif_user_read_date"),
            # TTL Index: Automatically expire notifications after 30 days (2,592,000 seconds)
            IndexModel([("created_at", ASCENDING)], expireAfterSeconds=2592000, name="idx_notif_ttl_30d"),
        ],
        Collections.AUDIT_LOGS: [
            IndexModel([("timestamp", DESCENDING)], name="idx_audit_timestamp_desc"),
            IndexModel([("actor.user_id", ASCENDING), ("timestamp", DESCENDING)], name="idx_audit_actor_time"),
            IndexModel([("action", ASCENDING), ("status", ASCENDING)], name="idx_audit_action_status"),
            IndexModel([("resource_type", ASCENDING), ("resource_id", ASCENDING)], name="idx_audit_resource"),
        ],
    }


def setup_indexes(db: Database) -> Dict[str, List[str]]:
    """
    Creates all defined indexes in the target MongoDB database.
    Returns a dictionary of created index names keyed by collection name.
    """
    created_summary = {}
    definitions = get_index_definitions()

    for col_name, index_models in definitions.items():
        collection = db[col_name]
        try:
            result_names = collection.create_indexes(index_models)
            created_summary[col_name] = result_names
            logger.info(f"Collection '{col_name}': {len(result_names)} indexes confirmed ({', '.join(result_names)})")
        except Exception as exc:
            logger.error(f"Failed to create indexes on collection '{col_name}': {exc}")
            raise

    return created_summary


def main():
    """CLI entrypoint to run index creation against the configured database."""
    settings = get_settings()
    logger.info(f"Initializing MongoDB indexes for database: {settings.DATABASE_NAME} ({settings.MONGODB_URL})")

    connected = db_manager.connect()
    if not connected:
        logger.error("Could not connect to MongoDB. Ensure mongod service is active or Atlas URI is valid.")
        sys.exit(1)

    try:
        summary = setup_indexes(db_manager.db)
        total_indexes = sum(len(v) for v in summary.values())
        logger.info(f"Successfully configured {total_indexes} indexes across all {len(summary)} collections.")
    finally:
        db_manager.disconnect()


if __name__ == "__main__":
    main()
