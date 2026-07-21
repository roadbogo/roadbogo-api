from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException
from app.models.dispatch import DispatchRequest, DispatchStatusHistory
from app.models.notification import AuditLog, EventOutbox, IdempotencyKey
from app.services import dispatch_assignment


class ScalarResult:
    def __init__(self, value): self.value = value
    def first(self): return self.value


class FakeSession:
    def __init__(self, values, *, fail_flush_at=None, fail_add_model=None, commit_error=None):
        self.values = list(values)
        self.fail_flush_at = fail_flush_at
        self.fail_add_model = fail_add_model
        self.commit_error = commit_error
        self.added = []
        self.statements = []
        self.flush_count = self.commit_count = self.rollback_count = 0

    def scalars(self, statement):
        self.statements.append(statement)
        return ScalarResult(self.values.pop(0))

    def add(self, value):
        if self.fail_add_model and isinstance(value, self.fail_add_model):
            raise RuntimeError("add failed")
        self.added.append(value)

    def flush(self):
        self.flush_count += 1
        if self.flush_count == self.fail_flush_at:
            raise RuntimeError("flush failed")
        for value in self.added:
            if isinstance(value, DispatchRequest) and value.dispatch_request_id is None:
                value.dispatch_request_id = 501

    def commit(self):
        self.commit_count += 1
        if self.commit_error:
            raise self.commit_error

    def rollback(self): self.rollback_count += 1


def _actor(user_id=7):
    return SimpleNamespace(user=SimpleNamespace(
        user_id=user_id, public_id=str(uuid4()), user_name="관제자"
    ))


def _incident(status="DISPATCH_REQUESTED", version=4, controller_id=7):
    return SimpleNamespace(
        incident_id=31, public_id=str(uuid4()), incident_no="INC-1",
        incident_status=status, version_no=version,
        current_controller_user_id=controller_id, claimed_at=object(), closed_at=None
    )


def _responder(*, duty="AVAILABLE", enabled=1, status="ACTIVE", deleted=None):
    role = SimpleNamespace(role_code="RESPONDER", is_active=1)
    user = SimpleNamespace(
        user_id=9, public_id=str(uuid4()), user_name="출동자",
        account_status=status, deleted_at=deleted,
        user_roles_users=[SimpleNamespace(role=role)],
        responder_profiles=[]
    )
    profile = SimpleNamespace(
        responder_code="RSP-1", duty_status=duty,
        is_dispatch_enabled=enabled, coverage_area="경부"
    )
    user.responder_profiles = [profile]
    return user, profile


def _execute(*, previous=None):
    incident = _incident()
    responder, profile = _responder()
    db = FakeSession([None, incident, responder, profile, 1, None, None, previous])
    result = dispatch_assignment.assign_dispatch(
        db, incident_public_id=incident.public_id,
        responder_public_id=responder.public_id, request_message="요청",
        expected_version_no=4, idempotency_key=str(uuid4()),
        current_user=_actor(), trace_id=str(uuid4())
    )
    return db, incident, responder, profile, result


def _added(db, model): return [v for v in db.added if isinstance(v, model)]


def test_assignment_success_creates_contract_records() -> None:
    db, incident, responder, profile, result = _execute()
    dispatch = _added(db, DispatchRequest)[0]
    assert dispatch.dispatch_status == "REQUESTED"
    assert dispatch.attempt_no == 1
    assert dispatch.previous_dispatch_request_id is None
    assert incident.incident_status == "DISPATCH_REQUESTED"
    assert incident.version_no == 5
    assert profile.duty_status == "BUSY"
    history = _added(db, DispatchStatusHistory)[0]
    assert history.from_status is None and history.to_status == "REQUESTED"
    assert history.metadata_json["responder_public_id"] == responder.public_id
    assert _added(db, AuditLog)[0].action_code == "DISPATCH.ASSIGN"
    outbox = _added(db, EventOutbox)[0]
    assert outbox.event_type == "DISPATCH.REQUESTED"
    assert outbox.aggregate_type == "DISPATCH"
    assert outbox.payload_json["resource"]["resource_type"] == "DISPATCH"
    assert "user_id" not in repr(outbox.payload_json)
    idempotency = _added(db, IdempotencyKey)[0]
    assert idempotency.processing_status == "COMPLETED"
    assert idempotency.response_code == 201
    assert result.data["dispatch"]["version_no"] == 0
    assert result.data["incident"]["version_no"] == 5
    assert db.commit_count == 1


