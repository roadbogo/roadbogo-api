from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.core.database import get_db
from app.core.exceptions import AppException
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
        client.post(
            f"/api/v1/dispatches/{dispatch_id}/depart",
            headers={"Idempotency-Key": str(uuid4())},
        ),
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


@pytest.mark.parametrize(
    ("path", "command", "previous_status", "status"),
    [
        ("depart", "depart", "ACCEPTED", "DEPARTED"),
        ("en-route", "en-route", "DEPARTED", "EN_ROUTE"),
        ("arrive", "arrive", "EN_ROUTE", "ARRIVED"),
        ("start-action", "start-action", "ARRIVED", "ACTION_IN_PROGRESS"),
    ],
)
def test_each_progress_router_passes_exact_command(
    monkeypatch, path, command, previous_status, status
) -> None:
    dispatch_id = str(uuid4())
    key = str(uuid4())
    captured = {}

    def fake_execute(db, **kwargs):
        captured.update(kwargs)
        return CommandResult(
            {
                "dispatch": {
                    "public_id": dispatch_id,
                    "previous_status": previous_status,
                    "status": status,
                    "occurred_at": "2026-07-22T06:00:00.000Z",
                    "version_no": 2,
                },
                "incident": {
                    "public_id": str(uuid4()),
                    "status": "DISPATCHED",
                    "version_no": 5,
                },
            },
            "완료",
        )

    monkeypatch.setattr("app.api.v1.dispatches.dispatch_progress.execute", fake_execute)
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: user("DISPATCH.UPDATE_OWN")
    try:
        response = TestClient(app).post(
            f"/api/v1/dispatches/{dispatch_id}/{path}",
            headers={"Idempotency-Key": key},
            json={"expected_version_no": 1},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["command"] == command
    assert captured["dispatch_public_id"] == dispatch_id
    assert captured["expected_version_no"] == 1
    assert captured["idempotency_key"] == key
    assert response.json()["data"]["dispatch"]["occurred_at"].endswith(".000Z")
    assert "user_id" not in response.text


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (404, "DISPATCH_NOT_FOUND"),
        (409, "DISPATCH_VERSION_CONFLICT"),
        (409, "DISPATCH_INVALID_STATE_TRANSITION"),
        (409, "DISPATCH_IDEMPOTENCY_CONFLICT"),
        (409, "INCIDENT_INVALID_STATE_TRANSITION"),
    ],
)
def test_progress_api_preserves_service_error_envelope(monkeypatch, status_code, code) -> None:
    def raise_error(db, **kwargs):
        raise AppException(status_code, code, "진행 명령 오류")

    monkeypatch.setattr("app.api.v1.dispatches.dispatch_progress.execute", raise_error)
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: user("DISPATCH.UPDATE_OWN")
    try:
        response = TestClient(app).post(
            f"/api/v1/dispatches/{uuid4()}/depart",
            headers={"Idempotency-Key": str(uuid4())},
            json={"expected_version_no": 1},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status_code
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == code
