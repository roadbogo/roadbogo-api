from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.models.dispatch import DispatchStatusHistory
from app.models.incident import IncidentStatusHistory
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services import dispatch_command, dispatch_query


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value

    def unique(self):
        return self

    def __iter__(self):
        return iter(self.value)


class FakeSession:
    def __init__(self, values, *, total=0, commit_error=None):
        self.values = list(values)
        self.total = total
        self.commit_error = commit_error
        self.added = []
        self.statements = []
        self.flush_count = self.commit_count = self.rollback_count = 0

    def scalars(self, statement):
        self.statements.append(statement)
        return ScalarResult(self.values.pop(0))

    def scalar(self, statement):
        self.statements.append(statement)
        return self.total

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


def _actor():
    return SimpleNamespace(
        user=SimpleNamespace(user_id=9, public_id=str(uuid4()), user_name="출동 담당자")
    )


def _incident():
    return SimpleNamespace(
        incident_id=31,
        public_id=str(uuid4()),
        incident_no="INC-1",
        incident_status="DISPATCH_REQUESTED",
        object_category="DEBRIS",
        current_risk_grade="HIGH",
        cctv_name_snapshot="CCTV 1",
        road_name_snapshot="도로",
        road_section_name_snapshot="구간",
        latitude_snapshot=Decimal("37.1"),
        longitude_snapshot=Decimal("127.1"),
        version_no=4,
    )


def _dispatch(incident=None):
    incident = incident or _incident()
    return SimpleNamespace(
        dispatch_request_id=10,
        public_id=str(uuid4()),
        incident_id=incident.incident_id,
        responder_user_id=9,
        assigned_by_user_id=7,
        assigned_by_user=SimpleNamespace(public_id=str(uuid4()), user_name="관제자"),
        incident=incident,
        previous_dispatch_request=None,
        attempt_no=1,
        dispatch_status="REQUESTED",
        status_change_method="MANUAL",
        request_message="출동 요청",
        rejection_reason=None,
        requested_at=datetime(2026, 7, 21),
        accepted_at=None,
        departed_at=None,
        en_route_at=None,
        arrived_at=None,
        action_started_at=None,
        action_completed_at=None,
        cancelled_at=None,
        version_no=0,
    )


def _added(db, model):
    return [value for value in db.added if isinstance(value, model)]


def test_list_mine_assembles_owned_dispatch_and_pagination() -> None:
    dispatch = _dispatch()
    db = FakeSession([[dispatch]], total=1)

    result = dispatch_query.list_mine(
        db, user_id=9, page=1, size=20, status=None, active_only=True
    )

    assert result["pagination"]["total_elements"] == 1
    assert result["items"][0]["public_id"] == dispatch.public_id
    assert result["items"][0]["requested_at"].endswith(".000Z")
    assert "responder_user_id" in str(db.statements[0])
    assert "dispatch_request_id DESC" in str(db.statements[1])
    assert "dispatch_request_id" not in result["items"][0]


def test_detail_hides_unowned_dispatch_as_not_found() -> None:
    db = FakeSession([None])

    with pytest.raises(AppException) as error:
        dispatch_query.detail(db, public_id=str(uuid4()), user_id=9)

    assert error.value.code == "DISPATCH_NOT_FOUND"
    statement = str(db.statements[0])
    assert "public_id" in statement and "responder_user_id" in statement


def test_accept_updates_dispatch_incident_and_creates_records() -> None:
    actor = _actor()
    incident = _incident()
    dispatch = _dispatch(incident)
    db = FakeSession([None, dispatch, object(), incident, object()])

    result = dispatch_command.execute(
        db,
        command="accept",
        dispatch_public_id=dispatch.public_id,
        expected_version_no=0,
        rejection_reason=None,
        idempotency_key=str(uuid4()),
        current_user=actor,
        trace_id=str(uuid4()),
    )

    assert dispatch.dispatch_status == "ACCEPTED"
    assert dispatch.accepted_at is not None and dispatch.version_no == 1
    assert incident.incident_status == "DISPATCHED" and incident.version_no == 5
    assert len(_added(db, DispatchStatusHistory)) == 1
    assert len(_added(db, IncidentStatusHistory)) == 1
    assert _added(db, AuditLog)[0].action_code == "DISPATCH.ACCEPT"
    assert {event.event_type for event in _added(db, EventOutbox)} == {
        "DISPATCH.ACCEPTED",
        "INCIDENT.STATUS_CHANGED",
    }
    assert _added(db, IdempotencyKey)[0].processing_status == "COMPLETED"
    assert result.data["incident"]["status"] == "DISPATCHED"
    assert "user_id" not in repr([event.payload_json for event in _added(db, EventOutbox)])
    assert db.commit_count == 1