def test_previous_dispatch_increments_attempt_and_links() -> None:
    previous = SimpleNamespace(dispatch_request_id=400, attempt_no=2)
    db, *_ = _execute(previous=previous)
    dispatch = _added(db, DispatchRequest)[0]
    assert dispatch.attempt_no == 3
    assert dispatch.previous_dispatch_request_id == 400


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([None, None], "INCIDENT_NOT_FOUND"),
        ([None, _incident(version=5)], "INCIDENT_VERSION_CONFLICT"),
        ([None, _incident(status="UNDER_REVIEW")], "INCIDENT_INVALID_STATE_TRANSITION"),
        ([None, _incident(controller_id=99)], "INCIDENT_NOT_ASSIGNED_CONTROLLER"),
    ],
)
def test_incident_validation(values, expected) -> None:
    responder, _ = _responder()
    db = FakeSession(values)
    with pytest.raises(AppException) as error:
        dispatch_assignment.assign_dispatch(
            db, incident_public_id=str(uuid4()), responder_public_id=responder.public_id,
            request_message=None, expected_version_no=4,
            idempotency_key=str(uuid4()), current_user=_actor(), trace_id=str(uuid4())
        )
    assert error.value.code == expected
    assert db.rollback_count == 1


@pytest.mark.parametrize(
    ("responder", "profile", "active_role", "code"),
    [
        (None, None, None, "DISPATCH_RESPONDER_NOT_FOUND"),
        (*_responder(duty="BUSY"), 1, "DISPATCH_RESPONDER_UNAVAILABLE"),
        (*_responder(duty="OFF_DUTY"), 1, "DISPATCH_RESPONDER_UNAVAILABLE"),
        (*_responder(duty="UNAVAILABLE"), 1, "DISPATCH_RESPONDER_UNAVAILABLE"),
        (*_responder(enabled=0), 1, "DISPATCH_RESPONDER_UNAVAILABLE"),
        (*_responder(status="INACTIVE"), 1, "DISPATCH_RESPONDER_UNAVAILABLE"),
        (_responder()[0], None, 1, "DISPATCH_RESPONDER_NOT_FOUND"),
        (*_responder(), None, "DISPATCH_RESPONDER_NOT_FOUND"),
    ],
)
def test_responder_validation(responder, profile, active_role, code) -> None:
    incident = _incident()
    values = [None, incident, responder]
    if responder is not None:
        values.extend([profile, active_role])
    db = FakeSession(values)
    with pytest.raises(AppException) as error:
        dispatch_assignment.assign_dispatch(
            db, incident_public_id=incident.public_id,
            responder_public_id=str(uuid4()), request_message=None,
            expected_version_no=4, idempotency_key=str(uuid4()),
            current_user=_actor(), trace_id=str(uuid4())
        )
    assert error.value.code == code


def test_responder_user_and_profile_are_locked_separately() -> None:
    responder, profile = _responder()
    db = FakeSession([responder, profile, 1])

    assert dispatch_assignment._lock_responder(db, responder.public_id) == (
        responder,
        profile,
    )
    assert db.statements[0]._for_update_arg is not None
    assert db.statements[1]._for_update_arg is not None
    assert db.statements[2]._for_update_arg is None
    assert "responder_profiles" in str(db.statements[1])


