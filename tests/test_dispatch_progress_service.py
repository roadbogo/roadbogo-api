from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException
from app.models.dispatch import DispatchStatusHistory
from app.models.incident import IncidentStatusHistory
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services import dispatch_progress


class Result:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class FakeDb:
    def __init__(
        self, values, incident_id, *, commit_error=None,
        fail_add_model=None, fail_flush_at=None, integrity_flush_at=None,
    ):
        self.values = list(values)
        self.incident_id = incident_id
        self.commit_error = commit_error
        self.fail_add_model = fail_add_model
        self.fail_flush_at = fail_flush_at
        self.integrity_flush_at = integrity_flush_at
        self.statements = []
        self.added = []
        self.flush_count = self.commit_count = self.rollback_count = 0

    def scalars(self, statement):
        self.statements.append(statement)
        return Result(self.values.pop(0))

    def scalar(self, statement):
        self.statements.append(statement)
        return self.incident_id

    def add(self, value):
        if self.fail_add_model and isinstance(value, self.fail_add_model):
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


def actor():
    return SimpleNamespace(
        user=SimpleNamespace(
            user_id=9, public_id=str(uuid4()), user_name="출동 담당자"
        )
    )


def objects(command):
    config = dispatch_progress.CONFIGS[command]
    incident = SimpleNamespace(
        incident_id=31,
        public_id=str(uuid4()),
        incident_no="INC-1",
        incident_status=config.incident_from,
        version_no=5,
    )
    dispatch = SimpleNamespace(
        dispatch_request_id=21,
        public_id=str(uuid4()),
        incident_id=31,
        responder_user_id=9,
        dispatch_status=config.dispatch_from,
        version_no=1,
        status_change_method="MANUAL",
        departed_at=None,
        en_route_at=None,
        arrived_at=None,
        action_started_at=None,
    )
    return config, incident, dispatch


def added(db, model):
    return [value for value in db.added if isinstance(value, model)]


@pytest.mark.parametrize("command", list(dispatch_progress.CONFIGS))
def test_progress_command_updates_contract_records(command) -> None:
    config, incident, dispatch = objects(command)
    values = [None, incident, dispatch, object()]
    if config.incident_to:
        values.append(object())
    db = FakeDb(values, incident.incident_id)

    result = dispatch_progress.execute(
        db,
        command=command,
        dispatch_public_id=dispatch.public_id,
        expected_version_no=1,
        idempotency_key=str(uuid4()),
        current_user=actor(),
        trace_id=str(uuid4()),
    )

    assert dispatch.dispatch_status == config.dispatch_to
    assert dispatch.version_no == 2 and dispatch.status_change_method == "MANUAL"
    occurred_at = getattr(dispatch, config.timestamp_field)
    assert occurred_at is not None
    assert result.data["dispatch"]["occurred_at"].endswith("Z")
    assert len(result.data["dispatch"]["occurred_at"].rsplit(".", 1)[1]) == 4
    assert len(added(db, DispatchStatusHistory)) == 1
    history = added(db, DispatchStatusHistory)[0]
    assert history.from_status == config.dispatch_from
    assert history.to_status == config.dispatch_to
    assert history.change_method == "MANUAL"
    audit = added(db, AuditLog)[0]
    assert audit.action_code == config.audit_action
    assert audit.before_json == {
        "public_id": dispatch.public_id,
        "status": config.dispatch_from,
        "version_no": 1,
    }
    assert audit.after_json == {
        "public_id": dispatch.public_id,
        "status": config.dispatch_to,
        "version_no": 2,
    }
    assert added(db, EventOutbox)[0].event_type == config.outbox_event
    payload = added(db, EventOutbox)[0].payload_json
    assert payload["notification"] is None
    assert payload["occurred_at"] == result.data["dispatch"]["occurred_at"]
    assert payload["data"]["changed_at"] == result.data["dispatch"]["occurred_at"]
    assert added(db, IdempotencyKey)[0].processing_status == "COMPLETED"
    assert db.statements[1]._for_update_arg is None
    assert [column.name for column in db.statements[1].selected_columns] == ["incident_id"]
    assert db.statements[2]._for_update_arg is not None
    assert "incidents" in str(db.statements[2])
    assert db.statements[3]._for_update_arg is not None
    assert "dispatch_requests" in str(db.statements[3])
    if config.incident_to:
        assert incident.incident_status == config.incident_to and incident.version_no == 6
        assert len(added(db, IncidentStatusHistory)) == 1
        assert added(db, IncidentStatusHistory)[0].reason_code == config.incident_reason
        assert {event.event_type for event in added(db, EventOutbox)} == {
            config.outbox_event,
            "INCIDENT.STATUS_CHANGED",
        }
    else:
        assert incident.incident_status == "DISPATCHED" and incident.version_no == 5
        assert not added(db, IncidentStatusHistory)
        assert len(added(db, EventOutbox)) == 1
    assert "user_id" not in repr([event.payload_json for event in added(db, EventOutbox)])
    assert db.commit_count == 1


