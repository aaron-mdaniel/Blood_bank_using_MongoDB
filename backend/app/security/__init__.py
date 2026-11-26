"""
Security package: password hashing, JWT authentication, and request dependencies.
"""
from app.security.hashing import hash_password, verify_password, check_needs_rehash
from app.security.jwt_handler import (
    create_access_token,
    decode_access_token,
    token_blacklist,
)
from app.security.dependencies import (
    oauth2_scheme,
    get_current_user,
    get_current_token_and_payload,
    require_roles,
    require_permissions,
)
from app.security import abac
from app.security.encryption import (
    FieldCipher,
    field_cipher,
    encrypt_fields,
    decrypt_fields,
)

__all__ = [
    "hash_password",
    "verify_password",
    "check_needs_rehash",
    "create_access_token",
    "decode_access_token",
    "token_blacklist",
    "oauth2_scheme",
    "get_current_user",
    "get_current_token_and_payload",
    "require_roles",
    "require_permissions",
    "abac",
    "FieldCipher",
    "field_cipher",
    "encrypt_fields",
    "decrypt_fields",
]
