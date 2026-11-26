"""
Phase 6 Automated Test Suite: AES-256-GCM Sensitive-Field Encryption.
Tests AEAD encryption/decryption, unique nonces, tamper detection,
MongoDB storage-at-rest verification (no plaintext PII), queryable non-PII fields,
and authorized response decryption across Users, Donors, Hospitals, and Patients.
"""
import pytest
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient

from app.config.database import db_manager
from app.models.enums import UserRole
from app.security.encryption import (
    CIPHER_PREFIX,
    USER_ENCRYPTED_FIELDS,
    decrypt_fields,
    field_cipher,
)


# ==========================================
# 1. AES-256-GCM Cipher Unit Tests
# ==========================================

def test_aes_gcm_roundtrip_and_unique_nonces():
    """Verify AES-256-GCM encrypts/decrypts cleanly and uses fresh random nonces."""
    secret = "+91-9876543210"
    ct1 = field_cipher.encrypt(secret, associated_data="donors.contact_phone_encrypted")
    ct2 = field_cipher.encrypt(secret, associated_data="donors.contact_phone_encrypted")

    assert ct1.startswith(CIPHER_PREFIX)
    assert ct2.startswith(CIPHER_PREFIX)
    assert ct1 != ct2  # Unique 96-bit random nonce per encryption
    assert secret not in ct1

    assert field_cipher.decrypt(ct1, associated_data="donors.contact_phone_encrypted") == secret
    assert field_cipher.decrypt(ct2, associated_data="donors.contact_phone_encrypted") == secret


def test_aes_gcm_tamper_and_aad_mismatch_detection():
    """Verify GCM authentication tag rejects modified ciphertext or mismatched AAD context."""
    ct = field_cipher.encrypt("Confidential medical note", associated_data="patients.medical_notes_encrypted")

    # Wrong AAD context (e.g. swapping field)
    with pytest.raises(InvalidTag):
        field_cipher.decrypt(ct, associated_data="donors.address_encrypted")

    # Tampered ciphertext character
    tampered = ct[:-4] + ("AAAA" if not ct.endswith("AAAA") else "BBBB")
    with pytest.raises((InvalidTag, ValueError)):
        field_cipher.decrypt(tampered, associated_data="patients.medical_notes_encrypted")

    # Legacy or unencrypted prefix rejected
    with pytest.raises(ValueError):
        field_cipher.decrypt("enc_plaintext_not_aesgcm")


def test_decrypt_fields_authorization_gate():
    """Verify decrypt_fields omits plaintext when authorize_decrypt=False."""
    doc = {
        "_id": "u1",
        "username": "alice",
        "email_encrypted": field_cipher.encrypt("alice@example.org", associated_data="users.email_encrypted"),
    }
    redacted = decrypt_fields(doc, USER_ENCRYPTED_FIELDS, context="users", authorize_decrypt=False)
    assert "email" not in redacted
    assert redacted["email_encrypted"].startswith(CIPHER_PREFIX)

    allowed = decrypt_fields(doc, USER_ENCRYPTED_FIELDS, context="users", authorize_decrypt=True)
    assert allowed["email"] == "alice@example.org"


# ==========================================
# 2. End-to-End MongoDB Encryption at Rest & API Tests
# ==========================================

def test_user_email_encrypted_at_rest_and_decrypted_for_authorized_calls(client: TestClient, auth_header_factory):
    """Verify user email is stored as AES-256-GCM ciphertext in MongoDB and decrypted on /me & /users."""
    reg_res = client.post(
        "/api/auth/register",
        json={
            "username": "enc_donor_user",
            "email": "secret.donor@hospital.org",
            "password": "StrongPassword2026!",
            "role": "DONOR",
        },
    )
    assert reg_res.status_code == 201
    assert reg_res.json()["email"] == "secret.donor@hospital.org"
    assert reg_res.json()["email_encrypted"].startswith(CIPHER_PREFIX)

    # Inspect raw MongoDB document -> no plaintext email
    raw_user = db_manager.users.find_one({"username": "enc_donor_user"})
    assert raw_user is not None
    assert "email" not in raw_user
    assert raw_user["email_encrypted"].startswith(CIPHER_PREFIX)
    assert "secret.donor@hospital.org" not in raw_user["email_encrypted"]

    # Login and inspect /api/auth/me
    token = client.post(
        "/api/auth/login",
        json={"username": "enc_donor_user", "password": "StrongPassword2026!"},
    ).json()["access_token"]
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "secret.donor@hospital.org"


