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
from app.schemas.incident import IncidentListItem
from app.services import incident_query


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
    def __init__(self, *, scalar_values=(), scalar_rows=(), execute_rows=()):
        self.scalar_values = list(scalar_values)
        self.scalar_rows = list(scalar_rows)
        self.execute_rows = list(execute_rows)
        self.statements = []

    def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_values.pop(0)

    def scalars(self, statement):
        self.statements.append(statement)
        return ScalarRows(self.scalar_rows.pop(0))

    def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(all=lambda: self.execute_rows)


def _dt(hour=0):
    return datetime(2026, 7, 20, hour, 0, 0, 123000)


def _file(*, status="ACTIVE", deleted_at=None):
    return SimpleNamespace(
        public_id=str(uuid4()),
        file_status=status,
        deleted_at=deleted_at,
        object_key="must-not-leak",
        bucket_name="must-not-leak",
    )


def _incident(*, risk=True, detection=True, controller=True, version_no=0):
    original = _file()
    annotated = _file()
    frame = SimpleNamespace(original_file=original)
    inference = SimpleNamespace(video_frame=frame, annotated_file=annotated)
    representative = (
        SimpleNamespace(
            public_id=str(uuid4()),
            confidence=Decimal("0.8123"),
            bbox_x=Decimal("0.1"),
            bbox_y=Decimal("0.2"),
            bbox_width=Decimal("0.3"),
            bbox_height=Decimal("0.4"),
            detected_at=_dt(1),
            inference_run=inference,
            object_clas=SimpleNamespace(class_code="TIRE", class_name="타이어"),
        )
        if detection
        else None
    )
    risk_value = (
        SimpleNamespace(
            confidence_value=Decimal("0.9234"),
            confidence_calculation_type="MAX",
            repeat_count=3,
            rule_code="RISK-1",
            rule_version_snapshot="1",
            rule_snapshot_json={"reason_codes": ["STOPPED"]},
        )
        if risk
        else None
    )
    return SimpleNamespace(
        incident_id=91,
        public_id=str(uuid4()),
        incident_no="INC-1",
        incident_status="NEW",
        object_category="DEBRIS",
        object_clas=SimpleNamespace(class_code="TIRE", class_name="타이어"),
        current_risk_score=Decimal("82.50"),
        current_risk_grade="HIGH",
        latest_risk_evaluation=risk_value,
        representative_detection=representative,
        detection_count=2,
        duration_ms=4200,
        first_detected_at=_dt(1),
        last_detected_at=_dt(2),
        acknowledged_at=None,
        current_controller_user=(
            SimpleNamespace(public_id=str(uuid4()), user_name="관제자")
            if controller
            else None
        ),
        current_controller_user_id=7 if controller else None,
        cctv=SimpleNamespace(public_id=str(uuid4()), km_post=Decimal("12.3")),
        cctv_name_snapshot="CCTV 1",
        direction_snapshot="ASC",
        road_name_snapshot="도로",
        road_section_name_snapshot="구간",
        latitude_snapshot=Decimal("37.1"),
        longitude_snapshot=Decimal("127.1"),
        version_no=version_no,
        updated_at=_dt(3),
        created_at=_dt(0),
        claimed_at=None,
        closed_at=None,
        tracked_object=None,
        incident_status_histories=[],
        incident_decisions=[],
        dispatch_requests=[],
        incident_evidences=[],
        incident_notes=[],
    )


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


def test_summary_empty_preserves_all_zero_buckets() -> None:
    result = incident_query.summary(FakeSession(execute_rows=[]))

    assert result["total_count"] == 0
    assert result["risk_grade_counts"] == {
        "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0
    }
    assert result["object_category_counts"] == {
        "VEHICLE": 0, "DEBRIS": 0, "WILDLIFE": 0, "OTHER": 0
    }
    assert result["generated_at"].endswith("Z")


def test_summary_aggregates_status_grade_and_category() -> None:
    rows = [
        ("NEW", "HIGH", "DEBRIS", 2),
        ("DISPATCHED", "CRITICAL", "VEHICLE", 3),
        ("ON_SCENE", "CRITICAL", "VEHICLE", 1),
    ]

    result = incident_query.summary(FakeSession(execute_rows=rows))

    assert result["total_count"] == 6
    assert result["new_count"] == 2
    assert result["dispatch_in_progress_count"] == 4
    assert result["risk_grade_counts"]["CRITICAL"] == 4


def test_summary_adds_date_range_conditions() -> None:
    db = FakeSession(execute_rows=[])

    incident_query.summary(db, from_dt=_dt(1), to_dt=_dt(2))

    sql = str(db.statements[0])
    assert "incidents.first_detected_at >=" in sql
    assert "incidents.first_detected_at <=" in sql


