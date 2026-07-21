import re
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException
from app.models.incident import IncidentClaim, IncidentStatusHistory
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services import incident_command


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class FakeSession:
    def __init__(
        self, scalar_values, *, fail_flush_at=None, commit_error=None,
        fail_add_model=None
    ):
        self.scalar_values = list(scalar_values)
        self.fail_flush_at = fail_flush_at
        self.commit_error = commit_error
        self.fail_add_model = fail_add_model
        self.added = []
        self.statements = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    def scalars(self, statement):
        self.statements.append(statement)
        return ScalarResult(self.scalar_values.pop(0))

    def add(self, value):
        if self.fail_add_model and isinstance(value, self.fail_add_model):
            raise RuntimeError(f"{self.fail_add_model.__name__} add failed")
        self.added.append(value)

    def flush(self):
        self.flush_count += 1
        if self.flush_count == self.fail_flush_at:
            raise RuntimeError("flush failed")

    def commit(self):
        self.commit_count += 1
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollback_count += 1


def _user(user_id=7):
    user = SimpleNamespace(
        user_id=user_id, public_id=str(uuid4()), user_name="관제자"
    )
    return SimpleNamespace(user=user, summary=SimpleNamespace(permissions=[]))


def _incident(status, version=0, controller_id=None):
    return SimpleNamespace(
        incident_id=31,
        public_id=str(uuid4()),
        incident_no="INC-20260721-1",
        incident_status=status,
        version_no=version,
        current_controller_user_id=controller_id,
        acknowledged_by_user_id=None,
        acknowledged_at=None,
        claimed_at=None,
    )


def _execute(command, incident, *, current_user=None, expected=None, extra=()):
    current_user = current_user or _user()
    db = FakeSession([None, incident, object(), *extra])
    result = incident_command.execute_command(
        db,
        command=command,
        incident_public_id=incident.public_id,
        expected_version_no=incident.version_no if expected is None else expected,
        idempotency_key=str(uuid4()),
        current_user=current_user,
        trace_id=str(uuid4()),
    )
    return db, result


def _added(db, model):
    return [item for item in db.added if isinstance(item, model)]


def test_acknowledge_creates_all_transaction_records() -> None:
    incident = _incident("NEW")
    user = _user()

    db, result = _execute("acknowledge", incident, current_user=user)

    assert incident.incident_status == "ACKNOWLEDGED"
    assert incident.acknowledged_by_user_id == user.user.user_id
    assert incident.acknowledged_at is not None
    assert incident.version_no == 1
    assert result.data["acknowledged_by"]["public_id"] == user.user.public_id
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z",
        result.data["acknowledged_at"],
    )
    assert db.commit_count == 1
    assert db.rollback_count == 0
    history = _added(db, IncidentStatusHistory)[0]
    assert history.reason_code == "CONTROLLER_ACKNOWLEDGED"
    audit = _added(db, AuditLog)[0]
    assert audit.action_code == "INCIDENT.ACKNOWLEDGE"
    assert audit.before_json == {"status": "NEW", "version_no": 0}
    outbox = _added(db, EventOutbox)[0]
    assert outbox.event_type == "INCIDENT.STATUS_CHANGED"
    assert outbox.aggregate_type == "INCIDENT"
    assert outbox.publish_status == "PENDING"
    assert "incident_id" not in repr(outbox.payload_json)
    assert "user_id" not in repr(outbox.payload_json)
    key = _added(db, IdempotencyKey)[0]
    assert key.processing_status == "COMPLETED"
    assert key.response_snapshot_json["data"] == result.data


def test_claim_creates_active_claim_and_assigns_controller() -> None:
    incident = _incident("ACKNOWLEDGED", version=1)
    user = _user()

    db, result = _execute("claim", incident, current_user=user, extra=(None,))

    claim = _added(db, IncidentClaim)[0]
    assert claim.controller_user_id == user.user.user_id
    assert claim.released_at is None
    assert incident.current_controller_user_id == user.user.user_id
    assert incident.claimed_at is not None
    assert incident.version_no == 2
    assert result.data["status"] == "CLAIMED"


