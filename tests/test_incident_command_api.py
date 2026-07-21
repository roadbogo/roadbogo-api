from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.services.incident_command import CommandResult


def _current_user(*permissions):
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


def test_command_authentication_is_required() -> None:
    try:
        response = _client().post(
            f"/api/v1/incidents/{uuid4()}/acknowledge",
            headers={"Idempotency-Key": str(uuid4())},
            json={"expected_version_no": 0},
        )
    finally:
        _clear()

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_ACCESS_TOKEN_MISSING"


def test_command_permission_is_required() -> None:
    try:
        response = _client(_current_user()).post(
            f"/api/v1/incidents/{uuid4()}/claim",
            headers={"Idempotency-Key": str(uuid4())},
            json={"expected_version_no": 1},
        )
    finally:
        _clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_PERMISSION_DENIED"


def test_role_without_permission_is_denied() -> None:
    user = _current_user()
    user.summary.roles = ["CONTROLLER"]
    try:
        response = _client(user).post(
            f"/api/v1/incidents/{uuid4()}/review",
            headers={"Idempotency-Key": str(uuid4())},
            json={"expected_version_no": 2},
        )
    finally:
        _clear()

    assert response.status_code == 403


def test_command_request_validation() -> None:
    client = _client(_current_user("INCIDENT.CLAIM"))
    public_id = uuid4()
    try:
        missing_header = client.post(
            f"/api/v1/incidents/{public_id}/claim",
            json={"expected_version_no": 0},
        )
        invalid_header = client.post(
            f"/api/v1/incidents/{public_id}/claim",
            headers={"Idempotency-Key": "invalid"},
            json={"expected_version_no": 0},
        )
        invalid_path = client.post(
            "/api/v1/incidents/not-a-uuid/claim",
            headers={"Idempotency-Key": str(uuid4())},
            json={"expected_version_no": 0},
        )
        negative = client.post(
            f"/api/v1/incidents/{public_id}/claim",
            headers={"Idempotency-Key": str(uuid4())},
            json={"expected_version_no": -1},
        )
        extra = client.post(
            f"/api/v1/incidents/{public_id}/claim",
            headers={"Idempotency-Key": str(uuid4())},
            json={"expected_version_no": 0, "incident_id": 1},
        )
    finally:
        _clear()

    assert {response.status_code for response in (
        missing_header, invalid_header, invalid_path, negative, extra
    )} == {422}


def test_each_command_calls_service_and_returns_contract(monkeypatch) -> None:
    calls = []

    def fake_execute(db, **kwargs):
        calls.append(kwargs)
        command = kwargs["command"]
        data = {
            "incident_public_id": kwargs["incident_public_id"],
            "previous_status": {
                "acknowledge": "NEW", "claim": "ACKNOWLEDGED", "review": "CLAIMED"
            }[command],
            "status": {
                "acknowledge": "ACKNOWLEDGED", "claim": "CLAIMED",
                "review": "UNDER_REVIEW"
            }[command],
            "version_no": kwargs["expected_version_no"] + 1,
        }
        actor = {
            "public_id": kwargs["current_user"].user.public_id,
            "user_name": kwargs["current_user"].user.user_name,
        }
        if command == "acknowledge":
            data.update(acknowledged_by=actor, acknowledged_at="2026-07-21T00:00:00.000Z")
        elif command == "claim":
            data.update(claimed_by=actor, claimed_at="2026-07-21T00:00:00.000Z")
        else:
            data["review_started_at"] = "2026-07-21T00:00:00.000Z"
        return CommandResult(data, "ok")

    monkeypatch.setattr("app.api.v1.incidents.incident_command.execute_command", fake_execute)
    user = _current_user("INCIDENT.CLAIM", "INCIDENT.DECIDE")
    client = _client(user)
    try:
        responses = [
            client.post(
                f"/api/v1/incidents/{uuid4()}/{command}",
                headers={"Idempotency-Key": str(uuid4())},
                json={"expected_version_no": version},
            )
            for command, version in (("acknowledge", 0), ("claim", 1), ("review", 2))
        ]
    finally:
        _clear()

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert [call["command"] for call in calls] == ["acknowledge", "claim", "review"]
    assert all("incident_id" not in response.text for response in responses)
    assert all(response.json()["data"]["version_no"] > 0 for response in responses)


def test_command_openapi_contract_is_concrete() -> None:
    schema = app.openapi()
    for command, model in (
        ("acknowledge", "IncidentAcknowledgeData"),
        ("claim", "IncidentClaimData"),
        ("review", "IncidentReviewData"),
    ):
        operation = schema["paths"][
            f"/api/v1/incidents/{{incident_public_id}}/{command}"
        ]["post"]
        header = next(
            parameter for parameter in operation["parameters"]
            if parameter["name"] == "Idempotency-Key"
        )
        assert header["required"] is True
        response_ref = operation["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        envelope = schema["components"]["schemas"][response_ref.rsplit("/", 1)[1]]
        assert envelope["properties"]["data"]["anyOf"][0]["$ref"].endswith(model)

    request_schema = schema["components"]["schemas"]["IncidentCommandRequest"]
    assert request_schema["properties"]["expected_version_no"]["minimum"] == 0
    forbidden = {"incident_id", "user_id", "actor_user_id", "organization_id", "Secret"}
    for name in ("IncidentAcknowledgeData", "IncidentClaimData", "IncidentReviewData"):
        assert not (set(schema["components"]["schemas"][name]["properties"]) & forbidden)


def test_existing_get_endpoints_remain_registered() -> None:
    paths = app.openapi()["paths"]

    assert "get" in paths["/api/v1/incidents"]
    assert "get" in paths["/api/v1/incidents/summary"]
    assert "get" in paths["/api/v1/incidents/{incident_public_id}"]
