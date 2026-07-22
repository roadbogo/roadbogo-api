from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.read_common import (
    IncidentStatus,
    PaginationData,
    ReadResponseModel,
    UtcDateTimeString,
)


class DutyStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    OFF_DUTY = "OFF_DUTY"
    UNAVAILABLE = "UNAVAILABLE"


class DispatchStatus(StrEnum):
    REQUESTED = "REQUESTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DEPARTED = "DEPARTED"
    EN_ROUTE = "EN_ROUTE"
    ARRIVED = "ARRIVED"
    ACTION_IN_PROGRESS = "ACTION_IN_PROGRESS"
    ACTION_COMPLETED = "ACTION_COMPLETED"
    CANCELLED = "CANCELLED"


class ResponderOrganization(ReadResponseModel):
    public_id: UUID
    organization_name: str


class ResponderListItem(ReadResponseModel):
    public_id: UUID
    user_name: str
    responder_code: str
    duty_status: DutyStatus
    is_dispatch_enabled: bool
    coverage_area: str | None
    organization: ResponderOrganization | None
    has_active_dispatch: bool


class ResponderListData(ReadResponseModel):
    items: list[ResponderListItem]
    pagination: PaginationData


class DispatchAssignmentRequest(ReadResponseModel):
    responder_public_id: UUID
    request_message: str | None = Field(default=None, max_length=1000)
    expected_version_no: int = Field(ge=0)

    @field_validator("request_message", mode="before")
    @classmethod
    def normalize_message(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class DispatchUserSummary(ReadResponseModel):
    public_id: UUID
    user_name: str


class DispatchResponderSummary(DispatchUserSummary):
    responder_code: str


class DispatchData(ReadResponseModel):
    public_id: UUID
    incident_public_id: UUID
    attempt_no: int
    status: DispatchStatus
    responder: DispatchResponderSummary
    assigned_by: DispatchUserSummary
    request_message: str | None
    requested_at: UtcDateTimeString
    version_no: int


class DispatchIncidentSummary(ReadResponseModel):
    public_id: UUID
    status: IncidentStatus
    version_no: int


class DispatchAssignmentData(ReadResponseModel):
    dispatch: DispatchData
    incident: DispatchIncidentSummary


class DispatchMineIncident(ReadResponseModel):
    public_id: UUID
    incident_no: str
    status: IncidentStatus
    object_category: str
    ai_risk_grade: str
    cctv_name: str
    road_name: str
    road_section_name: str
    latitude: float
    longitude: float


class DispatchMineItem(ReadResponseModel):
    public_id: UUID
    attempt_no: int
    status: DispatchStatus
    request_message: str | None
    requested_at: UtcDateTimeString
    accepted_at: UtcDateTimeString | None
    version_no: int
    incident: DispatchMineIncident
    assigned_by: DispatchUserSummary


class DispatchMineData(ReadResponseModel):
    items: list[DispatchMineItem]
    pagination: PaginationData


class DispatchDetailData(DispatchMineItem):
    rejection_reason: str | None
    departed_at: UtcDateTimeString | None
    en_route_at: UtcDateTimeString | None
    arrived_at: UtcDateTimeString | None
    action_started_at: UtcDateTimeString | None
    action_completed_at: UtcDateTimeString | None
    cancelled_at: UtcDateTimeString | None
    previous_dispatch_public_id: UUID | None


class DispatchVersionRequest(ReadResponseModel):
    expected_version_no: int = Field(ge=0)


class DispatchRejectRequest(DispatchVersionRequest):
    rejection_reason: str = Field(min_length=1, max_length=1000)

    @field_validator("rejection_reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class DispatchAcceptDispatch(ReadResponseModel):
    public_id: UUID
    previous_status: DispatchStatus
    status: DispatchStatus
    accepted_at: UtcDateTimeString
    version_no: int


class DispatchAcceptIncident(ReadResponseModel):
    public_id: UUID
    previous_status: IncidentStatus
    status: IncidentStatus
    version_no: int


class DispatchAcceptData(ReadResponseModel):
    dispatch: DispatchAcceptDispatch
    incident: DispatchAcceptIncident


class DispatchRejectDispatch(ReadResponseModel):
    public_id: UUID
    previous_status: DispatchStatus
    status: DispatchStatus
    rejection_reason: str
    version_no: int


class DispatchRejectIncident(ReadResponseModel):
    public_id: UUID
    status: IncidentStatus
    version_no: int


class DispatchRejectResponder(ReadResponseModel):
    public_id: UUID
    duty_status: DutyStatus


class DispatchRejectData(ReadResponseModel):
    dispatch: DispatchRejectDispatch
    incident: DispatchRejectIncident
    responder: DispatchRejectResponder


class DispatchProgressDispatch(ReadResponseModel):
    public_id: UUID
    previous_status: DispatchStatus
    status: DispatchStatus
    occurred_at: UtcDateTimeString
    version_no: int


class DispatchProgressIncident(ReadResponseModel):
    public_id: UUID
    status: IncidentStatus
    version_no: int


class DispatchProgressData(ReadResponseModel):
    dispatch: DispatchProgressDispatch
    incident: DispatchProgressIncident


class DispatchCompleteActionRequest(ReadResponseModel):
    expected_version_no: int = Field(ge=0)
    action_type: str = Field(min_length=1, max_length=60)
    action_detail: str = Field(min_length=1, max_length=5000)

    @field_validator("action_type", "action_detail", mode="before")
    @classmethod
    def normalize_action_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class DispatchCompletionDispatch(ReadResponseModel):
    public_id: UUID
    previous_status: DispatchStatus
    status: DispatchStatus
    action_completed_at: UtcDateTimeString
    version_no: int


class DispatchCompletionIncident(ReadResponseModel):
    public_id: UUID
    previous_status: IncidentStatus
    status: IncidentStatus
    version_no: int


class DispatchCompletionResponder(ReadResponseModel):
    public_id: UUID
    duty_status: DutyStatus


class DispatchCompletionReport(ReadResponseModel):
    public_id: UUID
    action_type: str
    action_detail: str
    action_started_at: UtcDateTimeString
    action_completed_at: UtcDateTimeString


class DispatchCompletionData(ReadResponseModel):
    dispatch: DispatchCompletionDispatch
    incident: DispatchCompletionIncident
    responder: DispatchCompletionResponder
    report: DispatchCompletionReport
