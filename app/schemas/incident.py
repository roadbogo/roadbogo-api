from typing import Any

from pydantic import BaseModel


class IncidentSummaryData(BaseModel):
    total_count: int
    new_count: int
    acknowledged_count: int
    claimed_count: int
    under_review_count: int
    dispatch_requested_count: int
    dispatch_in_progress_count: int
    action_completed_count: int
    closed_count: int
    false_positive_count: int
    risk_grade_counts: dict[str, int]
    object_category_counts: dict[str, int]
    generated_at: str


class PaginatedData(BaseModel):
    items: list[dict[str, Any]]
    pagination: dict[str, int]


class IncidentDetailData(BaseModel):
    public_id: str
    incident_no: str
    status: str
    version_no: int
    object: dict[str, Any]
    ai_analysis: dict[str, Any]
    cctv_snapshot: dict[str, Any]
    timeline: dict[str, Any]
    controller: dict[str, Any] | None
    decision: dict[str, Any] | None
    active_dispatch: dict[str, Any] | None
    representative_evidence: dict[str, Any] | None
    evidence_count: int
    memo_count: int
