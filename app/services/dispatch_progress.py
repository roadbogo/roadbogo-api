import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.dependencies.auth import CurrentUser
from app.models.dispatch import DispatchRequest, DispatchStateTransition, DispatchStatusHistory
from app.models.incident import Incident, IncidentStateTransition, IncidentStatusHistory
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services.incident_command import CommandResult, IDEMPOTENCY_RETENTION_HOURS
from app.services.query_common import utc_z


@dataclass(frozen=True)
class CommandConfig:
    scope_code: str
    dispatch_from: str
    dispatch_to: str
    timestamp_field: str
    audit_action: str
    outbox_event: str
    incident_from: str
    incident_to: str | None
    incident_reason: str | None
    message: str


CONFIGS = {
    "depart": CommandConfig(
        "DISPATCH_DEPART", "ACCEPTED", "DEPARTED", "departed_at",
        "DISPATCH.DEPART", "DISPATCH.DEPARTED", "DISPATCHED", None, None,
        "출동을 시작했습니다.",
    ),
    "en-route": CommandConfig(
        "DISPATCH_EN_ROUTE", "DEPARTED", "EN_ROUTE", "en_route_at",
        "DISPATCH.EN_ROUTE", "DISPATCH.EN_ROUTE", "DISPATCHED", None, None,
        "현장으로 이동 중입니다.",
    ),
    "arrive": CommandConfig(
        "DISPATCH_ARRIVE", "EN_ROUTE", "ARRIVED", "arrived_at",
        "DISPATCH.ARRIVE", "DISPATCH.ARRIVED", "DISPATCHED", "ON_SCENE",
        "RESPONDER_ARRIVED", "현장에 도착했습니다.",
    ),
    "start-action": CommandConfig(
        "DISPATCH_START_ACTION", "ARRIVED", "ACTION_IN_PROGRESS", "action_started_at",
        "DISPATCH.START_ACTION", "DISPATCH.ACTION_STARTED", "ON_SCENE",
        "ACTION_IN_PROGRESS", "RESPONDER_ACTION_STARTED", "현장 조치를 시작했습니다.",
    ),
}


def _error(status: int, code: str, message: str, details=None) -> AppException:
    return AppException(status, code, message, details)


