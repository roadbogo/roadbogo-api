from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.services.incident_command import CommandResult


def _user(*permissions):
    return SimpleNamespace(
        user=SimpleNamespace(user_id=7, public_id=str(uuid4()), user_name="관제자"),
        summary=SimpleNamespace(permissions=list(permissions), roles=[]),
    )


def _post(client, body=None, key=None, incident_id=None):
    return client.post(
        f"/api/v1/incidents/{incident_id or uuid4()}/dispatches",
        headers={} if key is None else {"Idempotency-Key": key},
        json=body or {
            "responder_public_id": str(uuid4()),
            "request_message": "요청",
            "expected_version_no": 4,
        },
    )


def test_dispatch_api_auth_permission_and_validation() -> None:
    app.dependency_overrides[get_db] = lambda: object()
    try:
        no_auth = _post(TestClient(app), key=str(uuid4()))
        app.dependency_overrides[get_current_user] = lambda: _user()
        denied = _post(TestClient(app), key=str(uuid4()))
        app.dependency_overrides[get_current_user] = lambda: _user("DISPATCH.ASSIGN")
        client = TestClient(app)
        valid = {"responder_public_id": str(uuid4()), "request_message": None, "expected_version_no": 4}
        invalid = [
            _post(client, valid), _post(client, valid, "invalid"),
            _post(client, valid, str(uuid4()), "invalid"),
            _post(client, valid | {"responder_public_id": "invalid"}, str(uuid4())),
            _post(client, valid | {"expected_version_no": -1}, str(uuid4())),
            _post(client, valid | {"request_message": "x" * 1001}, str(uuid4())),
            _post(client, valid | {"incident_id": 1}, str(uuid4())),
        ]
    finally:
        app.dependency_overrides.clear()
    assert no_auth.status_code == 401 and denied.status_code == 403
    assert {response.status_code for response in invalid} == {422}


def test_blank_message_is_normalized_and_success_schema(monkeypatch) -> None:
    captured = {}
    def fake_assign(db, **kwargs):
        captured.update(kwargs)
        return CommandResult({
            "dispatch": {
                "public_id": str(uuid4()), "incident_public_id": kwargs["incident_public_id"],
                "attempt_no": 1, "status": "REQUESTED",
                "responder": {"public_id": kwargs["responder_public_id"], "user_name": "출동자", "responder_code": "RSP-1"},
                "assigned_by": {"public_id": kwargs["current_user"].user.public_id, "user_name": "관제자"},
                "request_message": None, "requested_at": "2026-07-21T00:00:00.000Z", "version_no": 0,
            },
            "incident": {"public_id": kwargs["incident_public_id"], "status": "DISPATCH_REQUESTED", "version_no": 5},
        }, "출동 담당자를 배정했습니다.")
    monkeypatch.setattr("app.api.v1.dispatches.dispatch_assignment.assign_dispatch", fake_assign)
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: _user("DISPATCH.ASSIGN")
    try:
        client = TestClient(app)
        body = {
            "responder_public_id": str(uuid4()), "request_message": "   ", "expected_version_no": 4
        }
        key = str(uuid4())
        response = _post(client, body, key)
        replay = _post(client, body, key)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201
    assert replay.status_code == 201
    assert captured["request_message"] is None
    assert "user_id" not in response.text


def test_dispatch_openapi_is_concrete() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/api/v1/incidents/{incident_public_id}/dispatches"]["post"]
    assert next(p for p in operation["parameters"] if p["name"] == "Idempotency-Key")["required"] is True
    request = schema["components"]["schemas"]["DispatchAssignmentRequest"]
    assert request["properties"]["expected_version_no"]["minimum"] == 0
    response_ref = operation["responses"]["201"]["content"]["application/json"]["schema"]["$ref"]
    envelope = schema["components"]["schemas"][response_ref.rsplit("/", 1)[1]]
    assert envelope["properties"]["data"]["anyOf"][0]["$ref"].endswith("DispatchAssignmentData")
