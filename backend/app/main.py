"""
FastAPI Main Application.
Provides application lifecycle management, CORS middleware, and system health checks.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config.settings import get_settings
from app.config.database import db_manager
from app.schemas.audit_schema import AuditStatus
from app.services.audit_service import AuditService

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

    if settings.FORCE_HTTPS_REDIRECT:
        app.add_middleware(HTTPSRedirectMiddleware)

    audit_service = AuditService()

    @app.exception_handler(HTTPException)
    async def http_exception_audit_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """
        Centralized security audit hook recording all HTTP 403 Forbidden authorization denials.
        """
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            path_parts = [p for p in request.url.path.split("/") if p]
            resource_type = path_parts[1] if len(path_parts) > 1 else (path_parts[0] if path_parts else "system")
            resource_id = path_parts[2] if len(path_parts) > 2 else None
            actor = getattr(request.state, "current_user", None)
            audit_service.log_event(
                action="ACCESS_DENIED",
                resource_type=resource_type,
                resource_id=resource_id,
                status=AuditStatus.DENIED.value,
                actor=actor,
                metadata={
                    "method": request.method,
                    "path": request.url.path,
                    "reason": str(exc.detail),
                    "client_ip": request.client.host if request.client else None,
                },
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    @app.get("/", tags=["Root"])
    async def root(request: Request):
        """
        Root endpoint returning system identification for API clients,
        or redirecting interactive browsers to the web interface.
        """
        accept = request.headers.get("accept", "")
        if "text/html" in accept.lower():
            return RedirectResponse(url="/ui/login.html", status_code=status.HTTP_302_FOUND)
        return {
            "system": settings.PROJECT_NAME,
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
            "status": "online",
            "docs_url": f"{settings.API_V1_PREFIX}/docs",
            "ui_url": "/ui/login.html",
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
        audit_router,
        notification_router,
        blood_camp_router,
        analytics_router,
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
    app.include_router(audit_router, prefix=api_prefix)
    app.include_router(notification_router, prefix=api_prefix)
    app.include_router(blood_camp_router, prefix=api_prefix)
    app.include_router(analytics_router, prefix=api_prefix)

    # Serve Multi-Role Frontend Static Interface at /ui
    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
    if frontend_dir.exists() and frontend_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app


app = create_application()
