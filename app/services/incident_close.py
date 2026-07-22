import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.dependencies.auth import CurrentUser
from app.models.dispatch import DispatchRequest, FieldActionReport
from app.models.incident import Incident, IncidentStateTransition, IncidentStatusHistory
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services.incident_command import CommandResult, IDEMPOTENCY_RETENTION_HOURS
from app.services.query_common import utc_z

SCOPE = "INCIDENT_CLOSE"
MESSAGE = "사건이 최종 종료되었습니다."


def _error(status: int, code: str, message: str, details=None) -> AppException:
    return AppException(status, code, message, details)


def _request_hash(actor_id, incident_id, closure_code, closure_note, version) -> str:
    value = {
        "scope_code": SCOPE,
        "actor_public_id": actor_id,
        "incident_public_id": incident_id,
        "closure_code": closure_code,
        "closure_note": closure_note,
        "expected_version_no": version,
    }
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()).hexdigest()


def _existing(db: Session, key: str):
    return db.scalars(select(IdempotencyKey).where(
        IdempotencyKey.scope_code == SCOPE,
        IdempotencyKey.idempotency_key == key,
    ).with_for_update()).first()


def _replay(record, request_hash: str) -> CommandResult:
    if record.request_hash != request_hash or record.processing_status != "COMPLETED":
        raise _error(409, "INCIDENT_IDEMPOTENCY_CONFLICT", "멱등 요청을 재사용할 수 없습니다.")
    snapshot = record.response_snapshot_json
    data = snapshot.get("data") if isinstance(snapshot, dict) else None
    message = snapshot.get("message") if isinstance(snapshot, dict) else None
    if not isinstance(data, dict) or not isinstance(message, str) or not message.strip():
        raise _error(409, "INCIDENT_IDEMPOTENCY_CONFLICT", "처리 결과를 재사용할 수 없습니다.")
    return CommandResult(data, message)