def test_incident_conditions_use_current_user_and_null_controller() -> None:
    conditions = incident_query._incident_conditions(
        {"mine_only": True, "unclaimed_only": True, "current_user_id": 77}
    )
    rendered = " ".join(str(condition) for condition in conditions)

    assert "incidents.current_controller_user_id = " in rendered
    assert "incidents.current_controller_user_id IS NULL" in rendered
    assert any(value.value == 77 for condition in conditions for value in condition.get_children()
               if hasattr(value, "value"))


def test_incident_list_assembles_contract_and_priority_sort() -> None:
    incident = _incident(version_no=0)
    db = FakeSession(scalar_values=[1], scalar_rows=[[incident]])

    result = incident_query.list_incidents(
        db, page=1, size=20, filters={}, sort="priority,desc"
    )

    item = result["items"][0]
    assert item["version_no"] == 0
    assert item["representative_confidence"] == 0.9234
    assert item["claimed_by"]["user_name"] == "관제자"
    assert item["updated_at"] == "2026-07-20T03:00:00.123Z"
    assert "priority_order ASC" in str(db.statements[1])
    assert "incident_id" not in item
    assert "object_key" not in repr(item)
    assert "bucket_name" not in repr(item)


@pytest.mark.parametrize(
    ("risk", "detection", "expected"),
    [(True, True, 0.9234), (False, True, 0.8123), (False, False, None)],
)
def test_confidence_priority(risk, detection, expected) -> None:
    assert incident_query._confidence(
        _incident(risk=risk, detection=detection)
    ) == expected


def test_incident_list_nullable_class_and_claimed_by() -> None:
    incident = _incident(controller=False)
    incident.object_clas = None
    db = FakeSession(scalar_values=[1], scalar_rows=[[incident]])

    item = incident_query.list_incidents(
        db, page=1, size=20, filters={}, sort="priority,desc"
    )["items"][0]

    assert item["class_code"] is None
    assert item["class_name"] is None
    assert item["claimed_by"] is None


def test_incident_detail_chooses_active_data_and_counts(monkeypatch) -> None:
    incident = _incident(controller=False)
    old_decision = SimpleNamespace(
        public_id=str(uuid4()), superseded_at=_dt(2), decision_type="REAL_RISK",
        decision_reason="old", decided_by_user=SimpleNamespace(
            public_id=str(uuid4()), user_name="old"
        ), decided_at=_dt(1)
    )
    active_decision = SimpleNamespace(
        public_id=str(uuid4()), superseded_at=None, decision_type="REAL_RISK",
        decision_reason="active", decided_by_user=SimpleNamespace(
            public_id=str(uuid4()), user_name="decider"
        ), decided_at=_dt(2)
    )
    responder = SimpleNamespace(public_id=str(uuid4()), user_name="출동자")
    incident.incident_decisions = [old_decision, active_decision]
    incident.dispatch_requests = [
        SimpleNamespace(
            public_id=str(uuid4()), dispatch_status="CANCELLED", responder_user=responder,
            requested_at=_dt(3), updated_at=_dt(3)
        ),
        SimpleNamespace(
            public_id=str(uuid4()), dispatch_status="REQUESTED", responder_user=responder,
            requested_at=_dt(1), updated_at=_dt(1)
        ),
        SimpleNamespace(
            public_id=str(uuid4()), dispatch_status="ACCEPTED", responder_user=responder,
            requested_at=_dt(2), updated_at=_dt(2)
        ),
    ]
    incident.incident_status_histories = [
        SimpleNamespace(to_status="UNDER_REVIEW", changed_at=_dt(1)),
        SimpleNamespace(to_status="UNDER_REVIEW", changed_at=_dt(3)),
    ]
    incident.incident_evidences = [object(), object()]
    incident.incident_notes = [
        SimpleNamespace(deleted_at=None),
        SimpleNamespace(deleted_at=_dt(2)),
    ]
    monkeypatch.setattr(incident_query, "_base_incident", lambda *_: incident)

    result = incident_query.get_incident(object(), incident.public_id)

    assert result["controller"] is None
    assert result["decision"]["decision_reason"] == "active"
    assert result["active_dispatch"]["status"] == "ACCEPTED"
    assert result["timeline"]["review_started_at"] == "2026-07-20T03:00:00.123Z"
    assert result["evidence_count"] == 2
    assert result["memo_count"] == 1


