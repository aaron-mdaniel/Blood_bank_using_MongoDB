"""
FastAPI Main Application.
Provides application lifecycle management, CORS middleware, and system health checks.
"""
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import get_settings
from app.config.database import db_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("secure_blood_bank.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup connection pooling and graceful shutdown.
    """
    settings = get_settings()
    logger.info(f"Starting {settings.PROJECT_NAME} in '{settings.ENVIRONMENT}' mode...")

    # Connect to MongoDB if not already initialized
    if not db_manager.is_connected:
        connected = db_manager.connect()
        if connected:
            logger.info("MongoDB connection verified successfully.")
        else:
            logger.warning("MongoDB is currently offline or unreachable. Check database configuration.")
    else:
        logger.info("MongoDB connection already active (e.g. test fixture or injected client).")

    # Ensure canonical RBAC role definitions exist in MongoDB when connected
    if db_manager.is_connected:
        from app.services.rbac_service import RBACService
        RBACService().ensure_seeded()

    yield

    # Teardown
    if settings.ENVIRONMENT != "testing":
        logger.info("Shutting down application and closing database connections...")
        db_manager.disconnect()


def create_application() -> FastAPI:
    """
    Factory function creating and configuring the FastAPI instance.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        description=(
            "Centralized Blood Bank Management System demonstrating NoSQL database architecture, "
            "Argon2id hashing, AES-256-GCM field encryption, RBAC, ABAC, and security auditing."
        ),
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        redoc_url=f"{settings.API_V1_PREFIX}/redoc",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint returning system identification and API status."""
        return {
            "system": settings.PROJECT_NAME,
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
            "status": "online",
            "docs_url": f"{settings.API_V1_PREFIX}/docs",
        }

    @app.get(f"{settings.API_V1_PREFIX}/health", tags=["Health"])
    async def health_check() -> Dict[str, Any]:
        """Liveness probe for backend API container / service."""
        return {
            "status": "healthy",
            "environment": settings.ENVIRONMENT,
            "database_connected": db_manager.is_connected,
        }

    @app.get(f"{settings.API_V1_PREFIX}/health/db", tags=["Health"])
    async def database_health_check() -> JSONResponse:
        """
        Deep database readiness check.
        Executes MongoDB ping and reports connection status, latency, and collection metrics.
        """
        db_status = db_manager.ping()
        http_status = status.HTTP_200_OK if db_status.get("status") == "connected" else status.HTTP_503_SERVICE_UNAVAILABLE

        return JSONResponse(
            status_code=http_status,
            content={
                "component": "MongoDB",
                "database_name": settings.DATABASE_NAME,
                "diagnostics": db_status,
            }
        )

    # Register Domain CRUD & Authentication Routers
    from app.routers import (
        auth_router,
        user_router,
        role_router,
        donor_router,
        hospital_router,
        patient_router,
        donation_router,
        blood_unit_router,
        blood_request_router,
    )

    api_prefix = settings.API_V1_PREFIX
    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(user_router, prefix=api_prefix)
    app.include_router(role_router, prefix=api_prefix)
    app.include_router(donor_router, prefix=api_prefix)
    app.include_router(hospital_router, prefix=api_prefix)
    app.include_router(patient_router, prefix=api_prefix)
    app.include_router(donation_router, prefix=api_prefix)
    app.include_router(blood_unit_router, prefix=api_prefix)
    app.include_router(blood_request_router, prefix=api_prefix)

    return app


app = create_application()
