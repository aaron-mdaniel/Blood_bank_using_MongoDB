"""
Centralized Security Audit Logging Service.
Records authentication events, RBAC/ABAC denials, administrative changes,
and clinical inventory/request lifecycle operations while redacting sensitive data.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.repositories.audit_repository import AuditRepository
from app.schemas.audit_schema import AuditStatus

logger = logging.getLogger("secure_blood_bank.audit")

# Keys that must NEVER appear in plaintext inside audit_logs metadata
SENSITIVE_METADATA_KEYS = frozenset({
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "secret",
    "jwt_secret_key",
    "encryption_secret_key",
    "email",
    "email_encrypted",
    "contact_phone",
    "contact_phone_encrypted",
    "phone",
    "address",
    "address_encrypted",
    "emergency_contact",
    "emergency_contact_encrypted",
    "emergency_helpline",
    "emergency_helpline_encrypted",
    "medical_notes",
    "medical_notes_encrypted",
    "medical_screening_notes",
    "medical_screening_notes_encrypted",
})


def sanitize_metadata(value: Any) -> Any:
    """
    Recursively redacts sensitive keys (passwords, tokens, secrets, PII) from audit metadata.
    """
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for k, v in value.items():
            key_lower = str(k).strip().lower()
            if key_lower in SENSITIVE_METADATA_KEYS or any(
                frag in key_lower for frag in ("password", "secret", "private_key", "jwt", "token")
            ):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_metadata(v)
        return sanitized
    if isinstance(value, list):
        return [sanitize_metadata(item) for item in value]
    return value


class AuditService:
    """
    Centralized service for creating and querying tamper-aware audit log entries.
    """

    def __init__(self, audit_repo: AuditRepository = None):
        self.audit_repo = audit_repo or AuditRepository()

    @staticmethod
    def build_actor(actor: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
        if not actor:
            return {"user_id": None, "username": None, "role": "ANONYMOUS"}
        user_id = actor.get("_id") or actor.get("user_id") or actor.get("sub")
        return {
            "user_id": str(user_id) if user_id is not None else None,
            "username": actor.get("username"),
            "role": str(actor.get("role")) if actor.get("role") else None,
        }

    def log_event(
        self,
        action: str,
        resource_type: str,
        status: str = AuditStatus.SUCCESS.value,
        actor: Optional[Dict[str, Any]] = None,
        resource_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Persists a structured audit record into MongoDB audit_logs.
        Redacts any sensitive fields in metadata before storage.
        """
        now = datetime.now(timezone.utc)
        clean_metadata = sanitize_metadata(metadata or {})

        record = {
            "event_id": f"EVT-{uuid.uuid4().hex[:12].upper()}",
            "timestamp": now,
            "actor": self.build_actor(actor),
            "action": str(action),
            "resource_type": str(resource_type),
            "resource_id": str(resource_id) if resource_id is not None else None,
            "status": status.value if isinstance(status, AuditStatus) else str(status),
            "metadata": clean_metadata,
            "created_at": now,
            "updated_at": now,
        }

        try:
            return self.audit_repo.create(record)
        except Exception as exc:
            logger.error(f"Failed to persist audit event '{action}': {exc}")
            return None

    def list_audit_logs(
        self,
        action: Optional[str] = None,
        audit_status: Optional[str] = None,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return self.audit_repo.query_logs(
            action=action,
            audit_status=audit_status,
            user_id=user_id,
            resource_type=resource_type,
            start_time=start_time,
            end_time=end_time,
            skip=skip,
            limit=limit,
        )

    def get_audit_log(self, log_id: str) -> Dict[str, Any]:
        doc = self.audit_repo.get_by_event_id(log_id)
        if not doc:
            try:
                doc = self.audit_repo.get_by_id(log_id)
            except ValueError:
                doc = None
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audit log record not found.",
            )
        return doc
