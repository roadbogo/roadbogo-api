from fastapi.testclient import TestClient

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
