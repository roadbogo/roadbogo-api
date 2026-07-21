from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.models.incident import IncidentDecision, IncidentStatusHistory
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services import incident_decision


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class FakeSession:
    def __init__(
        self, values, *, fail_flush_at=None, fail_add_model=None,
        commit_error=None
    ):
        self.values = list(values)
        self.fail_flush_at = fail_flush_at
        self.fail_add_model = fail_add_model
        self.commit_error = commit_error
        self.statements = []
        self.added = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    def scalars(self, statement):
        self.statements.append(statement)
        return ScalarResult(self.values.pop(0))

    def add(self, value):
        if self.fail_add_model and isinstance(value, self.fail_add_model):
            raise RuntimeError(f"{self.fail_add_model.__name__} add failed")
        self.added.append(value)

    def flush(self):
        self.flush_count += 1
        if self.flush_count == self.fail_flush_at:
            raise RuntimeError("flush failed")
        for value in self.added:
            if isinstance(value, IncidentDecision) and value.incident_decision_id is None:
                value.incident_decision_id = 501

    def commit(self):
        self.commit_count += 1
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollback_count += 1


def _user(user_id=7):
    return SimpleNamespace(
        user=SimpleNamespace(
            user_id=user_id, public_id=str(uuid4()), user_name="관제자"
        ),
        summary=SimpleNamespace(permissions=[]),
    )


def _incident(status="UNDER_REVIEW", version=3, controller_id=7):
    return SimpleNamespace(
        incident_id=31,
        public_id=str(uuid4()),
        incident_no="INC-1",
        incident_status=status,
        version_no=version,
        current_controller_user_id=controller_id,
        claimed_at=object(),
        closed_at=None,
    )


def _active_decision():
    return SimpleNamespace(
        incident_decision_id=400,
        public_id=str(uuid4()),
        superseded_at=None,
        superseded_by_decision_id=None,
    )


def _execute(decision_type, *, incident=None, active=None, reason="판정 사유"):
    incident = incident or _incident()
    values = [None, incident]
    if decision_type != "NEEDS_REVIEW":
        values.append(object())
    values.append(active)
    db = FakeSession(values)
    result = incident_decision.decide_incident(
        db,
        incident_public_id=incident.public_id,
        decision_type=decision_type,
        decision_reason=reason,
        expected_version_no=incident.version_no,
        idempotency_key=str(uuid4()),
        current_user=_user(incident.current_controller_user_id),
        trace_id=str(uuid4()),
    )
    return db, incident, result


def _added(db, model):
    return [value for value in db.added if isinstance(value, model)]


@pytest.mark.parametrize(
    ("decision_type", "status", "reason_code", "closed"),
    [
        ("REAL_RISK", "DISPATCH_REQUESTED", "CONTROLLER_REAL_RISK_DECIDED", False),
        ("FALSE_POSITIVE", "FALSE_POSITIVE", "CONTROLLER_FALSE_POSITIVE_DECIDED", True),
        ("NO_DISPATCH", "CLOSED", "CONTROLLER_NO_DISPATCH_DECIDED", True),
    ],
)
def test_state_changing_decisions_create_history(
    decision_type, status, reason_code, closed
) -> None:
    incident = _incident()
    claimed_at = incident.claimed_at
    controller_id = incident.current_controller_user_id
    db, incident, result = _execute(decision_type, incident=incident)

    assert incident.incident_status == status
    assert incident.version_no == 4
    assert (incident.closed_at is not None) is closed
    assert incident.claimed_at is claimed_at
    assert incident.current_controller_user_id == controller_id
    decision = _added(db, IncidentDecision)[0]
    assert decision.decision_type == decision_type
    history = _added(db, IncidentStatusHistory)[0]
    assert history.reason_code == reason_code
    assert history.reason_text == "판정 사유"
    outbox = _added(db, EventOutbox)[0]
    assert outbox.event_type == "INCIDENT.STATUS_CHANGED"
    assert result.data["decision"]["public_id"] == decision.public_id
    idempotency = _added(db, IdempotencyKey)[0]
    assert idempotency.processing_status == "COMPLETED"
    assert idempotency.response_snapshot_json["data"] == result.data
    assert db.commit_count == 1


