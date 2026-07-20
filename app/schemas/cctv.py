from typing import Any

from pydantic import BaseModel


class CctvListData(BaseModel):
    items: list[dict[str, Any]]
    pagination: dict[str, int]
    fallback_used: bool


class CctvDetailData(BaseModel):
    public_id: str
    cctv_code: str
    external_its_cctv_id: str | None
    cctv_name: str
    source_type: str
    direction_code: str
    latitude: float
    longitude: float
    km_post: float | None
    operational_status: str
    is_active: bool
    road: dict[str, Any]
    road_section: dict[str, Any]
    stream: dict[str, Any]
    last_successful_sync_at: str | None
    created_at: str
    updated_at: str
