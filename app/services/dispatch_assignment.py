import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppException
from app.dependencies.auth import CurrentUser
from app.models.auth import ResponderProfile, User, UserRole
from app.models.dispatch import DispatchRequest, DispatchStatusHistory
from app.models.incident import Incident
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services.incident_command import CommandResult, IDEMPOTENCY_RETENTION_HOURS
from app.services.query_common import utc_z

SCOPE_CODE = "DISPATCH_ASSIGN"
SUCCESS_MESSAGE = "출동 담당자를 배정했습니다."


def canonical_request_hash(
    *, actor_public_id: str, incident_public_id: str,
    responder_public_id: str, request_message: str | None,
    expected_version_no: int
) -> str:
    canonical = {
        "scope_code": SCOPE_CODE,
        "actor_public_id": actor_public_id,
        "incident_public_id": incident_public_id,
        "body": {
            "responder_public_id": responder_public_id,
            "request_message": request_message,
            "expected_version_no": expected_version_no,
        },
    }
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _error(status: int, code: str, message: str, details=None) -> AppException:
    return AppException(status, code, message, details)


def _idempotency(db: Session, key: str) -> IdempotencyKey | None:
    return db.scalars(
        select(IdempotencyKey)
        .where(
            IdempotencyKey.scope_code == SCOPE_CODE,
            IdempotencyKey.idempotency_key == key,
        )
        .with_for_update()
    ).first()


def _replay_or_reject(record: IdempotencyKey, request_hash: str) -> CommandResult:
    if record.request_hash != request_hash:
        raise _error(
            409, "DISPATCH_IDEMPOTENCY_CONFLICT",
            "동일한 멱등 키에 다른 출동 요청이 전달되었습니다."
        )
    if record.processing_status == "COMPLETED" and isinstance(
        record.response_snapshot_json, dict
    ):
        snapshot = record.response_snapshot_json
        return CommandResult(snapshot["data"], snapshot["message"])
    raise _error(
        409, "DISPATCH_IDEMPOTENCY_CONFLICT",
        "동일한 멱등 키의 출동 요청이 처리 중입니다.",
        {"processing_status": record.processing_status},
    )


def _lock_incident(db: Session, public_id: str) -> Incident:
    incident = db.scalars(
        select(Incident).where(Incident.public_id == public_id).with_for_update()
    ).first()
    if incident is None:
        raise _error(404, "INCIDENT_NOT_FOUND", "사건 정보를 찾을 수 없습니다.")
    return incident


def _lock_responder(db: Session, public_id: str) -> tuple[User, ResponderProfile]:
    user = db.scalars(
        select(User)
        .where(User.public_id == public_id)
        .options(
            selectinload(User.responder_profiles),
            selectinload(User.user_roles_users).joinedload(UserRole.role),
        )
        .with_for_update()
    ).first()
    if user is None:
        raise _error(
            404, "DISPATCH_RESPONDER_NOT_FOUND",
            "출동 담당자 정보를 찾을 수 없습니다."
        )
    active_responder_role = any(
        user_role.role.role_code == "RESPONDER" and bool(user_role.role.is_active)
        for user_role in user.user_roles_users
    )
    profile = user.responder_profiles[0] if user.responder_profiles else None
    if not active_responder_role or profile is None:
        raise _error(
            404, "DISPATCH_RESPONDER_NOT_FOUND",
            "출동 담당자 정보를 찾을 수 없습니다."
        )
    return user, profile


def _active_dispatch(
    db: Session, *, incident_id: int | None = None, responder_user_id: int | None = None
) -> DispatchRequest | None:
    condition = (
        DispatchRequest.active_incident_id == incident_id
        if incident_id is not None
        else DispatchRequest.active_responder_id == responder_user_id
    )
    return db.scalars(select(DispatchRequest).where(condition).with_for_update()).first()


def _latest_dispatch(db: Session, incident_id: int) -> DispatchRequest | None:
    return db.scalars(
        select(DispatchRequest)
        .where(DispatchRequest.incident_id == incident_id)
        .order_by(DispatchRequest.attempt_no.desc())
        .limit(1)
        .with_for_update()
    ).first()


