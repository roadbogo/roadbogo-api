from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.services.incident_command import CommandResult


def user(*permissions):
    return SimpleNamespace(
        user=SimpleNamespace(user_id=9, public_id=str(uuid4()), user_name="담당자"),
        summary=SimpleNamespace(permissions=list(permissions), roles=["RESPONDER"]),
    )


def test_progress_api_openapi_auth_validation_and_success(monkeypatch) -> None:
    dispatch_id = str(uuid4())
    paths = ["depart", "en-route", "arrive", "start-action"]
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)
    no_auth = client.post(
        f"/api/v1/dispatches/{dispatch_id}/depart",
        headers={"Idempotency-Key": str(uuid4())},
        json={"expected_version_no": 1},
    )
    app.dependency_overrides[get_current_user] = lambda: user()
    denied = client.post(
        f"/api/v1/dispatches/{dispatch_id}/depart",
        headers={"Idempotency-Key": str(uuid4())},
        json={"expected_version_no": 1},
    )
    app.dependency_overrides[get_current_user] = lambda: user("DISPATCH.UPDATE_OWN")
    invalid = [
        client.post(f"/api/v1/dispatches/{dispatch_id}/depart", json={"expected_version_no": 1}),
        client.post(
            f"/api/v1/dispatches/{dispatch_id}/depart",
            headers={"Idempotency-Key": "invalid"}, json={"expected_version_no": 1},
        ),
        client.post(
            f"/api/v1/dispatches/{dispatch_id}/depart",
            headers={"Idempotency-Key": str(uuid4())}, json={"expected_version_no": -1},
        ),
        client.post(
            f"/api/v1/dispatches/{dispatch_id}/depart",
            headers={"Idempotency-Key": str(uuid4())},
            json={"expected_version_no": 1, "internal_id": 1},
        ),
    ]

    def fake_execute(db, **kwargs):
        return CommandResult(
            {
                "dispatch": {
                    "public_id": kwargs["dispatch_public_id"],
                    "previous_status": "ACCEPTED",
                    "status": "DEPARTED",
                    "occurred_at": "2026-07-22T06:00:00.000Z",
                    "version_no": 2,
                },
                "incident": {
                    "public_id": str(uuid4()), "status": "DISPATCHED", "version_no": 5
                },
            },
            "출동을 시작했습니다.",
        )

    monkeypatch.setattr("app.api.v1.dispatches.dispatch_progress.execute", fake_execute)
    success = client.post(
        f"/api/v1/dispatches/{dispatch_id}/depart",
        headers={"Idempotency-Key": str(uuid4())},
        json={"expected_version_no": 1},
    )
    schema = app.openapi()
    app.dependency_overrides.clear()

    assert no_auth.status_code == 401 and denied.status_code == 403
    assert {response.status_code for response in invalid} == {422}
    assert success.status_code == 200
    assert success.json()["data"]["dispatch"]["occurred_at"].endswith(".000Z")
    assert "internal_id" not in success.text and "user_id" not in success.text
    for path in paths:
        operation = schema["paths"][f"/api/v1/dispatches/{{dispatch_public_id}}/{path}"]["post"]
        assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
            "DispatchVersionRequest"
        )
        response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        assert "DispatchProgressData" in response_ref