def _hash(config: CommandConfig, actor_id: str, dispatch_id: str, version: int) -> str:
    value = {
        "scope_code": config.scope_code,
        "actor_public_id": actor_id,
        "dispatch_public_id": dispatch_id,
        "body": {"expected_version_no": version},
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _idempotency(db: Session, scope: str, key: str):
    return db.scalars(
        select(IdempotencyKey).where(
            IdempotencyKey.scope_code == scope,
            IdempotencyKey.idempotency_key == key,
        ).with_for_update()
    ).first()


def _replay(record, request_hash: str) -> CommandResult:
    if record.request_hash != request_hash or record.processing_status != "COMPLETED":
        raise _error(409, "DISPATCH_IDEMPOTENCY_CONFLICT", "멱등 요청을 재사용할 수 없습니다.")
    snapshot = record.response_snapshot_json
    if not isinstance(snapshot, dict):
        raise _error(409, "DISPATCH_IDEMPOTENCY_CONFLICT", "처리 결과를 재사용할 수 없습니다.")
    return CommandResult(snapshot["data"], snapshot["message"])


def _envelope(
    event_type: str, resource_type: str, resource_id: str, version: int,
    data: dict, now: datetime, trace_id: str,
) -> tuple[str, dict]:
    event_id = str(uuid4())
    return event_id, {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": utc_z(now),
        "resource": {"resource_type": resource_type, "resource_public_id": resource_id},
        "version_no": version,
        "data": data,
        "notification": None,
        "trace_id": trace_id,
    }


def execute(
    db: Session, *, command: str, dispatch_public_id: str,
    expected_version_no: int, idempotency_key: str,
    current_user: CurrentUser, trace_id: str,
) -> CommandResult:
    config = CONFIGS[command]
    actor_user_id = current_user.user.user_id
    actor_public_id = current_user.user.public_id
    actor_name = current_user.user.user_name
    request_hash = _hash(config, actor_public_id, dispatch_public_id, expected_version_no)
    now = datetime.now(UTC).replace(tzinfo=None)
    dispatch = incident = None
    dispatch_before = incident_before = None
    try:
        existing = _idempotency(db, config.scope_code, idempotency_key)
        if existing is not None:
            return _replay(existing, request_hash)
        idempotency = IdempotencyKey(
            scope_code=config.scope_code, idempotency_key=idempotency_key,
            request_hash=request_hash, processing_status="PROCESSING",
            expires_at=now + timedelta(hours=IDEMPOTENCY_RETENTION_HOURS),
        )
        db.add(idempotency)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            concurrent = _idempotency(db, config.scope_code, idempotency_key)
            if concurrent is None:
                raise
            return _replay(concurrent, request_hash)

        preview_incident_id = db.scalar(
            select(DispatchRequest.incident_id).where(
                DispatchRequest.public_id == dispatch_public_id,
                DispatchRequest.responder_user_id == actor_user_id,
            )
        )
        if preview_incident_id is None:
            raise _error(404, "DISPATCH_NOT_FOUND", "출동 요청 정보를 찾을 수 없습니다.")
        incident = db.scalars(
            select(Incident).where(Incident.incident_id == preview_incident_id).with_for_update()
        ).first()
        dispatch = db.scalars(
            select(DispatchRequest).where(
                DispatchRequest.public_id == dispatch_public_id,
                DispatchRequest.responder_user_id == actor_user_id,
            ).with_for_update()
        ).first()
        if (
            incident is None or dispatch is None
            or dispatch.public_id != dispatch_public_id
            or dispatch.responder_user_id != actor_user_id
            or dispatch.incident_id != preview_incident_id
        ):
            raise _error(404, "DISPATCH_NOT_FOUND", "출동 요청 정보를 찾을 수 없습니다.")
        if dispatch.version_no != expected_version_no:
            raise _error(
                409, "DISPATCH_VERSION_CONFLICT", "출동 요청 정보가 변경되었습니다.",
                {"requested_version_no": expected_version_no, "current_version_no": dispatch.version_no},
            )
        if dispatch.dispatch_status != config.dispatch_from:
            raise _error(
                409, "DISPATCH_INVALID_STATE_TRANSITION",
                "현재 출동 상태에서는 요청한 작업을 수행할 수 없습니다.",
                {"current_status": dispatch.dispatch_status, "requested_status": config.dispatch_to},
            )
        dispatch_transition = db.scalars(
            select(DispatchStateTransition).where(
                DispatchStateTransition.from_status == config.dispatch_from,
                DispatchStateTransition.to_status == config.dispatch_to,
                DispatchStateTransition.actor_scope == "RESPONDER",
                DispatchStateTransition.is_active == 1,
            )
        ).first()
        if dispatch_transition is None:
            raise _error(
                409, "DISPATCH_INVALID_STATE_TRANSITION",
                "현재 출동 상태에서는 요청한 작업을 수행할 수 없습니다.",
                {"current_status": dispatch.dispatch_status, "requested_status": config.dispatch_to},
            )
        if incident.incident_status != config.incident_from:
            raise _error(
                409, "INCIDENT_INVALID_STATE_TRANSITION",
                "현재 사건 상태에서는 요청한 작업을 수행할 수 없습니다.",
                {"current_status": incident.incident_status, "requested_status": config.incident_to},
            )
        if config.incident_to:
            incident_transition = db.scalars(
                select(IncidentStateTransition).where(
                    IncidentStateTransition.from_status == config.incident_from,
                    IncidentStateTransition.to_status == config.incident_to,
                    IncidentStateTransition.actor_scope == "SYSTEM",
                    IncidentStateTransition.is_active == 1,
                )
            ).first()
            if incident_transition is None:
                raise _error(
                    409, "INCIDENT_INVALID_STATE_TRANSITION",
                    "현재 사건 상태에서는 요청한 작업을 수행할 수 없습니다.",
                    {"current_status": incident.incident_status, "requested_status": config.incident_to},
                )

        dispatch_before = (
            dispatch.dispatch_status,
            dispatch.version_no,
            dispatch.status_change_method,
            getattr(dispatch, config.timestamp_field),
        )
        incident_before = (incident.incident_status, incident.version_no)
        dispatch.dispatch_status = config.dispatch_to
        dispatch.version_no += 1
        dispatch.status_change_method = "MANUAL"
        setattr(dispatch, config.timestamp_field, now)
        if config.incident_to:
            incident.incident_status = config.incident_to
            incident.version_no += 1

        db.add(DispatchStatusHistory(
            public_id=str(uuid4()), dispatch_request_id=dispatch.dispatch_request_id,
            from_status=config.dispatch_from, to_status=config.dispatch_to,
            actor_type="USER", actor_user_id=actor_user_id, change_method="MANUAL",
            idempotency_key=idempotency_key, changed_at=now,
            metadata_json={"dispatch_public_id": dispatch.public_id},
        ))
        if config.incident_to:
            db.add(IncidentStatusHistory(
                public_id=str(uuid4()), incident_id=incident.incident_id,
                from_status=config.incident_from, to_status=config.incident_to,
                actor_type="SYSTEM", actor_user_id=actor_user_id, change_source="AUTO",
                reason_code=config.incident_reason, idempotency_key=idempotency_key,
                changed_at=now, metadata_json={"dispatch_public_id": dispatch.public_id},
            ))
        db.add(AuditLog(
            public_id=str(uuid4()), actor_type="USER", actor_user_id=actor_user_id,
            action_code=config.audit_action, resource_type="DISPATCH",
            resource_public_id=dispatch.public_id, result_status="SUCCESS",
            before_json={"public_id": dispatch.public_id, "status": config.dispatch_from,
                         "version_no": dispatch_before[1]},
            after_json={"public_id": dispatch.public_id, "status": config.dispatch_to,
                        "version_no": dispatch.version_no},
            trace_id=trace_id,
        ))
        changed_by = {"public_id": actor_public_id, "user_name": actor_name}
        dispatch_event_id, dispatch_payload = _envelope(
            config.outbox_event, "DISPATCH", dispatch.public_id, dispatch.version_no,
            {"dispatch_public_id": dispatch.public_id, "incident_public_id": incident.public_id,
             "previous_status": config.dispatch_from, "status": config.dispatch_to,
             "changed_by": changed_by, "changed_at": utc_z(now)}, now, trace_id,
        )
        db.add(EventOutbox(
            event_uuid=dispatch_event_id, aggregate_type="DISPATCH",
            aggregate_public_id=dispatch.public_id, event_type=config.outbox_event,
            payload_json=dispatch_payload, publish_status="PENDING", retry_count=0,
            next_attempt_at=now,
        ))
        if config.incident_to:
            incident_event_id, incident_payload = _envelope(
                "INCIDENT.STATUS_CHANGED", "INCIDENT", incident.public_id,
                incident.version_no,
                {"incident_no": incident.incident_no, "previous_status": config.incident_from,
                 "status": config.incident_to, "changed_by": changed_by,
                 "changed_at": utc_z(now)}, now, trace_id,
            )
            db.add(EventOutbox(
                event_uuid=incident_event_id, aggregate_type="INCIDENT",
                aggregate_public_id=incident.public_id, event_type="INCIDENT.STATUS_CHANGED",
                payload_json=incident_payload, publish_status="PENDING", retry_count=0,
                next_attempt_at=now,
            ))
        data = {
            "dispatch": {"public_id": dispatch.public_id,
                         "previous_status": config.dispatch_from,
                         "status": config.dispatch_to, "occurred_at": utc_z(now),
                         "version_no": dispatch.version_no},
            "incident": {"public_id": incident.public_id, "status": incident.incident_status,
                         "version_no": incident.version_no},
        }
        idempotency.processing_status = "COMPLETED"
        idempotency.resource_type = "DISPATCH"
        idempotency.resource_public_id = dispatch.public_id
        idempotency.response_code = 200
        idempotency.response_snapshot_json = {"data": data, "message": config.message}
        db.flush()
        db.commit()
        return CommandResult(data, config.message)
    except Exception:
        db.rollback()
        if dispatch is not None and dispatch_before is not None:
            (
                dispatch.dispatch_status,
                dispatch.version_no,
                dispatch.status_change_method,
                timestamp,
            ) = dispatch_before
            setattr(dispatch, config.timestamp_field, timestamp)
        if incident is not None and incident_before is not None:
            incident.incident_status, incident.version_no = incident_before
        raise
