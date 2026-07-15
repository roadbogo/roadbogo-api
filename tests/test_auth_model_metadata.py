import app.models  # noqa: F401

from sqlalchemy import JSON
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, INTEGER, SMALLINT

from app.core.database import Base


EXPECTED_TABLES = {
    "ai_model_versions",
    "ai_models",
    "audit_logs",
    "business_sequences",
    "cctv_streams",
    "cctvs",
    "detections",
    "dispatch_requests",
    "dispatch_state_transitions",
    "dispatch_status_histories",
    "event_outbox",
    "field_action_files",
    "field_action_reports",
    "files",
    "idempotency_keys",
    "incident_claims",
    "incident_decisions",
    "incident_evidences",
    "incident_files",
    "incident_notes",
    "incident_state_transitions",
    "incident_status_histories",
    "incidents",
    "inference_runs",
    "its_sync_runs",
    "model_version_classes",
    "notification_recipients",
    "notifications",
    "object_classes",
    "organizations",
    "permissions",
    "responder_profiles",
    "road_sections",
    "roads",
    "role_permissions",
    "roles",
    "track_observations",
    "tracked_objects",
    "tracking_sessions",
    "user_roles",
    "user_sessions",
    "users",
    "video_frames",
    "risk_evaluations",
}


def test_mvp_models_are_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_mvp_constraint_and_lookup_index_counts() -> None:
    foreign_keys = sum(
        len(table.foreign_key_constraints) for table in Base.metadata.tables.values()
    )
    lookup_indexes = {
        index.name
        for table in Base.metadata.tables.values()
        for index in table.indexes
        if index.name and index.name.startswith("ix_")
    }

    assert foreign_keys == 74
    assert len(lookup_indexes) == 26


def test_mariadb_specific_column_types_are_preserved() -> None:
    columns = [column for table in Base.metadata.tables.values() for column in table.columns]
    integer_columns = [
        column for column in columns if isinstance(column.type, (BIGINT, INTEGER, SMALLINT))
    ]
    datetime_columns = [column for column in columns if isinstance(column.type, DATETIME)]

    assert integer_columns
    assert all(column.type.unsigned for column in integer_columns)
    assert datetime_columns
    assert all(column.type.fsp == 3 for column in datetime_columns)
    assert sum(isinstance(column.type, JSON) for column in columns) == 13
    assert sum(column.computed is not None for column in columns) == 6


def test_foreign_key_names_and_delete_policies_are_explicit() -> None:
    foreign_keys = [
        constraint
        for table in Base.metadata.tables.values()
        for constraint in table.foreign_key_constraints
    ]

    assert all(constraint.name and constraint.name.startswith("fk_") for constraint in foreign_keys)
    assert {constraint.ondelete for constraint in foreign_keys} == {
        "CASCADE",
        "RESTRICT",
        "SET NULL",
    }
