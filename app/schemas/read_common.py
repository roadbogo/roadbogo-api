from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

UtcDateTimeString = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"),
]
FileContentUrl = Annotated[
    str,
    StringConstraints(pattern=r"^/api/v1/files/[0-9a-fA-F-]{36}/content$"),
]


class ReadResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PaginationData(ReadResponseModel):
    page: int
    size: int
    total_elements: int
    total_pages: int


class PublicUserSummary(ReadResponseModel):
    public_id: UUID
    user_name: str


class BboxData(ReadResponseModel):
    x: float
    y: float
    width: float
    height: float


class IncidentStatus(StrEnum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CLAIMED = "CLAIMED"
    UNDER_REVIEW = "UNDER_REVIEW"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    DISPATCH_REQUESTED = "DISPATCH_REQUESTED"
    DISPATCHED = "DISPATCHED"
    ON_SCENE = "ON_SCENE"
    ACTION_IN_PROGRESS = "ACTION_IN_PROGRESS"
    ACTION_COMPLETED = "ACTION_COMPLETED"
    CLOSED = "CLOSED"


class RiskGrade(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ObjectCategory(StrEnum):
    VEHICLE = "VEHICLE"
    DEBRIS = "DEBRIS"
    WILDLIFE = "WILDLIFE"
    OTHER = "OTHER"


class DirectionCode(StrEnum):
    ASC = "ASC"
    DESC = "DESC"
    BOTH = "BOTH"
    UNKNOWN = "UNKNOWN"


class CctvSourceType(StrEnum):
    ITS = "ITS"
    MANUAL = "MANUAL"
    DEMO = "DEMO"


class CctvOperationalStatus(StrEnum):
    NORMAL = "NORMAL"
    DELAYED = "DELAYED"
    FAULT = "FAULT"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"


class StreamType(StrEnum):
    LIVE = "LIVE"
    DEMO = "DEMO"


class ProtocolType(StrEnum):
    RTSP = "RTSP"
    HLS = "HLS"
    HTTP = "HTTP"
    FILE = "FILE"
    OTHER = "OTHER"


class StreamStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ERROR = "ERROR"


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
