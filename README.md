# Secure Centralized Blood Bank Management System Using NoSQL

An enterprise-grade academic platform demonstrating advanced NoSQL document modeling, cryptographic security, role-based and resource-level access control, and atomic inventory management.

---

## Technology Stack

- **Frontend**: HTML5, CSS3, Vanilla JavaScript (5 Role-Based Dashboards)
- **Backend**: Python 3.13, FastAPI, Pydantic v2, PyMongo
- **Database**: MongoDB (Local or Atlas) + MongoDB Compass
- **Security**: Argon2id password hashing, AES-256-GCM field-level encryption, JWT Bearer tokens
- **Testing**: Pytest, FastAPI TestClient, mongomock

---

## Directory Structure

```text
secure-blood-bank/
├── backend/
│   ├── app/
│   │   ├── config/
│   │   │   ├── settings.py         # Pydantic BaseSettings environment config
│   │   │   └── database.py         # MongoDB connection manager & collection handles
│   │   ├── models/                 # Domain enums & RBAC permission definitions
│   │   ├── repositories/           # PyMongo data access layer (CRUD & atomic updates)
│   │   ├── routers/                # FastAPI REST routers (Auth, Roles, Domain APIs)
│   │   ├── schemas/                # Pydantic v2 request/response schemas
│   │   ├── security/               # Argon2id, JWT, AES-256-GCM, RBAC & ABAC
│   │   ├── services/               # Auth, RBAC, Audit, Notification, Compatibility & Workflows
│   │   └── main.py                 # FastAPI app, lifespan & 403 audit handler
│   ├── deploy/
│   │   └── nginx-tls.conf          # Production HTTPS/TLS reverse proxy config
│   ├── scripts/
│   │   ├── create_indexes.py       # MongoDB compound, unique, 2dsphere & TTL index script
│   │   ├── seed_roles.py           # Seeds default 5 RBAC roles in roles_permissions
│   │   └── seed_demo.py            # Idempotent academic demo dataset across 11 collections
│   ├── tests/
│   │   ├── conftest.py             # Pytest fixtures, mock DB & role auth header factory
│   │   ├── test_database.py        # Phase 1 verification tests
│   │   ├── test_crud_repositories.py # Phase 2 repository unit tests
│   │   ├── test_crud_api.py        # Phase 2 CRUD API tests
│   │   ├── test_auth.py            # Phase 3 authentication tests
│   │   ├── test_rbac.py            # Phase 4 RBAC authorization tests
│   │   ├── test_abac.py            # Phase 5 resource-level ABAC tests
│   │   ├── test_encryption.py      # Phase 6 AES-256-GCM encryption tests
│   │   ├── test_audit.py           # Phase 7 centralized audit logging tests
│   │   ├── test_workflows.py       # Phase 8 workflows & atomic allocation tests
│   │   ├── test_phase9.py          # Phase 9 aggregations, blood_camps & UI tests
│   │   └── test_e2e_and_performance.py # Phase 10 E2E, concurrency & perf benchmarks
│   ├── .env.example                # Configuration template
│   ├── .env                        # Local configuration
│   ├── requirements.txt            # Python dependencies
│   └── run.py                      # Development server runner
├── documentation/                  # Architecture, DB Schema, Security, API & Postman docs
│   ├── architecture.md
│   ├── database-schema.md
│   ├── security-design.md
│   ├── api-documentation.md
│   └── postman_collection.json
├── frontend/                       # Multi-role HTML5/CSS3/JS Web Interface (/ui)
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── admin/index.html
│   ├── bloodbank/index.html
│   ├── hospital/index.html
│   ├── doctor/index.html
│   ├── donor/index.html
│   ├── css/styles.css
│   └── js/
├── prompt/                         # Academic specifications & requirements
├── .gitignore
└── README.md
```

---

## 11 MongoDB Collections

1. `users` - System actors with role, status, lockout counters, and Argon2id hash
2. `roles_permissions` - Granular RBAC definitions
3. `donors` - Donor profiles with encrypted PII and eligibility tracking
4. `hospitals` - Registered medical centers with geospatial coordinates
5. `patients` - Hospital patient medical records
6. `donations` - Donation events and screening status
7. `blood_units` - Individual blood unit tracking with expiry and storage location
8. `blood_requests` - Clinical transfusion requests with priority queue
9. `blood_camps` - Community blood drives with GeoJSON locations
10. `notifications` - In-app alerts with 30-day TTL index auto-expiration
11. `audit_logs` - Centralized compliance and security audit trails

---

## Setup & Execution Instructions

### 1. Install Dependencies
```bash
python -m pip install -r backend/requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` in the `backend/` directory:
```bash
cp backend/.env.example backend/.env
```
Ensure `MONGODB_URL` points to your active MongoDB instance (e.g. `mongodb://localhost:27017` or MongoDB Atlas URI).

### 3. Initialize MongoDB Indexes, RBAC Roles & Optional Demo Data
```bash
python backend/scripts/create_indexes.py
python backend/scripts/seed_roles.py
python backend/scripts/seed_demo.py   # Optional: seeds 5 demo role accounts & sample records
```

### 4. Run the Development Server
```bash
python backend/run.py
```
Or with Uvicorn directly:
```bash
uvicorn app.main:app --app-dir backend --reload --port 8000
```
Interactive web interface & API documentation will be available at:
- **Web Interface (Login & Role Dashboards)**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/) (or [http://127.0.0.1:8000/ui/login.html](http://127.0.0.1:8000/ui/login.html))
- **Swagger UI**: [http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs)
- **ReDoc**: [http://127.0.0.1:8000/api/redoc](http://127.0.0.1:8000/api/redoc)

### 5. Execute Automated Test Suite
```bash
python -m pytest backend/tests -v
```

---

## Documentation & Demo Reference

- [Application Architecture](documentation/architecture.md)
- [Database Schema & Indexes](documentation/database-schema.md)
- [Security Design](documentation/security-design.md)
- [REST API Reference](documentation/api-documentation.md)
- [Postman Collection](documentation/postman_collection.json)

### Optional Demo Accounts (`python backend/scripts/seed_demo.py`)

| Role | Username | Password | Scope |
| :--- | :--- | :--- | :--- |
| `ADMIN` | `admin_demo` | `AdminDemo2026!` | Global |
| `BLOOD_BANK_STAFF` | `staff_demo` | `StaffDemo2026!` | `bb_central` |
| `HOSPITAL_STAFF` | `hospital_demo` | `HospitalDemo2026!` | `hosp_city_01` |
| `DOCTOR` | `doctor_demo` | `DoctorDemo2026!` | `hosp_city_01` |
| `DONOR` | `donor_demo` | `DonorDemo2026!` | Self |