def test_needs_review_keeps_status_without_history() -> None:
    db, incident, result = _execute("NEEDS_REVIEW")

    assert incident.incident_status == "UNDER_REVIEW"
    assert incident.version_no == 4
    assert incident.closed_at is None
    assert _added(db, IncidentStatusHistory) == []
    assert len(_added(db, IncidentDecision)) == 1
    assert _added(db, EventOutbox)[0].event_type == "INCIDENT.DECISION_RECORDED"
    assert result.data["status"] == "UNDER_REVIEW"


def test_existing_decision_is_superseded_and_linked() -> None:
    active = _active_decision()
    db, _, _ = _execute("REAL_RISK", active=active)

    new_decision = _added(db, IncidentDecision)[0]
    assert active.superseded_at is not None
    assert active.superseded_by_decision_id == new_decision.incident_decision_id
    assert new_decision.superseded_at is None
    assert db.flush_count >= 4


def test_audit_and_outbox_expose_only_public_identifiers() -> None:
    db, _, _ = _execute("REAL_RISK", active=_active_decision())

    audit = _added(db, AuditLog)[0]
    assert audit.action_code == "INCIDENT.DECIDE"
    assert audit.before_json["active_decision_public_id"] is not None
    assert audit.after_json["decision_public_id"] is not None
    outbox = _added(db, EventOutbox)[0]
    assert outbox.aggregate_type == "INCIDENT"
    assert outbox.publish_status == "PENDING"
    payload = repr(outbox.payload_json)
    assert "incident_id" not in payload
    assert "user_id" not in payload
    assert "actor_user_id" not in payload


