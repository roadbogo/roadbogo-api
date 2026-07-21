from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app


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