def _integrity_error(exc: IntegrityError) -> AppException | None:
    message = str(exc.orig).lower()
    if "uk_dispatch_requests_active_incident" in message:
        return _error(
            409, "DISPATCH_ALREADY_ASSIGNED",
            "해당 사건에는 이미 활성 출동 요청이 있습니다."
        )
    if "uk_dispatch_requests_active_responder" in message:
        return _error(
            409, "DISPATCH_RESPONDER_BUSY",
            "해당 담당자는 이미 다른 출동을 진행 중입니다."
        )
    return None


def _response_data(
    *, dispatch: DispatchRequest, incident: Incident, responder: User,
    profile: ResponderProfile, current_user: CurrentUser, now: datetime
) -> dict[str, Any]:
    return {
        "dispatch": {
            "public_id": dispatch.public_id,
            "incident_public_id": incident.public_id,
            "attempt_no": dispatch.attempt_no,
            "status": dispatch.dispatch_status,
            "responder": {
                "public_id": responder.public_id,
                "user_name": responder.user_name,
                "responder_code": profile.responder_code,
            },
            "assigned_by": {
                "public_id": current_user.user.public_id,
                "user_name": current_user.user.user_name,
            },
            "request_message": dispatch.request_message,
            "requested_at": utc_z(now),
            "version_no": dispatch.version_no,
        },
        "incident": {
            "public_id": incident.public_id,
            "status": incident.incident_status,
            "version_no": incident.version_no,
        },
    }


