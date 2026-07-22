from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException
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
    def __init__(
        self, values, incident_id, *, commit_error=None,
        fail_add_model=None, fail_add_at=None, fail_flush_at=None,
        integrity_flush_at=None,
    ):
        self.values = list(values)
        self.incident_id = incident_id
        self.commit_error = commit_error
        self.fail_add_model = fail_add_model
        self.fail_add_at = fail_add_at
        self.fail_flush_at = fail_flush_at
        self.integrity_flush_at = integrity_flush_at
        self.statements = []
        self.added = []
        self.add_counts = {}
        self.flush_count = self.commit_count = self.rollback_count = 0

    def scalars(self, statement):
        self.statements.append(statement)
        return Result(self.values.pop(0))

    def scalar(self, statement):
        self.statements.append(statement)
        return self.incident_id

    def add(self, value):
        model = type(value)
        self.add_counts[model] = self.add_counts.get(model, 0) + 1
        if self.fail_add_model is not None:
            if isinstance(self.fail_add_model, tuple):
                fail_model, fail_at = self.fail_add_model
                if model is fail_model and self.add_counts[model] == fail_at:
                    raise RuntimeError("add failed")
            elif model is self.fail_add_model:
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
        self.added.clear()


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


@pytest.mark.parametrize(
    "snapshot",
    [None, [], {}, {"message": "완료"}, {"data": {}}, {"data": [], "message": "완료"},
     {"data": {}, "message": None}, {"data": {}, "message": ""},
     {"data": {}, "message": "   "}],
)
def test_completion_completed_idempotency_conflicts_for_invalid_snapshots(snapshot) -> None:
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
        response_snapshot_json=snapshot,
    )
    db = FakeDb([record], incident.incident_id)

    with pytest.raises(AppException) as error:
        execute(db, dispatch, user)

    assert error.value.code == "DISPATCH_IDEMPOTENCY_CONFLICT"
    assert db.rollback_count == 1
    assert db.commit_count == 0


def test_completion_idempotency_hash_mismatch_conflicts() -> None:
    incident, _profile, dispatch = objects()
    user = actor()
    record = SimpleNamespace(
        request_hash="different",
        processing_status="COMPLETED",
        response_snapshot_json={"data": {"replayed": True}, "message": "완료"},
    )
    db = FakeDb([record], incident.incident_id)

    with pytest.raises(AppException) as error:
        execute(db, dispatch, user)

    assert error.value.code == "DISPATCH_IDEMPOTENCY_CONFLICT"
    assert db.rollback_count == 1
    assert db.commit_count == 0


@pytest.mark.parametrize("status", ["PROCESSING", "FAILED"])
def test_completion_incomplete_idempotency_conflicts(status) -> None:
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
        processing_status=status,
        response_snapshot_json=None,
    )
    db = FakeDb([record], incident.incident_id)

    with pytest.raises(AppException) as error:
        execute(db, dispatch, user)

    assert error.value.code == "DISPATCH_IDEMPOTENCY_CONFLICT"
    assert db.rollback_count == 1
    assert db.commit_count == 0


def test_completion_integrity_race_replays_completed_record() -> None:
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
    db = FakeDb([None, record], incident.incident_id, integrity_flush_at=1)

    result = execute(db, dispatch, user)

    assert result.data == {"replayed": True}
    assert db.rollback_count == 1 and db.commit_count == 0
    assert db.added == []


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