def test_response_schema_forbids_internal_and_storage_fields() -> None:
    payload = incident_query.list_incidents(
        FakeSession(scalar_values=[1], scalar_rows=[[_incident()]]),
        page=1, size=20, filters={}, sort="priority,desc"
    )["items"][0]
    payload["incident_id"] = 1

    with pytest.raises(ValidationError):
        IncidentListItem.model_validate(payload)


def test_incident_openapi_uses_concrete_nested_schemas() -> None:
    schema = app.openapi()
    list_schema = schema["components"]["schemas"]["IncidentListData"]
    detail_schema = schema["components"]["schemas"]["IncidentDetailData"]
    item_schema = schema["components"]["schemas"]["IncidentListItem"]

    assert list_schema["properties"]["items"]["items"]["$ref"].endswith(
        "/IncidentListItem"
    )
    assert detail_schema["properties"]["object"]["$ref"].endswith(
        "/IncidentObjectData"
    )
    assert "incident_id" not in item_schema["properties"]
    assert item_schema["additionalProperties"] is False


def test_evidence_service_filters_sorts_and_hides_inactive_files() -> None:
    inactive = _file(status="MISSING")
    deleted = _file(deleted_at=_dt(3))
    frame = SimpleNamespace(original_file=inactive)
    inference = SimpleNamespace(video_frame=frame, annotated_file=deleted)
    detection = SimpleNamespace(
        public_id=str(uuid4()),
        detected_at=_dt(2),
        confidence=Decimal("0.9125"),
        bbox_x=Decimal("0.1"),
        bbox_y=Decimal("0.2"),
        bbox_width=Decimal("0.3"),
        bbox_height=Decimal("0.4"),
        object_clas=SimpleNamespace(class_code="TIRE", class_name="타이어"),
        inference_run=inference,
    )
    tracked = SimpleNamespace(public_id=str(uuid4()), external_track_id="TRACK-1")
    risk = SimpleNamespace(
        risk_score=Decimal("82.5"), risk_grade="HIGH", duration_ms=4200,
        repeat_count=3, tracked_object=tracked,
        rule_snapshot_json={"reason_codes": ["STOPPED"]},
    )
    evidence = SimpleNamespace(
        incident_evidence_id=1, evidence_type="PRIMARY", is_primary=1,
        added_at=_dt(1), detection=detection, video_frame=frame,
        risk_evaluation=risk,
    )
    db = FakeSession(scalar_values=[91, 1], scalar_rows=[[evidence]])

    result = incident_query.evidences(
        db, str(uuid4()), page=1, size=20,
        representative_only=True, sort="detected_at,desc"
    )

    item = result["items"][0]
    assert item["bbox"] == {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
    assert item["original_image_url"] is None
    assert item["annotated_image_url"] is None
    assert item["detected_at"] == "2026-07-20T02:00:00.123Z"
    sql = str(db.statements[2])
    assert "incident_evidences.is_primary =" in sql
    assert "coalesce(detections.detected_at, incident_evidences.added_at) DESC" in sql
    assert "object_key" not in repr(item)


def test_evidence_empty_list() -> None:
    db = FakeSession(scalar_values=[91, 0], scalar_rows=[[]])

    result = incident_query.evidences(
        db, str(uuid4()), page=1, size=20,
        representative_only=False, sort="detected_at,asc"
    )

    assert result["items"] == []
    assert result["pagination"]["total_pages"] == 0


def test_history_service_supports_null_and_present_actor() -> None:
    actor = SimpleNamespace(public_id=str(uuid4()), user_name="관제자")
    rows = [
        SimpleNamespace(
            public_id=str(uuid4()), from_status=None, to_status="NEW",
            actor_type="SYSTEM", actor_user=None, change_source="SYSTEM",
            reason_code=None, reason_text=None, changed_at=_dt(1),
            incident_status_history_id=1,
        ),
        SimpleNamespace(
            public_id=str(uuid4()), from_status="NEW", to_status="ACKNOWLEDGED",
            actor_type="USER", actor_user=actor, change_source="MANUAL",
            reason_code=None, reason_text="확인", changed_at=_dt(2),
            incident_status_history_id=2,
        ),
    ]
    db = FakeSession(scalar_values=[91, 2], scalar_rows=[rows])

    result = incident_query.histories(
        db, str(uuid4()), page=1, size=50, sort="changed_at,asc"
    )

    assert result["items"][0]["actor"] is None
    assert result["items"][1]["actor"]["user_name"] == "관제자"
    assert result["items"][1]["changed_at"] == "2026-07-20T02:00:00.123Z"
    assert "actor_user_id" not in repr(result["items"])
