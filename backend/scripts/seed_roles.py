"""
MongoDB Role-Permission Seeding Script.
Populates the roles_permissions collection with canonical RBAC definitions
for ADMIN, BLOOD_BANK_STAFF, HOSPITAL_STAFF, DOCTOR, and DONOR.
"""
import sys
import logging
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config.settings import get_settings
from app.config.database import db_manager
from app.services.rbac_service import RBACService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("secure_blood_bank.seed_roles")


def main():
    """CLI entrypoint to seed default RBAC roles into MongoDB."""
    settings = get_settings()
    logger.info(f"Seeding RBAC roles in database: {settings.DATABASE_NAME} ({settings.MONGODB_URL})")

    if not db_manager.connect():
        logger.error("Could not connect to MongoDB. Ensure mongod service is active or Atlas URI is valid.")
        sys.exit(1)

    try:
        rbac_service = RBACService()
        roles = rbac_service.reset_defaults()
        logger.info(f"Successfully seeded {len(roles)} RBAC roles into 'roles_permissions'.")
    finally:
        db_manager.disconnect()


if __name__ == "__main__":
    main()
