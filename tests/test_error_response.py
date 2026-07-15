from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException
from app.main import create_app


def test_app_exception_uses_common_error_response() -> None:
    app = create_app()

    @app.get("/test/app-error")
    async def app_error() -> None:
        raise AppException()

    client = TestClient(app)

    response = client.get("/test/app-error")
    body = response.json()

    assert response.status_code == 400
    assert body["success"] is False
    assert body["error"]["code"] == "COMMON_BAD_REQUEST"
    assert body["trace_id"]


def test_http_401_403_405_use_common_mappings() -> None:
    app = create_app()

    @app.get("/test/unauthorized")
    async def unauthorized() -> None:
        raise StarletteHTTPException(status_code=401)

    @app.get("/test/forbidden")
    async def forbidden() -> None:
        raise StarletteHTTPException(status_code=403)

    client = TestClient(app)

    unauthorized_response = client.get("/test/unauthorized")
    forbidden_response = client.get("/test/forbidden")
    method_response = client.post("/api/v1/health")

    assert unauthorized_response.json()["error"]["code"] == "COMMON_UNAUTHORIZED"
    assert forbidden_response.json()["error"]["code"] == "COMMON_FORBIDDEN"
    assert method_response.status_code == 405
    assert method_response.json()["error"]["code"] == "COMMON_METHOD_NOT_ALLOWED"


def test_unknown_http_status_does_not_use_bad_request_code() -> None:
    app = create_app()

    @app.get("/test/teapot")
    async def teapot() -> None:
        raise StarletteHTTPException(status_code=418)

    client = TestClient(app)

    response = client.get("/test/teapot")

    assert response.status_code == 418
    assert response.json()["error"]["code"] == "COMMON_HTTP_ERROR"
