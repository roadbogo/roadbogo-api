from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app


def _user():
    return SimpleNamespace(
        user=SimpleNamespace(user_id=8),
        summary=SimpleNamespace(permissions=["CCTV.READ"]),
    )


def test_cctv_list_rejects_invalid_enum() -> None:
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).get(
            "/api/v1/cctvs", params={"operational_status": "FAILED"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_cctv_detail_does_not_expose_stream_secret(monkeypatch) -> None:
    public_id = uuid4()
    data = {
        "public_id": str(public_id),
        "cctv_code": "C-1",
        "external_its_cctv_id": None,
        "cctv_name": "CCTV 1",
        "source_type": "ITS",
        "direction_code": "ASC",
        "latitude": 37.0,
        "longitude": 127.0,
        "km_post": None,
        "operational_status": "NORMAL",
        "is_active": True,
        "road": {"public_id": str(uuid4()), "road_code": "R", "road_name": "Road"},
        "road_section": {
            "public_id": str(uuid4()),
            "section_code": "S",
            "section_name": "Section",
        },
        "stream": {
            "available": True,
            "stream_type": "LIVE",
            "protocol_type": "HLS",
            "stream_status": "ACTIVE",
        },
        "last_successful_sync_at": None,
        "created_at": "2026-07-20T00:00:00.000Z",
        "updated_at": "2026-07-20T00:00:00.000Z",
    }
    monkeypatch.setattr("app.api.v1.cctvs.cctv_query.get_cctv", lambda *_: data)
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).get(f"/api/v1/cctvs/{public_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "endpoint_secret_ref" not in response.text
