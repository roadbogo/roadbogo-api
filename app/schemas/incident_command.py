from uuid import UUID

from pydantic import Field

from app.schemas.read_common import IncidentStatus, ReadResponseModel, UtcDateTimeString


class IncidentCommandRequest(ReadResponseModel):
    expected_version_no: int = Field(ge=0)


class IncidentActorSummary(ReadResponseModel):
    public_id: UUID
    user_name: str


class IncidentAcknowledgeData(ReadResponseModel):
    incident_public_id: UUID
    previous_status: IncidentStatus
    status: IncidentStatus
    acknowledged_by: IncidentActorSummary
    acknowledged_at: UtcDateTimeString
    version_no: int


class IncidentClaimData(ReadResponseModel):
    incident_public_id: UUID
    previous_status: IncidentStatus
    status: IncidentStatus
    claimed_by: IncidentActorSummary
    claimed_at: UtcDateTimeString
    version_no: int


class IncidentReviewData(ReadResponseModel):
    incident_public_id: UUID
    previous_status: IncidentStatus
    status: IncidentStatus
    review_started_at: UtcDateTimeString
    version_no: int
