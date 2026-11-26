"""
Pydantic schemas for MongoDB Aggregation Dashboard Analytics & Change Stream Status.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class BloodGroupStat(BaseModel):
    blood_group: str
    rh_factor: str
    count: int


class ComponentStat(BaseModel):
    component_type: str
    status: str
    count: int


class StatusCount(BaseModel):
    status: str
    count: int


class PriorityCount(BaseModel):
    priority: str
    count: int


class MonthlyDonationStat(BaseModel):
    year: int
    month: int
    count: int
    total_volume_ml: int


class DashboardAnalyticsResponse(BaseModel):
    scope_blood_bank_id: Optional[str] = None
    total_donors: int
    eligible_donors: int
    total_donations: int
    available_blood_units: int
    expiring_soon_units: int
    pending_requests: int
    approved_requests: int
    allocated_requests: int
    blood_group_distribution: List[BloodGroupStat]
    component_breakdown: List[ComponentStat]
    request_status_breakdown: List[StatusCount]
    request_priority_breakdown: List[PriorityCount]
    monthly_donations: List[MonthlyDonationStat]


class ChangeStreamStatusResponse(BaseModel):
    supported: bool
    mode: str
    details: str
    watched_collections: List[str]
    recent_inventory_events: List[Dict[str, Any]]
