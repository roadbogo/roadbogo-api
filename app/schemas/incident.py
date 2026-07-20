from typing import Literal
from uuid import UUID

from app.schemas.read_common import (
    BboxData,
    DirectionCode,
    DispatchStatus,
    FileContentUrl,
    IncidentStatus,
    ObjectCategory,
    PaginationData,
    PublicUserSummary,
    ReadResponseModel,
    RiskGrade,
    UtcDateTimeString,
)


class RiskGradeCounts(ReadResponseModel):
    CRITICAL: int
    HIGH: int
    MEDIUM: int
    LOW: int


class ObjectCategoryCounts(ReadResponseModel):
    VEHICLE: int
    DEBRIS: int
    WILDLIFE: int
    OTHER: int


class IncidentSummaryData(ReadResponseModel):
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
    risk_grade_counts: RiskGradeCounts
    object_category_counts: ObjectCategoryCounts
    generated_at: UtcDateTimeString


class IncidentListCctv(ReadResponseModel):
    public_id: UUID
    cctv_name: str
    direction_code: DirectionCode


class IncidentLocation(ReadResponseModel):
    road_name: str
    road_section_name: str
    latitude: float
    longitude: float


class IncidentListItem(ReadResponseModel):
    public_id: UUID
    incident_no: str
    status: IncidentStatus
    object_category: ObjectCategory
    class_code: str | None
    class_name: str | None
    ai_risk_score: float
    ai_risk_grade: RiskGrade
    representative_confidence: float | None
    detection_count: int
    duration_ms: int
    first_detected_at: UtcDateTimeString
    last_detected_at: UtcDateTimeString
    acknowledged_at: UtcDateTimeString | None
    claimed_by: PublicUserSummary | None
    cctv: IncidentListCctv
    location: IncidentLocation
    representative_image_url: FileContentUrl | None
    version_no: int
    updated_at: UtcDateTimeString


class IncidentListData(ReadResponseModel):
    items: list[IncidentListItem]
    pagination: PaginationData


class IncidentObjectData(ReadResponseModel):
    object_category: ObjectCategory
    class_code: str | None
    class_name: str | None
    tracked_object_public_id: UUID | None
    external_track_id: str | None


class IncidentAiAnalysisData(ReadResponseModel):
    representative_confidence: float | None
    confidence_calculation_type: Literal["LAST", "MAX", "AVERAGE"] | None
    risk_score: float
    risk_grade: RiskGrade
    duration_ms: int
    repeat_count: int | None
    rule_code: str | None
    rule_version: str | None
    reason_codes: list[str]


class IncidentCctvSnapshot(ReadResponseModel):
    cctv_public_id: UUID
    cctv_name: str
    direction_code: DirectionCode
    road_name: str
    road_section_name: str
    latitude: float
    longitude: float
    km_post: float | None


class IncidentTimeline(ReadResponseModel):
    first_detected_at: UtcDateTimeString
    last_detected_at: UtcDateTimeString
    created_at: UtcDateTimeString
    updated_at: UtcDateTimeString
    acknowledged_at: UtcDateTimeString | None
    claimed_at: UtcDateTimeString | None
    review_started_at: UtcDateTimeString | None
    closed_at: UtcDateTimeString | None


class IncidentDecisionData(ReadResponseModel):
    public_id: UUID
    decision_type: Literal["REAL_RISK", "FALSE_POSITIVE", "NEEDS_REVIEW", "NO_DISPATCH"]
    decision_reason: str
    decided_by: PublicUserSummary
    decided_at: UtcDateTimeString


class ActiveDispatchData(ReadResponseModel):
    public_id: UUID
    status: DispatchStatus
    responder: PublicUserSummary
    requested_at: UtcDateTimeString
    updated_at: UtcDateTimeString


class RepresentativeEvidenceData(ReadResponseModel):
    detection_public_id: UUID | None
    original_image_url: FileContentUrl | None
    annotated_image_url: FileContentUrl | None
    bbox: BboxData | None


class IncidentDetailData(ReadResponseModel):
    public_id: UUID
    incident_no: str
    status: IncidentStatus
    version_no: int
    object: IncidentObjectData
    ai_analysis: IncidentAiAnalysisData
    cctv_snapshot: IncidentCctvSnapshot
    timeline: IncidentTimeline
    controller: PublicUserSummary | None
    decision: IncidentDecisionData | None
    active_dispatch: ActiveDispatchData | None
    representative_evidence: RepresentativeEvidenceData | None
    evidence_count: int
    memo_count: int


class IncidentEvidenceRiskData(ReadResponseModel):
    risk_score: float
    risk_grade: RiskGrade
    duration_ms: int
    repeat_count: int
    tracked_object_public_id: UUID
    external_track_id: str
    reason_codes: list[str]


class IncidentEvidenceItem(ReadResponseModel):
    detection_public_id: UUID | None
    evidence_type: Literal["PRIMARY", "ADDITIONAL", "MERGED", "MANUAL"]
    is_representative: bool
    detected_at: UtcDateTimeString
    class_code: str | None
    class_name: str | None
    confidence: float | None
    bbox: BboxData | None
    original_image_url: FileContentUrl | None
    annotated_image_url: FileContentUrl | None
    risk: IncidentEvidenceRiskData | None


class IncidentEvidenceListData(ReadResponseModel):
    items: list[IncidentEvidenceItem]
    pagination: PaginationData


class IncidentHistoryItem(ReadResponseModel):
    public_id: UUID
    from_status: IncidentStatus | None
    to_status: IncidentStatus
    actor_type: Literal["USER", "SYSTEM", "DEVICE"]
    actor: PublicUserSummary | None
    change_source: Literal["MANUAL", "SYSTEM", "DEVICE", "AUTO"]
    reason_code: str | None
    reason_text: str | None
    changed_at: UtcDateTimeString


class IncidentHistoryListData(ReadResponseModel):
    items: list[IncidentHistoryItem]
    pagination: PaginationData