def assign_dispatch(
    db: Session,
    *,
    incident_public_id: str,
    responder_public_id: str,
    request_message: str | None,
    expected_version_no: int,
    idempotency_key: str,
    current_user: CurrentUser,
    trace_id: str,
) -> CommandResult:
    request_hash = canonical_request_hash(
        actor_public_id=current_user.user.public_id,
        incident_public_id=incident_public_id,
        responder_public_id=responder_public_id,
        request_message=request_message,
        expected_version_no=expected_version_no,
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    try:
        existing = _idempotency(db, idempotency_key)
        if existing is not None:
            return _replay_or_reject(existing, request_hash)
        idempotency = IdempotencyKey(
            scope_code=SCOPE_CODE,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            processing_status="PROCESSING",
            expires_at=now + timedelta(hours=IDEMPOTENCY_RETENTION_HOURS),
        )
        db.add(idempotency)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            concurrent = _idempotency(db, idempotency_key)
            if concurrent is None:
                raise
            return _replay_or_reject(concurrent, request_hash)

        incident = _lock_incident(db, incident_public_id)
        if incident.version_no != expected_version_no:
            raise _error(
                409, "INCIDENT_VERSION_CONFLICT",
                "사건 정보가 변경되었습니다. 최신 정보를 다시 확인해 주세요.",
                {
                    "requested_version_no": expected_version_no,
                    "current_version_no": incident.version_no,
                },
            )
        if incident.incident_status != "DISPATCH_REQUESTED":
            raise _error(
                409, "INCIDENT_INVALID_STATE_TRANSITION",
                "현재 사건 상태에서는 요청한 작업을 수행할 수 없습니다.",
                {
                    "current_status": incident.incident_status,
                    "requested_status": "DISPATCH_REQUESTED",
                },
            )
        if incident.current_controller_user_id != current_user.user.user_id:
            raise _error(
                403, "INCIDENT_NOT_ASSIGNED_CONTROLLER",
                "해당 사건의 담당 관제자가 아닙니다."
            )

        responder, profile = _lock_responder(db, responder_public_id)
        if (
            responder.account_status != "ACTIVE"
            or responder.deleted_at is not None
            or not profile.is_dispatch_enabled
            or profile.duty_status != "AVAILABLE"
        ):
            raise _error(
                409, "DISPATCH_RESPONDER_UNAVAILABLE",
                "현재 출동할 수 없는 담당자입니다."
            )
        if _active_dispatch(db, incident_id=incident.incident_id) is not None:
            raise _error(
                409, "DISPATCH_ALREADY_ASSIGNED",
                "해당 사건에는 이미 활성 출동 요청이 있습니다."
            )
        if _active_dispatch(db, responder_user_id=responder.user_id) is not None:
            raise _error(
                409, "DISPATCH_RESPONDER_BUSY",
                "해당 담당자는 이미 다른 출동을 진행 중입니다."
            )
        previous = _latest_dispatch(db, incident.incident_id)
        attempt_no = previous.attempt_no + 1 if previous else 1
        dispatch = DispatchRequest(
            public_id=str(uuid4()),
            incident_id=incident.incident_id,
            attempt_no=attempt_no,
            responder_user_id=responder.user_id,
            assigned_by_user_id=current_user.user.user_id,
            dispatch_status="REQUESTED",
            status_change_method="MANUAL",
            requested_at=now,
            version_no=0,
            previous_dispatch_request_id=(
                previous.dispatch_request_id if previous else None
            ),
            request_message=request_message,
            rejection_reason=None,
        )
        db.add(dispatch)
        try:
            db.flush()
        except IntegrityError as exc:
            conflict = _integrity_error(exc)
            if conflict:
                raise conflict from exc
            raise

        db.add(
            DispatchStatusHistory(
                public_id=str(uuid4()),
                dispatch_request_id=dispatch.dispatch_request_id,
                from_status=None,
                to_status="REQUESTED",
                actor_type="USER",
                actor_user_id=current_user.user.user_id,
                change_method="MANUAL",
                reason_text=request_message,
                idempotency_key=idempotency_key,
                changed_at=now,
                metadata_json={
                    "incident_public_id": incident.public_id,
                    "responder_public_id": responder.public_id,
                    "attempt_no": attempt_no,
                },
            )
        )
        previous_incident_version = incident.version_no
        incident.version_no += 1
        db.add(
            AuditLog(
                public_id=str(uuid4()),
                actor_type="USER",
                actor_user_id=current_user.user.user_id,
                action_code="DISPATCH.ASSIGN",
                resource_type="DISPATCH",
                resource_public_id=dispatch.public_id,
                result_status="SUCCESS",
                before_json={
                    "incident_status": incident.incident_status,
                    "incident_version_no": previous_incident_version,
                    "active_dispatch_public_id": None,
                },
                after_json={
                    "incident_status": incident.incident_status,
                    "incident_version_no": incident.version_no,
                    "dispatch_public_id": dispatch.public_id,
                    "dispatch_status": "REQUESTED",
                    "responder_public_id": responder.public_id,
                    "attempt_no": attempt_no,
                },
                trace_id=trace_id,
            )
        )
        event_id = str(uuid4())
        db.add(
            EventOutbox(
                event_uuid=event_id,
                aggregate_type="DISPATCH",
                aggregate_public_id=dispatch.public_id,
                event_type="DISPATCH.REQUESTED",
                payload_json={
                    "event_id": event_id,
                    "event_type": "DISPATCH.REQUESTED",
                    "occurred_at": utc_z(now),
                    "resource": {
                        "resource_type": "DISPATCH",
                        "resource_public_id": dispatch.public_id,
                    },
                    "version_no": 0,
                    "data": {
                        "dispatch_public_id": dispatch.public_id,
                        "incident_public_id": incident.public_id,
                        "incident_no": incident.incident_no,
                        "status": "REQUESTED",
                        "attempt_no": attempt_no,
                        "responder": {
                            "public_id": responder.public_id,
                            "user_name": responder.user_name,
                            "responder_code": profile.responder_code,
                        },
                        "assigned_by": {
                            "public_id": current_user.user.public_id,
                            "user_name": current_user.user.user_name,
                        },
                        "request_message": request_message,
                        "requested_at": utc_z(now),
                    },
                    "notification": None,
                    "trace_id": trace_id,
                },
                publish_status="PENDING",
                retry_count=0,
                next_attempt_at=now,
            )
        )
        data = _response_data(
            dispatch=dispatch,
            incident=incident,
            responder=responder,
            profile=profile,
            current_user=current_user,
            now=now,
        )
        idempotency.processing_status = "COMPLETED"
        idempotency.resource_type = "DISPATCH"
        idempotency.resource_public_id = dispatch.public_id
        idempotency.response_code = 200
        idempotency.response_snapshot_json = {
            "data": data,
            "message": SUCCESS_MESSAGE,
        }
        db.flush()
        db.commit()
        return CommandResult(data, SUCCESS_MESSAGE)
    except Exception:
        db.rollback()
        raise
