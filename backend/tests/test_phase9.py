"""
Phase 9 Automated Test Suite: MongoDB Aggregations, Geospatial Blood Camps,
Change Stream Diagnostics, and Multi-Role Frontend Static Serving.
"""
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.models.enums import UserRole


def _get_uid(client: TestClient, headers: dict) -> str:
    return client.get("/api/auth/me", headers=headers).json()["_id"]


# ==========================================
# 1. MongoDB Aggregation Analytics Tests
# ==========================================

def test_analytics_dashboard_aggregations_and_scoping(client: TestClient, auth_header_factory):
    """Verify MongoDB aggregation pipelines compute accurate KPIs and enforce role/bank scoping."""
    admin_hdrs = auth_header_factory(UserRole.ADMIN, username="an_admin")
    bb1_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="an_bb1", blood_bank_id="bb_1")
    bb2_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="an_bb2", blood_bank_id="bb_2")
    doc_hdrs = auth_header_factory(UserRole.DOCTOR, username="an_doc", hospital_id="hosp_an")
    donor_hdrs = auth_header_factory(UserRole.DONOR, username="an_donor")
    donor_uid = _get_uid(client, donor_hdrs)

    # Create donor, donation, units in bb_1 and bb_2, and a blood request
    donor = client.post(
        "/api/donors",
        json={
            "user_id": donor_uid,
            "donor_card_number": "CARD-AN-1",
            "first_name": "Aria",
            "last_name": "Sen",
            "date_of_birth": "1991-06-01",
            "gender": "FEMALE",
            "blood_group": "A",
            "rh_factor": "POSITIVE",
            "contact_phone": "+91-9000111222",
            "address": "10 Residency Rd",
        },
        headers=admin_hdrs,
    ).json()

    client.post(
        "/api/donations",
        json={
            "donation_code": "DON-AN-1",
            "donor_id": donor["_id"],
            "blood_bank_id": "bb_1",
            "volume_ml": 450,
            "hemoglobin_g_dl": 14.0,
            "blood_pressure": "120/80",
            "screening_status": "PASSED",
        },
        headers=bb1_hdrs,
    )

    now = datetime.now(timezone.utc)
    # 2 units in bb_1 (1 expiring in 3 days, 1 in 20 days), 1 unit in bb_2
    for uid, bb_id, hdrs, exp in [
        ("UNIT-AN-1", "bb_1", bb1_hdrs, now + timedelta(days=3)),
        ("UNIT-AN-2", "bb_1", bb1_hdrs, now + timedelta(days=20)),
        ("UNIT-AN-3", "bb_2", bb2_hdrs, now + timedelta(days=15)),
    ]:
        client.post(
            "/api/blood-units",
            json={
                "unit_id": uid,
                "source_donation_id": "DON-AN-1",
                "blood_bank_id": bb_id,
                "blood_group": "A",
                "rh_factor": "POSITIVE",
                "component_type": "RBC",
                "volume_ml": 250,
                "expiry_date": exp.isoformat(),
                "storage_location": {"refrigerator_id": "REF-1", "shelf": "S1"},
            },
            headers=hdrs,
        )

    client.post(
        "/api/blood-requests",
        json={
            "request_code": "REQ-AN-1",
            "hospital_id": "hosp_an",
            "doctor_id": _get_uid(client, doc_hdrs),
            "patient_id": "pat_an",
            "blood_group": "A",
            "rh_factor": "POSITIVE",
            "component_type": "RBC",
            "units_requested": 1,
            "priority": "CRITICAL",
            "clinical_reason": "Trauma care",
        },
        headers=doc_hdrs,
    )

    # Admin sees global totals (3 available units, 1 expiring within 7d)
    admin_stats = client.get("/api/analytics/dashboard", headers=admin_hdrs)
    assert admin_stats.status_code == 200
    a_data = admin_stats.json()
    assert a_data["total_donors"] == 1
    assert a_data["total_donations"] == 1
    assert a_data["available_blood_units"] == 3
    assert a_data["expiring_soon_units"] == 1
    assert a_data["pending_requests"] == 1
    assert len(a_data["monthly_donations"]) == 1
    assert a_data["monthly_donations"][0]["total_volume_ml"] == 450

    # bb_1 staff sees only bb_1's 2 available units
    bb1_stats = client.get("/api/analytics/dashboard", headers=bb1_hdrs)
    assert bb1_stats.status_code == 200
    assert bb1_stats.json()["scope_blood_bank_id"] == "bb_1"
    assert bb1_stats.json()["available_blood_units"] == 2

    # Doctor & Donor cannot read full admin dashboard (403), Doctor can read inventory distribution
    assert client.get("/api/analytics/dashboard", headers=doc_hdrs).status_code == 403
    assert client.get("/api/analytics/dashboard", headers=donor_hdrs).status_code == 403
    dist_res = client.get("/api/analytics/inventory-distribution", headers=doc_hdrs)
    assert dist_res.status_code == 200
    assert dist_res.json()[0]["available_units"] == 3

    # Change streams diagnostics endpoint
    cs_res = client.get("/api/analytics/change-streams/status", headers=admin_hdrs)
    assert cs_res.status_code == 200
    assert "watched_collections" in cs_res.json()