def test_missing_incident() -> None:
    db = FakeSession([None, None])

    with pytest.raises(AppException) as error:
        incident_decision.decide_incident(
            db, incident_public_id=str(uuid4()), decision_type="REAL_RISK",
            decision_reason="사유", expected_version_no=3,
            idempotency_key=str(uuid4()), current_user=_user(), trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_NOT_FOUND"
    assert db.rollback_count == 1


def test_version_conflict() -> None:
    incident = _incident(version=4)
    db = FakeSession([None, incident])

    with pytest.raises(AppException) as error:
        incident_decision.decide_incident(
            db, incident_public_id=incident.public_id, decision_type="REAL_RISK",
            decision_reason="사유", expected_version_no=3,
            idempotency_key=str(uuid4()), current_user=_user(), trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_VERSION_CONFLICT"
    assert error.value.details["current_version_no"] == 4


def test_non_under_review_status_is_rejected() -> None:
    incident = _incident(status="CLAIMED")
    db = FakeSession([None, incident])

    with pytest.raises(AppException) as error:
        incident_decision.decide_incident(
            db, incident_public_id=incident.public_id, decision_type="NEEDS_REVIEW",
            decision_reason="사유", expected_version_no=3,
            idempotency_key=str(uuid4()), current_user=_user(), trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_INVALID_STATE_TRANSITION"
    assert error.value.details["requested_status"] == "UNDER_REVIEW"


def test_other_controller_is_rejected() -> None:
    incident = _incident(controller_id=99)
    db = FakeSession([None, incident])

    with pytest.raises(AppException) as error:
        incident_decision.decide_incident(
            db, incident_public_id=incident.public_id, decision_type="NEEDS_REVIEW",
            decision_reason="사유", expected_version_no=3,
            idempotency_key=str(uuid4()), current_user=_user(7), trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_NOT_ASSIGNED_CONTROLLER"


def test_missing_transition_is_rejected() -> None:
    incident = _incident()
    db = FakeSession([None, incident, None])

    with pytest.raises(AppException) as error:
        incident_decision.decide_incident(
            db, incident_public_id=incident.public_id, decision_type="REAL_RISK",
            decision_reason="사유", expected_version_no=3,
            idempotency_key=str(uuid4()), current_user=_user(), trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_INVALID_STATE_TRANSITION"


def test_completed_idempotency_replays_without_writes() -> None:
    user = _user()
    public_id = str(uuid4())
    request_hash = incident_decision.canonical_request_hash(
        actor_public_id=user.user.public_id, incident_public_id=public_id,
        decision_type="REAL_RISK", decision_reason="사유", expected_version_no=3
    )
    snapshot = {"data": {"version_no": 4}, "message": "저장"}
    record = SimpleNamespace(
        request_hash=request_hash, processing_status="COMPLETED",
        response_snapshot_json=snapshot
    )
    db = FakeSession([record])

    result = incident_decision.decide_incident(
        db, incident_public_id=public_id, decision_type="REAL_RISK",
        decision_reason="사유", expected_version_no=3,
        idempotency_key=str(uuid4()), current_user=user, trace_id=str(uuid4())
    )

    assert result.data == snapshot["data"]
    assert db.added == []


@pytest.mark.parametrize("status", ["PROCESSING", "FAILED"])
def test_incomplete_idempotency_is_conflict(status) -> None:
    user = _user()
    public_id = str(uuid4())
    request_hash = incident_decision.canonical_request_hash(
        actor_public_id=user.user.public_id, incident_public_id=public_id,
        decision_type="NEEDS_REVIEW", decision_reason="사유", expected_version_no=3
    )
    record = SimpleNamespace(
        request_hash=request_hash, processing_status=status,
        response_snapshot_json=None
    )
    db = FakeSession([record])

    with pytest.raises(AppException) as error:
        incident_decision.decide_incident(
            db, incident_public_id=public_id, decision_type="NEEDS_REVIEW",
            decision_reason="사유", expected_version_no=3,
            idempotency_key=str(uuid4()), current_user=user, trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_IDEMPOTENCY_CONFLICT"


def test_different_request_hash_is_conflict() -> None:
    db = FakeSession([SimpleNamespace(
        request_hash="different", processing_status="COMPLETED",
        response_snapshot_json={}
    )])

    with pytest.raises(AppException) as error:
        incident_decision.decide_incident(
            db, incident_public_id=str(uuid4()), decision_type="REAL_RISK",
            decision_reason="사유", expected_version_no=3,
            idempotency_key=str(uuid4()), current_user=_user(), trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("model", [IncidentStatusHistory, AuditLog, EventOutbox])
def test_storage_failure_rolls_back(model) -> None:
    incident = _incident()
    db = FakeSession(
        [None, incident, object(), None], fail_add_model=model
    )

    with pytest.raises(RuntimeError):
        incident_decision.decide_incident(
            db, incident_public_id=incident.public_id, decision_type="REAL_RISK",
            decision_reason="사유", expected_version_no=3,
            idempotency_key=str(uuid4()), current_user=_user(), trace_id=str(uuid4())
        )

    assert db.rollback_count == 1
    assert db.commit_count == 0


def test_new_decision_flush_failure_after_supersede_rolls_back() -> None:
    incident = _incident()
    active = _active_decision()
    db = FakeSession([None, incident, object(), active], fail_flush_at=3)

    with pytest.raises(RuntimeError):
        incident_decision.decide_incident(
            db, incident_public_id=incident.public_id, decision_type="REAL_RISK",
            decision_reason="사유", expected_version_no=3,
            idempotency_key=str(uuid4()), current_user=_user(), trace_id=str(uuid4())
        )

    assert active.superseded_at is not None
    assert db.rollback_count == 1


def test_idempotency_completion_flush_failure_rolls_back() -> None:
    incident = _incident()
    db = FakeSession([None, incident, object(), None], fail_flush_at=3)

    with pytest.raises(RuntimeError):
        incident_decision.decide_incident(
            db, incident_public_id=incident.public_id, decision_type="REAL_RISK",
            decision_reason="사유", expected_version_no=3,
            idempotency_key=str(uuid4()), current_user=_user(), trace_id=str(uuid4())
        )

    assert db.rollback_count == 1
    assert db.commit_count == 0


def test_commit_failure_rolls_back() -> None:
    incident = _incident()
    db = FakeSession(
        [None, incident, object(), None], commit_error=RuntimeError("commit failed")
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        incident_decision.decide_incident(
            db, incident_public_id=incident.public_id, decision_type="REAL_RISK",
            decision_reason="사유", expected_version_no=3,
            idempotency_key=str(uuid4()), current_user=_user(), trace_id=str(uuid4())
        )

    assert db.rollback_count == 1