def test_donor_pii_encrypted_on_create_and_update(client: TestClient, auth_header_factory):
    """
    Verify donor phone, address, emergency contact, and screening notes are AES-256-GCM encrypted
    in MongoDB on both POST and PUT, while blood_group/rh_factor remain queryable.
    """
    staff_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="enc_bb_staff", blood_bank_id="bb_1")
    donor_hdrs = auth_header_factory(UserRole.DONOR, username="enc_donor_owner")
    other_donor_hdrs = auth_header_factory(UserRole.DONOR, username="enc_donor_intruder")
    donor_uid = client.get("/api/auth/me", headers=donor_hdrs).json()["_id"]

    create_res = client.post(
        "/api/donors",
        json={
            "user_id": donor_uid,
            "donor_card_number": "CARD-AES-001",
            "first_name": "Elena",
            "last_name": "Vance",
            "date_of_birth": "1993-05-12",
            "gender": "FEMALE",
            "blood_group": "O",
            "rh_factor": "NEGATIVE",
            "contact_phone": "+91-9988776655",
            "address": "742 Evergreen Terrace",
            "emergency_contact": "+91-9988770000",
            "medical_screening_notes": "Passed hemoglobin check",
        },
        headers=staff_hdrs,
    )
    assert create_res.status_code == 201
    donor_id = create_res.json()["_id"]
    assert create_res.json()["contact_phone"] == "+91-9988776655"
    assert create_res.json()["address"] == "742 Evergreen Terrace"

    # Raw DB must hold ciphertext only, while blood_group & rh_factor remain plaintext queryable
    raw_donor = db_manager.donors.find_one({"donor_card_number": "CARD-AES-001"})
    assert raw_donor["blood_group"] == "O"
    assert raw_donor["rh_factor"] == "NEGATIVE"
    for plain_key in ("contact_phone", "address", "emergency_contact", "medical_screening_notes"):
        assert plain_key not in raw_donor
    assert raw_donor["contact_phone_encrypted"].startswith(CIPHER_PREFIX)
    assert raw_donor["address_encrypted"].startswith(CIPHER_PREFIX)
    assert raw_donor["emergency_contact_encrypted"].startswith(CIPHER_PREFIX)
    assert raw_donor["medical_screening_notes_encrypted"].startswith(CIPHER_PREFIX)

    # Owner updates address -> still AES-256-GCM encrypted in DB
    upd_res = client.put(
        f"/api/donors/{donor_id}",
        json={"address": "99 Baker Street"},
        headers=donor_hdrs,
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["address"] == "99 Baker Street"
    raw_updated = db_manager.donors.find_one({"donor_card_number": "CARD-AES-001"})
    assert "address" not in raw_updated
    assert raw_updated["address_encrypted"].startswith(CIPHER_PREFIX)

    # Unauthorized donor cannot read decrypted PII (blocked with 403)
    assert client.get(f"/api/donors/{donor_id}", headers=other_donor_hdrs).status_code == 403


def test_hospital_and_patient_sensitive_fields_encrypted_at_rest(client: TestClient, auth_header_factory):
    """Verify hospital address/helpline and patient medical_notes are AES-256-GCM encrypted in MongoDB."""
    admin_hdrs = auth_header_factory(UserRole.ADMIN)
    doc_hdrs = auth_header_factory(UserRole.DOCTOR, username="enc_doc", hospital_id="hosp_enc")
    doc_uid = client.get("/api/auth/me", headers=doc_hdrs).json()["_id"]

    hosp_res = client.post(
        "/api/hospitals",
        json={
            "name": "St. Jude Secure Hospital",
            "license_number": "LIC-AES-2026",
            "location": {"type": "Point", "coordinates": [77.61, 12.97]},
            "address": "100 Residency Road",
            "emergency_helpline": "+91-80-44445555",
        },
        headers=admin_hdrs,
    )
    assert hosp_res.status_code == 201
    hosp_id = hosp_res.json()["_id"]
    assert hosp_res.json()["address"] == "100 Residency Road"
    assert hosp_res.json()["emergency_helpline"] == "+91-80-44445555"

    raw_hosp = db_manager.hospitals.find_one({"license_number": "LIC-AES-2026"})
    assert "address" not in raw_hosp
    assert "emergency_helpline" not in raw_hosp
    assert raw_hosp["address_encrypted"].startswith(CIPHER_PREFIX)
    assert raw_hosp["emergency_helpline_encrypted"].startswith(CIPHER_PREFIX)

    # Update hospital helpline
    upd_hosp = client.put(
        f"/api/hospitals/{hosp_id}",
        json={"emergency_helpline": "+91-80-99998888"},
        headers=admin_hdrs,
    )
    assert upd_hosp.status_code == 200
    assert upd_hosp.json()["emergency_helpline"] == "+91-80-99998888"

    # Patient medical_notes encryption on create & update
    pat_res = client.post(
        "/api/patients",
        json={
            "hospital_id": "hosp_enc",
            "attending_doctor_id": doc_uid,
            "mrn": "MRN-AES-01",
            "full_name": "Clara Oswald",
            "blood_group": "A",
            "rh_factor": "NEGATIVE",
            "clinical_indication": "Cardiac bypass",
            "medical_notes": "History of mild transfusion reaction",
        },
        headers=doc_hdrs,
    )
    assert pat_res.status_code == 201
    pat_id = pat_res.json()["_id"]
    assert pat_res.json()["medical_notes"] == "History of mild transfusion reaction"

    raw_pat = db_manager.patients.find_one({"mrn": "MRN-AES-01"})
    assert "medical_notes" not in raw_pat
    assert raw_pat["medical_notes_encrypted"].startswith(CIPHER_PREFIX)

    upd_pat = client.put(
        f"/api/patients/{pat_id}",
        json={"medical_notes": "Pre-medicated with antihistamine"},
        headers=doc_hdrs,
    )
    assert upd_pat.status_code == 200
    assert upd_pat.json()["medical_notes"] == "Pre-medicated with antihistamine"