def test_claim_rejects_existing_active_claim() -> None:
    incident = _incident("ACKNOWLEDGED")
    db = FakeSession([None, incident, object(), object()])

    with pytest.raises(AppException) as error:
        incident_command.execute_command(
            db, command="claim", incident_public_id=incident.public_id,
            expected_version_no=0, idempotency_key=str(uuid4()),
            current_user=_user(), trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_ALREADY_CLAIMED"
    assert db.rollback_count == 1
    assert db.commit_count == 0


def test_review_requires_assigned_controller_and_preserves_claim_fields() -> None:
    user = _user()
    incident = _incident("CLAIMED", version=2, controller_id=user.user.user_id)
    incident.claimed_at = object()
    claimed_at = incident.claimed_at

    db, result = _execute("review", incident, current_user=user)

    assert incident.incident_status == "UNDER_REVIEW"
    assert incident.current_controller_user_id == user.user.user_id
    assert incident.claimed_at is claimed_at
    assert result.data["review_started_at"].endswith("Z")
    assert not any(item.__class__.__name__ == "IncidentDecision" for item in db.added)


def test_review_rejects_other_controller() -> None:
    incident = _incident("CLAIMED", controller_id=99)
    db = FakeSession([None, incident, object()])

    with pytest.raises(AppException) as error:
        incident_command.execute_command(
            db, command="review", incident_public_id=incident.public_id,
            expected_version_no=0, idempotency_key=str(uuid4()),
            current_user=_user(7), trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_NOT_ASSIGNED_CONTROLLER"
    assert db.rollback_count == 1


def test_version_conflict_contains_current_version_and_rolls_back() -> None:
    incident = _incident("NEW", version=4)
    db = FakeSession([None, incident])

    with pytest.raises(AppException) as error:
        incident_command.execute_command(
            db, command="acknowledge", incident_public_id=incident.public_id,
            expected_version_no=3, idempotency_key=str(uuid4()),
            current_user=_user(), trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_VERSION_CONFLICT"
    assert error.value.details == {
        "requested_version_no": 3, "current_version_no": 4
    }
    assert db.rollback_count == 1


def test_missing_or_inactive_transition_is_rejected() -> None:
    incident = _incident("NEW")
    db = FakeSession([None, incident, None])

    with pytest.raises(AppException) as error:
        incident_command.execute_command(
            db, command="acknowledge", incident_public_id=incident.public_id,
            expected_version_no=0, idempotency_key=str(uuid4()),
            current_user=_user(), trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_INVALID_STATE_TRANSITION"
    assert error.value.details["requested_status"] == "ACKNOWLEDGED"
    transition_sql = str(db.statements[2])
    assert "actor_scope" in transition_sql
    assert "is_active" in transition_sql


def test_incident_query_uses_for_update_lock() -> None:
    incident = _incident("NEW")
    db, _ = _execute("acknowledge", incident)

    assert "FOR UPDATE" in str(db.statements[1])


def test_completed_idempotency_replays_snapshot_without_writes() -> None:
    snapshot = {
        "data": {"incident_public_id": str(uuid4()), "version_no": 1},
        "message": "사건을 확인했습니다.",
    }
    user = _user()
    incident_public_id = str(uuid4())
    key = str(uuid4())
    request_hash = incident_command.canonical_request_hash(
        scope_code="INCIDENT_ACKNOWLEDGE", actor_public_id=user.user.public_id,
        incident_public_id=incident_public_id, expected_version_no=0
    )
    record = SimpleNamespace(
        request_hash=request_hash, processing_status="COMPLETED",
        response_snapshot_json=snapshot
    )
    db = FakeSession([record])

    result = incident_command.execute_command(
        db, command="acknowledge", incident_public_id=incident_public_id,
        expected_version_no=0, idempotency_key=key,
        current_user=user, trace_id=str(uuid4())
    )

    assert result.data == snapshot["data"]
    assert db.added == []
    assert db.commit_count == 0


@pytest.mark.parametrize("status", ["PROCESSING", "FAILED"])
def test_non_completed_idempotency_is_conflict(status) -> None:
    user = _user()
    incident_public_id = str(uuid4())
    request_hash = incident_command.canonical_request_hash(
        scope_code="INCIDENT_CLAIM", actor_public_id=user.user.public_id,
        incident_public_id=incident_public_id, expected_version_no=1
    )
    record = SimpleNamespace(
        request_hash=request_hash, processing_status=status,
        response_snapshot_json=None
    )
    db = FakeSession([record])

    with pytest.raises(AppException) as error:
        incident_command.execute_command(
            db, command="claim", incident_public_id=incident_public_id,
            expected_version_no=1, idempotency_key=str(uuid4()),
            current_user=user, trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_IDEMPOTENCY_CONFLICT"
    assert error.value.details["processing_status"] == status
    assert db.rollback_count == 1


def test_different_request_with_same_key_is_conflict() -> None:
    record = SimpleNamespace(
        request_hash="different", processing_status="COMPLETED",
        response_snapshot_json={}
    )
    db = FakeSession([record])

    with pytest.raises(AppException) as error:
        incident_command.execute_command(
            db, command="review", incident_public_id=str(uuid4()),
            expected_version_no=2, idempotency_key=str(uuid4()),
            current_user=_user(), trace_id=str(uuid4())
        )

    assert error.value.code == "INCIDENT_IDEMPOTENCY_CONFLICT"


def test_concurrent_idempotency_insert_replays_completed_record() -> None:
    user = _user()
    incident_public_id = str(uuid4())
    request_hash = incident_command.canonical_request_hash(
        scope_code="INCIDENT_ACKNOWLEDGE",
        actor_public_id=user.user.public_id,
        incident_public_id=incident_public_id,
        expected_version_no=0,
    )
    snapshot = {"data": {"version_no": 1}, "message": "완료"}
    concurrent = SimpleNamespace(
        request_hash=request_hash,
        processing_status="COMPLETED",
        response_snapshot_json=snapshot,
    )
    integrity_error = IntegrityError("insert", {}, RuntimeError("unique"))
    db = FakeSession([None, concurrent])

    def fail_first_flush():
        db.flush_count += 1
        if db.flush_count == 1:
            raise integrity_error

    db.flush = fail_first_flush

    result = incident_command.execute_command(
        db,
        command="acknowledge",
        incident_public_id=incident_public_id,
        expected_version_no=0,
        idempotency_key=str(uuid4()),
        current_user=user,
        trace_id=str(uuid4()),
    )

    assert result.data == snapshot["data"]
    assert db.rollback_count == 1
    assert db.commit_count == 0


def test_claim_integrity_error_is_translated() -> None:
    incident = _incident("ACKNOWLEDGED")
    error = IntegrityError("insert", {}, RuntimeError("unique"))
    db = FakeSession([None, incident, object(), None], fail_flush_at=2)

    def fail_with_integrity():
        db.flush_count += 1
        if db.flush_count == 2:
            raise error

    db.flush = fail_with_integrity

    with pytest.raises(AppException) as raised:
        incident_command.execute_command(
            db, command="claim", incident_public_id=incident.public_id,
            expected_version_no=0, idempotency_key=str(uuid4()),
            current_user=_user(), trace_id=str(uuid4())
        )

    assert raised.value.code == "INCIDENT_ALREADY_CLAIMED"
    assert db.rollback_count == 1


@pytest.mark.parametrize("fail_flush_at", [1, 2])
def test_flush_failure_rolls_back(fail_flush_at) -> None:
    incident = _incident("NEW")
    db = FakeSession([None, incident, object()], fail_flush_at=fail_flush_at)

    with pytest.raises(RuntimeError):
        incident_command.execute_command(
            db, command="acknowledge", incident_public_id=incident.public_id,
            expected_version_no=0, idempotency_key=str(uuid4()),
            current_user=_user(), trace_id=str(uuid4())
        )

    assert db.rollback_count == 1
    assert db.commit_count == 0


@pytest.mark.parametrize("model", [AuditLog, EventOutbox])
def test_audit_or_outbox_failure_rolls_back(model) -> None:
    incident = _incident("NEW")
    db = FakeSession([None, incident, object()], fail_add_model=model)

    with pytest.raises(RuntimeError):
        incident_command.execute_command(
            db, command="acknowledge", incident_public_id=incident.public_id,
            expected_version_no=0, idempotency_key=str(uuid4()),
            current_user=_user(), trace_id=str(uuid4())
        )

    assert db.rollback_count == 1
    assert db.commit_count == 0


def test_commit_failure_rolls_back() -> None:
    incident = _incident("NEW")
    db = FakeSession(
        [None, incident, object()], commit_error=RuntimeError("commit failed")
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        incident_command.execute_command(
            db, command="acknowledge", incident_public_id=incident.public_id,
            expected_version_no=0, idempotency_key=str(uuid4()),
            current_user=_user(), trace_id=str(uuid4())
        )

    assert db.rollback_count == 1
    assert db.commit_count == 1


def test_canonical_hash_is_stable_and_actor_sensitive() -> None:
    values = dict(
        scope_code="INCIDENT_CLAIM", actor_public_id=str(uuid4()),
        incident_public_id=str(uuid4()), expected_version_no=1
    )

    assert incident_command.canonical_request_hash(**values) == (
        incident_command.canonical_request_hash(**values)
    )
    assert incident_command.canonical_request_hash(**values) != (
        incident_command.canonical_request_hash(**(values | {"expected_version_no": 2}))
    )
