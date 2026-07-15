from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.config import settings
from app.core.responses import success_response
from app.schemas.common import SuccessResponse

router = APIRouter()


class HealthData(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    server_time: str


def utc_now_z() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@router.get("/health", response_model=SuccessResponse[HealthData])
async def health_check(request: Request) -> dict[str, Any]:
    return success_response(
        data={
            "status": "UP",
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env,
            "server_time": utc_now_z(),
        },
        trace_id=request.state.trace_id,
    )
