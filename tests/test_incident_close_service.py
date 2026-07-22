from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException
from app.models.incident import IncidentStatusHistory
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services import incident_close


class Result:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class FakeDb:
    def __init__(
        self, values, *, fail_model=None, commit_error=None,
        fail_flush_at=None, integrity_flush_at=None,
    ):
        self.values = list(values)
        self.fail_model = fail_model
        self.commit_error = commit_error
        self.fail_flush_at = fail_flush_at
        self.integrity_flush_at = integrity_flush_at
        self.statements = []
        self.added = []
        self.flush_count = self.commit_count = self.rollback_count = 0

    def scalars(self, statement):
        self.statements.append(statement)
        return Result(self.values.pop(0))

    def add(self, value):
        if type(value) is self.fail_model:
            raise RuntimeError("add failed")
        self.added.append(value)

    def flush(self):
        self.flush_count += 1
        if self.flush_count == self.integrity_flush_at:
            raise IntegrityError("insert", {}, RuntimeError("duplicate"))
        if self.flush_count == self.fail_flush_at:
            raise RuntimeError("flush failed")

    def commit(self):
        self.commit_count += 1
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollback_count += 1


def actor(*, user_id=9, roles=("CONTROLLER",)):
    return SimpleNamespace(
        user=SimpleNamespace(user_id=user_id, public_id=str(uuid4()), user_name="관제자"),
        summary=SimpleNamespace(roles=list(roles)),
    )


def objects():
    incident = SimpleNamespace(
        incident_id=31, public_id=str(uuid4()), incident_no="INC-1",
        incident_status="ACTION_COMPLETED", current_controller_user_id=9,
        version_no=10, closed_at=None,
    )
    dispatch = SimpleNamespace(
        dispatch_request_id=21, public_id=str(uuid4()), incident_id=31,
        attempt_no=2, dispatch_status="ACTION_COMPLETED",
        action_completed_at=datetime(2026, 7, 22, 7),
    )
    report = SimpleNamespace(
        public_id=str(uuid4()), dispatch_request_id=21,
        action_completed_at=datetime(2026, 7, 22, 7),
    )
    return incident, dispatch, report


def execute(db, incident, current_user=None):
    return incident_close.execute(
        db, incident_public_id=incident.public_id,
        closure_code="FIELD_ACTION_COMPLETED", closure_note="  현장 조치 확인  ",
        expected_version_no=10, idempotency_key=str(uuid4()),
        current_user=current_user or actor(), trace_id=str(uuid4()),
    )


def test_close_success_contract_and_records() -> None:
    incident, dispatch, report = objects()
    db = FakeDb([None, incident, dispatch, report, object()])

    result = execute(db, incident)

    assert incident.incident_status == "CLOSED"
    assert incident.version_no == 11 and incident.closed_at is not None
    assert result.data["closed_at"].endswith("Z")
    assert len(result.data["closed_at"].rsplit(".", 1)[1]) == 4
    history = next(x for x in db.added if isinstance(x, IncidentStatusHistory))
    assert history.reason_text == "현장 조치 확인"
    assert history.metadata_json == {
        "incident_public_id": incident.public_id,
        "dispatch_public_id": dispatch.public_id,
        "report_public_id": report.public_id,
        "closure_code": "FIELD_ACTION_COMPLETED",
    }
    audit = next(x for x in db.added if isinstance(x, AuditLog))
    outbox = next(x for x in db.added if isinstance(x, EventOutbox))
    assert audit.action_code == "INCIDENT.CLOSE"
    assert "closure_note" not in repr((audit.before_json, audit.after_json))
    assert outbox.payload_json["data"]["status"] == "CLOSED"
    assert "closure_note" not in repr(outbox.payload_json)
    assert all(key not in repr(outbox.payload_json) for key in ("incident_id", "user_id"))
    idempotency = next(x for x in db.added if isinstance(x, IdempotencyKey))
    assert idempotency.processing_status == "COMPLETED"
    assert idempotency.response_code == 200
    assert db.commit_count == 1
    assert "FOR UPDATE" in str(db.statements[1]).upper()
    assert "attempt_no DESC" in str(db.statements[2])
    assert "FOR UPDATE" in str(db.statements[2]).upper()


