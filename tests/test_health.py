import re

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.main import create_app

UTC_Z_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def test_health_check_success_response() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health")
    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["message"] is None
    assert body["trace_id"]
    assert body["data"]["status"] == "UP"
    assert body["data"]["service"]
    assert body["data"]["version"] == "0.1.0"
    assert body["data"]["environment"] == "local"
    assert UTC_Z_PATTERN.match(body["data"]["server_time"])
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Trace-ID"] == body["trace_id"]


def test_request_id_header_is_preserved() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health", headers={"X-Request-ID": "request-123"})

    assert response.headers["X-Request-ID"] == "request-123"
    assert response.json()["trace_id"] == response.headers["X-Trace-ID"]


def test_missing_url_uses_common_404_response() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/missing")
    body = response.json()

    assert response.status_code == 404
    assert body["success"] is False
    assert body["error"]["code"] == "COMMON_RESOURCE_NOT_FOUND"
    assert body["trace_id"]


def test_unhandled_error_uses_common_500_response() -> None:
    app = create_app()
    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("private detail")

    app.include_router(router, prefix="/test")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/test/boom")
    body = response.json()

    assert response.status_code == 500
    assert body["success"] is False
    assert body["error"]["code"] == "COMMON_INTERNAL_ERROR"
    assert body["error"]["details"] is None
    assert "private detail" not in body["error"]["message"]
    assert body["trace_id"]
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Trace-ID"] == body["trace_id"]


def test_validation_error_uses_common_response() -> None:
    app = create_app()
    router = APIRouter()

    @router.get("/items/{item_id}")
    async def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    app.include_router(router, prefix="/test")
    client = TestClient(app)

    response = client.get("/test/items/not-a-number")
    body = response.json()

    assert response.status_code == 422
    assert body["success"] is False
    assert body["error"]["code"] == "COMMON_VALIDATION_ERROR"
    assert body["error"]["details"]["fields"]
    assert body["trace_id"]
