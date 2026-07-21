from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.services.incident_command import CommandResult


def _user(*permissions):
    return SimpleNamespace(
        user=SimpleNamespace(
            user_id=7, public_id=str(uuid4()), user_name="관제자"
        ),
        summary=SimpleNamespace(permissions=list(permissions), roles=[]),
    )


def _client(user=None):
    app.dependency_overrides[get_db] = lambda: object()
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _clear():
    app.dependency_overrides.clear()


def _request(client, *, body=None, key=None, public_id=None):
    headers = {} if key is None else {"Idempotency-Key": key}
    return client.post(
        f"/api/v1/incidents/{public_id or uuid4()}/decisions",
        headers=headers,
        json=body or {
            "decision_type": "REAL_RISK",
            "decision_reason": "판정 사유",
            "expected_version_no": 3,
        },
    )


def test_authentication_and_permission() -> None:
    try:
        no_auth = _request(_client(), key=str(uuid4()))
        no_permission = _request(_client(_user()), key=str(uuid4()))
        role_only_user = _user()
        role_only_user.summary.roles = ["CONTROLLER"]
        role_only = _request(_client(role_only_user), key=str(uuid4()))
    finally:
        _clear()

    assert no_auth.status_code == 401
    assert no_permission.status_code == 403
    assert no_permission.json()["error"]["code"] == "AUTH_PERMISSION_DENIED"
    assert role_only.status_code == 403


def test_header_path_and_body_validation() -> None:
    client = _client(_user("INCIDENT.DECIDE"))
    valid = {
        "decision_type": "REAL_RISK", "decision_reason": "사유",
        "expected_version_no": 3
    }
    try:
        responses = [
            _request(client, body=valid),
            _request(client, body=valid, key="invalid"),
            _request(client, body=valid, key=str(uuid4()), public_id="invalid"),
            _request(client, key=str(uuid4()), body=valid | {"expected_version_no": -1}),
            _request(client, key=str(uuid4()), body=valid | {"decision_reason": ""}),
            _request(client, key=str(uuid4()), body=valid | {"decision_reason": "   "}),
            _request(client, key=str(uuid4()), body=valid | {"decision_reason": "x" * 1001}),
            _request(client, key=str(uuid4()), body=valid | {"decision_type": "UNKNOWN"}),
            _request(client, key=str(uuid4()), body=valid | {"incident_id": 1}),
        ]
    finally:
        _clear()

    assert {response.status_code for response in responses} == {422}


def test_success_response_and_trimmed_reason(monkeypatch) -> None:
    captured = {}

    def fake_decide(db, **kwargs):
        captured.update(kwargs)
        return CommandResult(
            {
                "incident_public_id": kwargs["incident_public_id"],
                "previous_status": "UNDER_REVIEW",
                "status": "DISPATCH_REQUESTED",
                "decision": {
                    "public_id": str(uuid4()),
                    "decision_type": kwargs["decision_type"],
                    "decision_reason": kwargs["decision_reason"],
                    "decided_by": {
                        "public_id": kwargs["current_user"].user.public_id,
                        "user_name": kwargs["current_user"].user.user_name,
                    },
                    "decided_at": "2026-07-21T03:00:00.000Z",
                },
                "version_no": 4,
            },
            "사건 판정을 저장했습니다.",
        )

    monkeypatch.setattr(
        "app.api.v1.incidents.incident_decision.decide_incident", fake_decide
    )
    try:
        response = _request(
            _client(_user("INCIDENT.DECIDE")),
            key=str(uuid4()),
            body={
                "decision_type": "REAL_RISK",
                "decision_reason": "  판정 사유  ",
                "expected_version_no": 3,
            },
        )
    finally:
        _clear()

    assert response.status_code == 200
    assert captured["decision_reason"] == "판정 사유"
    assert response.json()["data"]["version_no"] == 4
    assert "incident_id" not in response.text


def test_openapi_and_existing_endpoints() -> None:
    schema = app.openapi()
    operation = schema["paths"][
        "/api/v1/incidents/{incident_public_id}/decisions"
    ]["post"]
    header = next(
        item for item in operation["parameters"]
        if item["name"] == "Idempotency-Key"
    )
    assert header["required"] is True
    request_schema = schema["components"]["schemas"]["IncidentDecisionRequest"]
    assert request_schema["properties"]["expected_version_no"]["minimum"] == 0
    response_ref = operation["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    envelope = schema["components"]["schemas"][response_ref.rsplit("/", 1)[1]]
    assert envelope["properties"]["data"]["anyOf"][0]["$ref"].endswith(
        "IncidentDecisionResultData"
    )
    response_schema = schema["components"]["schemas"]["IncidentDecisionResultData"]
    assert "incident_id" not in response_schema["properties"]
    assert "get" in schema["paths"]["/api/v1/incidents"]
    for command in ("acknowledge", "claim", "review"):
        assert "post" in schema["paths"][
            f"/api/v1/incidents/{{incident_public_id}}/{command}"
        ]
