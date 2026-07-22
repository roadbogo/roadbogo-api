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


def test_completion_api_auth_validation_success_and_openapi(monkeypatch) -> None:
    dispatch_id = str(uuid4())
    path = f"/api/v1/dispatches/{dispatch_id}/complete-action"
    body = {
        "expected_version_no": 4,
        "action_type": " DEBRIS_REMOVAL ",
        "action_detail": " 낙하물을 제거했습니다. ",
    }
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)
    no_auth = client.post(path, headers={"Idempotency-Key": str(uuid4())}, json=body)
    app.dependency_overrides[get_current_user] = lambda: user()
    denied = client.post(path, headers={"Idempotency-Key": str(uuid4())}, json=body)
    app.dependency_overrides[get_current_user] = lambda: user("DISPATCH.UPDATE_OWN")
    invalid = [
        client.post(path, json=body),
        client.post(path, headers={"Idempotency-Key": "invalid"}, json=body),
        client.post(path, headers={"Idempotency-Key": str(uuid4())}),
        client.post(
            path,
            headers={"Idempotency-Key": str(uuid4())},
            json=body | {"expected_version_no": -1},
        ),
        client.post(
            path,
            headers={"Idempotency-Key": str(uuid4())},
            json=body | {"action_type": "   "},
        ),
        client.post(
            path,
            headers={"Idempotency-Key": str(uuid4())},
            json=body | {"action_detail": "   "},
        ),
        client.post(
            path,
            headers={"Idempotency-Key": str(uuid4())},
            json=body | {"action_type": "A" * 61},
        ),
        client.post(
            path,
            headers={"Idempotency-Key": str(uuid4())},
            json=body | {"action_detail": "a" * 5001},
        ),
        client.post(
            path,
            headers={"Idempotency-Key": str(uuid4())},
            json={"action_type": "DEBRIS_REMOVAL", "action_detail": "낙하물을 제거했습니다."},
        ),
        client.post(
            path,
            headers={"Idempotency-Key": str(uuid4())},
            json=body | {"internal_id": 1},
        ),
    ]
    captured = {}

    def fake_execute(db, **kwargs):
        captured.update(kwargs)
        return CommandResult(
            {
                "dispatch": {
                    "public_id": dispatch_id,
                    "previous_status": "ACTION_IN_PROGRESS",
                    "status": "ACTION_COMPLETED",
                    "action_completed_at": "2026-07-22T07:00:00.000Z",
                    "version_no": 5,
                },
                "incident": {
                    "public_id": str(uuid4()),
                    "previous_status": "ACTION_IN_PROGRESS",
                    "status": "ACTION_COMPLETED",
                    "version_no": 8,
                },
                "responder": {"public_id": str(uuid4()), "duty_status": "AVAILABLE"},
                "report": {
                    "public_id": str(uuid4()),
                    "action_type": kwargs["action_type"],
                    "action_detail": kwargs["action_detail"],
                    "action_started_at": "2026-07-22T06:40:00.000Z",
                    "action_completed_at": "2026-07-22T07:00:00.000Z",
                },
            },
            "현장 조치를 완료했습니다.",
        )

    monkeypatch.setattr("app.api.v1.dispatches.dispatch_completion.execute", fake_execute)
    key = str(uuid4())
    success = client.post(path, headers={"Idempotency-Key": key}, json=body)
    schema = app.openapi()
    app.dependency_overrides.clear()

    assert no_auth.status_code == 401 and denied.status_code == 403
    assert {response.status_code for response in invalid} == {422}
    assert success.status_code == 200
    assert captured["dispatch_public_id"] == dispatch_id
    assert captured["expected_version_no"] == 4
    assert captured["action_type"] == "DEBRIS_REMOVAL"
    assert captured["action_detail"] == "낙하물을 제거했습니다."
    assert captured["idempotency_key"] == key
    assert "internal_id" not in success.text and "user_id" not in success.text
    operation = schema["paths"]["/api/v1/dispatches/{dispatch_public_id}/complete-action"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "DispatchCompleteActionRequest"
    )
    response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert "DispatchCompletionData" in response_ref


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (404, "DISPATCH_NOT_FOUND"),
        (409, "DISPATCH_VERSION_CONFLICT"),
        (409, "DISPATCH_INVALID_STATE_TRANSITION"),
        (409, "INCIDENT_INVALID_STATE_TRANSITION"),
        (409, "DISPATCH_RESPONDER_STATUS_CONFLICT"),
        (409, "DISPATCH_ACTION_REPORT_ALREADY_EXISTS"),
        (409, "DISPATCH_IDEMPOTENCY_CONFLICT"),
    ],
)
def test_completion_api_preserves_service_error_envelope(monkeypatch, status_code, code) -> None:
    dispatch_id = str(uuid4())
    path = f"/api/v1/dispatches/{dispatch_id}/complete-action"

    def raise_error(db, **kwargs):
        raise AppException(status_code, code, "완료 처리 오류")

    monkeypatch.setattr("app.api.v1.dispatches.dispatch_completion.execute", raise_error)
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: user("DISPATCH.UPDATE_OWN")
    client = TestClient(app)
    try:
        response = client.post(
            path,
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "expected_version_no": 4,
                "action_type": "DEBRIS_REMOVAL",
                "action_detail": "낙하물을 제거했습니다.",
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == status_code
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == code
    assert response.json()["trace_id"]
    assert "user_id" not in response.text
    assert "action_detail" not in response.text
