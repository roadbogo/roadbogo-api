import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.dependencies.auth import CurrentUser
from app.models.incident import (
    Incident,
    IncidentDecision,
    IncidentStateTransition,
    IncidentStatusHistory,
)
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.schemas.incident_decision import DecisionType
from app.services.incident_command import CommandResult, IDEMPOTENCY_RETENTION_HOURS
from app.services.query_common import utc_z

SCOPE_CODE = "INCIDENT_DECISION"
SUCCESS_MESSAGE = "사건 판정을 저장했습니다."

DECISION_TARGETS: dict[str, tuple[str, str | None]] = {
    "REAL_RISK": ("DISPATCH_REQUESTED", "CONTROLLER_REAL_RISK_DECIDED"),
    "FALSE_POSITIVE": ("FALSE_POSITIVE", "CONTROLLER_FALSE_POSITIVE_DECIDED"),
    "NEEDS_REVIEW": ("UNDER_REVIEW", None),
    "NO_DISPATCH": ("CLOSED", "CONTROLLER_NO_DISPATCH_DECIDED"),
}


def canonical_request_hash(
    *, actor_public_id: str, incident_public_id: str, decision_type: str,
    decision_reason: str, expected_version_no: int
) -> str:
    canonical = {
        "scope_code": SCOPE_CODE,
        "actor_public_id": actor_public_id,
        "incident_public_id": incident_public_id,
        "body": {
            "decision_type": decision_type,
            "decision_reason": decision_reason,
            "expected_version_no": expected_version_no,
        },
    }
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _error(status_code: int, code: str, message: str, details=None) -> AppException:
    return AppException(status_code, code, message, details)


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
            409,
            "INCIDENT_IDEMPOTENCY_CONFLICT",
            "동일한 멱등 키에 다른 사건 요청이 전달되었습니다.",
        )
    if record.processing_status == "COMPLETED":
        snapshot = record.response_snapshot_json
        if isinstance(snapshot, dict):
            return CommandResult(snapshot["data"], snapshot["message"])
    raise _error(
        409,
        "INCIDENT_IDEMPOTENCY_CONFLICT",
        "동일한 멱등 키의 요청이 처리 중입니다.",
        {"processing_status": record.processing_status},
    )


def _lock_incident(db: Session, public_id: str) -> Incident:
    incident = db.scalars(
        select(Incident).where(Incident.public_id == public_id).with_for_update()
    ).first()
    if incident is None:
        raise _error(404, "INCIDENT_NOT_FOUND", "사건 정보를 찾을 수 없습니다.")
    return incident


def _validate_version(incident: Incident, expected_version_no: int) -> None:
    if incident.version_no != expected_version_no:
        raise _error(
            409,
            "INCIDENT_VERSION_CONFLICT",
            "사건 정보가 변경되었습니다. 최신 정보를 다시 확인해 주세요.",
            {
                "requested_version_no": expected_version_no,
                "current_version_no": incident.version_no,
            },
        )


def _validate_under_review(incident: Incident, target_status: str) -> None:
    if incident.incident_status != "UNDER_REVIEW":
        raise _error(
            409,
            "INCIDENT_INVALID_STATE_TRANSITION",
            "현재 사건 상태에서는 요청한 작업을 수행할 수 없습니다.",
            {
                "current_status": incident.incident_status,
                "requested_status": target_status,
            },
        )


def _validate_controller(incident: Incident, current_user: CurrentUser) -> None:
    if incident.current_controller_user_id != current_user.user.user_id:
        raise _error(
            403,
            "INCIDENT_NOT_ASSIGNED_CONTROLLER",
            "해당 사건의 담당 관제자가 아닙니다.",
        )


def _validate_transition(db: Session, target_status: str) -> None:
    transition = db.scalars(
        select(IncidentStateTransition).where(
            IncidentStateTransition.from_status == "UNDER_REVIEW",
            IncidentStateTransition.to_status == target_status,
            IncidentStateTransition.actor_scope == "CONTROLLER",
            IncidentStateTransition.is_active == 1,
        )
    ).first()
    if transition is None:
        raise _error(
            409,
            "INCIDENT_INVALID_STATE_TRANSITION",
            "현재 사건 상태에서는 요청한 작업을 수행할 수 없습니다.",
            {"current_status": "UNDER_REVIEW", "requested_status": target_status},
        )


def _active_decision(db: Session, incident_id: int) -> IncidentDecision | None:
    return db.scalars(
        select(IncidentDecision)
        .where(
            IncidentDecision.incident_id == incident_id,
            IncidentDecision.superseded_at.is_(None),
        )
        .with_for_update()
    ).first()


def _result_data(
    *, incident: Incident, previous_status: str, decision: IncidentDecision,
    current_user: CurrentUser, now: datetime
) -> dict[str, Any]:
    return {
        "incident_public_id": incident.public_id,
        "previous_status": previous_status,
        "status": incident.incident_status,
        "decision": {
            "public_id": decision.public_id,
            "decision_type": decision.decision_type,
            "decision_reason": decision.decision_reason,
            "decided_by": {
                "public_id": current_user.user.public_id,
                "user_name": current_user.user.user_name,
            },
            "decided_at": utc_z(now),
        },
        "version_no": incident.version_no,
    }


