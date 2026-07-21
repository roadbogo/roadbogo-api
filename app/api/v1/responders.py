from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success_response
from app.dependencies.auth import CurrentUser
from app.dependencies.permissions import require_permissions
from app.schemas.common import SuccessResponse
from app.schemas.dispatch import DutyStatus, ResponderListData
from app.services import responder_query

router = APIRouter(prefix="/responders", tags=["responders"])
DispatchPermission = Annotated[
    CurrentUser, Depends(require_permissions("DISPATCH.ASSIGN"))
]


@router.get("", response_model=SuccessResponse[ResponderListData])
def get_responders(
    request: Request,
    _: DispatchPermission,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    duty_status: DutyStatus | None = None,
    available_only: bool = True,
    db: Session = Depends(get_db),
):
    data = responder_query.list_responders(
        db,
        page=page,
        size=size,
        keyword=keyword,
        duty_status=duty_status.value if duty_status else None,
        available_only=available_only,
    )
    return success_response(data=data, trace_id=request.state.trace_id)
