# REST API Reference

Base URL: `http://127.0.0.1:8000` (Interactive OpenAPI Docs: `/api/docs` and `/api/redoc`)

| Router | Endpoint | Method | Required Permission / Auth | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| Health | `/api/health`, `/api/health/db` | `GET` | Public | API liveness and MongoDB connectivity/latency |
| Auth | `/api/auth/register`, `/api/auth/login` | `POST` | Public (`ADMIN` reg blocked) | Account registration & Argon2id/JWT login |
| Auth | `/api/auth/me`, `/api/auth/logout` | `GET`, `POST` | Authenticated Bearer JWT | Current user profile & `jti` session revocation |
| Users | `/api/users`, `/api/users/{user_id}` | `POST`, `GET`, `PUT`, `DELETE` | `users:read/write/delete` (`ADMIN`) | System user & role management |
| Roles | `/api/roles`, `/api/roles/{role_name}`, `/api/roles/seed` | `GET`, `PUT`, `POST` | `roles:read/write` (`ADMIN`) | Inspect, customize, or reset RBAC matrix |
| Donors | `/api/donors`, `/api/donors/{donor_id}` | `POST`, `GET`, `PUT`, `DELETE` | `donors:read/write/delete` + ABAC | Donor profiles with encrypted PII |
| Hospitals | `/api/hospitals`, `/api/hospitals/nearby`, `/api/hospitals/{id}` | `POST`, `GET`, `PUT` | `hospitals:read/write` | Hospital records & `2dsphere` nearby lookup |
| Patients | `/api/patients`, `/api/patients/{patient_id}` | `POST`, `GET`, `PUT` | `patients:read/write` + ABAC | Patient records with encrypted `medical_notes` |
| Donations | `/api/donations`, `/api/donations/{id}`, `/api/donations/{id}/separate-components` | `POST`, `GET`, `PUT` | `donations:read/write` + ABAC | Donation events & component unit generation |
| Blood Units | `/api/blood-units`, `/api/blood-units/{unit_id}` | `POST`, `GET`, `PUT` | `blood_units:read/write` + ABAC | Individual blood unit inventory tracking |
| Blood Requests | `/api/blood-requests`, `/api/blood-requests/triage`, `/api/blood-requests/{id}` | `POST`, `GET`, `PUT` | `blood_requests:read/write/approve` + ABAC | Request submission & priority triage queue |
| Blood Requests | `/api/blood-requests/{id}/approve`, `/reject`, `/allocate` | `POST` | `blood_requests:approve` + ABAC | Request decision & FIFO atomic unit allocation |
| Blood Camps | `/api/blood-camps`, `/api/blood-camps/nearby`, `/api/blood-camps/{id}` | `POST`, `GET`, `PUT` | `camps:read/write` + ABAC | Community drives & `2dsphere` nearby search |
| Notifications | `/api/notifications`, `/{id}/read`, `/read-all`, `/scan-alerts` | `GET`, `PATCH`, `POST` | `notifications:read/write` + ABAC | User-scoped alerts & expiry/low-stock scanner |
| Analytics | `/api/analytics/dashboard`, `/inventory-distribution`, `/change-streams/status` | `GET` | `reports:read` or `blood_units:read` | MongoDB aggregation stats & change streams |
| Audit | `/api/audit`, `/api/audit/{log_id}` | `GET` | `audit:read` (`ADMIN` only) | Compliance & security audit log viewer |
