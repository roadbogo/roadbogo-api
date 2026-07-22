from types import SimpleNamespace
from uuid import uuid4

import pytest

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
    def __init__(self, values, incident_id, *, commit_error=None):
        self.values = list(values)
        self.incident_id = incident_id
        self.commit_error = commit_error
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
        self.added.append(value)

    def flush(self):
        self.flush_count += 1

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
    assert added(db, AuditLog)[0].action_code == config.audit_action
    assert added(db, EventOutbox)[0].event_type == config.outbox_event
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
    assert incident.incident_status == config.incident_from and incident.version_no == 5
    assert db.rollback_count == 1
