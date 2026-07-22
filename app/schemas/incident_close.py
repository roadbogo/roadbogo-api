from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.base import RequestModel
from app.schemas.read_common import ReadResponseModel, UtcDateTimeString


class IncidentCloseRequest(RequestModel):
    closure_code: Literal["FIELD_ACTION_COMPLETED"]
    closure_note: str = Field(min_length=1, max_length=1000)
    expected_version_no: int = Field(ge=0)

    @field_validator("closure_note", mode="before")
    @classmethod
    def normalize_note(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class IncidentActorSummary(ReadResponseModel):
    public_id: UUID
    user_name: str


class IncidentCloseData(ReadResponseModel):
    incident_public_id: UUID
    previous_status: Literal["ACTION_COMPLETED"]
    status: Literal["CLOSED"]
    closure_code: Literal["FIELD_ACTION_COMPLETED"]
    closed_by: IncidentActorSummary
    closed_at: UtcDateTimeString
    version_no: int
