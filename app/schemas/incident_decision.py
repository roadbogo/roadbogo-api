from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.incident_command import IncidentActorSummary
from app.schemas.read_common import IncidentStatus, ReadResponseModel, UtcDateTimeString

DecisionType = Literal["REAL_RISK", "FALSE_POSITIVE", "NEEDS_REVIEW", "NO_DISPATCH"]


class IncidentDecisionRequest(ReadResponseModel):
    decision_type: DecisionType
    decision_reason: str = Field(min_length=1, max_length=1000)
    expected_version_no: int = Field(ge=0)

    @field_validator("decision_reason", mode="before")
    @classmethod
    def strip_reason(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class IncidentDecisionSummary(ReadResponseModel):
    public_id: UUID
    decision_type: DecisionType
    decision_reason: str
    decided_by: IncidentActorSummary
    decided_at: UtcDateTimeString


class IncidentDecisionResultData(ReadResponseModel):
    incident_public_id: UUID
    previous_status: IncidentStatus
    status: IncidentStatus
    decision: IncidentDecisionSummary
    version_no: int
