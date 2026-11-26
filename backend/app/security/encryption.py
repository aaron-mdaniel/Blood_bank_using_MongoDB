"""
AES-256-GCM Authenticated Field-Level Encryption Module.
Encrypts sensitive PII and clinical notes before persistence in MongoDB
and decrypts them only for authorized application responses.
"""
import base64
import binascii
import os
from typing import Any, Dict, Optional
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config.settings import get_settings

CIPHER_PREFIX = "aesgcm:v1:"
NONCE_SIZE_BYTES = 12  # 96-bit standard GCM nonce
KEY_SIZE_BYTES = 32    # 256-bit AES key

# Canonical field mappings: plaintext_input_key -> encrypted_db_field_key
USER_ENCRYPTED_FIELDS: Dict[str, str] = {
    "email": "email_encrypted",
}

DONOR_ENCRYPTED_FIELDS: Dict[str, str] = {
    "contact_phone": "contact_phone_encrypted",
    "address": "address_encrypted",
    "emergency_contact": "emergency_contact_encrypted",
    "medical_screening_notes": "medical_screening_notes_encrypted",
}

HOSPITAL_ENCRYPTED_FIELDS: Dict[str, str] = {
    "address": "address_encrypted",
    "emergency_helpline": "emergency_helpline_encrypted",
}

PATIENT_ENCRYPTED_FIELDS: Dict[str, str] = {
    "medical_notes": "medical_notes_encrypted",
}


class FieldCipher:
    """
    AES-256-GCM cipher wrapper using the environment-configured 256-bit key.
    Every encryption generates a fresh 96-bit cryptographic random nonce.
    """

    def _get_aesgcm(self) -> AESGCM:
        settings = get_settings()
        raw_b64 = settings.ENCRYPTION_SECRET_KEY
        if not raw_b64:
            raise RuntimeError("ENCRYPTION_SECRET_KEY is not configured.")
        try:
            key_bytes = base64.b64decode(raw_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError("ENCRYPTION_SECRET_KEY must be valid base64.") from exc

        if len(key_bytes) != KEY_SIZE_BYTES:
            raise RuntimeError(
                f"ENCRYPTION_SECRET_KEY must decode to {KEY_SIZE_BYTES} bytes (256 bits), got {len(key_bytes)}."
            )
        return AESGCM(key_bytes)

    def encrypt(
        self,
        plaintext: Optional[str],
        associated_data: Optional[str] = None,
    ) -> Optional[str]:
        """
        Encrypts a plaintext string using AES-256-GCM.
        Returns a versioned token 'aesgcm:v1:<base64(nonce + ciphertext_and_tag)>'.
        """
        if plaintext is None:
            return None
        aesgcm = self._get_aesgcm()
        nonce = os.urandom(NONCE_SIZE_BYTES)
        aad = associated_data.encode("utf-8") if associated_data else None
        ciphertext = aesgcm.encrypt(nonce, str(plaintext).encode("utf-8"), aad)
        packed = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return f"{CIPHER_PREFIX}{packed}"

    def decrypt(
        self,
        token: Optional[str],
        associated_data: Optional[str] = None,
    ) -> Optional[str]:
        """
        Decrypts and verifies an AES-256-GCM token.
        Raises ValueError on malformed format or InvalidTag on ciphertext/AAD tampering.
        """
        if token is None:
            return None
        if not isinstance(token, str) or not token.startswith(CIPHER_PREFIX):
            raise ValueError("Invalid encrypted field format; expected AES-256-GCM v1 token.")

        b64_part = token[len(CIPHER_PREFIX):]
        try:
            raw = base64.urlsafe_b64decode(b64_part.encode("ascii"))
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Corrupted base64 payload in encrypted field.") from exc

        if len(raw) <= NONCE_SIZE_BYTES + 16:
            raise ValueError("Encrypted payload is truncated or missing authentication tag.")

        nonce = raw[:NONCE_SIZE_BYTES]
        ciphertext = raw[NONCE_SIZE_BYTES:]
        aad = associated_data.encode("utf-8") if associated_data else None

        aesgcm = self._get_aesgcm()
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, aad)
        return plaintext_bytes.decode("utf-8")


# Singleton cipher instance
field_cipher = FieldCipher()


def encrypt_fields(
    data: Dict[str, Any],
    field_map: Dict[str, str],
    context: str,
) -> Dict[str, Any]:
    """
    Replaces plaintext keys in `data` (per `field_map`) with AES-256-GCM encrypted fields.
    Binds each encrypted value to `<context>.<encrypted_field>` as AEAD associated data.
    """
    result = dict(data)
    for plain_key, enc_key in field_map.items():
        if plain_key in result:
            plain_val = result.pop(plain_key)
            if plain_val is not None:
                result[enc_key] = field_cipher.encrypt(
                    str(plain_val),
                    associated_data=f"{context}.{enc_key}",
                )
    return result


def decrypt_fields(
    doc: Optional[Dict[str, Any]],
    field_map: Dict[str, str],
    context: str,
    authorize_decrypt: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Returns a shallow copy of `doc` with decrypted plaintext fields populated when
    `authorize_decrypt` is True. Never exposes plaintext when `authorize_decrypt` is False.
    """
    if doc is None:
        return None
    result = dict(doc)
    if not authorize_decrypt:
        for plain_key in field_map:
            result.pop(plain_key, None)
        return result

    for plain_key, enc_key in field_map.items():
        enc_val = result.get(enc_key)
        if not enc_val:
            continue
        if isinstance(enc_val, str) and enc_val.startswith(CIPHER_PREFIX):
            result[plain_key] = field_cipher.decrypt(
                enc_val,
                associated_data=f"{context}.{enc_key}",
            )
    return result
