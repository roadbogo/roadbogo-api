from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.dependencies.auth import CurrentUser
from app.dependencies.permissions import require_permissions
from app.schemas.cctv import CctvDetailData, CctvListData
from app.schemas.common import SuccessResponse
from app.services import cctv_query

router = APIRouter(prefix="/cctvs", tags=["cctvs"])
CctvPermission = Annotated[CurrentUser, Depends(require_permissions("CCTV.READ"))]


@router.get("", response_model=SuccessResponse[CctvListData])
def get_cctvs(
    request: Request,
    _: CctvPermission,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    road_public_id: UUID | None = None,
    road_section_public_id: UUID | None = None,
    direction_code: Literal["ASC", "DESC", "BOTH", "UNKNOWN"] | None = None,
    operational_status: Literal["NORMAL", "DELAYED", "FAULT", "INACTIVE", "UNKNOWN"] | None = None,
    source_type: Literal["ITS", "MANUAL", "DEMO"] | None = None,
    min_latitude: float | None = Query(None, ge=-90, le=90),
    max_latitude: float | None = Query(None, ge=-90, le=90),
    min_longitude: float | None = Query(None, ge=-180, le=180),
    max_longitude: float | None = Query(None, ge=-180, le=180),
    sort: Literal["cctv_name,asc"] = "cctv_name,asc",
    db: Session = Depends(get_db),
):
    if min_latitude is not None and max_latitude is not None and min_latitude > max_latitude:
        raise AppException(422, "COMMON_VALIDATION_ERROR", "요청값을 확인해 주세요.")
    if min_longitude is not None and max_longitude is not None and min_longitude > max_longitude:
        raise AppException(422, "COMMON_VALIDATION_ERROR", "요청값을 확인해 주세요.")
    data = cctv_query.list_cctvs(
        db, page=page, size=size, filters=locals().copy(), sort=sort
    )
    return success_response(data=data, trace_id=request.state.trace_id)


@router.get("/{cctv_public_id}", response_model=SuccessResponse[CctvDetailData])
def get_cctv(
    cctv_public_id: UUID,
    request: Request,
    _: CctvPermission,
    db: Session = Depends(get_db),
):
    return success_response(
        data=cctv_query.get_cctv(db, str(cctv_public_id)),
        trace_id=request.state.trace_id,
    )
