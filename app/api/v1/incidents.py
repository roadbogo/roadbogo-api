from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AfterValidator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.dependencies.auth import CurrentUser
from app.dependencies.permissions import require_permissions
from app.schemas.common import SuccessResponse
from app.schemas.incident import (
    IncidentDetailData,
    IncidentEvidenceListData,
    IncidentHistoryListData,
    IncidentListData,
    IncidentSummaryData,
)
from app.services import incident_query

router = APIRouter(prefix="/incidents", tags=["incidents"])
IncidentPermission = Annotated[
    CurrentUser, Depends(require_permissions("INCIDENT.READ_ALL"))
]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone offset is required")
    return value.astimezone(UTC).replace(tzinfo=None)


AwareDatetime = Annotated[datetime, AfterValidator(_aware)]


def _range(from_dt: datetime | None, to_dt: datetime | None) -> None:
    if from_dt is not None and to_dt is not None and from_dt > to_dt:
        raise AppException(
            422, "COMMON_VALIDATION_ERROR", "요청값을 확인해 주세요."
        )


@router.get("/summary", response_model=SuccessResponse[IncidentSummaryData])
def get_summary(
    request: Request,
    _: IncidentPermission,
    from_dt: AwareDatetime | None = Query(None, alias="from"),
    to_dt: AwareDatetime | None = Query(None, alias="to"),
    road_public_id: UUID | None = None,
    db: Session = Depends(get_db),
):
    _range(from_dt, to_dt)
    data = incident_query.summary(
        db, from_dt=from_dt, to_dt=to_dt, road_public_id=road_public_id
    )
    return success_response(data=data, trace_id=request.state.trace_id)


@router.get("", response_model=SuccessResponse[IncidentListData])
def get_incidents(
    request: Request,
    current_user: IncidentPermission,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    status: Literal["NEW", "ACKNOWLEDGED", "CLAIMED", "UNDER_REVIEW", "FALSE_POSITIVE", "DISPATCH_REQUESTED", "DISPATCHED", "ON_SCENE", "ACTION_IN_PROGRESS", "ACTION_COMPLETED", "CLOSED"] | None = None,
    risk_grade: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] | None = None,
    object_category: Literal["VEHICLE", "DEBRIS", "WILDLIFE", "OTHER"] | None = None,
    class_code: str | None = None,
    cctv_public_id: UUID | None = None,
    road_public_id: UUID | None = None,
    road_section_public_id: UUID | None = None,
    controller_public_id: UUID | None = None,
    mine_only: bool = False,
    unclaimed_only: bool = False,
    from_dt: AwareDatetime | None = Query(None, alias="from"),
    to_dt: AwareDatetime | None = Query(None, alias="to"),
    sort: Literal["priority,desc", "first_detected_at,desc", "last_detected_at,desc", "risk_score,desc", "status,asc"] = "priority,desc",
    db: Session = Depends(get_db),
):
    _range(from_dt, to_dt)
    filters = locals().copy()
    filters["current_user_id"] = current_user.user.user_id
    data = incident_query.list_incidents(
        db, page=page, size=size, filters=filters, sort=sort
    )
    return success_response(data=data, trace_id=request.state.trace_id)


@router.get("/{incident_public_id}", response_model=SuccessResponse[IncidentDetailData])
def get_incident(
    incident_public_id: UUID,
    request: Request,
    _: IncidentPermission,
    db: Session = Depends(get_db),
):
    return success_response(
        data=incident_query.get_incident(db, str(incident_public_id)),
        trace_id=request.state.trace_id,
    )


@router.get(
    "/{incident_public_id}/evidences",
    response_model=SuccessResponse[IncidentEvidenceListData],
)
def get_evidences(
    incident_public_id: UUID,
    request: Request,
    _: IncidentPermission,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    representative_only: bool = False,
    sort: Literal["detected_at,asc", "detected_at,desc"] = "detected_at,asc",
    db: Session = Depends(get_db),
):
    return success_response(
        data=incident_query.evidences(
            db, str(incident_public_id), page=page, size=size,
            representative_only=representative_only, sort=sort
        ),
        trace_id=request.state.trace_id,
    )


@router.get(
    "/{incident_public_id}/histories",
    response_model=SuccessResponse[IncidentHistoryListData],
)
def get_histories(
    incident_public_id: UUID,
    request: Request,
    _: IncidentPermission,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    sort: Literal["changed_at,asc", "changed_at,desc"] = "changed_at,asc",
    db: Session = Depends(get_db),
):
    return success_response(
        data=incident_query.histories(
            db, str(incident_public_id), page=page, size=size, sort=sort
        ),
        trace_id=request.state.trace_id,
    )
