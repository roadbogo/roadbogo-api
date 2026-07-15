from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def test_trace_id_header_is_preserved_when_uuid() -> None:
    client = TestClient(create_app())
    trace_id = str(uuid4())

    response = client.get("/api/v1/health", headers={"X-Trace-ID": trace_id})

    assert response.headers["X-Trace-ID"] == trace_id
    assert response.json()["trace_id"] == trace_id


def test_too_long_context_headers_are_replaced() -> None:
    client = TestClient(create_app())
    too_long = "x" * 129

    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": too_long, "X-Trace-ID": too_long},
    )

    assert response.headers["X-Request-ID"] != too_long
    assert response.headers["X-Trace-ID"] != too_long
    assert response.json()["trace_id"] == response.headers["X-Trace-ID"]
    UUID(response.headers["X-Request-ID"])
    UUID(response.headers["X-Trace-ID"])


def test_invalid_context_headers_are_replaced() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "request-123", "X-Trace-ID": "trace-123"},
    )

    assert response.headers["X-Request-ID"] != "request-123"
    assert response.headers["X-Trace-ID"] != "trace-123"
    assert response.json()["trace_id"] == response.headers["X-Trace-ID"]
    UUID(response.headers["X-Request-ID"])
    UUID(response.headers["X-Trace-ID"])


def test_blank_context_headers_are_replaced() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "   ", "X-Trace-ID": "   "},
    )

    UUID(response.headers["X-Request-ID"])
    UUID(response.headers["X-Trace-ID"])