@pytest.mark.parametrize(
    ("scenario", "expected_code"),
    [
        ("preview_missing", "DISPATCH_NOT_FOUND"),
        ("locked_missing", "DISPATCH_NOT_FOUND"),
        ("responder_missing", "DISPATCH_NOT_FOUND"),
        ("dispatch_missing", "DISPATCH_NOT_FOUND"),
        ("other_responder", "DISPATCH_NOT_FOUND"),
        ("public_id", "DISPATCH_NOT_FOUND"),
        ("preview_mismatch", "DISPATCH_NOT_FOUND"),
        ("profile_user", "DISPATCH_NOT_FOUND"),
        ("version", "DISPATCH_VERSION_CONFLICT"),
        ("status", "DISPATCH_INVALID_STATE_TRANSITION"),
        ("action_started_at", "DISPATCH_INVALID_STATE_TRANSITION"),
        ("incident_status", "INCIDENT_INVALID_STATE_TRANSITION"),
        ("duty_status", "DISPATCH_RESPONDER_STATUS_CONFLICT"),
        ("dispatch_transition", "DISPATCH_INVALID_STATE_TRANSITION"),
        ("incident_transition", "INCIDENT_INVALID_STATE_TRANSITION"),
        ("too_early", "DISPATCH_INVALID_STATE_TRANSITION"),
        ("report_exists", "DISPATCH_ACTION_REPORT_ALREADY_EXISTS"),
    ],
)
def test_completion_validation_errors(scenario, expected_code) -> None:
    incident, profile, dispatch = objects()
    requested_public_id = dispatch.public_id
    incident_id = incident.incident_id
    values = [None, incident, profile, dispatch, object(), object(), None]
    if scenario == "preview_missing":
        values = [None]
        incident_id = None
    elif scenario == "locked_missing":
        values = [None, None, profile, dispatch]
    elif scenario == "responder_missing":
        values = [None, incident, None, dispatch]
    elif scenario == "dispatch_missing":
        values = [None, incident, profile, None]
    elif scenario == "other_responder":
        dispatch.responder_user_id = 99
    elif scenario == "public_id":
        requested_public_id = str(uuid4())
    elif scenario == "preview_mismatch":
        dispatch.incident_id = 999
    elif scenario == "profile_user":
        profile.user_id = 99
    elif scenario == "version":
        dispatch.version_no = 5
    elif scenario == "status":
        dispatch.dispatch_status = "ARRIVED"
    elif scenario == "action_started_at":
        dispatch.action_started_at = None
    elif scenario == "incident_status":
        incident.incident_status = "ON_SCENE"
    elif scenario == "duty_status":
        profile.duty_status = "AVAILABLE"
    elif scenario == "dispatch_transition":
        values[4] = None
    elif scenario == "incident_transition":
        values[5] = None
    elif scenario == "too_early":
        dispatch.action_started_at = datetime(3026, 1, 1, 0, 0)
    elif scenario == "report_exists":
        values[6] = object()

    db = FakeDb(values, incident_id)

    with pytest.raises(AppException) as error:
        dispatch_completion.execute(
            db,
            dispatch_public_id=requested_public_id,
            expected_version_no=4,
            action_type="DEBRIS_REMOVAL",
            action_detail="낙하물을 제거했습니다.",
            idempotency_key=str(uuid4()),
            current_user=actor(),
            trace_id=str(uuid4()),
        )

    assert error.value.code == expected_code
    if scenario == "version":
        assert error.value.details == {"requested_version_no": 4, "current_version_no": 5}
    assert db.rollback_count == 1
    assert not added(db, FieldActionReport)
    assert not added(db, DispatchStatusHistory)
    assert not added(db, IncidentStatusHistory)
    assert not added(db, AuditLog)
    assert not added(db, EventOutbox)


