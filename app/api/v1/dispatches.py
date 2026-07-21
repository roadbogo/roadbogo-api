from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success_response
from app.dependencies.auth import CurrentUser
from app.dependencies.permissions import require_permissions
from app.schemas.common import SuccessResponse
from app.schemas.dispatch import DispatchAssignmentData, DispatchAssignmentRequest
from app.services import dispatch_assignment

router = APIRouter(tags=["dispatches"])
DispatchPermission = Annotated[
    CurrentUser, Depends(require_permissions("DISPATCH.ASSIGN"))
]


@router.post(
    "/incidents/{incident_public_id}/dispatches",
    response_model=SuccessResponse[DispatchAssignmentData],
    status_code=201,
)
def assign_dispatch(
    incident_public_id: UUID,
    payload: DispatchAssignmentRequest,
    request: Request,
    current_user: DispatchPermission,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    result = dispatch_assignment.assign_dispatch(
        db,
        incident_public_id=str(incident_public_id),
        responder_public_id=str(payload.responder_public_id),
        request_message=payload.request_message,
        expected_version_no=payload.expected_version_no,
        idempotency_key=str(idempotency_key),
        current_user=current_user,
        trace_id=request.state.trace_id,
    )
    return success_response(
        data=result.data,
        message=result.message,
        trace_id=request.state.trace_id,
    )
