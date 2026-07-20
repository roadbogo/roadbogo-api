from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.schemas.cctv import CctvListItem
from app.services import cctv_query


class ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def unique(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class FakeSession:
    def __init__(self, *, scalar_values=(), scalar_rows=()):
        self.scalar_values = list(scalar_values)
        self.scalar_rows = list(scalar_rows)
        self.statements = []

    def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_values.pop(0)

    def scalars(self, statement):
        self.statements.append(statement)
        return ScalarRows(self.scalar_rows.pop(0))


def _dt(hour=0):
    return datetime(2026, 7, 20, hour, 0, 0, 123000)


def _cctv(*, streams=(), deleted_at=None):
    return SimpleNamespace(
        cctv_id=1,
        public_id=str(uuid4()),
        cctv_code="C-1",
        external_its_cctv_id=None,
        cctv_name="CCTV 1",
        source_type="ITS",
        direction_code="ASC",
        latitude=Decimal("37.1"),
        longitude=Decimal("127.1"),
        km_post=None,
        operational_status="NORMAL",
        is_active=1,
        deleted_at=deleted_at,
        cctv_streams=list(streams),
        road_section=SimpleNamespace(
            public_id=str(uuid4()),
            section_code="S-1",
            section_name="구간",
            road=SimpleNamespace(
                public_id=str(uuid4()), road_code="R-1", road_name="도로"
            ),
        ),
        last_successful_sync_at=_dt(1),
        created_at=_dt(0),
        updated_at=_dt(2),
    )


def _stream(*, status="ACTIVE", primary=True, valid_to=None):
    return SimpleNamespace(
        stream_type="LIVE",
        protocol_type="HLS",
        endpoint_secret_ref="must-not-leak",
        stream_status=status,
        is_primary=primary,
        valid_from=_dt(0),
        valid_to=valid_to,
    )


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


def test_cctv_list_filters_deleted_rows_and_builds_active_stream() -> None:
    cctv = _cctv(streams=[_stream()])
    sync = SimpleNamespace(used_fallback_data=1)
    db = FakeSession(scalar_values=[1], scalar_rows=[[cctv], [sync]])

    result = cctv_query.list_cctvs(
        db, page=1, size=20, filters={}, sort="cctv_name,asc"
    )

    assert result["items"][0]["has_stream"] is True
    assert result["fallback_used"] is True
    assert result["items"][0]["last_successful_sync_at"].endswith(".123Z")
    assert "cctvs.deleted_at IS NULL" in str(db.statements[0])
    assert "endpoint_secret_ref" not in repr(result)


@pytest.mark.parametrize(
    ("filters", "fragment"),
    [
        ({"direction_code": "ASC"}, "cctvs.direction_code ="),
        ({"operational_status": "NORMAL"}, "cctvs.operational_status ="),
        ({"source_type": "ITS"}, "cctvs.source_type ="),
        ({"min_latitude": 37.0, "max_longitude": 128.0}, "cctvs.latitude >="),
    ],
)
def test_cctv_list_applies_filters(filters, fragment) -> None:
    db = FakeSession(scalar_values=[0], scalar_rows=[[], []])

    cctv_query.list_cctvs(
        db, page=1, size=20, filters=filters, sort="cctv_name,asc"
    )

    assert fragment in str(db.statements[0])


def test_stream_excludes_expired_non_primary_and_inactive() -> None:
    now = _dt(3)

    assert cctv_query._stream(_cctv(streams=[]), now) is None
    assert cctv_query._stream(
        _cctv(streams=[_stream(valid_to=_dt(2))]), now
    ) is None
    assert cctv_query._stream(
        _cctv(streams=[_stream(primary=False), _stream(status="ERROR")]), now
    ) is None


def test_fallback_query_uses_only_completed_cctv_metadata() -> None:
    db = FakeSession(scalar_values=[0], scalar_rows=[[], []])

    result = cctv_query.list_cctvs(
        db, page=1, size=20, filters={}, sort="cctv_name,asc"
    )
    sql = str(db.statements[-1])

    assert result["fallback_used"] is False
    assert "its_sync_runs.sync_type =" in sql
    assert "its_sync_runs.run_status IN" in sql
    assert "its_sync_runs.finished_at IS NOT NULL" in sql
    assert "its_sync_runs.finished_at DESC" in sql


def test_cctv_detail_404() -> None:
    with pytest.raises(Exception) as error:
        cctv_query.get_cctv(FakeSession(scalar_rows=[[]]), str(uuid4()))

    assert error.value.code == "CCTV_NOT_FOUND"


def test_cctv_detail_stream_contract_has_no_secret() -> None:
    cctv = _cctv(streams=[_stream()])

    result = cctv_query.get_cctv(
        FakeSession(scalar_rows=[[cctv]]), cctv.public_id
    )

    assert result["stream"] == {
        "available": True,
        "stream_type": "LIVE",
        "protocol_type": "HLS",
        "stream_status": "ACTIVE",
    }
    assert "endpoint_secret_ref" not in repr(result)
    assert "cctv_id" not in result


def test_cctv_schema_forbids_internal_fields() -> None:
    cctv = _cctv()
    payload = cctv_query.list_cctvs(
        FakeSession(scalar_values=[1], scalar_rows=[[cctv], []]),
        page=1, size=20, filters={}, sort="cctv_name,asc"
    )["items"][0]
    payload["endpoint_secret_ref"] = "secret"

    with pytest.raises(ValidationError):
        CctvListItem.model_validate(payload)


def test_cctv_openapi_uses_concrete_item_schema() -> None:
    schema = app.openapi()
    list_schema = schema["components"]["schemas"]["CctvListData"]
    item_schema = schema["components"]["schemas"]["CctvListItem"]

    assert list_schema["properties"]["items"]["items"]["$ref"].endswith(
        "/CctvListItem"
    )
    assert item_schema["additionalProperties"] is False
    assert "endpoint_secret_ref" not in item_schema["properties"]
