from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success_response
from app.dependencies.auth import CurrentUser
from app.dependencies.permissions import require_permissions
from app.schemas.common import SuccessResponse
from app.schemas.dispatch import (
    DispatchAssignmentData,
    DispatchAssignmentRequest,
    DispatchAcceptData,
    DispatchDetailData,
    DispatchMineData,
    DispatchProgressData,
    DispatchRejectRequest,
    DispatchRejectData,
    DispatchStatus,
    DispatchVersionRequest,
)
from app.services import dispatch_assignment, dispatch_command, dispatch_progress, dispatch_query

router = APIRouter(tags=["dispatches"])
DispatchPermission = Annotated[
    CurrentUser, Depends(require_permissions("DISPATCH.ASSIGN"))
]
DispatchReadOwnPermission = Annotated[
    CurrentUser, Depends(require_permissions("DISPATCH.READ_OWN"))
]
DispatchUpdateOwnPermission = Annotated[
    CurrentUser, Depends(require_permissions("DISPATCH.UPDATE_OWN"))
]


@router.get(
    "/dispatches/mine",
    response_model=SuccessResponse[DispatchMineData],
)
def list_my_dispatches(
    request: Request,
    current_user: DispatchReadOwnPermission,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    status: DispatchStatus | None = Query(default=None),
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    data = dispatch_query.list_mine(
        db,
        user_id=current_user.user.user_id,
        page=page,
        size=size,
        status=status.value if status else None,
        active_only=active_only,
    )
    return success_response(data=data, trace_id=request.state.trace_id)


@router.get(
    "/dispatches/{dispatch_public_id}",
    response_model=SuccessResponse[DispatchDetailData],
)
def get_my_dispatch(
    dispatch_public_id: UUID,
    request: Request,
    current_user: DispatchReadOwnPermission,
    db: Session = Depends(get_db),
):
    data = dispatch_query.detail(
        db,
        public_id=str(dispatch_public_id),
        user_id=current_user.user.user_id,
    )
    return success_response(data=data, trace_id=request.state.trace_id)


def _command_response(
    *, command: str, dispatch_public_id: UUID,
    payload: DispatchVersionRequest, request: Request,
    current_user: CurrentUser, idempotency_key: UUID, db: Session,
):
    result = dispatch_command.execute(
        db,
        command=command,
        dispatch_public_id=str(dispatch_public_id),
        expected_version_no=payload.expected_version_no,
        rejection_reason=(
            payload.rejection_reason if isinstance(payload, DispatchRejectRequest) else None
        ),
        idempotency_key=str(idempotency_key),
        current_user=current_user,
        trace_id=request.state.trace_id,
    )
    return success_response(
        data=result.data, message=result.message, trace_id=request.state.trace_id
    )


@router.post(
    "/dispatches/{dispatch_public_id}/accept",
    response_model=SuccessResponse[DispatchAcceptData],
)
def accept_dispatch(
    dispatch_public_id: UUID,
    payload: DispatchVersionRequest,
    request: Request,
    current_user: DispatchUpdateOwnPermission,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    return _command_response(
        command="accept", dispatch_public_id=dispatch_public_id, payload=payload,
        request=request, current_user=current_user,
        idempotency_key=idempotency_key, db=db,
    )


@router.post(
    "/dispatches/{dispatch_public_id}/reject",
    response_model=SuccessResponse[DispatchRejectData],
)
def reject_dispatch(
    dispatch_public_id: UUID,
    payload: DispatchRejectRequest,
    request: Request,
    current_user: DispatchUpdateOwnPermission,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    return _command_response(
        command="reject", dispatch_public_id=dispatch_public_id, payload=payload,
        request=request, current_user=current_user,
        idempotency_key=idempotency_key, db=db,
    )


def _progress_response(
    *, command: str, dispatch_public_id: UUID,
    payload: DispatchVersionRequest, request: Request,
    current_user: CurrentUser, idempotency_key: UUID, db: Session,
):
    result = dispatch_progress.execute(
        db,
        command=command,
        dispatch_public_id=str(dispatch_public_id),
        expected_version_no=payload.expected_version_no,
        idempotency_key=str(idempotency_key),
        current_user=current_user,
        trace_id=request.state.trace_id,
    )
    return success_response(
        data=result.data, message=result.message, trace_id=request.state.trace_id
    )


@router.post(
    "/dispatches/{dispatch_public_id}/depart",
    response_model=SuccessResponse[DispatchProgressData],
)
def depart_dispatch(
    dispatch_public_id: UUID, payload: DispatchVersionRequest, request: Request,
    current_user: DispatchUpdateOwnPermission,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    return _progress_response(
        command="depart", dispatch_public_id=dispatch_public_id, payload=payload,
        request=request, current_user=current_user, idempotency_key=idempotency_key, db=db,
    )


@router.post(
    "/dispatches/{dispatch_public_id}/en-route",
    response_model=SuccessResponse[DispatchProgressData],
)
def en_route_dispatch(
    dispatch_public_id: UUID, payload: DispatchVersionRequest, request: Request,
    current_user: DispatchUpdateOwnPermission,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    return _progress_response(
        command="en-route", dispatch_public_id=dispatch_public_id, payload=payload,
        request=request, current_user=current_user, idempotency_key=idempotency_key, db=db,
    )


@router.post(
    "/dispatches/{dispatch_public_id}/arrive",
    response_model=SuccessResponse[DispatchProgressData],
)
def arrive_dispatch(
    dispatch_public_id: UUID, payload: DispatchVersionRequest, request: Request,
    current_user: DispatchUpdateOwnPermission,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    return _progress_response(
        command="arrive", dispatch_public_id=dispatch_public_id, payload=payload,
        request=request, current_user=current_user, idempotency_key=idempotency_key, db=db,
    )


@router.post(
    "/dispatches/{dispatch_public_id}/start-action",
    response_model=SuccessResponse[DispatchProgressData],
)
def start_action_dispatch(
    dispatch_public_id: UUID, payload: DispatchVersionRequest, request: Request,
    current_user: DispatchUpdateOwnPermission,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    return _progress_response(
        command="start-action", dispatch_public_id=dispatch_public_id, payload=payload,
        request=request, current_user=current_user, idempotency_key=idempotency_key, db=db,
    )


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
