import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.dependencies.auth import CurrentUser
from app.models.incident import (
    Incident,
    IncidentClaim,
    IncidentStateTransition,
    IncidentStatusHistory,
)
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services.query_common import utc_z

IDEMPOTENCY_RETENTION_HOURS = 24

Command = Literal["acknowledge", "claim", "review"]


@dataclass(frozen=True)
class CommandConfig:
    scope_code: str
    target_status: str
    reason_code: str
    action_code: str
    message: str


@dataclass(frozen=True)
class CommandResult:
    data: dict[str, Any]
    message: str


CONFIGS = {
    "acknowledge": CommandConfig(
        "INCIDENT_ACKNOWLEDGE",
        "ACKNOWLEDGED",
        "CONTROLLER_ACKNOWLEDGED",
        "INCIDENT.ACKNOWLEDGE",
        "사건을 확인했습니다.",
    ),
    "claim": CommandConfig(
        "INCIDENT_CLAIM",
        "CLAIMED",
        "CONTROLLER_CLAIMED",
        "INCIDENT.CLAIM",
        "사건을 선점했습니다.",
    ),
    "review": CommandConfig(
        "INCIDENT_REVIEW",
        "UNDER_REVIEW",
        "CONTROLLER_REVIEW_STARTED",
        "INCIDENT.REVIEW",
        "사건 검토를 시작했습니다.",
    ),
}


def canonical_request_hash(
    *,
    scope_code: str,
    actor_public_id: str,
    incident_public_id: str,
    expected_version_no: int,
) -> str:
    canonical = {
        "scope_code": scope_code,
        "actor_public_id": actor_public_id,
        "incident_public_id": incident_public_id,
        "body": {"expected_version_no": expected_version_no},
    }
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _error(status_code: int, code: str, message: str, details=None) -> AppException:
    return AppException(status_code, code, message, details)


def _existing_idempotency(
    db: Session, scope_code: str, idempotency_key: str
) -> IdempotencyKey | None:
    return db.scalars(
        select(IdempotencyKey)
        .where(
            IdempotencyKey.scope_code == scope_code,
            IdempotencyKey.idempotency_key == idempotency_key,
        )
        .with_for_update()
    ).first()


def _replay_or_reject(
    record: IdempotencyKey, request_hash: str
) -> CommandResult:
    if record.request_hash != request_hash:
        raise _error(
            409,
            "INCIDENT_IDEMPOTENCY_CONFLICT",
            "동일한 멱등 키에 다른 사건 요청이 전달되었습니다.",
        )
    if record.processing_status == "COMPLETED":
        snapshot = record.response_snapshot_json
        if not isinstance(snapshot, dict):
            raise _error(
                409,
                "INCIDENT_IDEMPOTENCY_CONFLICT",
                "동일한 멱등 키의 처리 결과를 재사용할 수 없습니다.",
            )
        return CommandResult(data=snapshot["data"], message=snapshot["message"])
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