# ==========================================
# 2. Geospatial Blood Camps Tests
# ==========================================

def test_blood_camps_crud_and_geospatial_nearby(client: TestClient, auth_header_factory):
    """Verify blood camp creation, blood_bank_id ABAC scope, and 2dsphere nearby lookup."""
    bb1_hdrs = auth_header_factory(UserRole.BLOOD_BANK_STAFF, username="camp_bb1", blood_bank_id="bb_camp1")
    donor_hdrs = auth_header_factory(UserRole.DONOR, username="camp_donor")

    now = datetime.now(timezone.utc)
    # Cross-bank creation blocked (403)
    assert (
        client.post(
            "/api/blood-camps",
            json={
                "camp_code": "CAMP-FORGE",
                "title": "Unauthorized Camp",
                "organizer_blood_bank_id": "bb_other",
                "location": {"type": "Point", "coordinates": [77.5946, 12.9716]},
                "address": "MG Road",
                "start_time": (now + timedelta(days=1)).isoformat(),
                "end_time": (now + timedelta(days=1, hours=6)).isoformat(),
            },
            headers=bb1_hdrs,
        ).status_code
        == 403
    )

    # Create Bangalore camp & Mysore camp (~130km away)
    c1 = client.post(
        "/api/blood-camps",
        json={
            "camp_code": "CAMP-BLR-01",
            "title": "Bangalore Central Drive",
            "organizer_blood_bank_id": "bb_camp1",
            "location": {"type": "Point", "coordinates": [77.5946, 12.9716]},
            "address": "Cubbon Park, Bangalore",
            "start_time": (now + timedelta(days=2)).isoformat(),
            "end_time": (now + timedelta(days=2, hours=6)).isoformat(),
            "capacity_donors": 150,
        },
        headers=bb1_hdrs,
    )
    assert c1.status_code == 201

    c2 = client.post(
        "/api/blood-camps",
        json={
            "camp_code": "CAMP-MYS-01",
            "title": "Mysore Palace Drive",
            "organizer_blood_bank_id": "bb_camp1",
            "location": {"type": "Point", "coordinates": [76.6394, 12.2958]},
            "address": "Palace Grounds, Mysore",
            "start_time": (now + timedelta(days=3)).isoformat(),
            "end_time": (now + timedelta(days=3, hours=6)).isoformat(),
            "capacity_donors": 120,
        },
        headers=bb1_hdrs,
    )
    assert c2.status_code == 201

    # Donor queries within 25km of Bangalore -> gets CAMP-BLR-01 only
    nearby = client.get(
        "/api/blood-camps/nearby?longitude=77.59&latitude=12.97&radius_km=25",
        headers=donor_hdrs,
    )
    assert nearby.status_code == 200
    assert [c["camp_code"] for c in nearby.json()] == ["CAMP-BLR-01"]
    assert nearby.json()[0]["distance_km"] < 2.0


# ==========================================
# 3. Frontend Web Interface Serving Tests
# ==========================================

def test_frontend_pages_and_assets_served(client: TestClient):
    """Verify FastAPI serves the multi-role HTML5/CSS3/JS frontend under /ui and redirects browser /."""
    # Browser Accept: text/html on / redirects to /ui/login.html
    redir = client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert redir.status_code == 302
    assert redir.headers["location"] == "/ui/login.html"

    # All frontend entry pages & static assets load cleanly (200 OK)
    ui_paths = [
        "/ui/index.html",
        "/ui/login.html",
        "/ui/register.html",
        "/ui/admin/index.html",
        "/ui/bloodbank/index.html",
        "/ui/hospital/index.html",
        "/ui/doctor/index.html",
        "/ui/donor/index.html",
        "/ui/css/styles.css",
        "/ui/js/api.js",
        "/ui/js/auth.js",
        "/ui/js/ui.js",
        "/ui/js/dashboard.js",
    ]
    for path in ui_paths:
        res = client.get(path)
        assert res.status_code == 200, f"Expected 200 OK for {path}, got {res.status_code}"