def test_progress_completed_idempotency_replays_without_writes() -> None:
    config, incident, dispatch = objects("depart")
    user = actor()
    request_hash = dispatch_progress._hash(
        config, user.user.public_id, dispatch.public_id, 1
    )
    record = SimpleNamespace(
        request_hash=request_hash,
        processing_status="COMPLETED",
        response_snapshot_json={"data": {"snapshot": True}, "message": "완료"},
    )
    db = FakeDb([record], incident.incident_id)

    result = dispatch_progress.execute(
        db,
        command="depart",
        dispatch_public_id=dispatch.public_id,
        expected_version_no=1,
        idempotency_key=str(uuid4()),
        current_user=user,
        trace_id=str(uuid4()),
    )

    assert result.data == {"snapshot": True}
    assert db.added == [] and db.commit_count == 0


def test_progress_commit_failure_rolls_back_and_restores_state() -> None:
    config, incident, dispatch = objects("arrive")
    dispatch.status_change_method = "DEVICE"
    db = FakeDb(
        [None, incident, dispatch, object(), object()],
        incident.incident_id,
        commit_error=RuntimeError("commit failed"),
    )

    with pytest.raises(RuntimeError):
        dispatch_progress.execute(
            db,
            command="arrive",
            dispatch_public_id=dispatch.public_id,
            expected_version_no=1,
            idempotency_key=str(uuid4()),
            current_user=actor(),
            trace_id=str(uuid4()),
        )

    assert dispatch.dispatch_status == config.dispatch_from and dispatch.version_no == 1
    assert dispatch.arrived_at is None
    assert dispatch.status_change_method == "DEVICE"
    assert incident.incident_status == config.incident_from and incident.version_no == 5
    assert db.rollback_count == 1
    assert db.commit_count == 1


@pytest.mark.parametrize(
    "failure",
    [DispatchStatusHistory, IncidentStatusHistory, AuditLog, EventOutbox, "flush"],
)
def test_progress_storage_failure_restores_all_state(failure) -> None:
    config, incident, dispatch = objects("arrive")
    dispatch.status_change_method = "DEVICE"
    db = FakeDb(
        [None, incident, dispatch, object(), object()],
        incident.incident_id,
        fail_add_model=failure if failure != "flush" else None,
        fail_flush_at=2 if failure == "flush" else None,
    )

    with pytest.raises(RuntimeError):
        dispatch_progress.execute(
            db, command="arrive", dispatch_public_id=dispatch.public_id,
            expected_version_no=1, idempotency_key=str(uuid4()),
            current_user=actor(), trace_id=str(uuid4()),
        )

    assert dispatch.dispatch_status == config.dispatch_from
    assert dispatch.version_no == 1
    assert dispatch.status_change_method == "DEVICE"
    assert dispatch.arrived_at is None
    assert incident.incident_status == config.incident_from
    assert incident.version_no == 5
    assert db.rollback_count == 1 and db.commit_count == 0


