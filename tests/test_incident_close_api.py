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
        user=SimpleNamespace(user_id=9, public_id=str(uuid4()), user_name="관제자"),
        summary=SimpleNamespace(permissions=list(permissions), roles=["CONTROLLER"]),
    )


def test_close_api_contract_and_validation(monkeypatch) -> None:
    incident_id = str(uuid4())
    path = f"/api/v1/incidents/{incident_id}/close"
    body = {"closure_code": "FIELD_ACTION_COMPLETED", "closure_note": " 완료 확인 ", "expected_version_no": 10}
    captured = {}

    def execute(db, **kwargs):
        captured.update(kwargs)
        return CommandResult({
            "incident_public_id": incident_id, "previous_status": "ACTION_COMPLETED",
            "status": "CLOSED", "closure_code": "FIELD_ACTION_COMPLETED",
            "closed_by": {"public_id": str(uuid4()), "user_name": "관제자"},
            "closed_at": "2026-07-22T08:00:00.000Z", "version_no": 11,
        }, "사건이 최종 종료되었습니다.")

    monkeypatch.setattr("app.api.v1.incidents.incident_close.execute", execute)
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)
    no_auth = client.post(path, headers={"Idempotency-Key": str(uuid4())}, json=body)
    app.dependency_overrides[get_current_user] = lambda: user()
    denied = client.post(path, headers={"Idempotency-Key": str(uuid4())}, json=body)
    app.dependency_overrides[get_current_user] = lambda: user("INCIDENT.CLOSE")
    invalid = [
        client.post(path, json=body),
        client.post(path, headers={"Idempotency-Key": "bad"}, json=body),
        client.post(path, headers={"Idempotency-Key": str(uuid4())}),
        client.post(path, headers={"Idempotency-Key": str(uuid4())}, json={**body, "closure_code": "OTHER"}),
        client.post(path, headers={"Idempotency-Key": str(uuid4())}, json={**body, "closure_note": " "}),
        client.post(path, headers={"Idempotency-Key": str(uuid4())}, json={**body, "closure_note": "x" * 1001}),
        client.post(path, headers={"Idempotency-Key": str(uuid4())}, json={**body, "expected_version_no": -1}),
        client.post(path, headers={"Idempotency-Key": str(uuid4())}, json={**body, "extra": True}),
    ]
    success = client.post(path, headers={"Idempotency-Key": str(uuid4())}, json=body)
    app.dependency_overrides.clear()

    assert no_auth.status_code == 401 and denied.status_code == 403
    assert all(response.status_code == 422 for response in invalid)
    assert success.status_code == 200
    assert success.json()["data"]["closed_at"].endswith(".000Z")
    assert captured["closure_note"] == "완료 확인"
    schema = app.openapi()["paths"][path.replace(incident_id, "{incident_public_id}")]["post"]
    assert schema["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("IncidentCloseRequest")
    response_schema = schema["responses"]["200"]["content"]["application/json"]["schema"]
    assert "IncidentCloseData" in response_schema["$ref"]


@pytest.mark.parametrize(
    ("status_code", "code", "message", "details"),
    [
        (404, "INCIDENT_NOT_FOUND", "사건 정보를 찾을 수 없습니다.", None),
        (403, "INCIDENT_NOT_ASSIGNED_CONTROLLER", "해당 사건의 담당 관제자가 아닙니다.", None),
        (409, "INCIDENT_VERSION_CONFLICT", "사건 정보가 변경되었습니다. 최신 정보를 다시 확인해 주세요.", {"requested_version_no": 10, "current_version_no": 11}),
        (409, "INCIDENT_INVALID_STATE_TRANSITION", "사건 상태 전이를 수행할 수 없습니다.", {"current_status": "CLOSED", "requested_status": "CLOSED"}),
        (409, "INCIDENT_ACTION_REPORT_REQUIRED", "현장 조치 결과가 등록되지 않았습니다.", None),
        (409, "INCIDENT_IDEMPOTENCY_CONFLICT", "멱등 요청을 재사용할 수 없습니다.", None),
    ],
)
def test_close_api_preserves_service_error_envelope(
    monkeypatch, status_code, code, message, details,
) -> None:
    incident_id = str(uuid4())

    def raise_error(db, **kwargs):
        raise AppException(status_code, code, message, details)

    monkeypatch.setattr("app.api.v1.incidents.incident_close.execute", raise_error)
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: user("INCIDENT.CLOSE")
    client = TestClient(app)
    try:
        response = client.post(
            f"/api/v1/incidents/{incident_id}/close",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "closure_code": "FIELD_ACTION_COMPLETED",
                "closure_note": "민감한 종료 메모",
                "expected_version_no": 10,
            },
        )
    finally:
        app.dependency_overrides.clear()
    payload = response.json()
    assert response.status_code == status_code
    assert payload["success"] is False
    assert payload["error"] == {"code": code, "message": message, "details": details}
    assert payload["trace_id"]
    assert "민감한 종료 메모" not in response.text
    assert "user_id" not in response.text
