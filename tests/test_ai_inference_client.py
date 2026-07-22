from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest

from app.core.exceptions import AppException
from app.schemas.ai_inference import (
    AiCaptureSource,
    AiExecutionMode,
    AiInferenceExecutionRequest,
    AiInferenceInputRequest,
    AiInternalInferenceRequest,
    AiModelCode,
    AiTrackingRequest,
    AiVideoFrameRequest,
)
from app.services.ai_inference_client import AiInferenceClient


def make_payload() -> AiInternalInferenceRequest:
    return AiInternalInferenceRequest(
        request_id=uuid4(),
        inference_run_public_id=uuid4(),
        video_frame=AiVideoFrameRequest(
            public_id=uuid4(),
            cctv_public_id=uuid4(),
            captured_at=datetime.now(UTC),
            frame_sequence=7,
            original_width=1920,
            original_height=1080,
            capture_source=AiCaptureSource.LIVE,
        ),
        input=AiInferenceInputRequest(
            file_public_id=uuid4(),
            download_url="https://example.com/frame.jpg",
            mime_type="image/jpeg",
        ),
        tracking=AiTrackingRequest(
            tracking_session_key="CCTV-001",
        ),
        execution=AiInferenceExecutionRequest(
            model_codes=[AiModelCode.VEHICLE_DETECTOR],
            execution_mode=AiExecutionMode.SEQUENTIAL,
            threshold_profile_code="DEFAULT",
        ),
    )


def make_client(handler) -> tuple[AiInferenceClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return (
        AiInferenceClient(
            base_url="http://192.168.0.102:8010",
            internal_api_prefix="/api/internal/v1",
            internal_api_key="test-secret",
            timeout_seconds=10.0,
            http_client=http_client,
        ),
        http_client,
    )


def success_body(payload, trace_id):
    return {
        "success": True,
        "data": {
            "request_id": str(payload.request_id),
            "inference_run_public_id": str(payload.inference_run_public_id),
            "video_frame_public_id": str(payload.video_frame.public_id),
            "image": {"width": 1920, "height": 1080},
            "model_count": 1,
            "total_detection_count": 1,
            "incident_detection_count": 1,
            "processing_time_ms": 25,
            "model_results": [
                {
                    "model_code": "VEHICLE_DETECTOR",
                    "detection_count": 1,
                    "detections": [
                        {
                            "detection_index": 0,
                            "class_index": 1,
                            "raw_name": "car",
                            "class_code": "CAR",
                            "incident_target": True,
                            "confidence": 0.91,
                            "bounding_box": {
                                "x": 0.1,
                                "y": 0.2,
                                "width": 0.3,
                                "height": 0.4,
                            },
                        }
                    ],
                }
            ],
        },
        "trace_id": str(trace_id),
    }


def test_successful_inference_request() -> None:
    payload = make_payload()
    idempotency_key = uuid4()
    trace_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/internal/v1/inferences"
        assert request.headers["X-Internal-API-Key"] == "test-secret"
        assert request.headers["Idempotency-Key"] == str(idempotency_key)
        assert request.headers["X-Request-ID"] == str(payload.request_id)
        assert request.headers["X-Trace-ID"] == str(trace_id)
        return httpx.Response(200, json=success_body(payload, trace_id))

    client, http_client = make_client(handler)
    try:
        result = client.infer(
            payload,
            idempotency_key=idempotency_key,
            request_id=payload.request_id,
            trace_id=trace_id,
        )
    finally:
        http_client.close()

    assert result.data.total_detection_count == 1
    assert result.data.model_results[0].detections[0].class_code == "CAR"


def test_ai_error_response_is_preserved() -> None:
    payload = make_payload()
    trace_id = uuid4()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={
                "success": False,
                "error": {
                    "code": "AI_INFERENCE_UNAVAILABLE",
                    "message": "AI inference is unavailable.",
                    "details": None,
                },
                "trace_id": str(trace_id),
            },
        )

    client, http_client = make_client(handler)
    try:
        with pytest.raises(AppException) as error:
            client.infer(
                payload,
                idempotency_key=uuid4(),
                request_id=payload.request_id,
                trace_id=trace_id,
            )
    finally:
        http_client.close()

    assert error.value.status_code == 503
    assert error.value.code == "AI_INFERENCE_UNAVAILABLE"


def test_network_failure_is_mapped() -> None:
    payload = make_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    client, http_client = make_client(handler)
    try:
        with pytest.raises(AppException) as error:
            client.infer(
                payload,
                idempotency_key=uuid4(),
                request_id=payload.request_id,
                trace_id=uuid4(),
            )
    finally:
        http_client.close()

    assert error.value.code == "AI_SERVER_UNAVAILABLE"
    assert error.value.status_code == 503


def test_invalid_success_response_is_rejected() -> None:
    payload = make_payload()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True})

    client, http_client = make_client(handler)
    try:
        with pytest.raises(AppException) as error:
            client.infer(
                payload,
                idempotency_key=uuid4(),
                request_id=payload.request_id,
                trace_id=uuid4(),
            )
    finally:
        http_client.close()

    assert error.value.code == "AI_RESPONSE_INVALID"


def test_unconfigured_client_is_rejected() -> None:
    client = AiInferenceClient(
        base_url=None,
        internal_api_prefix="/api/internal/v1",
        internal_api_key=None,
        timeout_seconds=10.0,
    )
    payload = make_payload()

    with pytest.raises(AppException) as error:
        client.infer(
            payload,
            idempotency_key=uuid4(),
            request_id=payload.request_id,
            trace_id=uuid4(),
        )

    assert error.value.code == "AI_CLIENT_NOT_CONFIGURED"


def test_request_id_mismatch_is_rejected_before_http_call() -> None:
    payload = make_payload()
    client = AiInferenceClient(
        base_url="http://192.168.0.102:8010",
        internal_api_prefix="/api/internal/v1",
        internal_api_key="test-secret",
        timeout_seconds=10.0,
    )

    with pytest.raises(AppException) as error:
        client.infer(
            payload,
            idempotency_key=uuid4(),
            request_id=UUID("00000000-0000-0000-0000-000000000001"),
            trace_id=uuid4(),
        )

    assert error.value.code == "AI_REQUEST_ID_MISMATCH"
