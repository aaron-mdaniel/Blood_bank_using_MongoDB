# Security Architecture & Cryptographic Controls

## 1. Authentication & Credential Protection
- **Argon2id Password Hashing** ([hashing.py](file:///c:/Users/AARON/Downloads/M.%20Tech/ADBMS%20Seminar/ADBMS%20Project/backend/app/security/hashing.py)): Uses `argon2-cffi` (`time_cost=3`, `memory_cost=65536` KiB, `parallelism=4`). Plaintext passwords are never stored, logged, or returned.
- **Brute-Force Lockout**: After 5 consecutive failed logins, `UserRepository.increment_failed_attempts` locks the account for 15 minutes (`HTTP 403`).
- **JWT Bearer Sessions** ([jwt_handler.py](file:///c:/Users/AARON/Downloads/M.%20Tech/ADBMS%20Seminar/ADBMS%20Project/backend/app/security/jwt_handler.py)): HS256-signed tokens with `sub`, `username`, `role`, `hospital_id`, `blood_bank_id`, `iat`, `exp`, and `jti`. Logout revokes `jti` via `token_blacklist`.
- **Privilege Escalation Prevention**: `POST /api/auth/register` rejects `ADMIN` self-registration (`HTTP 403`); `ADMIN` accounts are provisioned via Admin-only `POST /api/users`.

## 2. Authorization Layers (RBAC + ABAC)
- **RBAC** ([permissions.py](file:///c:/Users/AARON/Downloads/M.%20Tech/ADBMS%20Seminar/ADBMS%20Project/backend/app/models/permissions.py), [rbac_service.py](file:///c:/Users/AARON/Downloads/M.%20Tech/ADBMS%20Seminar/ADBMS%20Project/backend/app/services/rbac_service.py)): Permissions are stored in `roles_permissions` and enforced on every protected endpoint (`401` unauthenticated, `403` unauthorized).
- **ABAC** ([abac.py](file:///c:/Users/AARON/Downloads/M.%20Tech/ADBMS%20Seminar/ADBMS%20Project/backend/app/security/abac.py)):
  - `DONOR`: Own donor profile and own donations only; clinical eligibility fields protected from donor self-modification.
  - `HOSPITAL_STAFF`: Scoped to assigned `hospital_id` for patients/requests and `AVAILABLE` blood units.
  - `DOCTOR`: Scoped to assigned patients (`attending_doctor_id == user._id`) and own requests.
  - `BLOOD_BANK_STAFF`: Scoped to assigned `blood_bank_id` for donations, blood units, allocations, and blood camps.

## 3. Sensitive-Field Encryption (AES-256-GCM)
- Implemented in [encryption.py](file:///c:/Users/AARON/Downloads/M.%20Tech/ADBMS%20Seminar/ADBMS%20Project/backend/app/security/encryption.py) using a 256-bit environment key (`ENCRYPTION_SECRET_KEY`).
- Generates a fresh 96-bit random nonce per encryption (`aesgcm:v1:<base64(nonce + ciphertext + tag)>`).
- Uses AEAD Associated Data (`<collection>.<encrypted_field>`) to detect both ciphertext tampering and cross-field substitution.
- Plaintext fields are decrypted only in authorized API responses and omitted whenever `authorize_decrypt=False`.

## 4. Centralized Audit Logging & Transport Security
- **Audit Redaction** ([audit_service.py](file:///c:/Users/AARON/Downloads/M.%20Tech/ADBMS%20Seminar/ADBMS%20Project/backend/app/services/audit_service.py)): Recursively redacts passwords, tokens, JWT/encryption secrets, and PII as `"[REDACTED]"`.
- **Global `403` Capture** ([main.py](file:///c:/Users/AARON/Downloads/M.%20Tech/ADBMS%20Seminar/ADBMS%20Project/backend/app/main.py)): Records all `HTTP 403` denials as `ACCESS_DENIED` in `audit_logs`.
- **HTTPS / TLS**: Supported via `SSL_CERTFILE`/`SSL_KEYFILE` in [run.py](file:///c:/Users/AARON/Downloads/M.%20Tech/ADBMS%20Seminar/ADBMS%20Project/backend/run.py), `FORCE_HTTPS_REDIRECT`, and [nginx-tls.conf](file:///c:/Users/AARON/Downloads/M.%20Tech/ADBMS%20Seminar/ADBMS%20Project/backend/deploy/nginx-tls.conf).