@pytest.mark.parametrize("roles", [("CONTROL_MANAGER",), ("SYSTEM_ADMIN",)])
def test_manager_roles_can_close_unassigned_incident(roles) -> None:
    incident, dispatch, report = objects()
    incident.current_controller_user_id = 77
    db = FakeDb([None, incident, dispatch, report, object()])
    assert execute(db, incident, actor(roles=roles)).data["status"] == "CLOSED"


def test_unassigned_controller_is_denied() -> None:
    incident, dispatch, report = objects()
    incident.current_controller_user_id = 77
    db = FakeDb([None, incident, dispatch, report])
    with pytest.raises(AppException) as exc:
        execute(db, incident)
    assert exc.value.status_code == 403
    assert exc.value.code == "INCIDENT_NOT_ASSIGNED_CONTROLLER"
    assert db.rollback_count == 1 and db.commit_count == 0


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda i, d, r: setattr(i, "version_no", 11), "INCIDENT_VERSION_CONFLICT"),
        (lambda i, d, r: setattr(i, "incident_status", "CLOSED"), "INCIDENT_INVALID_STATE_TRANSITION"),
        (lambda i, d, r: setattr(i, "closed_at", datetime(2026, 7, 22)), "INCIDENT_INVALID_STATE_TRANSITION"),
        (lambda i, d, r: setattr(d, "dispatch_status", "ARRIVED"), "INCIDENT_INVALID_STATE_TRANSITION"),
        (lambda i, d, r: setattr(d, "action_completed_at", None), "INCIDENT_INVALID_STATE_TRANSITION"),
        (lambda i, d, r: setattr(r, "action_completed_at", None), "INCIDENT_ACTION_REPORT_REQUIRED"),
        (lambda i, d, r: setattr(r, "dispatch_request_id", 99), "INCIDENT_ACTION_REPORT_REQUIRED"),
    ],
)
def test_close_validation_errors(mutate, code) -> None:
    incident, dispatch, report = objects()
    mutate(incident, dispatch, report)
    db = FakeDb([None, incident, dispatch, report, object()])
    with pytest.raises(AppException) as exc:
        execute(db, incident)
    assert exc.value.code == code
    assert db.rollback_count == 1 and db.commit_count == 0


def test_version_conflict_contract() -> None:
    incident, dispatch, report = objects()
    incident.version_no = 11
    db = FakeDb([None, incident, dispatch, report])
    with pytest.raises(AppException) as exc:
        execute(db, incident)
    assert exc.value.status_code == 409
    assert exc.value.code == "INCIDENT_VERSION_CONFLICT"
    assert exc.value.message == "사건 정보가 변경되었습니다. 최신 정보를 다시 확인해 주세요."
    assert exc.value.details == {"requested_version_no": 10, "current_version_no": 11}


@pytest.mark.parametrize("closed", [False, True])
def test_state_transition_error_details(closed) -> None:
    incident, dispatch, report = objects()
    if closed:
        incident.closed_at = datetime(2026, 7, 22)
    else:
        incident.incident_status = "ON_SCENE"
    db = FakeDb([None, incident, dispatch, report])
    with pytest.raises(AppException) as exc:
        execute(db, incident)
    assert exc.value.details == {
        "current_status": incident.incident_status,
        "requested_status": "CLOSED",
    }


@pytest.mark.parametrize("missing", ["incident", "dispatch", "report", "transition"])
def test_close_missing_dependencies(missing) -> None:
    incident, dispatch, report = objects()
    values = [None, incident, dispatch, report, object()]
    values[{"incident": 1, "dispatch": 2, "report": 3, "transition": 4}[missing]] = None
    db = FakeDb(values)
    with pytest.raises(AppException) as exc:
        execute(db, incident)
    expected = {
        "incident": "INCIDENT_NOT_FOUND", "dispatch": "INCIDENT_INVALID_STATE_TRANSITION",
        "report": "INCIDENT_ACTION_REPORT_REQUIRED",
        "transition": "INCIDENT_INVALID_STATE_TRANSITION",
    }
    assert exc.value.code == expected[missing]


