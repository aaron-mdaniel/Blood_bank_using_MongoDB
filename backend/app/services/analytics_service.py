"""
MongoDB Aggregation Analytics & Change Stream Monitor Service.
Executes multi-stage MongoDB aggregation pipelines for real-time dashboards
and reports MongoDB Change Stream capability on replica sets.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.config.database import Collections, db_manager
from app.models.enums import BloodUnitStatus, DonorEligibility, RequestStatus
from app.repositories.audit_repository import AuditRepository


class AnalyticsService:
    """
    Provides aggregation-pipeline analytics and Change Stream diagnostics.
    """

    def __init__(self, audit_repo: AuditRepository = None):
        self.audit_repo = audit_repo or AuditRepository()

    def get_dashboard_analytics(
        self,
        blood_bank_id: Optional[str] = None,
        expiry_days: int = 7,
    ) -> Dict[str, Any]:
        """
        Computes system-wide or blood-bank-scoped dashboard metrics using
        MongoDB aggregation pipelines ($match, $group, $project, $sort).
        """
        now = datetime.now(timezone.utc)
        expiry_cutoff = now + timedelta(days=expiry_days)

        # 1. Donors summary via aggregation
        donor_pipeline = [
            {
                "$group": {
                    "_id": "$eligibility_status",
                    "count": {"$sum": 1},
                }
            }
        ]
        donor_groups = list(db_manager.donors.aggregate(donor_pipeline))
        total_donors = sum(g["count"] for g in donor_groups)
        eligible_donors = sum(
            g["count"] for g in donor_groups if g["_id"] == DonorEligibility.ELIGIBLE.value
        )

        # 2. Donations count & monthly trend via $group on $year/$month
        donation_match: Dict[str, Any] = {}
        if blood_bank_id:
            donation_match["blood_bank_id"] = str(blood_bank_id)

        monthly_pipeline = [
            {"$match": donation_match},
            {
                "$group": {
                    "_id": {
                        "year": {"$year": "$donation_date"},
                        "month": {"$month": "$donation_date"},
                    },
                    "count": {"$sum": 1},
                    "total_volume_ml": {"$sum": "$volume_ml"},
                }
            },
            {"$sort": {"_id.year": 1, "_id.month": 1}},
        ]
        monthly_raw = list(db_manager.donations.aggregate(monthly_pipeline))
        monthly_donations = [
            {
                "year": int(item["_id"]["year"]),
                "month": int(item["_id"]["month"]),
                "count": int(item["count"]),
                "total_volume_ml": int(item.get("total_volume_ml", 0)),
            }
            for item in monthly_raw
            if item.get("_id") and item["_id"].get("year") and item["_id"].get("month")
        ]
        total_donations = sum(m["count"] for m in monthly_donations)

        # 3. Available blood units & blood group distribution
        available_match: Dict[str, Any] = {
            "status": BloodUnitStatus.AVAILABLE.value,
            "expiry_date": {"$gt": now},
        }
        if blood_bank_id:
            available_match["blood_bank_id"] = str(blood_bank_id)

        blood_group_pipeline = [
            {"$match": available_match},
            {
                "$group": {
                    "_id": {"blood_group": "$blood_group", "rh_factor": "$rh_factor"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.blood_group": 1, "_id.rh_factor": 1}},
        ]
        bg_raw = list(db_manager.blood_units.aggregate(blood_group_pipeline))
        blood_group_distribution = [
            {
                "blood_group": item["_id"]["blood_group"],
                "rh_factor": item["_id"]["rh_factor"],
                "count": int(item["count"]),
            }
            for item in bg_raw
        ]
        available_blood_units = sum(item["count"] for item in blood_group_distribution)

        # 4. Expiring soon count via aggregation
        expiring_pipeline = [
            {
                "$match": {
                    **available_match,
                    "expiry_date": {"$gt": now, "$lte": expiry_cutoff},
                }
            },
            {"$count": "total"},
        ]
        exp_res = list(db_manager.blood_units.aggregate(expiring_pipeline))
        expiring_soon_units = int(exp_res[0]["total"]) if exp_res else 0

        # 5. Component & status breakdown
        unit_scope_match: Dict[str, Any] = {}
        if blood_bank_id:
            unit_scope_match["blood_bank_id"] = str(blood_bank_id)
        component_pipeline = [
            {"$match": unit_scope_match},
            {
                "$group": {
                    "_id": {"component_type": "$component_type", "status": "$status"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.component_type": 1, "_id.status": 1}},
        ]
        comp_raw = list(db_manager.blood_units.aggregate(component_pipeline))
        component_breakdown = [
            {
                "component_type": item["_id"]["component_type"],
                "status": item["_id"]["status"],
                "count": int(item["count"]),
            }
            for item in comp_raw
        ]

        # 6. Blood requests status & priority breakdowns
        req_status_pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        req_status_raw = list(db_manager.blood_requests.aggregate(req_status_pipeline))
        request_status_breakdown = [
            {"status": item["_id"], "count": int(item["count"])}
            for item in req_status_raw
        ]
        status_map = {item["status"]: item["count"] for item in request_status_breakdown}

        req_priority_pipeline = [
            {"$group": {"_id": "$priority", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        req_prio_raw = list(db_manager.blood_requests.aggregate(req_priority_pipeline))
        request_priority_breakdown = [
            {"priority": item["_id"], "count": int(item["count"])}
            for item in req_prio_raw
        ]

        return {
            "scope_blood_bank_id": blood_bank_id,
            "total_donors": total_donors,
            "eligible_donors": eligible_donors,
            "total_donations": total_donations,
            "available_blood_units": available_blood_units,
            "expiring_soon_units": expiring_soon_units,
            "pending_requests": status_map.get(RequestStatus.PENDING.value, 0),
            "approved_requests": status_map.get(RequestStatus.APPROVED.value, 0),
            "allocated_requests": (
                status_map.get(RequestStatus.ALLOCATED.value, 0)
                + status_map.get(RequestStatus.PARTIALLY_ALLOCATED.value, 0)
            ),
            "blood_group_distribution": blood_group_distribution,
            "component_breakdown": component_breakdown,
            "request_status_breakdown": request_status_breakdown,
            "request_priority_breakdown": request_priority_breakdown,
            "monthly_donations": monthly_donations,
        }

    def get_available_inventory_distribution(self) -> List[Dict[str, Any]]:
        """
        Aggregates AVAILABLE unexpired blood units by (blood_group, rh_factor, component_type)
        for hospital staff and clinicians.
        """
        now = datetime.now(timezone.utc)
        pipeline = [
            {
                "$match": {
                    "status": BloodUnitStatus.AVAILABLE.value,
                    "expiry_date": {"$gt": now},
                }
            },
            {
                "$group": {
                    "_id": {
                        "blood_group": "$blood_group",
                        "rh_factor": "$rh_factor",
                        "component_type": "$component_type",
                    },
                    "available_units": {"$sum": 1},
                    "earliest_expiry": {"$min": "$expiry_date"},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "blood_group": "$_id.blood_group",
                    "rh_factor": "$_id.rh_factor",
                    "component_type": "$_id.component_type",
                    "available_units": 1,
                    "earliest_expiry": 1,
                }
            },
            {"$sort": {"blood_group": 1, "rh_factor": 1, "component_type": 1}},
        ]
        return list(db_manager.blood_units.aggregate(pipeline))

    def get_change_stream_status(self) -> Dict[str, Any]:
        """
        Probes whether MongoDB Change Streams (replica set / Atlas) are available,
        and returns recent inventory/request change events from audit_logs.
        """
        supported = False
        mode = "mock_or_standalone"
        details = "Change Streams require a MongoDB replica set (e.g. Atlas). Falling back to audit-stream feed."

        client = db_manager.client
        if client is not None and not type(client).__module__.startswith("mongomock"):
            try:
                hello = client.admin.command("hello")
                if hello.get("setName") or hello.get("msg") == "isdbgrid":
                    supported = True
                    mode = "replica_set_change_stream_ready"
                    details = f"Replica set '{hello.get('setName', 'sharded')}' supports db.watch() Change Streams."
                else:
                    mode = "standalone_mongod"
            except Exception as exc:
                details = f"Change stream probe unavailable: {exc}"

        recent = self.audit_repo.find_many(
            {"resource_type": {"$in": [Collections.BLOOD_UNITS, Collections.BLOOD_REQUESTS]}},
            limit=10,
            sort=[("timestamp", -1)],
        )
        return {
            "supported": supported,
            "mode": mode,
            "details": details,
            "watched_collections": [Collections.BLOOD_UNITS, Collections.BLOOD_REQUESTS],
            "recent_inventory_events": recent,
        }
