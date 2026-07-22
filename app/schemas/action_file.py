from enum import StrEnum
from uuid import UUID
from app.schemas.read_common import ReadResponseModel, UtcDateTimeString


class PhotoPhase(StrEnum):
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    OTHER = "OTHER"


class ActionFileItem(ReadResponseModel):
    public_id: UUID
    original_file_name: str
    mime_type: str
    size_bytes: int
    photo_phase: PhotoPhase
    display_order: int
    download_url: str
    created_at: UtcDateTimeString


class ActionFileUploadData(ReadResponseModel):
    file: ActionFileItem


class ActionFileListData(ReadResponseModel):
    items: list[ActionFileItem]
