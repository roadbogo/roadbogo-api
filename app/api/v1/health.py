from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.schemas.common import SuccessResponse

router = APIRouter()


class HealthData(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    server_time: str


class DatabaseHealthData(BaseModel):
    status: str
    database: str


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


@router.get("/health/db", response_model=SuccessResponse[DatabaseHealthData])
def database_health_check(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise AppException(
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="데이터베이스 연결에 실패했습니다.",
        ) from exc

    return success_response(
        data={
            "status": "UP",
            "database": settings.db_scheme,
        },
        trace_id=request.state.trace_id,
    )