def execute(
    db: Session, *, incident_public_id: str, closure_code: str, closure_note: str,
    expected_version_no: int, idempotency_key: str, current_user: CurrentUser,
    trace_id: str,
) -> CommandResult:
    actor_user_id = current_user.user.user_id
    actor_public_id = current_user.user.public_id
    actor_name = current_user.user.user_name
    roles = set(current_user.summary.roles)
    note = closure_note.strip()
    request_hash = _request_hash(
        actor_public_id, incident_public_id, closure_code, note, expected_version_no
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    incident = None
    before = None
    try:
        existing = _existing(db, idempotency_key)
        if existing is not None:
            return _replay(existing, request_hash)
        idempotency = IdempotencyKey(
            scope_code=SCOPE, idempotency_key=idempotency_key, request_hash=request_hash,
            processing_status="PROCESSING",
            expires_at=now + timedelta(hours=IDEMPOTENCY_RETENTION_HOURS),
        )
        db.add(idempotency)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            concurrent = _existing(db, idempotency_key)
            if concurrent is None:
                raise
            return _replay(concurrent, request_hash)

        incident = db.scalars(select(Incident).where(
            Incident.public_id == incident_public_id
        ).with_for_update()).first()
        if incident is None or incident.public_id != incident_public_id:
            raise _error(404, "INCIDENT_NOT_FOUND", "사건 정보를 찾을 수 없습니다.")
        dispatch = db.scalars(select(DispatchRequest).where(
            DispatchRequest.incident_id == incident.incident_id
        ).order_by(DispatchRequest.attempt_no.desc()).with_for_update()).first()
        report = None
        if dispatch is not None:
            report = db.scalars(select(FieldActionReport).where(
                FieldActionReport.dispatch_request_id == dispatch.dispatch_request_id
            )).first()

        if (
            incident.current_controller_user_id != actor_user_id
            and not roles.intersection({"CONTROL_MANAGER", "SYSTEM_ADMIN"})
        ):
            raise _error(
                403, "INCIDENT_NOT_ASSIGNED_CONTROLLER",
                "해당 사건의 담당 관제자가 아닙니다.",
            )
        if incident.version_no != expected_version_no:
            raise _error(409, "INCIDENT_VERSION_CONFLICT", "사건 정보가 변경되었습니다.")
        if incident.incident_status != "ACTION_COMPLETED" or incident.closed_at is not None:
            raise _error(409, "INCIDENT_INVALID_STATE_TRANSITION", "사건 상태 전이를 수행할 수 없습니다.")
        transition = db.scalars(select(IncidentStateTransition).where(
            IncidentStateTransition.from_status == "ACTION_COMPLETED",
            IncidentStateTransition.to_status == "CLOSED",
            IncidentStateTransition.actor_scope == "CONTROLLER",
            IncidentStateTransition.is_active == 1,
        )).first()
        if transition is None:
            raise _error(409, "INCIDENT_INVALID_STATE_TRANSITION", "사건 상태 전이를 수행할 수 없습니다.")
        if (
            dispatch is None or dispatch.incident_id != incident.incident_id
            or dispatch.dispatch_status != "ACTION_COMPLETED"
            or dispatch.action_completed_at is None
        ):
            raise _error(409, "INCIDENT_INVALID_STATE_TRANSITION", "완료된 출동 정보를 확인할 수 없습니다.")
        if (
            report is None or report.dispatch_request_id != dispatch.dispatch_request_id
            or report.action_completed_at is None
        ):
            raise _error(
                409, "INCIDENT_ACTION_REPORT_REQUIRED",
                "현장 조치 결과가 등록되지 않았습니다.",
            )

        before = (incident.incident_status, incident.version_no, incident.closed_at)
        incident.incident_status = "CLOSED"
        incident.version_no += 1
        incident.closed_at = now
        metadata = {
            "incident_public_id": incident.public_id,
            "dispatch_public_id": dispatch.public_id,
            "report_public_id": report.public_id,
            "closure_code": closure_code,
        }
        db.add(IncidentStatusHistory(
            public_id=str(uuid4()), incident_id=incident.incident_id,
            from_status="ACTION_COMPLETED", to_status="CLOSED", actor_type="USER",
            actor_user_id=actor_user_id, change_source="MANUAL",
            reason_code=closure_code, reason_text=note,
            idempotency_key=idempotency_key, changed_at=now, metadata_json=metadata,
        ))
        db.add(AuditLog(
            public_id=str(uuid4()), actor_type="USER", actor_user_id=actor_user_id,
            action_code="INCIDENT.CLOSE", resource_type="INCIDENT",
            resource_public_id=incident.public_id, result_status="SUCCESS",
            before_json={"public_id": incident.public_id, "status": before[0], "version_no": before[1]},
            after_json={"public_id": incident.public_id, "status": "CLOSED",
                        "version_no": incident.version_no, "closure_code": closure_code,
                        "dispatch_public_id": dispatch.public_id,
                        "report_public_id": report.public_id},
            trace_id=trace_id,
        ))
        actor = {"public_id": actor_public_id, "user_name": actor_name}
        event_id = str(uuid4())
        payload = {
            "event_id": event_id, "event_type": "INCIDENT.STATUS_CHANGED",
            "occurred_at": utc_z(now),
            "resource": {"resource_type": "INCIDENT", "resource_public_id": incident.public_id},
            "version_no": incident.version_no,
            "data": {"incident_no": incident.incident_no,
                     "previous_status": "ACTION_COMPLETED", "status": "CLOSED",
                     "closure_code": closure_code, "closed_by": actor,
                     "closed_at": utc_z(now), "changed_by": actor,
                     "changed_at": utc_z(now)},
            "notification": None, "trace_id": trace_id,
        }
        db.add(EventOutbox(
            event_uuid=event_id, aggregate_type="INCIDENT",
            aggregate_public_id=incident.public_id, event_type="INCIDENT.STATUS_CHANGED",
            payload_json=payload, publish_status="PENDING", retry_count=0,
            next_attempt_at=now,
        ))
        data = {
            "incident_public_id": incident.public_id,
            "previous_status": "ACTION_COMPLETED", "status": "CLOSED",
            "closure_code": closure_code, "closed_by": actor,
            "closed_at": utc_z(now), "version_no": incident.version_no,
        }
        idempotency.processing_status = "COMPLETED"
        idempotency.resource_type = "INCIDENT"
        idempotency.resource_public_id = incident.public_id
        idempotency.response_code = 200
        idempotency.response_snapshot_json = {"data": data, "message": MESSAGE}
        db.flush()
        db.commit()
        return CommandResult(data, MESSAGE)
    except Exception:
        db.rollback()
        if incident is not None and before is not None:
            incident.incident_status, incident.version_no, incident.closed_at = before
        raise
