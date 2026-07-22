from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
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