def test_active_incident_and_responder_conflicts() -> None:
    incident = _incident()
    responder, _ = _responder()
    profile = responder.responder_profiles[0]
    for values, code in (
        ([None, incident, responder, profile, 1, object()], "DISPATCH_ALREADY_ASSIGNED"),
        ([None, incident, responder, profile, 1, None, object()], "DISPATCH_RESPONDER_BUSY"),
    ):
        with pytest.raises(AppException) as error:
            dispatch_assignment.assign_dispatch(
                FakeSession(values), incident_public_id=incident.public_id,
                responder_public_id=responder.public_id, request_message=None,
                expected_version_no=4, idempotency_key=str(uuid4()),
                current_user=_actor(), trace_id=str(uuid4())
            )
        assert error.value.code == code


@pytest.mark.parametrize(
    ("constraint", "code"),
    [
        ("uk_dispatch_requests_active_incident", "DISPATCH_ALREADY_ASSIGNED"),
        ("uk_dispatch_requests_active_responder", "DISPATCH_RESPONDER_BUSY"),
    ],
)
def test_integrity_error_mapping(constraint, code) -> None:
    exc = IntegrityError("insert", {}, RuntimeError(f"Duplicate {constraint}"))
    assert dispatch_assignment._integrity_error(exc).code == code


def test_completed_idempotency_replays() -> None:
    actor = _actor()
    incident_id = str(uuid4())
    responder_id = str(uuid4())
    request_hash = dispatch_assignment.canonical_request_hash(
        actor_public_id=actor.user.public_id, incident_public_id=incident_id,
        responder_public_id=responder_id, request_message=None, expected_version_no=4
    )
    snapshot = {"data": {"ok": True}, "message": "완료"}
    record = SimpleNamespace(request_hash=request_hash, processing_status="COMPLETED", response_snapshot_json=snapshot)
    db = FakeSession([record])
    result = dispatch_assignment.assign_dispatch(
        db, incident_public_id=incident_id, responder_public_id=responder_id,
        request_message=None, expected_version_no=4, idempotency_key=str(uuid4()),
        current_user=actor, trace_id=str(uuid4())
    )
    assert result.data == snapshot["data"] and db.added == []


@pytest.mark.parametrize("model", [DispatchStatusHistory, AuditLog, EventOutbox])
def test_storage_failure_rolls_back(model) -> None:
    incident = _incident()
    responder, profile = _responder()
    db = FakeSession(
        [None, incident, responder, profile, 1, None, None, None],
        fail_add_model=model,
    )
    with pytest.raises(RuntimeError):
        dispatch_assignment.assign_dispatch(
            db, incident_public_id=incident.public_id, responder_public_id=responder.public_id,
            request_message=None, expected_version_no=4, idempotency_key=str(uuid4()),
            current_user=_actor(), trace_id=str(uuid4())
        )
    assert db.rollback_count == 1


def test_idempotency_completion_failure_rolls_back() -> None:
    incident = _incident()
    responder, profile = _responder()
    db = FakeSession(
        [None, incident, responder, profile, 1, None, None, None],
        fail_flush_at=3,
    )
    with pytest.raises(RuntimeError):
        dispatch_assignment.assign_dispatch(
            db,
            incident_public_id=incident.public_id,
            responder_public_id=responder.public_id,
            request_message=None,
            expected_version_no=4,
            idempotency_key=str(uuid4()),
            current_user=_actor(),
            trace_id=str(uuid4()),
        )
    assert db.rollback_count == 1


def test_commit_failure_rolls_back() -> None:
    incident = _incident()
    responder, profile = _responder()
    db = FakeSession(
        [None, incident, responder, profile, 1, None, None, None],
        commit_error=RuntimeError("commit failed"),
    )
    with pytest.raises(RuntimeError):
        dispatch_assignment.assign_dispatch(
            db, incident_public_id=incident.public_id, responder_public_id=responder.public_id,
            request_message=None, expected_version_no=4, idempotency_key=str(uuid4()),
            current_user=_actor(), trace_id=str(uuid4())
        )
    assert db.rollback_count == 1
