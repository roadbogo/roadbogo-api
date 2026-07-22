import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.dependencies.auth import CurrentUser
from app.models.auth import ResponderProfile
from app.models.dispatch import (
    DispatchRequest,
    DispatchStateTransition,
    DispatchStatusHistory,
    FieldActionReport,
)
from app.models.incident import Incident, IncidentStateTransition, IncidentStatusHistory
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services.incident_command import CommandResult, IDEMPOTENCY_RETENTION_HOURS
from app.services.query_common import utc_z

SCOPE = "DISPATCH_COMPLETE_ACTION"
MESSAGE = "현장 조치를 완료했습니다."


def _error(status: int, code: str, message: str, details=None) -> AppException:
    return AppException(status, code, message, details)


def _request_hash(
    actor_public_id: str, dispatch_public_id: str, expected_version_no: int,
    action_type: str, action_detail: str,
) -> str:
    value = {
        "scope_code": SCOPE,
        "actor_public_id": actor_public_id,
        "dispatch_public_id": dispatch_public_id,
        "body": {
            "expected_version_no": expected_version_no,
            "action_type": action_type,
            "action_detail": action_detail,
        },
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _existing(db: Session, key: str):
    return db.scalars(
        select(IdempotencyKey).where(
            IdempotencyKey.scope_code == SCOPE,
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


def _envelope(event_type, resource_type, resource_id, version, data, now, trace_id):
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
    db: Session, *, dispatch_public_id: str, expected_version_no: int,
    action_type: str, action_detail: str, idempotency_key: str,
    current_user: CurrentUser, trace_id: str,
) -> CommandResult:
    actor_user_id = current_user.user.user_id
    actor_public_id = current_user.user.public_id
    actor_name = current_user.user.user_name
    dispatch_id = dispatch_public_id
    request_hash = _request_hash(
        actor_public_id, dispatch_id, expected_version_no, action_type, action_detail
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    dispatch = incident = profile = None
    dispatch_before = incident_before = profile_before = None
    try:
        existing = _existing(db, idempotency_key)
        if existing is not None:
            return _replay(existing, request_hash)
        idempotency = IdempotencyKey(
            scope_code=SCOPE, idempotency_key=idempotency_key,
            request_hash=request_hash, processing_status="PROCESSING",
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

        preview_incident_id = db.scalar(
            select(DispatchRequest.incident_id).where(
                DispatchRequest.public_id == dispatch_id,
                DispatchRequest.responder_user_id == actor_user_id,
            )
        )
        if preview_incident_id is None:
            raise _error(404, "DISPATCH_NOT_FOUND", "출동 요청 정보를 찾을 수 없습니다.")
        incident = db.scalars(
            select(Incident).where(Incident.incident_id == preview_incident_id).with_for_update()
        ).first()
        profile = db.scalars(
            select(ResponderProfile)
            .where(ResponderProfile.user_id == actor_user_id)
            .with_for_update()
        ).first()
        dispatch = db.scalars(
            select(DispatchRequest).where(
                DispatchRequest.public_id == dispatch_id,
                DispatchRequest.responder_user_id == actor_user_id,
            ).with_for_update()
        ).first()
        if (
            incident is None or profile is None or dispatch is None
            or dispatch.public_id != dispatch_id
            or dispatch.responder_user_id != actor_user_id
            or dispatch.incident_id != preview_incident_id
            or profile.user_id != actor_user_id
        ):
            raise _error(404, "DISPATCH_NOT_FOUND", "출동 요청 정보를 찾을 수 없습니다.")
        if dispatch.version_no != expected_version_no:
            raise _error(
                409, "DISPATCH_VERSION_CONFLICT", "출동 요청 정보가 변경되었습니다.",
                {"requested_version_no": expected_version_no, "current_version_no": dispatch.version_no},
            )
        if dispatch.dispatch_status != "ACTION_IN_PROGRESS" or dispatch.action_started_at is None:
            raise _error(
                409, "DISPATCH_INVALID_STATE_TRANSITION",
                "현재 출동 상태에서는 요청한 작업을 수행할 수 없습니다.",
                {"current_status": dispatch.dispatch_status, "requested_status": "ACTION_COMPLETED"},
            )
        if incident.incident_status != "ACTION_IN_PROGRESS":
            raise _error(
                409, "INCIDENT_INVALID_STATE_TRANSITION",
                "현재 사건 상태에서는 요청한 작업을 수행할 수 없습니다.",
                {"current_status": incident.incident_status, "requested_status": "ACTION_COMPLETED"},
            )
        if profile.duty_status != "BUSY":
            raise _error(409, "DISPATCH_RESPONDER_STATUS_CONFLICT", "출동 담당자 상태가 올바르지 않습니다.")
        dispatch_transition = db.scalars(
            select(DispatchStateTransition).where(
                DispatchStateTransition.from_status == "ACTION_IN_PROGRESS",
                DispatchStateTransition.to_status == "ACTION_COMPLETED",
                DispatchStateTransition.actor_scope == "RESPONDER",
                DispatchStateTransition.is_active == 1,
            )
        ).first()
        if dispatch_transition is None:
            raise _error(409, "DISPATCH_INVALID_STATE_TRANSITION", "출동 상태 전이를 수행할 수 없습니다.")
        incident_transition = db.scalars(
            select(IncidentStateTransition).where(
                IncidentStateTransition.from_status == "ACTION_IN_PROGRESS",
                IncidentStateTransition.to_status == "ACTION_COMPLETED",
                IncidentStateTransition.actor_scope == "SYSTEM",
                IncidentStateTransition.is_active == 1,
            )
        ).first()
        if incident_transition is None:
            raise _error(409, "INCIDENT_INVALID_STATE_TRANSITION", "사건 상태 전이를 수행할 수 없습니다.")
        if db.scalars(
            select(FieldActionReport).where(
                FieldActionReport.dispatch_request_id == dispatch.dispatch_request_id
            ).with_for_update()
        ).first() is not None:
            raise _error(409, "DISPATCH_ACTION_REPORT_ALREADY_EXISTS", "현장 조치 보고서가 이미 존재합니다.")
        if now < dispatch.action_started_at:
            raise _error(409, "DISPATCH_INVALID_STATE_TRANSITION", "조치 완료 시각이 올바르지 않습니다.")

        report = FieldActionReport(
            public_id=str(uuid4()), dispatch_request_id=dispatch.dispatch_request_id,
            action_type=action_type, action_detail=action_detail,
            created_by_user_id=actor_user_id, action_started_at=dispatch.action_started_at,
            action_completed_at=now,
        )
        db.add(report)
        dispatch_before = (
            dispatch.dispatch_status, dispatch.version_no,
            dispatch.status_change_method, dispatch.action_completed_at,
        )
        incident_before = (incident.incident_status, incident.version_no)
        profile_before = profile.duty_status
        dispatch.dispatch_status = "ACTION_COMPLETED"
        dispatch.version_no += 1
        dispatch.status_change_method = "MANUAL"
        dispatch.action_completed_at = now
        incident.incident_status = "ACTION_COMPLETED"
        incident.version_no += 1
        profile.duty_status = "AVAILABLE"

        metadata = {"dispatch_public_id": dispatch.public_id, "report_public_id": report.public_id}
        db.add(DispatchStatusHistory(
            public_id=str(uuid4()), dispatch_request_id=dispatch.dispatch_request_id,
            from_status="ACTION_IN_PROGRESS", to_status="ACTION_COMPLETED",
            actor_type="USER", actor_user_id=actor_user_id, change_method="MANUAL",
            idempotency_key=idempotency_key, changed_at=now, metadata_json=metadata,
        ))
        db.add(IncidentStatusHistory(
            public_id=str(uuid4()), incident_id=incident.incident_id,
            from_status="ACTION_IN_PROGRESS", to_status="ACTION_COMPLETED",
            actor_type="SYSTEM", actor_user_id=actor_user_id, change_source="AUTO",
            reason_code="RESPONDER_ACTION_COMPLETED", idempotency_key=idempotency_key,
            changed_at=now, metadata_json=metadata,
        ))
        db.add(AuditLog(
            public_id=str(uuid4()), actor_type="USER", actor_user_id=actor_user_id,
            action_code="DISPATCH.COMPLETE_ACTION", resource_type="DISPATCH",
            resource_public_id=dispatch.public_id, result_status="SUCCESS",
            before_json={"public_id": dispatch.public_id, "status": "ACTION_IN_PROGRESS",
                         "version_no": dispatch_before[1]},
            after_json={"public_id": dispatch.public_id, "status": "ACTION_COMPLETED",
                        "version_no": dispatch.version_no, "report_public_id": report.public_id},
            trace_id=trace_id,
        ))
        changed_by = {"public_id": actor_public_id, "user_name": actor_name}
        dispatch_event_id, dispatch_payload = _envelope(
            "DISPATCH.ACTION_COMPLETED", "DISPATCH", dispatch.public_id, dispatch.version_no,
            {"dispatch_public_id": dispatch.public_id, "incident_public_id": incident.public_id,
             "previous_status": "ACTION_IN_PROGRESS", "status": "ACTION_COMPLETED",
             "report_public_id": report.public_id, "changed_by": changed_by,
             "changed_at": utc_z(now)}, now, trace_id,
        )
        incident_event_id, incident_payload = _envelope(
            "INCIDENT.STATUS_CHANGED", "INCIDENT", incident.public_id, incident.version_no,
            {"incident_no": incident.incident_no, "previous_status": "ACTION_IN_PROGRESS",
             "status": "ACTION_COMPLETED", "changed_by": changed_by,
             "changed_at": utc_z(now)}, now, trace_id,
        )
        for event_id, aggregate, aggregate_id, event_type, payload in (
            (dispatch_event_id, "DISPATCH", dispatch.public_id, "DISPATCH.ACTION_COMPLETED", dispatch_payload),
            (incident_event_id, "INCIDENT", incident.public_id, "INCIDENT.STATUS_CHANGED", incident_payload),
        ):
            db.add(EventOutbox(
                event_uuid=event_id, aggregate_type=aggregate,
                aggregate_public_id=aggregate_id, event_type=event_type,
                payload_json=payload, publish_status="PENDING", retry_count=0,
                next_attempt_at=now,
            ))
        data = {
            "dispatch": {"public_id": dispatch.public_id, "previous_status": "ACTION_IN_PROGRESS",
                         "status": "ACTION_COMPLETED", "action_completed_at": utc_z(now),
                         "version_no": dispatch.version_no},
            "incident": {"public_id": incident.public_id, "previous_status": "ACTION_IN_PROGRESS",
                         "status": "ACTION_COMPLETED", "version_no": incident.version_no},
            "responder": {"public_id": actor_public_id, "duty_status": "AVAILABLE"},
            "report": {"public_id": report.public_id, "action_type": report.action_type,
                       "action_detail": report.action_detail,
                       "action_started_at": utc_z(report.action_started_at),
                       "action_completed_at": utc_z(now)},
        }
        idempotency.processing_status = "COMPLETED"
        idempotency.resource_type = "DISPATCH"
        idempotency.resource_public_id = dispatch.public_id
        idempotency.response_code = 200
        idempotency.response_snapshot_json = {"data": data, "message": MESSAGE}
        db.flush()
        db.commit()
        return CommandResult(data, MESSAGE)
    except Exception:
        db.rollback()
        if dispatch is not None and dispatch_before is not None:
            (dispatch.dispatch_status, dispatch.version_no,
             dispatch.status_change_method, dispatch.action_completed_at) = dispatch_before
        if incident is not None and incident_before is not None:
            incident.incident_status, incident.version_no = incident_before
        if profile is not None and profile_before is not None:
            profile.duty_status = profile_before
        raise
