from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class AiContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AiCaptureSource(StrEnum):
    LIVE = "LIVE"
    DEMO = "DEMO"
    UPLOAD = "UPLOAD"


class AiExecutionMode(StrEnum):
    PARALLEL = "PARALLEL"
    SEQUENTIAL = "SEQUENTIAL"


class AiModelCode(StrEnum):
    VEHICLE_DETECTOR = "VEHICLE_DETECTOR"
    DEBRIS_DETECTOR = "DEBRIS_DETECTOR"
    WILDLIFE_DETECTOR = "WILDLIFE_DETECTOR"


class AiVideoFrameRequest(AiContractModel):
    public_id: UUID
    cctv_public_id: UUID
    captured_at: datetime
    frame_sequence: int = Field(ge=0)
    original_width: int = Field(ge=1)
    original_height: int = Field(ge=1)
    capture_source: AiCaptureSource


class AiInferenceInputRequest(AiContractModel):
    file_public_id: UUID
    download_url: HttpUrl
    mime_type: str

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"image/jpeg", "image/png"}:
            raise ValueError("mime_type must be image/jpeg or image/png.")
        return normalized


class AiTrackingRequest(AiContractModel):
    tracking_session_key: str = Field(min_length=1, max_length=160)


class AiInferenceExecutionRequest(AiContractModel):
    model_codes: list[AiModelCode] = Field(min_length=1)
    execution_mode: AiExecutionMode
    threshold_profile_code: str = Field(min_length=1, max_length=60)

    @field_validator("model_codes")
    @classmethod
    def reject_duplicate_models(cls, value: list[AiModelCode]) -> list[AiModelCode]:
        if len(value) != len(set(value)):
            raise ValueError("model_codes must not contain duplicates.")
        return value


class AiInternalInferenceRequest(AiContractModel):
    request_id: UUID
    inference_run_public_id: UUID
    video_frame: AiVideoFrameRequest
    input: AiInferenceInputRequest
    tracking: AiTrackingRequest
    execution: AiInferenceExecutionRequest


class AiBoundingBoxResponse(AiContractModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(ge=0.0, le=1.0)
    height: float = Field(ge=0.0, le=1.0)


class AiDetectionResponse(AiContractModel):
    detection_index: int = Field(ge=0)
    class_index: int = Field(ge=0)
    raw_name: str
    class_code: str
    incident_target: bool
    confidence: float = Field(ge=0.0, le=1.0)
    bounding_box: AiBoundingBoxResponse


class AiModelResultResponse(AiContractModel):
    model_code: AiModelCode
    detection_count: int = Field(ge=0)
    detections: list[AiDetectionResponse]


class AiImageResponse(AiContractModel):
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class AiInternalInferenceData(AiContractModel):
    request_id: UUID
    inference_run_public_id: UUID
    video_frame_public_id: UUID
    image: AiImageResponse
    model_count: int = Field(ge=0)
    total_detection_count: int = Field(ge=0)
    incident_detection_count: int = Field(ge=0)
    processing_time_ms: int = Field(ge=0)
    model_results: list[AiModelResultResponse]


class AiInternalInferenceResponse(AiContractModel):
    success: Literal[True]
    data: AiInternalInferenceData
    trace_id: UUID


class AiErrorDetail(AiContractModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class AiInternalErrorResponse(AiContractModel):
    success: Literal[False]
    error: AiErrorDetail
    trace_id: UUID