def test_reject_releases_responder_and_keeps_incident_status() -> None:
    actor = _actor()
    incident = _incident()
    dispatch = _dispatch(incident)
    profile = SimpleNamespace(duty_status="BUSY")
    db = FakeSession([None, dispatch, object(), profile, incident])

    result = dispatch_command.execute(
        db,
        command="reject",
        dispatch_public_id=dispatch.public_id,
        expected_version_no=0,
        rejection_reason="다른 현장 대응 중",
        idempotency_key=str(uuid4()),
        current_user=actor,
        trace_id=str(uuid4()),
    )

    assert dispatch.dispatch_status == "REJECTED" and dispatch.version_no == 1
    assert dispatch.rejection_reason == "다른 현장 대응 중"
    assert profile.duty_status == "AVAILABLE"
    assert incident.incident_status == "DISPATCH_REQUESTED" and incident.version_no == 5
    assert not _added(db, IncidentStatusHistory)
    assert _added(db, AuditLog)[0].action_code == "DISPATCH.REJECT"
    assert _added(db, EventOutbox)[0].event_type == "DISPATCH.REJECTED"
    assert result.data["responder"]["duty_status"] == "AVAILABLE"


def test_completed_idempotency_replays_without_writes() -> None:
    actor = _actor()
    dispatch_id = str(uuid4())
    scope, request_hash = dispatch_command.canonical_request_hash(
        command="accept",
        actor_public_id=actor.user.public_id,
        dispatch_public_id=dispatch_id,
        expected_version_no=0,
        rejection_reason=None,
    )
    record = SimpleNamespace(
        request_hash=request_hash,
        processing_status="COMPLETED",
        response_snapshot_json={"data": {"ok": True}, "message": "완료"},
    )
    db = FakeSession([record])

    result = dispatch_command.execute(
        db,
        command="accept",
        dispatch_public_id=dispatch_id,
        expected_version_no=0,
        rejection_reason=None,
        idempotency_key=scope,
        current_user=actor,
        trace_id=str(uuid4()),
    )

    assert result.data == {"ok": True}
    assert db.added == [] and db.commit_count == 0


@pytest.mark.parametrize(
    ("values", "dispatch", "expected_code"),
    [
        ([None, None], None, "DISPATCH_NOT_FOUND"),
        ([None, _dispatch()], "version", "DISPATCH_VERSION_CONFLICT"),
        ([None, _dispatch()], "status", "DISPATCH_INVALID_STATE_TRANSITION"),
        ([None, _dispatch(), None], "transition", "DISPATCH_INVALID_STATE_TRANSITION"),
    ],
)
def test_accept_validation_errors(values, dispatch, expected_code) -> None:
    actor = _actor()
    target = values[1] if len(values) > 1 else None
    if dispatch == "version":
        target.version_no = 1
    elif dispatch == "status":
        target.dispatch_status = "ACCEPTED"

    with pytest.raises(AppException) as error:
        dispatch_command.execute(
            FakeSession(values),
            command="accept",
            dispatch_public_id=str(uuid4()),
            expected_version_no=0,
            rejection_reason=None,
            idempotency_key=str(uuid4()),
            current_user=actor,
            trace_id=str(uuid4()),
        )

    assert error.value.code == expected_code


def test_accept_rejects_incident_state_mismatch() -> None:
    actor = _actor()
    incident = _incident()
    incident.incident_status = "DISPATCHED"
    dispatch = _dispatch(incident)
    db = FakeSession([None, dispatch, object(), incident])

    with pytest.raises(AppException) as error:
        dispatch_command.execute(
            db,
            command="accept",
            dispatch_public_id=dispatch.public_id,
            expected_version_no=0,
            rejection_reason=None,
            idempotency_key=str(uuid4()),
            current_user=actor,
            trace_id=str(uuid4()),
        )

    assert error.value.code == "INCIDENT_INVALID_STATE_TRANSITION"


def test_idempotency_hash_or_processing_conflict() -> None:
    actor = _actor()
    record = SimpleNamespace(
        request_hash="different",
        processing_status="PROCESSING",
        response_snapshot_json=None,
    )
    db = FakeSession([record])

    with pytest.raises(AppException) as error:
        dispatch_command.execute(
            db,
            command="accept",
            dispatch_public_id=str(uuid4()),
            expected_version_no=0,
            rejection_reason=None,
            idempotency_key=str(uuid4()),
            current_user=actor,
            trace_id=str(uuid4()),
        )

    assert error.value.code == "DISPATCH_IDEMPOTENCY_CONFLICT"


def test_commit_failure_rolls_back() -> None:
    actor = _actor()
    incident = _incident()
    dispatch = _dispatch(incident)
    db = FakeSession(
        [None, dispatch, object(), incident, object()],
        commit_error=RuntimeError("commit failed"),
    )
    with pytest.raises(RuntimeError):
        dispatch_command.execute(
            db,
            command="accept",
            dispatch_public_id=dispatch.public_id,
            expected_version_no=0,
            rejection_reason=None,
            idempotency_key=str(uuid4()),
            current_user=actor,
            trace_id=str(uuid4()),
        )
    assert db.rollback_count == 1