def _event_payload(
    *, event_id: str, event_type: str, incident: Incident,
    previous_status: str, decision: IncidentDecision,
    current_user: CurrentUser, now: datetime, trace_id: str
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": utc_z(now),
        "resource": {
            "resource_type": "INCIDENT",
            "resource_public_id": incident.public_id,
        },
        "incident_no": incident.incident_no,
        "previous_status": previous_status,
        "status": incident.incident_status,
        "version_no": incident.version_no,
        "decision": {
            "public_id": decision.public_id,
            "decision_type": decision.decision_type,
            "decision_reason": decision.decision_reason,
            "decided_by": {
                "public_id": current_user.user.public_id,
                "user_name": current_user.user.user_name,
            },
        },
        "trace_id": trace_id,
    }


def decide_incident(
    db: Session,
    *,
    incident_public_id: str,
    decision_type: DecisionType,
    decision_reason: str,
    expected_version_no: int,
    idempotency_key: str,
    current_user: CurrentUser,
    trace_id: str,
) -> CommandResult:
    target_status, reason_code = DECISION_TARGETS[decision_type]
    request_hash = canonical_request_hash(
        actor_public_id=current_user.user.public_id,
        incident_public_id=incident_public_id,
        decision_type=decision_type,
        decision_reason=decision_reason,
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
        _validate_version(incident, expected_version_no)
        _validate_under_review(incident, target_status)
        _validate_controller(incident, current_user)
        if decision_type != "NEEDS_REVIEW":
            _validate_transition(db, target_status)

        previous_status = incident.incident_status
        previous_version = incident.version_no
        active = _active_decision(db, incident.incident_id)
        active_public_id = active.public_id if active else None
        if active is not None:
            active.superseded_at = now
            db.flush()

        decision = IncidentDecision(
            public_id=str(uuid4()),
            incident_id=incident.incident_id,
            decision_type=decision_type,
            decision_reason=decision_reason,
            decided_by_user_id=current_user.user.user_id,
            idempotency_key=idempotency_key,
            decided_at=now,
            superseded_at=None,
            superseded_by_decision_id=None,
        )
        db.add(decision)
        db.flush()
        if active is not None:
            active.superseded_by_decision_id = decision.incident_decision_id

        incident.incident_status = target_status
        incident.version_no += 1
        if decision_type in ("FALSE_POSITIVE", "NO_DISPATCH"):
            incident.closed_at = now

        if reason_code is not None:
            db.add(
                IncidentStatusHistory(
                    public_id=str(uuid4()),
                    incident_id=incident.incident_id,
                    from_status=previous_status,
                    to_status=target_status,
                    actor_type="USER",
                    actor_user_id=current_user.user.user_id,
                    change_source="MANUAL",
                    reason_code=reason_code,
                    reason_text=decision_reason,
                    idempotency_key=idempotency_key,
                    changed_at=now,
                )
            )

        db.add(
            AuditLog(
                public_id=str(uuid4()),
                actor_type="USER",
                actor_user_id=current_user.user.user_id,
                action_code="INCIDENT.DECIDE",
                resource_type="INCIDENT",
                resource_public_id=incident.public_id,
                result_status="SUCCESS",
                before_json={
                    "status": previous_status,
                    "version_no": previous_version,
                    "active_decision_public_id": active_public_id,
                },
                after_json={
                    "status": target_status,
                    "version_no": incident.version_no,
                    "decision_public_id": decision.public_id,
                    "decision_type": decision_type,
                },
                trace_id=trace_id,
            )
        )
        event_type = (
            "INCIDENT.DECISION_RECORDED"
            if decision_type == "NEEDS_REVIEW"
            else "INCIDENT.STATUS_CHANGED"
        )
        event_id = str(uuid4())
        db.add(
            EventOutbox(
                event_uuid=event_id,
                aggregate_type="INCIDENT",
                aggregate_public_id=incident.public_id,
                event_type=event_type,
                payload_json=_event_payload(
                    event_id=event_id,
                    event_type=event_type,
                    incident=incident,
                    previous_status=previous_status,
                    decision=decision,
                    current_user=current_user,
                    now=now,
                    trace_id=trace_id,
                ),
                publish_status="PENDING",
                retry_count=0,
                next_attempt_at=now,
            )
        )
        data = _result_data(
            incident=incident,
            previous_status=previous_status,
            decision=decision,
            current_user=current_user,
            now=now,
        )
        idempotency.processing_status = "COMPLETED"
        idempotency.resource_type = "INCIDENT"
        idempotency.resource_public_id = incident.public_id
        idempotency.response_code = 200
        idempotency.response_snapshot_json = {
            "data": data,
            "message": SUCCESS_MESSAGE,
        }
        db.flush()
        db.commit()
        return CommandResult(data=data, message=SUCCESS_MESSAGE)
    except Exception:
        db.rollback()
        raise
