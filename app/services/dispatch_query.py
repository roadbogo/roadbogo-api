from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import AppException
from app.models.dispatch import DispatchRequest
from app.services.query_common import number, pagination, utc_z

TERMINAL_STATUSES = ("REJECTED", "CANCELLED", "ACTION_COMPLETED")


def _not_found() -> AppException:
    return AppException(404, "DISPATCH_NOT_FOUND", "출동 요청 정보를 찾을 수 없습니다.")


def _item(dispatch: DispatchRequest) -> dict:
    incident = dispatch.incident
    return {
        "public_id": dispatch.public_id,
        "attempt_no": dispatch.attempt_no,
        "status": dispatch.dispatch_status,
        "request_message": dispatch.request_message,
        "requested_at": utc_z(dispatch.requested_at),
        "accepted_at": utc_z(dispatch.accepted_at) if dispatch.accepted_at else None,
        "version_no": dispatch.version_no,
        "incident": {
            "public_id": incident.public_id,
            "incident_no": incident.incident_no,
            "status": incident.incident_status,
            "object_category": incident.object_category,
            "ai_risk_grade": incident.current_risk_grade,
            "cctv_name": incident.cctv_name_snapshot,
            "road_name": incident.road_name_snapshot,
            "road_section_name": incident.road_section_name_snapshot,
            "latitude": number(incident.latitude_snapshot),
            "longitude": number(incident.longitude_snapshot),
        },
        "assigned_by": {
            "public_id": dispatch.assigned_by_user.public_id,
            "user_name": dispatch.assigned_by_user.user_name,
        },
    }


def list_mine(
    db: Session, *, user_id: int, page: int, size: int,
    status: str | None, active_only: bool,
) -> dict:
    conditions = [DispatchRequest.responder_user_id == user_id]
    if status:
        conditions.append(DispatchRequest.dispatch_status == status)
    if active_only:
        conditions.append(DispatchRequest.dispatch_status.not_in(TERMINAL_STATUSES))
    total = db.scalar(
        select(func.count()).select_from(DispatchRequest).where(*conditions)
    ) or 0
    active_order = case(
        (DispatchRequest.dispatch_status.in_(TERMINAL_STATUSES), 1), else_=0
    )
    stmt = (
        select(DispatchRequest)
        .where(*conditions)
        .options(
            joinedload(DispatchRequest.incident),
            joinedload(DispatchRequest.assigned_by_user),
        )
        .order_by(
            active_order.asc(),
            DispatchRequest.requested_at.desc(),
            DispatchRequest.dispatch_request_id.desc(),
        )
        .offset((page - 1) * size)
        .limit(size)
    )
    return {
        "items": [_item(value) for value in db.scalars(stmt).unique()],
        "pagination": pagination(page, size, total),
    }


def detail(db: Session, *, public_id: str, user_id: int) -> dict:
    dispatch = db.scalars(
        select(DispatchRequest)
        .where(
            DispatchRequest.public_id == public_id,
            DispatchRequest.responder_user_id == user_id,
        )
        .options(
            joinedload(DispatchRequest.incident),
            joinedload(DispatchRequest.assigned_by_user),
            joinedload(DispatchRequest.previous_dispatch_request),
        )
    ).first()
    if dispatch is None:
        raise _not_found()
    data = _item(dispatch)
    data.update(
        {
            "rejection_reason": dispatch.rejection_reason,
            "departed_at": utc_z(dispatch.departed_at) if dispatch.departed_at else None,
            "en_route_at": utc_z(dispatch.en_route_at) if dispatch.en_route_at else None,
            "arrived_at": utc_z(dispatch.arrived_at) if dispatch.arrived_at else None,
            "action_started_at": (
                utc_z(dispatch.action_started_at) if dispatch.action_started_at else None
            ),
            "action_completed_at": (
                utc_z(dispatch.action_completed_at) if dispatch.action_completed_at else None
            ),
            "cancelled_at": utc_z(dispatch.cancelled_at) if dispatch.cancelled_at else None,
            "previous_dispatch_public_id": (
                dispatch.previous_dispatch_request.public_id
                if dispatch.previous_dispatch_request else None
            ),
        }
    )
    return data
