from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.services.incident_command import CommandResult


def _user(*permissions):
    return SimpleNamespace(
        user=SimpleNamespace(user_id=9, public_id=str(uuid4()), user_name="담당자"),
        summary=SimpleNamespace(permissions=list(permissions), roles=["RESPONDER"]),
    )


def test_dispatch_responder_auth_permissions_and_body_validation() -> None:
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)
    dispatch_id = str(uuid4())
    try:
        no_auth = client.get("/api/v1/dispatches/mine")
        app.dependency_overrides[get_current_user] = lambda: _user()
        denied_read = client.get("/api/v1/dispatches/mine")
        denied_update = client.post(
            f"/api/v1/dispatches/{dispatch_id}/accept",
            headers={"Idempotency-Key": str(uuid4())},
            json={"expected_version_no": 0},
        )
        app.dependency_overrides[get_current_user] = lambda: _user("DISPATCH.UPDATE_OWN")
        missing_key = client.post(
            f"/api/v1/dispatches/{dispatch_id}/accept",
            json={"expected_version_no": 0},
        )
        invalid_reason = client.post(
            f"/api/v1/dispatches/{dispatch_id}/reject",
            headers={"Idempotency-Key": str(uuid4())},
            json={"expected_version_no": 0, "rejection_reason": "   "},
        )
        extra = client.post(
            f"/api/v1/dispatches/{dispatch_id}/accept",
            headers={"Idempotency-Key": str(uuid4())},
            json={"expected_version_no": 0, "internal_id": 1},
        )
    finally:
        app.dependency_overrides.clear()

    assert no_auth.status_code == 401
    assert denied_read.status_code == 403 and denied_update.status_code == 403
    assert missing_key.status_code == 422
    assert invalid_reason.status_code == 422 and extra.status_code == 422


def test_dispatch_responder_openapi_uses_concrete_schemas() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    assert paths["/api/v1/dispatches/mine"]["get"]["responses"]["200"]
    assert paths["/api/v1/dispatches/{dispatch_public_id}"]["get"]["responses"]["200"]
    accept = paths["/api/v1/dispatches/{dispatch_public_id}/accept"]["post"]
    reject = paths["/api/v1/dispatches/{dispatch_public_id}/reject"]["post"]
    assert accept["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "DispatchVersionRequest"
    )
    assert reject["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "DispatchRejectRequest"
    )
    assert next(
        parameter for parameter in accept["parameters"] if parameter["name"] == "Idempotency-Key"
    )["required"] is True
    accept_response = accept["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    reject_response = reject["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert accept_response != reject_response
    assert "DispatchAcceptData" in accept_response
    assert "DispatchRejectData" in reject_response


def test_accept_and_reject_success_responses_have_distinct_contracts(monkeypatch) -> None:
    dispatch_id = str(uuid4())
    incident_id = str(uuid4())
    user = _user("DISPATCH.UPDATE_OWN")

    def fake_execute(db, **kwargs):
        if kwargs["command"] == "accept":
            return CommandResult(
                {
                    "dispatch": {
                        "public_id": dispatch_id,
                        "previous_status": "REQUESTED",
                        "status": "ACCEPTED",
                        "accepted_at": "2026-07-21T00:00:00.000Z",
                        "version_no": 1,
                    },
                    "incident": {
                        "public_id": incident_id,
                        "previous_status": "DISPATCH_REQUESTED",
                        "status": "DISPATCHED",
                        "version_no": 5,
                    },
                },
                "출동 요청을 수락했습니다.",
            )
        return CommandResult(
            {
                "dispatch": {
                    "public_id": dispatch_id,
                    "previous_status": "REQUESTED",
                    "status": "REJECTED",
                    "rejection_reason": "다른 현장 대응 중",
                    "version_no": 1,
                },
                "incident": {
                    "public_id": incident_id,
                    "status": "DISPATCH_REQUESTED",
                    "version_no": 5,
                },
                "responder": {
                    "public_id": user.user.public_id,
                    "duty_status": "AVAILABLE",
                },
            },
            "출동 요청을 거절했습니다.",
        )

    monkeypatch.setattr("app.api.v1.dispatches.dispatch_command.execute", fake_execute)
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    key = str(uuid4())
    try:
        accept = client.post(
            f"/api/v1/dispatches/{dispatch_id}/accept",
            headers={"Idempotency-Key": key},
            json={"expected_version_no": 0},
        )
        accept_replay = client.post(
            f"/api/v1/dispatches/{dispatch_id}/accept",
            headers={"Idempotency-Key": key},
            json={"expected_version_no": 0},
        )
        reject = client.post(
            f"/api/v1/dispatches/{dispatch_id}/reject",
            headers={"Idempotency-Key": key},
            json={"expected_version_no": 0, "rejection_reason": "다른 현장 대응 중"},
        )
    finally:
        app.dependency_overrides.clear()

    assert accept.status_code == accept_replay.status_code == reject.status_code == 200
    assert accept.json()["data"] == accept_replay.json()["data"]
    accept_data = accept.json()["data"]
    reject_data = reject.json()["data"]
    assert "rejection_reason" not in accept_data["dispatch"]
    assert "responder" not in accept_data
    assert "accepted_at" not in reject_data["dispatch"]
    assert "previous_status" not in reject_data["incident"]
