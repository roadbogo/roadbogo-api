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
from app.models.dispatch import DispatchRequest, DispatchStateTransition, DispatchStatusHistory
from app.models.incident import Incident, IncidentStateTransition, IncidentStatusHistory
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services.incident_command import CommandResult, IDEMPOTENCY_RETENTION_HOURS
from app.services.query_common import utc_z

MESSAGES = {
    "accept": "출동 요청을 수락했습니다.",
    "reject": "출동 요청을 거절했습니다.",
}


def _error(status: int, code: str, message: str, details=None) -> AppException:
    return AppException(status, code, message, details)


def canonical_request_hash(
    *, command: str, actor_public_id: str, dispatch_public_id: str,
    expected_version_no: int, rejection_reason: str | None,
) -> tuple[str, str]:
    scope = "DISPATCH_ACCEPT" if command == "accept" else "DISPATCH_REJECT"
    body = {"expected_version_no": expected_version_no}
    if command == "reject":
        body["rejection_reason"] = rejection_reason
    value = {
        "scope_code": scope,
        "actor_public_id": actor_public_id,
        "dispatch_public_id": dispatch_public_id,
        "body": body,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return scope, hashlib.sha256(encoded).hexdigest()


def _existing(db: Session, scope: str, key: str):
    return db.scalars(
        select(IdempotencyKey).where(
            IdempotencyKey.scope_code == scope,
            IdempotencyKey.idempotency_key == key,
        ).with_for_update()
    ).first()


def _replay(record, request_hash: str) -> CommandResult:
    if record.request_hash != request_hash or record.processing_status != "COMPLETED":
        raise _error(
            409, "DISPATCH_IDEMPOTENCY_CONFLICT",
            "동일한 멱등 키의 출동 요청을 재사용할 수 없습니다.",
            {"processing_status": record.processing_status},
        )
    snapshot = record.response_snapshot_json
    if not isinstance(snapshot, dict):
        raise _error(409, "DISPATCH_IDEMPOTENCY_CONFLICT", "처리 결과를 재사용할 수 없습니다.")
    return CommandResult(snapshot["data"], snapshot["message"])


def _transition(db: Session, current: str, target: str) -> None:
    found = db.scalars(
        select(DispatchStateTransition).where(
            DispatchStateTransition.from_status == current,
            DispatchStateTransition.to_status == target,
            DispatchStateTransition.actor_scope == "RESPONDER",
            DispatchStateTransition.is_active == 1,
        )
    ).first()
    if found is None:
        raise _error(
            409, "DISPATCH_INVALID_STATE_TRANSITION",
            "현재 출동 상태에서는 요청한 작업을 수행할 수 없습니다.",
            {"current_status": current, "requested_status": target},
        )


def _incident_transition(db: Session, current: str) -> None:
    found = db.scalars(
        select(IncidentStateTransition).where(
            IncidentStateTransition.from_status == current,
            IncidentStateTransition.to_status == "DISPATCHED",
            IncidentStateTransition.actor_scope == "SYSTEM",
            IncidentStateTransition.is_active == 1,
        )
    ).first()
    if found is None:
        raise _error(
            409, "INCIDENT_INVALID_STATE_TRANSITION",
            "현재 사건 상태에서는 요청한 작업을 수행할 수 없습니다.",
            {"current_status": current, "requested_status": "DISPATCHED"},
        )


def _envelope(
    *, event_type: str, resource_type: str, resource_public_id: str,
    version_no: int, data: dict, now: datetime, trace_id: str,
) -> tuple[str, dict]:
    event_id = str(uuid4())
    return event_id, {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": utc_z(now),
        "resource": {
            "resource_type": resource_type,
            "resource_public_id": resource_public_id,
        },
        "version_no": version_no,
        "data": data,
        "notification": None,
        "trace_id": trace_id,
    }


def execute(
    db: Session, *, command: str, dispatch_public_id: str,
    expected_version_no: int, rejection_reason: str | None,
    idempotency_key: str, current_user: CurrentUser, trace_id: str,
) -> CommandResult:
    scope, request_hash = canonical_request_hash(
        command=command,
        actor_public_id=current_user.user.public_id,
        dispatch_public_id=dispatch_public_id,
        expected_version_no=expected_version_no,
        rejection_reason=rejection_reason,
    )
    target = "ACCEPTED" if command == "accept" else "REJECTED"
    now = datetime.now(UTC).replace(tzinfo=None)
    try:
        existing = _existing(db, scope, idempotency_key)
        if existing is not None:
            return _replay(existing, request_hash)
        idempotency = IdempotencyKey(
            scope_code=scope,
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
            concurrent = _existing(db, scope, idempotency_key)
            if concurrent is None:
                raise
            return _replay(concurrent, request_hash)

        dispatch = db.scalars(
            select(DispatchRequest).where(
                DispatchRequest.public_id == dispatch_public_id,
                DispatchRequest.responder_user_id == current_user.user.user_id,
            ).with_for_update()
        ).first()
        if dispatch is None:
            raise _error(404, "DISPATCH_NOT_FOUND", "출동 요청 정보를 찾을 수 없습니다.")
        if dispatch.version_no != expected_version_no:
            raise _error(
                409, "DISPATCH_VERSION_CONFLICT", "출동 요청 정보가 변경되었습니다.",
                {
                    "requested_version_no": expected_version_no,
                    "current_version_no": dispatch.version_no,
                },
            )
        if dispatch.dispatch_status != "REQUESTED":
            raise _error(
                409, "DISPATCH_INVALID_STATE_TRANSITION",
                "현재 출동 상태에서는 요청한 작업을 수행할 수 없습니다.",
                {"current_status": dispatch.dispatch_status, "requested_status": target},
            )
        _transition(db, "REQUESTED", target)
        responder_profile = None
        if command == "reject":
            responder_profile = db.scalars(
                select(ResponderProfile)
                .where(ResponderProfile.user_id == current_user.user.user_id)
                .with_for_update()
            ).first()
            if responder_profile is None:
                raise _error(404, "DISPATCH_NOT_FOUND", "출동 요청 정보를 찾을 수 없습니다.")
        incident = db.scalars(
            select(Incident).where(Incident.incident_id == dispatch.incident_id).with_for_update()
        ).first()
        if incident is None:
            raise _error(409, "INCIDENT_INVALID_STATE_TRANSITION", "연결된 사건을 처리할 수 없습니다.")

        previous_dispatch_version = dispatch.version_no
        previous_incident_status = incident.incident_status
        if command == "accept":
            if incident.incident_status != "DISPATCH_REQUESTED":
                raise _error(
                    409, "INCIDENT_INVALID_STATE_TRANSITION",
                    "현재 사건 상태에서는 요청한 작업을 수행할 수 없습니다.",
                    {"current_status": incident.incident_status, "requested_status": "DISPATCHED"},
                )
            _incident_transition(db, incident.incident_status)

        dispatch.dispatch_status = target
        dispatch.version_no += 1
        dispatch.status_change_method = "MANUAL"
        if command == "accept":
            dispatch.accepted_at = now
            incident.incident_status = "DISPATCHED"
        else:
            dispatch.rejection_reason = rejection_reason
            responder_profile.duty_status = "AVAILABLE"
        incident.version_no += 1

        db.add(DispatchStatusHistory(
            public_id=str(uuid4()), dispatch_request_id=dispatch.dispatch_request_id,
            from_status="REQUESTED", to_status=target, actor_type="USER",
            actor_user_id=current_user.user.user_id, change_method="MANUAL",
            reason_text=rejection_reason, idempotency_key=idempotency_key, changed_at=now,
            metadata_json={"dispatch_public_id": dispatch.public_id},
        ))
        if command == "accept":
            db.add(IncidentStatusHistory(
                public_id=str(uuid4()), incident_id=incident.incident_id,
                from_status=previous_incident_status, to_status="DISPATCHED",
                actor_type="SYSTEM", actor_user_id=current_user.user.user_id,
                change_source="AUTO", reason_code="RESPONDER_DISPATCH_ACCEPTED",
                idempotency_key=idempotency_key, changed_at=now,
                metadata_json={"dispatch_public_id": dispatch.public_id},
            ))
        db.add(AuditLog(
            public_id=str(uuid4()), actor_type="USER",
            actor_user_id=current_user.user.user_id,
            action_code="DISPATCH.ACCEPT" if command == "accept" else "DISPATCH.REJECT",
            resource_type="DISPATCH", resource_public_id=dispatch.public_id,
            result_status="SUCCESS",
            before_json={
                "public_id": dispatch.public_id,
                "status": "REQUESTED",
                "version_no": previous_dispatch_version,
            },
            after_json={
                "public_id": dispatch.public_id,
                "status": target,
                "version_no": dispatch.version_no,
            },
            reason_text=rejection_reason, trace_id=trace_id,
        ))
        dispatch_data = {
            "dispatch_public_id": dispatch.public_id,
            "incident_public_id": incident.public_id,
            "previous_status": "REQUESTED",
            "status": target,
            "changed_by": {
                "public_id": current_user.user.public_id,
                "user_name": current_user.user.user_name,
            },
            "changed_at": utc_z(now),
        }
        if command == "reject":
            dispatch_data["rejection_reason"] = rejection_reason
        event_type = "DISPATCH.ACCEPTED" if command == "accept" else "DISPATCH.REJECTED"
        event_id, payload = _envelope(
            event_type=event_type, resource_type="DISPATCH",
            resource_public_id=dispatch.public_id, version_no=dispatch.version_no,
            data=dispatch_data, now=now, trace_id=trace_id,
        )
        db.add(EventOutbox(
            event_uuid=event_id, aggregate_type="DISPATCH",
            aggregate_public_id=dispatch.public_id, event_type=event_type,
            payload_json=payload, publish_status="PENDING", retry_count=0,
            next_attempt_at=now,
        ))
        if command == "accept":
            incident_event_id, incident_payload = _envelope(
                event_type="INCIDENT.STATUS_CHANGED", resource_type="INCIDENT",
                resource_public_id=incident.public_id, version_no=incident.version_no,
                data={
                    "incident_no": incident.incident_no,
                    "previous_status": previous_incident_status,
                    "status": incident.incident_status,
                    "changed_by": {
                        "public_id": current_user.user.public_id,
                        "user_name": current_user.user.user_name,
                    },
                    "changed_at": utc_z(now),
                },
                now=now, trace_id=trace_id,
            )
            db.add(EventOutbox(
                event_uuid=incident_event_id, aggregate_type="INCIDENT",
                aggregate_public_id=incident.public_id,
                event_type="INCIDENT.STATUS_CHANGED", payload_json=incident_payload,
                publish_status="PENDING", retry_count=0, next_attempt_at=now,
            ))

        data = {
            "dispatch": {
                "public_id": dispatch.public_id,
                "previous_status": "REQUESTED",
                "status": target,
                "accepted_at": utc_z(now) if command == "accept" else None,
                "rejection_reason": rejection_reason,
                "version_no": dispatch.version_no,
            },
            "incident": {
                "public_id": incident.public_id,
                "previous_status": previous_incident_status if command == "accept" else None,
                "status": incident.incident_status,
                "version_no": incident.version_no,
            },
            "responder": (
                {"public_id": current_user.user.public_id, "duty_status": "AVAILABLE"}
                if command == "reject" else None
            ),
        }
        idempotency.processing_status = "COMPLETED"
        idempotency.resource_type = "DISPATCH"
        idempotency.resource_public_id = dispatch.public_id
        idempotency.response_code = 200
        idempotency.response_snapshot_json = {"data": data, "message": MESSAGES[command]}
        db.flush()
        db.commit()
        return CommandResult(data, MESSAGES[command])
    except Exception:
        db.rollback()
        raise