def _validate_transition(db: Session, current_status: str, target_status: str) -> None:
    transition = db.scalars(
        select(IncidentStateTransition).where(
            IncidentStateTransition.from_status == current_status,
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
            {"current_status": current_status, "requested_status": target_status},
        )


def _active_claim(db: Session, incident_id: int) -> IncidentClaim | None:
    return db.scalars(
        select(IncidentClaim).where(
            IncidentClaim.incident_id == incident_id,
            IncidentClaim.released_at.is_(None),
        )
    ).first()


def _event_payload(
    *, incident: Incident, previous_status: str, actor: CurrentUser,
    changed_at: datetime, trace_id: str, event_id: str
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": "INCIDENT.STATUS_CHANGED",
        "occurred_at": utc_z(changed_at),
        "resource": {
            "resource_type": "INCIDENT",
            "resource_public_id": incident.public_id,
        },
        "version_no": incident.version_no,
        "data": {
            "incident_no": incident.incident_no,
            "previous_status": previous_status,
            "status": incident.incident_status,
            "changed_by": {
                "public_id": actor.user.public_id,
                "user_name": actor.user.user_name,
            },
            "changed_at": utc_z(changed_at),
        },
        "notification": None,
        "trace_id": trace_id,
    }


def _success_data(
    command: Command, incident: Incident, previous_status: str,
    actor: CurrentUser, changed_at: datetime
) -> dict[str, Any]:
    base = {
        "incident_public_id": incident.public_id,
        "previous_status": previous_status,
        "status": incident.incident_status,
        "version_no": incident.version_no,
    }
    if command == "acknowledge":
        base.update(
            acknowledged_by={
                "public_id": actor.user.public_id,
                "user_name": actor.user.user_name,
            },
            acknowledged_at=utc_z(changed_at),
        )
    elif command == "claim":
        base.update(
            claimed_by={
                "public_id": actor.user.public_id,
                "user_name": actor.user.user_name,
            },
            claimed_at=utc_z(changed_at),
        )
    else:
        base["review_started_at"] = utc_z(changed_at)
    return base


def execute_command(
    db: Session,
    *,
    command: Command,
    incident_public_id: str,
    expected_version_no: int,
    idempotency_key: str,
    current_user: CurrentUser,
    trace_id: str,
) -> CommandResult:
    config = CONFIGS[command]
    request_hash = canonical_request_hash(
        scope_code=config.scope_code,
        actor_public_id=current_user.user.public_id,
        incident_public_id=incident_public_id,
        expected_version_no=expected_version_no,
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    try:
        existing = _existing_idempotency(db, config.scope_code, idempotency_key)
        if existing is not None:
            return _replay_or_reject(existing, request_hash)

        idempotency = IdempotencyKey(
            scope_code=config.scope_code,
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
            concurrent = _existing_idempotency(
                db, config.scope_code, idempotency_key
            )
            if concurrent is None:
                raise
            return _replay_or_reject(concurrent, request_hash)

        incident = _lock_incident(db, incident_public_id)
        _validate_version(incident, expected_version_no)
        previous_status = incident.incident_status
        _validate_transition(db, previous_status, config.target_status)

        if command == "claim":
            if _active_claim(db, incident.incident_id) is not None:
                raise _error(
                    409,
                    "INCIDENT_ALREADY_CLAIMED",
                    "다른 관제자가 이미 선점한 사건입니다.",
                )
            claim = IncidentClaim(
                    public_id=str(uuid4()),
                    incident_id=incident.incident_id,
                    controller_user_id=current_user.user.user_id,
                    idempotency_key=idempotency_key,
                    claimed_at=now,
                    released_at=None,
                    release_reason=None,
                )
            db.add(claim)
            try:
                db.flush()
            except IntegrityError as exc:
                raise _error(
                    409,
                    "INCIDENT_ALREADY_CLAIMED",
                    "다른 관제자가 이미 선점한 사건입니다.",
                ) from exc
            incident.current_controller_user_id = current_user.user.user_id
            incident.claimed_at = now
        elif command == "review":
            if incident.current_controller_user_id != current_user.user.user_id:
                raise _error(
                    403,
                    "INCIDENT_NOT_ASSIGNED_CONTROLLER",
                    "해당 사건의 담당 관제자가 아닙니다.",
                )
        else:
            incident.acknowledged_by_user_id = current_user.user.user_id
            incident.acknowledged_at = now

        incident.incident_status = config.target_status
        incident.version_no += 1
        history = IncidentStatusHistory(
            public_id=str(uuid4()),
            incident_id=incident.incident_id,
            from_status=previous_status,
            to_status=config.target_status,
            actor_type="USER",
            actor_user_id=current_user.user.user_id,
            change_source="MANUAL",
            reason_code=config.reason_code,
            reason_text=None,
            idempotency_key=idempotency_key,
            changed_at=now,
        )
        db.add(history)
        db.add(
            AuditLog(
                public_id=str(uuid4()),
                actor_type="USER",
                actor_user_id=current_user.user.user_id,
                action_code=config.action_code,
                resource_type="INCIDENT",
                resource_public_id=incident.public_id,
                result_status="SUCCESS",
                before_json={"status": previous_status, "version_no": expected_version_no},
                after_json={"status": config.target_status, "version_no": incident.version_no},
                trace_id=trace_id,
            )
        )
        event_id = str(uuid4())
        db.add(
            EventOutbox(
                event_uuid=event_id,
                aggregate_type="INCIDENT",
                aggregate_public_id=incident.public_id,
                event_type="INCIDENT.STATUS_CHANGED",
                payload_json=_event_payload(
                    incident=incident,
                    previous_status=previous_status,
                    actor=current_user,
                    changed_at=now,
                    trace_id=trace_id,
                    event_id=event_id,
                ),
                publish_status="PENDING",
                retry_count=0,
                next_attempt_at=now,
            )
        )
        data = _success_data(command, incident, previous_status, current_user, now)
        idempotency.processing_status = "COMPLETED"
        idempotency.resource_type = "INCIDENT"
        idempotency.resource_public_id = incident.public_id
        idempotency.response_code = 200
        idempotency.response_snapshot_json = {"data": data, "message": config.message}
        db.flush()
        db.commit()
        return CommandResult(data=data, message=config.message)
    except Exception:
        db.rollback()
        raise
