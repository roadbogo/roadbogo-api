from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.core.database import get_db
from app.core.exceptions import AppException
from app.dependencies.auth import get_current_user
from app.main import app
from app.services import action_file
from app.services.file_storage import FileStorage, get_file_storage

JPEG = b"\xff\xd8\xffdata"
PNG = b"\x89PNG\r\n\x1a\ndata"
WEBP = b"RIFF1234WEBPdata"


@pytest.mark.parametrize(
    ("name", "mime", "data"),
    [
        ("a.jpg", "image/jpeg", JPEG),
        ("a.jpeg", "image/jpeg", JPEG),
        ("a.png", "image/png", PNG),
        ("a.webp", "image/webp", WEBP),
    ],
)
def test_file_validation_success(name, mime, data):
    safe, _, actual = action_file.validate_file("../../" + name, mime, data)
    assert safe == name and actual == mime


@pytest.mark.parametrize(
    ("name", "mime", "data", "code"),
    [
        ("a.jpg", "image/jpeg", b"", "FILE_EMPTY"),
        ("a.gif", "image/gif", b"GIF89a", "FILE_INVALID_TYPE"),
        ("a", "image/jpeg", JPEG, "FILE_NAME_INVALID"),
        ("a.jpg", "image/png", JPEG, "FILE_INVALID_TYPE"),
    ],
)
def test_file_validation_errors(name, mime, data, code):
    with pytest.raises(AppException) as exc:
        action_file.validate_file(name, mime, data)
    assert exc.value.code == code


def test_file_too_large():
    with pytest.raises(AppException) as exc:
        action_file.validate_file("a.jpg", "image/jpeg", b"x" * (action_file.MAX_SIZE + 1))
    assert exc.value.status_code == 413


class Client:
    def __init__(self):
        self.calls = []

    def put_object(self, *a, **kw):
        self.calls.append("put")

    def remove_object(self, *a):
        self.calls.append("remove")

    def presigned_get_object(self, *a, **kw):
        self.calls.append(kw["expires"].total_seconds())
        return "signed"


def test_storage_adapter():
    c = Client()
    s = FileStorage(c, "bucket")
    s.put_object("key", JPEG, "image/jpeg")
    s.remove_object("key")
    assert s.presigned_get_url("key") == "signed" and c.calls == ["put", "remove", 900.0]


def user(*permissions):
    return SimpleNamespace(
        user=SimpleNamespace(user_id=1, public_id=str(uuid4()), user_name="u"),
        summary=SimpleNamespace(permissions=list(permissions), roles=["RESPONDER"]),
    )


def test_api_openapi_and_validation():
    path = f"/api/v1/dispatches/{uuid4()}/action-files"
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_file_storage] = lambda: SimpleNamespace()
    client = TestClient(app)
    assert client.get(path).status_code == 401
    app.dependency_overrides[get_current_user] = lambda: user()
    assert client.get(path).status_code == 403
    app.dependency_overrides[get_current_user] = lambda: user(
        "FILE.UPLOAD_ACTION", "FILE.READ_ASSIGNED"
    )
    response = client.post(
        path, headers={"Idempotency-Key": str(uuid4())}, data={"photo_phase": "BAD"}
    )
    app.dependency_overrides.clear()
    assert response.status_code == 422
    spec = app.openapi()["paths"]["/api/v1/dispatches/{dispatch_public_id}/action-files"]
    assert "post" in spec and "get" in spec