@pytest.mark.parametrize(
    ("scenario", "expected_code"),
    [
        ("preview_missing", "DISPATCH_NOT_FOUND"),
        ("locked_missing", "DISPATCH_NOT_FOUND"),
        ("owner", "DISPATCH_NOT_FOUND"),
        ("public_id", "DISPATCH_NOT_FOUND"),
        ("incident_id", "DISPATCH_NOT_FOUND"),
        ("version", "DISPATCH_VERSION_CONFLICT"),
        ("status", "DISPATCH_INVALID_STATE_TRANSITION"),
        ("dispatch_transition", "DISPATCH_INVALID_STATE_TRANSITION"),
        ("incident_status", "INCIDENT_INVALID_STATE_TRANSITION"),
        ("incident_transition", "INCIDENT_INVALID_STATE_TRANSITION"),
    ],
)
def test_progress_validation_errors(scenario, expected_code) -> None:
    command = "arrive" if scenario == "incident_transition" else "depart"
    config, incident, dispatch = objects(command)
    incident_id = incident.incident_id
    values = [None, incident, dispatch, object()]
    if scenario == "preview_missing":
        incident_id = None
        values = [None]
    elif scenario == "locked_missing":
        values = [None, incident, None]
    elif scenario == "owner":
        dispatch.responder_user_id = 99
    elif scenario == "public_id":
        dispatch.public_id = str(uuid4())
    elif scenario == "incident_id":
        dispatch.incident_id = 999
    elif scenario == "version":
        dispatch.version_no = 2
    elif scenario == "status":
        dispatch.dispatch_status = "ARRIVED"
    elif scenario == "dispatch_transition":
        values[-1] = None
    elif scenario == "incident_status":
        incident.incident_status = "ON_SCENE"
    elif scenario == "incident_transition":
        values.append(None)
    requested_public_id = dispatch.public_id
    if scenario == "public_id":
        requested_public_id = str(uuid4())
    db = FakeDb(values, incident_id)

    with pytest.raises(AppException) as error:
        dispatch_progress.execute(
            db, command=command, dispatch_public_id=requested_public_id,
            expected_version_no=1, idempotency_key=str(uuid4()),
            current_user=actor(), trace_id=str(uuid4()),
        )

    assert error.value.code == expected_code
    if scenario == "version":
        assert error.value.details == {"requested_version_no": 1, "current_version_no": 2}
    assert db.rollback_count == 1
    assert not added(db, DispatchStatusHistory)
    assert not added(db, IncidentStatusHistory)
    assert not added(db, AuditLog)
    assert not added(db, EventOutbox)


@pytest.mark.parametrize("status", ["PROCESSING", "FAILED"])
def test_progress_incomplete_idempotency_conflicts(status) -> None:
    config, incident, dispatch = objects("depart")
    user = actor()
    record = SimpleNamespace(
        request_hash=dispatch_progress._hash(config, user.user.public_id, dispatch.public_id, 1),
        processing_status=status,
        response_snapshot_json=None,
    )
    db = FakeDb([record], incident.incident_id)
    with pytest.raises(AppException) as error:
        dispatch_progress.execute(
            db, command="depart", dispatch_public_id=dispatch.public_id,
            expected_version_no=1, idempotency_key=str(uuid4()),
            current_user=user, trace_id=str(uuid4()),
        )
    assert error.value.code == "DISPATCH_IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("variant", ["hash", "snapshot"])
def test_progress_invalid_completed_idempotency_conflicts(variant) -> None:
    config, incident, dispatch = objects("depart")
    user = actor()
    request_hash = dispatch_progress._hash(config, user.user.public_id, dispatch.public_id, 1)
    record = SimpleNamespace(
        request_hash="different" if variant == "hash" else request_hash,
        processing_status="COMPLETED",
        response_snapshot_json=None,
    )
    with pytest.raises(AppException) as error:
        dispatch_progress.execute(
            FakeDb([record], incident.incident_id), command="depart",
            dispatch_public_id=dispatch.public_id, expected_version_no=1,
            idempotency_key=str(uuid4()), current_user=user, trace_id=str(uuid4()),
        )
    assert error.value.code == "DISPATCH_IDEMPOTENCY_CONFLICT"


def test_progress_integrity_race_replays_completed_record() -> None:
    config, incident, dispatch = objects("depart")
    user = actor()
    request_hash = dispatch_progress._hash(config, user.user.public_id, dispatch.public_id, 1)
    record = SimpleNamespace(
        request_hash=request_hash, processing_status="COMPLETED",
        response_snapshot_json={"data": {"replayed": True}, "message": "완료"},
    )
    db = FakeDb([None, record], incident.incident_id, integrity_flush_at=1)
    result = dispatch_progress.execute(
        db, command="depart", dispatch_public_id=dispatch.public_id,
        expected_version_no=1, idempotency_key=str(uuid4()),
        current_user=user, trace_id=str(uuid4()),
    )
    assert result.data == {"replayed": True}
    assert db.rollback_count == 1 and db.commit_count == 0
    assert not added(db, DispatchStatusHistory)
