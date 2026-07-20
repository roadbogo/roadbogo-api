from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app


def _user():
    return SimpleNamespace(
        user=SimpleNamespace(user_id=7),
        summary=SimpleNamespace(permissions=["INCIDENT.READ_ALL"]),
    )


def test_incident_summary_rejects_naive_datetime() -> None:
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).get(
            "/api/v1/incidents/summary", params={"from": "2026-07-20T00:00:00"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["success"] is False


def test_incident_detail_rejects_invalid_uuid() -> None:
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).get("/api/v1/incidents/not-a-uuid")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_incident_history_route_uses_public_uuid(monkeypatch) -> None:
    public_id = uuid4()
    captured = {}

    def fake_histories(db, value, **kwargs):
        captured["public_id"] = value
        return {
            "items": [],
            "pagination": {"page": 1, "size": 50, "total_elements": 0, "total_pages": 0},
        }

    monkeypatch.setattr("app.api.v1.incidents.incident_query.histories", fake_histories)
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).get(f"/api/v1/incidents/{public_id}/histories")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["public_id"] == str(public_id)
    assert response.json()["data"]["pagination"]["total_pages"] == 0