@pytest.mark.parametrize(
    ("failure","fail_add_model","fail_flush_at"),
    [
        ("report", FieldActionReport, None),
        ("dispatch_history", DispatchStatusHistory, None),
        ("incident_history", IncidentStatusHistory, None),
        ("audit", AuditLog, None),
        ("first_outbox", (EventOutbox, 1), None),
        ("second_outbox", (EventOutbox, 2), None),
        ("snapshot_flush", None, 2),
    ],
)
def test_completion_storage_failures_restore_state(failure, fail_add_model, fail_flush_at) -> None:
    incident, profile, dispatch = objects()
    dispatch.status_change_method = "DEVICE"
    db = FakeDb(
        [None, incident, profile, dispatch, object(), object(), None],
        incident.incident_id,
        fail_add_model=fail_add_model,
        fail_flush_at=fail_flush_at,
    )

    with pytest.raises(RuntimeError):
        dispatch_completion.execute(
            db,
            dispatch_public_id=dispatch.public_id,
            expected_version_no=4,
            action_type="DEBRIS_REMOVAL",
            action_detail="낙하물을 제거했습니다.",
            idempotency_key=str(uuid4()),
            current_user=actor(),
            trace_id=str(uuid4()),
        )

    assert dispatch.dispatch_status == "ACTION_IN_PROGRESS"
    assert dispatch.version_no == 4
    assert dispatch.status_change_method == "DEVICE"
    assert dispatch.action_completed_at is None
    assert incident.incident_status == "ACTION_IN_PROGRESS"
    assert incident.version_no == 7
    assert profile.duty_status == "BUSY"
    assert db.rollback_count == 1
    assert db.commit_count == 0
    assert not added(db, FieldActionReport)
    assert not added(db, DispatchStatusHistory)
    assert not added(db, IncidentStatusHistory)
    assert not added(db, AuditLog)
    assert not added(db, EventOutbox)


def test_completion_success_contract_details() -> None:
    incident, profile, dispatch = objects()
    db = FakeDb([None, incident, profile, dispatch, object(), object(), None], incident.incident_id)

    result = execute(db, dispatch)

    report = added(db, FieldActionReport)[0]
    assert report.public_id is not None
    assert report.dispatch_request_id == dispatch.dispatch_request_id
    assert report.created_by_user_id == actor().user.user_id
    assert report.action_type == "DEBRIS_REMOVAL"
    assert report.action_detail == "낙하물을 제거했습니다."
    assert report.action_started_at == dispatch.action_started_at
    assert report.action_completed_at == dispatch.action_completed_at
    assert len(added(db, DispatchStatusHistory)) == 1
    history = added(db, DispatchStatusHistory)[0]
    assert history.from_status == "ACTION_IN_PROGRESS"
    assert history.to_status == "ACTION_COMPLETED"
    assert history.change_method == "MANUAL"
    assert history.metadata_json == {
        "dispatch_public_id": dispatch.public_id,
        "report_public_id": report.public_id,
    }
    incident_history = added(db, IncidentStatusHistory)[0]
    assert incident_history.reason_code == "RESPONDER_ACTION_COMPLETED"
    assert incident_history.metadata_json == {
        "dispatch_public_id": dispatch.public_id,
        "report_public_id": report.public_id,
    }
    audit = added(db, AuditLog)[0]
    assert audit.before_json == {
        "public_id": dispatch.public_id,
        "status": "ACTION_IN_PROGRESS",
        "version_no": 4,
    }
    assert audit.after_json == {
        "public_id": dispatch.public_id,
        "status": "ACTION_COMPLETED",
        "version_no": 5,
        "report_public_id": report.public_id,
    }
    outboxes = added(db, EventOutbox)
    assert {event.event_type for event in outboxes} == {
        "DISPATCH.ACTION_COMPLETED",
        "INCIDENT.STATUS_CHANGED",
    }
    assert outboxes[0].payload_json["notification"] is None
    assert outboxes[1].payload_json["notification"] is None
    assert outboxes[0].payload_json["trace_id"] == outboxes[1].payload_json["trace_id"]
    assert outboxes[0].payload_json["occurred_at"] == result.data["dispatch"]["action_completed_at"]
    assert outboxes[1].payload_json["data"]["changed_at"] == result.data["dispatch"]["action_completed_at"]
    assert "action_detail" not in repr([event.payload_json for event in outboxes])
    assert "user_id" not in repr([event.payload_json for event in outboxes])
    idempotency = added(db, IdempotencyKey)[0]
    assert idempotency.response_snapshot_json == {"data": result.data, "message": "현장 조치를 완료했습니다."}
    assert db.commit_count == 1