@pytest.mark.parametrize("model", [IncidentStatusHistory, AuditLog, EventOutbox])
def test_storage_failures_restore_incident(model) -> None:
    incident, dispatch, report = objects()
    db = FakeDb([None, incident, dispatch, report, object()], fail_model=model)
    with pytest.raises(RuntimeError):
        execute(db, incident)
    assert (incident.incident_status, incident.version_no, incident.closed_at) == (
        "ACTION_COMPLETED", 10, None
    )
    assert db.rollback_count == 1 and db.commit_count == 0


def test_commit_failure_restores_incident() -> None:
    incident, dispatch, report = objects()
    db = FakeDb([None, incident, dispatch, report, object()], commit_error=RuntimeError("commit"))
    with pytest.raises(RuntimeError):
        execute(db, incident)
    assert (incident.incident_status, incident.version_no, incident.closed_at) == (
        "ACTION_COMPLETED", 10, None
    )
    assert db.rollback_count == 1 and db.commit_count == 1


def test_final_snapshot_flush_failure_restores_incident() -> None:
    incident, dispatch, report = objects()
    db = FakeDb([None, incident, dispatch, report, object()], fail_flush_at=2)
    with pytest.raises(RuntimeError):
        execute(db, incident)
    assert (incident.incident_status, incident.version_no, incident.closed_at) == (
        "ACTION_COMPLETED", 10, None
    )
    assert db.rollback_count == 1 and db.commit_count == 0


@pytest.mark.parametrize("snapshot", [None, [], {}, {"data": {}}, {"message": "ok"}, {"data": [], "message": "ok"}, {"data": {}, "message": " "}])
def test_invalid_completed_snapshot_conflicts(snapshot) -> None:
    record = SimpleNamespace(
        request_hash="hash", processing_status="COMPLETED",
        response_snapshot_json=snapshot,
    )
    with pytest.raises(AppException) as exc:
        incident_close._replay(record, "hash")
    assert exc.value.code == "INCIDENT_IDEMPOTENCY_CONFLICT"


def test_completed_snapshot_replays_without_commit() -> None:
    incident, _, _ = objects()
    user = actor()
    request_hash = incident_close._request_hash(
        user.user.public_id, incident.public_id, "FIELD_ACTION_COMPLETED",
        "현장 조치 확인", 10,
    )
    record = SimpleNamespace(
        request_hash=request_hash, processing_status="COMPLETED",
        response_snapshot_json={"data": {"status": "CLOSED"}, "message": "완료"},
    )
    db = FakeDb([record])
    result = execute(db, incident, user)
    assert result.data == {"status": "CLOSED"}
    assert db.commit_count == 0


@pytest.mark.parametrize("status", ["PROCESSING", "FAILED"])
def test_non_completed_idempotency_record_conflicts(status) -> None:
    record = SimpleNamespace(
        request_hash="hash", processing_status=status, response_snapshot_json=None,
    )
    with pytest.raises(AppException) as exc:
        incident_close._replay(record, "hash")
    assert exc.value.code == "INCIDENT_IDEMPOTENCY_CONFLICT"


def test_idempotency_hash_mismatch_conflicts() -> None:
    record = SimpleNamespace(
        request_hash="other", processing_status="COMPLETED",
        response_snapshot_json={"data": {}, "message": "완료"},
    )
    with pytest.raises(AppException) as exc:
        incident_close._replay(record, "hash")
    assert exc.value.code == "INCIDENT_IDEMPOTENCY_CONFLICT"


def test_integrity_race_replays_completed_record() -> None:
    incident, _, _ = objects()
    user = actor()
    request_hash = incident_close._request_hash(
        user.user.public_id, incident.public_id, "FIELD_ACTION_COMPLETED",
        "현장 조치 확인", 10,
    )
    record = SimpleNamespace(
        request_hash=request_hash, processing_status="COMPLETED",
        response_snapshot_json={"data": {"status": "CLOSED"}, "message": "완료"},
    )
    db = FakeDb([None, record], integrity_flush_at=1)
    result = execute(db, incident, user)
    assert result.data == {"status": "CLOSED"}
    assert db.rollback_count == 1 and db.commit_count == 0
