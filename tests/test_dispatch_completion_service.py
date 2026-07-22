from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.dispatch import DispatchStatusHistory, FieldActionReport
from app.models.incident import IncidentStatusHistory
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services import dispatch_completion


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
        user=SimpleNamespace(user_id=9, public_id=str(uuid4()), user_name="담당자")
    )


def objects():
    incident = SimpleNamespace(
        incident_id=31,
        public_id=str(uuid4()),
        incident_no="INC-1",
        incident_status="ACTION_IN_PROGRESS",
        version_no=7,
    )
    profile = SimpleNamespace(user_id=9, duty_status="BUSY")
    dispatch = SimpleNamespace(
        dispatch_request_id=21,
        public_id=str(uuid4()),
        incident_id=31,
        responder_user_id=9,
        dispatch_status="ACTION_IN_PROGRESS",
        version_no=4,
        status_change_method="DEVICE",
        action_started_at=datetime(2026, 7, 21, 6, 40),
        action_completed_at=None,
    )
    return incident, profile, dispatch


def added(db, model):
    return [value for value in db.added if isinstance(value, model)]


def execute(db, dispatch, current_user=None):
    return dispatch_completion.execute(
        db,
        dispatch_public_id=dispatch.public_id,
        expected_version_no=4,
        action_type="DEBRIS_REMOVAL",
        action_detail="낙하물을 제거했습니다.",
        idempotency_key=str(uuid4()),
        current_user=current_user or actor(),
        trace_id=str(uuid4()),
    )


def test_completion_success_creates_report_and_contract_records() -> None:
    incident, profile, dispatch = objects()
    db = FakeDb(
        [None, incident, profile, dispatch, object(), object(), None],
        incident.incident_id,
    )

    result = execute(db, dispatch)

    assert dispatch.dispatch_status == "ACTION_COMPLETED"
    assert dispatch.version_no == 5 and dispatch.status_change_method == "MANUAL"
    assert dispatch.action_completed_at is not None
    assert incident.incident_status == "ACTION_COMPLETED" and incident.version_no == 8
    assert profile.duty_status == "AVAILABLE"
    report = added(db, FieldActionReport)[0]
    assert report.action_type == "DEBRIS_REMOVAL"
    assert report.action_detail == "낙하물을 제거했습니다."
    assert report.action_started_at == dispatch.action_started_at
    assert report.action_completed_at == dispatch.action_completed_at
    assert len(added(db, DispatchStatusHistory)) == 1
    assert added(db, IncidentStatusHistory)[0].reason_code == "RESPONDER_ACTION_COMPLETED"
    audit = added(db, AuditLog)[0]
    assert audit.action_code == "DISPATCH.COMPLETE_ACTION"
    assert "action_detail" not in repr((audit.before_json, audit.after_json))
    assert {event.event_type for event in added(db, EventOutbox)} == {
        "DISPATCH.ACTION_COMPLETED",
        "INCIDENT.STATUS_CHANGED",
    }
    assert "action_detail" not in repr([event.payload_json for event in added(db, EventOutbox)])
    assert "user_id" not in repr([event.payload_json for event in added(db, EventOutbox)])
    assert added(db, IdempotencyKey)[0].processing_status == "COMPLETED"
    assert result.data["report"]["action_completed_at"].endswith("Z")
    assert db.statements[1]._for_update_arg is None
    assert [column.name for column in db.statements[1].selected_columns] == ["incident_id"]
    assert "incidents" in str(db.statements[2])
    assert "responder_profiles" in str(db.statements[3])
    assert "dispatch_requests" in str(db.statements[4])
    assert all(db.statements[index]._for_update_arg is not None for index in (2, 3, 4))
    assert db.commit_count == 1


def test_completion_completed_idempotency_replays_without_writes() -> None:
    incident, _profile, dispatch = objects()
    user = actor()
    request_hash = dispatch_completion._request_hash(
        user.user.public_id,
        dispatch.public_id,
        4,
        "DEBRIS_REMOVAL",
        "낙하물을 제거했습니다.",
    )
    record = SimpleNamespace(
        request_hash=request_hash,
        processing_status="COMPLETED",
        response_snapshot_json={"data": {"replayed": True}, "message": "완료"},
    )
    db = FakeDb([record], incident.incident_id)

    result = execute(db, dispatch, user)

    assert result.data == {"replayed": True}
    assert db.added == [] and db.commit_count == 0


def test_completion_existing_report_is_rejected() -> None:
    incident, profile, dispatch = objects()
    db = FakeDb(
        [None, incident, profile, dispatch, object(), object(), object()],
        incident.incident_id,
    )
    with pytest.raises(Exception) as error:
        execute(db, dispatch)
    assert error.value.code == "DISPATCH_ACTION_REPORT_ALREADY_EXISTS"
    assert db.rollback_count == 1


def test_completion_commit_failure_restores_all_objects() -> None:
    incident, profile, dispatch = objects()
    db = FakeDb(
        [None, incident, profile, dispatch, object(), object(), None],
        incident.incident_id,
        commit_error=RuntimeError("commit failed"),
    )
    with pytest.raises(RuntimeError):
        execute(db, dispatch)
    assert dispatch.dispatch_status == "ACTION_IN_PROGRESS"
    assert dispatch.version_no == 4
    assert dispatch.status_change_method == "DEVICE"
    assert dispatch.action_completed_at is None
    assert incident.incident_status == "ACTION_IN_PROGRESS" and incident.version_no == 7
    assert profile.duty_status == "BUSY"
    assert db.rollback_count == 1
