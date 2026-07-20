from uuid import UUID

from app.schemas.read_common import (
    CctvOperationalStatus,
    CctvSourceType,
    DirectionCode,
    PaginationData,
    ProtocolType,
    ReadResponseModel,
    StreamStatus,
    StreamType,
    UtcDateTimeString,
)


class RoadSummary(ReadResponseModel):
    public_id: UUID
    road_code: str
    road_name: str


class RoadSectionSummary(ReadResponseModel):
    public_id: UUID
    section_code: str
    section_name: str


class CctvListItem(ReadResponseModel):
    public_id: UUID
    cctv_code: str
    cctv_name: str
    source_type: CctvSourceType
    direction_code: DirectionCode
    latitude: float
    longitude: float
    km_post: float | None
    operational_status: CctvOperationalStatus
    is_active: bool
    has_stream: bool
    road: RoadSummary
    road_section: RoadSectionSummary
    last_successful_sync_at: UtcDateTimeString | None


class CctvListData(ReadResponseModel):
    items: list[CctvListItem]
    pagination: PaginationData
    fallback_used: bool


class CctvStreamSummary(ReadResponseModel):
    available: bool
    stream_type: StreamType | None
    protocol_type: ProtocolType | None
    stream_status: StreamStatus | None


class CctvDetailData(ReadResponseModel):
    public_id: UUID
    cctv_code: str
    external_its_cctv_id: str | None
    cctv_name: str
    source_type: CctvSourceType
    direction_code: DirectionCode
    latitude: float
    longitude: float
    km_post: float | None
    operational_status: CctvOperationalStatus
    is_active: bool
    road: RoadSummary
    road_section: RoadSectionSummary
    stream: CctvStreamSummary
    last_successful_sync_at: UtcDateTimeString | None
    created_at: UtcDateTimeString
    updated_at: UtcDateTimeString
