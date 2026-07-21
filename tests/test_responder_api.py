from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.services import responder_query


class FakeSession:
    def __init__(self, total=0, rows=()):
        self.total = total
        self.rows = list(rows)
        self.statements = []

    def scalar(self, statement):
        self.statements.append(statement)
        return self.total

    def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(all=lambda: self.rows)


def _user(*permissions):
    return SimpleNamespace(
        user=SimpleNamespace(user_id=7),
        summary=SimpleNamespace(permissions=list(permissions), roles=[]),
    )


def test_responder_query_contract_and_filters() -> None:
    user = SimpleNamespace(public_id=str(uuid4()), user_name="출동자")
    profile = SimpleNamespace(
        responder_code="RSP-1", duty_status="AVAILABLE",
        is_dispatch_enabled=1, coverage_area="경부"
    )
    organization = SimpleNamespace(
        public_id=str(uuid4()), organization_name="출동팀"
    )
    db = FakeSession(1, [(user, profile, organization, False)])

    result = responder_query.list_responders(
        db, page=1, size=20, keyword=" 출동 ",
        duty_status=None, available_only=True
    )

    item = result["items"][0]
    assert item["public_id"] == user.public_id
    assert item["has_active_dispatch"] is False
    assert result["pagination"]["total_pages"] == 1
    assert "user_id" not in item
    sql = str(db.statements[0])
    assert "users.account_status =" in sql
    assert "users.deleted_at IS NULL" in sql
    assert "roles.role_code =" in sql
    assert "responder_profiles.is_dispatch_enabled =" in sql
    assert "responder_profiles.duty_status =" in sql
    assert "NOT (EXISTS" in sql


def test_available_only_false_returns_busy_and_active_dispatch() -> None:
    user = SimpleNamespace(public_id=str(uuid4()), user_name="출동자")
    profile = SimpleNamespace(
        responder_code="RSP-1", duty_status="BUSY",
        is_dispatch_enabled=1, coverage_area=None
    )
    db = FakeSession(1, [(user, profile, None, True)])

    result = responder_query.list_responders(
        db, page=1, size=20, keyword=None,
        duty_status="BUSY", available_only=False
    )

    assert result["items"][0]["duty_status"] == "BUSY"
    assert result["items"][0]["organization"] is None
    assert result["items"][0]["has_active_dispatch"] is True
    assert "NOT (EXISTS" not in str(db.statements[0])


def test_responder_api_auth_permission_and_validation() -> None:
    app.dependency_overrides[get_db] = lambda: object()
    try:
        no_auth = TestClient(app).get("/api/v1/responders")
        app.dependency_overrides[get_current_user] = lambda: _user()
        denied = TestClient(app).get("/api/v1/responders")
        app.dependency_overrides[get_current_user] = lambda: _user("DISPATCH.ASSIGN")
        invalid = TestClient(app).get(
            "/api/v1/responders?page=0&size=101&duty_status=INVALID"
        )
    finally:
        app.dependency_overrides.clear()

    assert no_auth.status_code == 401
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "AUTH_PERMISSION_DENIED"
    assert invalid.status_code == 422


def test_responder_openapi_is_concrete_and_defaults_available() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/api/v1/responders"]["get"]
    parameter = next(p for p in operation["parameters"] if p["name"] == "available_only")
    assert parameter["schema"]["default"] is True
    list_schema = schema["components"]["schemas"]["ResponderListData"]
    assert list_schema["properties"]["items"]["items"]["$ref"].endswith(
        "ResponderListItem"
    )
    item = schema["components"]["schemas"]["ResponderListItem"]
    assert not ({"user_id", "responder_profile_id", "organization_id", "role_id"} & set(item["properties"]))
