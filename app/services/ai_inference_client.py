from uuid import UUID

import httpx
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.exceptions import AppException
from app.schemas.ai_inference import (
    AiInternalErrorResponse,
    AiInternalInferenceRequest,
    AiInternalInferenceResponse,
)


class AiInferenceClient:
    def __init__(
        self,
        *,
        base_url: str | None,
        internal_api_prefix: str,
        internal_api_key: str | None,
        timeout_seconds: float,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.internal_api_prefix = "/" + internal_api_prefix.strip("/")
        self.internal_api_key = internal_api_key
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    @classmethod
    def from_settings(
        cls,
        app_settings: Settings = settings,
        *,
        http_client: httpx.Client | None = None,
    ) -> "AiInferenceClient":
        api_key = (
            app_settings.ai_internal_api_key.get_secret_value()
            if app_settings.ai_internal_api_key is not None
            else None
        )
        return cls(
            base_url=app_settings.ai_server_base_url,
            internal_api_prefix=app_settings.ai_server_internal_api_v1_prefix,
            internal_api_key=api_key,
            timeout_seconds=app_settings.ai_inference_timeout_seconds,
            http_client=http_client,
        )

    @property
    def endpoint_url(self) -> str:
        if not self.base_url or not self.internal_api_key:
            raise AppException(
                status_code=503,
                code="AI_CLIENT_NOT_CONFIGURED",
                message="AI server connection is not configured.",
            )
        return f"{self.base_url}{self.internal_api_prefix}/inferences"

    def infer(
        self,
        payload: AiInternalInferenceRequest,
        *,
        idempotency_key: UUID,
        request_id: UUID,
        trace_id: UUID,
    ) -> AiInternalInferenceResponse:
        if request_id != payload.request_id:
            raise AppException(
                status_code=400,
                code="AI_REQUEST_ID_MISMATCH",
                message="The request identifier does not match the payload.",
            )

        headers = {
            "X-Internal-API-Key": self.internal_api_key or "",
            "Idempotency-Key": str(idempotency_key),
            "X-Request-ID": str(request_id),
            "X-Trace-ID": str(trace_id),
        }

        try:
            response = self._post(
                self.endpoint_url,
                headers=headers,
                json=payload.model_dump(mode="json"),
            )
        except httpx.RequestError as error:
            raise AppException(
                status_code=503,
                code="AI_SERVER_UNAVAILABLE",
                message="The AI server could not be reached.",
                details={"reason": type(error).__name__},
            ) from error

        if not response.is_success:
            self._raise_ai_error(response)

        try:
            result = AiInternalInferenceResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise AppException(
                status_code=502,
                code="AI_RESPONSE_INVALID",
                message="The AI server returned an invalid response.",
            ) from error

        mismatched_fields = []
        if result.data.request_id != payload.request_id:
            mismatched_fields.append("request_id")
        if result.data.inference_run_public_id != payload.inference_run_public_id:
            mismatched_fields.append("inference_run_public_id")
        if result.data.video_frame_public_id != payload.video_frame.public_id:
            mismatched_fields.append("video_frame_public_id")
        if result.trace_id != trace_id:
            mismatched_fields.append("trace_id")

        if mismatched_fields:
            raise AppException(
                status_code=502,
                code="AI_RESPONSE_INVALID",
                message="The AI server response identifiers do not match the request.",
                details={"mismatched_fields": mismatched_fields},
            )

        return result

    def _post(self, url: str, **kwargs) -> httpx.Response:
        if self.http_client is not None:
            return self.http_client.post(url, **kwargs)

        with httpx.Client(timeout=self.timeout_seconds) as client:
            return client.post(url, **kwargs)

    @staticmethod
    def _raise_ai_error(response: httpx.Response) -> None:
        try:
            error_response = AiInternalErrorResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise AppException(
                status_code=502,
                code="AI_SERVER_ERROR",
                message="The AI server returned an invalid error response.",
                details={"upstream_status_code": response.status_code},
            ) from error

        raise AppException(
            status_code=response.status_code,
            code=error_response.error.code,
            message=error_response.error.message,
            details=error_response.error.details,
        )
