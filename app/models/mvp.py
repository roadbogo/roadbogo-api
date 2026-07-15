from typing import Optional
import datetime
import decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Computed,
    DATE,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    VARBINARY,
    text,
)
from sqlalchemy.dialects.mysql import (
    BIGINT,
    CHAR,
    DATETIME,
    DECIMAL,
    INTEGER,
    SMALLINT,
    TEXT,
    TINYINT,
    VARCHAR,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

__all__ = [
    "AiModel",
    "AiModelVersion",
    "AuditLog",
    "BusinessSequence",
    "Cctv",
    "CctvStream",
    "Detection",
    "DispatchRequest",
    "DispatchStateTransition",
    "DispatchStatusHistory",
    "EventOutbox",
    "FieldActionFile",
    "FieldActionReport",
    "File",
    "IdempotencyKey",
    "Incident",
    "IncidentClaim",
    "IncidentDecision",
    "IncidentEvidence",
    "IncidentFile",
    "IncidentNote",
    "IncidentStateTransition",
    "IncidentStatusHistory",
    "InferenceRun",
    "ItsSyncRun",
    "ModelVersionClass",
    "Notification",
    "NotificationRecipient",
    "ObjectClass",
    "Organization",
    "Permission",
    "ResponderProfile",
    "RiskEvaluation",
    "Road",
    "RoadSection",
    "Role",
    "RolePermission",
    "TrackedObject",
    "TrackingSession",
    "TrackObservation",
    "User",
    "UserRole",
    "UserSession",
    "VideoFrame",
]


class AiModel(Base):
    __tablename__ = "ai_models"
    __table_args__ = (
        CheckConstraint(
            "`model_category` in ('VEHICLE','DEBRIS','WILDLIFE')", name="ck_ai_models_category"
        ),
        CheckConstraint("`model_status` in ('ACTIVE','INACTIVE')", name="ck_ai_models_status"),
        Index("uk_ai_models_code", "model_code", unique=True),
        Index("uk_ai_models_public_id", "public_id", unique=True),
    )

    ai_model_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    model_code: Mapped[str] = mapped_column(VARCHAR(60), nullable=False)
    model_name: Mapped[str] = mapped_column(VARCHAR(120), nullable=False)
    model_category: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    execution_order: Mapped[int] = mapped_column(
        SMALLINT(5, unsigned=True), nullable=False, server_default=text("1")
    )
    model_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'ACTIVE'")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    description: Mapped[Optional[str]] = mapped_column(VARCHAR(1000))

    ai_model_versions: Mapped[list["AiModelVersion"]] = relationship(
        "AiModelVersion", back_populates="ai_model"
    )


class BusinessSequence(Base):
    __tablename__ = "business_sequences"
    __table_args__ = (CheckConstraint("`last_value` >= 0", name="ck_business_sequences_value"),)

    sequence_code: Mapped[str] = mapped_column(VARCHAR(40), primary_key=True)
    sequence_date: Mapped[datetime.date] = mapped_column(DATE, primary_key=True)
    last_value: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), nullable=False, server_default=text("0")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )


class DispatchStateTransition(Base):
    __tablename__ = "dispatch_state_transitions"
    __table_args__ = (
        CheckConstraint(
            "`actor_scope` in ('CONTROLLER','RESPONDER','SYSTEM','DEVICE','ADMIN')",
            name="ck_dispatch_transition_actor",
        ),
        Index(
            "uk_dispatch_state_transitions", "from_status", "to_status", "actor_scope", unique=True
        ),
    )

    dispatch_state_transition_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    from_status: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    to_status: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    actor_scope: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )


class EventOutbox(Base):
    __tablename__ = "event_outbox"
    __table_args__ = (
        CheckConstraint(
            "`publish_status` in ('PENDING','PROCESSING','PUBLISHED','FAILED','DEAD')",
            name="ck_event_outbox_status",
        ),
        Index("ix_event_outbox_worker", "publish_status", "next_attempt_at", "event_outbox_id"),
        Index("uk_event_outbox_uuid", "event_uuid", unique=True),
    )

    event_outbox_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    event_uuid: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    aggregate_public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    event_type: Mapped[str] = mapped_column(VARCHAR(80), nullable=False)
    payload_json: Mapped[object] = mapped_column(JSON, nullable=False)
    publish_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'PENDING'")
    )
    retry_count: Mapped[int] = mapped_column(
        INTEGER(10, unsigned=True), nullable=False, server_default=text("0")
    )
    next_attempt_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    locked_by: Mapped[Optional[str]] = mapped_column(VARCHAR(100))
    locked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    last_error: Mapped[Optional[str]] = mapped_column(VARCHAR(1000))


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        CheckConstraint("`expires_at` > `created_at`", name="ck_idempotency_keys_expiry"),
        CheckConstraint(
            "`processing_status` in ('PROCESSING','COMPLETED','FAILED')",
            name="ck_idempotency_keys_status",
        ),
        Index("ix_idempotency_keys_expiry", "expires_at", "processing_status"),
        Index("uk_idempotency_keys", "scope_code", "idempotency_key", unique=True),
    )

    idempotency_key_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    scope_code: Mapped[str] = mapped_column(VARCHAR(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(VARCHAR(180), nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'PROCESSING'")
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    resource_type: Mapped[Optional[str]] = mapped_column(VARCHAR(60))
    resource_public_id: Mapped[Optional[str]] = mapped_column(CHAR(36))
    response_code: Mapped[Optional[int]] = mapped_column(INTEGER(10, unsigned=True))
    response_snapshot_json: Mapped[Optional[object]] = mapped_column(JSON)


class IncidentStateTransition(Base):
    __tablename__ = "incident_state_transitions"
    __table_args__ = (
        CheckConstraint(
            "`actor_scope` in ('SYSTEM','CONTROLLER','RESPONDER','ADMIN')",
            name="ck_incident_transition_actor",
        ),
        Index(
            "uk_incident_state_transitions", "from_status", "to_status", "actor_scope", unique=True
        ),
    )

    incident_state_transition_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    from_status: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    to_status: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    actor_scope: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )


class ItsSyncRun(Base):
    __tablename__ = "its_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "`finished_at` is null or `finished_at` >= `started_at`", name="ck_its_sync_runs_period"
        ),
        CheckConstraint(
            "`run_status` in ('RUNNING','SUCCEEDED','PARTIAL','FAILED')",
            name="ck_its_sync_runs_status",
        ),
        Index("ix_its_sync_runs_started", "started_at", "run_status"),
        Index("uk_its_sync_runs_idempotency", "idempotency_key", unique=True),
        Index("uk_its_sync_runs_public_id", "public_id", unique=True),
    )

    its_sync_run_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(VARCHAR(120), nullable=False)
    sync_type: Mapped[str] = mapped_column(
        VARCHAR(30), nullable=False, server_default=text("'CCTV_METADATA'")
    )
    run_status: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    used_fallback_data: Mapped[int] = mapped_column(
        TINYINT(1), nullable=False, server_default=text("0")
    )
    requested_count: Mapped[int] = mapped_column(
        INTEGER(10, unsigned=True), nullable=False, server_default=text("0")
    )
    inserted_count: Mapped[int] = mapped_column(
        INTEGER(10, unsigned=True), nullable=False, server_default=text("0")
    )
    updated_count: Mapped[int] = mapped_column(
        INTEGER(10, unsigned=True), nullable=False, server_default=text("0")
    )
    failed_count: Mapped[int] = mapped_column(
        INTEGER(10, unsigned=True), nullable=False, server_default=text("0")
    )
    started_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    error_code: Mapped[Optional[str]] = mapped_column(VARCHAR(80))
    error_message: Mapped[Optional[str]] = mapped_column(VARCHAR(1000))
    trace_id: Mapped[Optional[str]] = mapped_column(VARCHAR(100))
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "`severity` in ('INFO','WARNING','HIGH','CRITICAL')", name="ck_notifications_severity"
        ),
        Index("uk_notifications_dedup", "deduplication_key", unique=True),
        Index("uk_notifications_public_id", "public_id", unique=True),
    )

    notification_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(VARCHAR(180), nullable=False)
    notification_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    severity: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    title: Mapped[str] = mapped_column(VARCHAR(200), nullable=False)
    body: Mapped[str] = mapped_column(VARCHAR(2000), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    resource_type: Mapped[Optional[str]] = mapped_column(VARCHAR(50))
    resource_public_id: Mapped[Optional[str]] = mapped_column(CHAR(36))
    payload_json: Mapped[Optional[object]] = mapped_column(JSON)

    notification_recipients: Mapped[list["NotificationRecipient"]] = relationship(
        "NotificationRecipient", back_populates="notification"
    )


class ObjectClass(Base):
    __tablename__ = "object_classes"
    __table_args__ = (
        CheckConstraint(
            "`object_category` in ('VEHICLE','DEBRIS','WILDLIFE')",
            name="ck_object_classes_category",
        ),
        Index("uk_object_classes_code", "class_code", unique=True),
    )

    object_class_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    class_code: Mapped[str] = mapped_column(VARCHAR(60), nullable=False)
    class_name: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    object_category: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    is_incident_target: Mapped[int] = mapped_column(
        TINYINT(1), nullable=False, server_default=text("1")
    )
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )

    model_version_classes: Mapped[list["ModelVersionClass"]] = relationship(
        "ModelVersionClass", back_populates="object_clas"
    )
    tracked_objects: Mapped[list["TrackedObject"]] = relationship(
        "TrackedObject", back_populates="object_clas"
    )
    detections: Mapped[list["Detection"]] = relationship("Detection", back_populates="object_clas")
    incidents: Mapped[list["Incident"]] = relationship("Incident", back_populates="object_clas")


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "`organization_type` in ('SYSTEM','CONTROL_CENTER','DISPATCH_TEAM','AI_TEAM','OTHER')",
            name="ck_organizations_type",
        ),
        ForeignKeyConstraint(
            ["parent_organization_id"],
            ["organizations.organization_id"],
            name="fk_organizations_parent",
        ),
        Index("fk_organizations_parent", "parent_organization_id"),
        Index("uk_organizations_code", "organization_code", unique=True),
        Index("uk_organizations_public_id", "public_id", unique=True),
    )

    organization_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    organization_code: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    organization_name: Mapped[str] = mapped_column(VARCHAR(120), nullable=False)
    organization_type: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    parent_organization_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))

    parent_organization: Mapped[Optional["Organization"]] = relationship(
        "Organization", remote_side=[organization_id], back_populates="parent_organization_reverse"
    )
    parent_organization_reverse: Mapped[list["Organization"]] = relationship(
        "Organization", remote_side=[parent_organization_id], back_populates="parent_organization"
    )
    users: Mapped[list["User"]] = relationship("User", back_populates="organization")


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        CheckConstraint(
            "`scope_type` in ('GLOBAL','ORGANIZATION','ASSIGNED','OWN')",
            name="ck_permissions_scope",
        ),
        Index("uk_permissions_code", "permission_code", unique=True),
    )

    permission_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    permission_code: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    permission_name: Mapped[str] = mapped_column(VARCHAR(120), nullable=False)
    resource_code: Mapped[str] = mapped_column(VARCHAR(60), nullable=False)
    action_code: Mapped[str] = mapped_column(VARCHAR(40), nullable=False)
    scope_type: Mapped[str] = mapped_column(
        VARCHAR(30), nullable=False, server_default=text("'GLOBAL'")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    description: Mapped[Optional[str]] = mapped_column(VARCHAR(500))

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="permission"
    )


class Road(Base):
    __tablename__ = "roads"
    __table_args__ = (
        CheckConstraint(
            "`road_type` in ('EXPRESSWAY','NATIONAL_ROAD','OTHER')", name="ck_roads_type"
        ),
        Index("uk_roads_code", "road_code", unique=True),
        Index("uk_roads_public_id", "public_id", unique=True),
    )

    road_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    road_code: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    road_name: Mapped[str] = mapped_column(VARCHAR(120), nullable=False)
    road_type: Mapped[str] = mapped_column(
        VARCHAR(30), nullable=False, server_default=text("'EXPRESSWAY'")
    )
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )

    road_sections: Mapped[list["RoadSection"]] = relationship("RoadSection", back_populates="road")


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (Index("uk_roles_code", "role_code", unique=True),)

    role_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    role_code: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    role_name: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    is_system_role: Mapped[int] = mapped_column(
        TINYINT(1), nullable=False, server_default=text("1")
    )
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    description: Mapped[Optional[str]] = mapped_column(VARCHAR(500))

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="role"
    )
    user_roles: Mapped[list["UserRole"]] = relationship("UserRole", back_populates="role")


class RoadSection(Base):
    __tablename__ = "road_sections"
    __table_args__ = (
        CheckConstraint(
            "`start_km` is null or `end_km` is null or `end_km` >= `start_km`",
            name="ck_road_sections_km",
        ),
        ForeignKeyConstraint(["road_id"], ["roads.road_id"], name="fk_road_sections_road"),
        Index("fk_road_sections_road", "road_id"),
        Index("uk_road_sections_code", "section_code", unique=True),
        Index("uk_road_sections_public_id", "public_id", unique=True),
    )

    road_section_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    road_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    section_code: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    section_name: Mapped[str] = mapped_column(VARCHAR(150), nullable=False)
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    start_point_name: Mapped[Optional[str]] = mapped_column(VARCHAR(120))
    end_point_name: Mapped[Optional[str]] = mapped_column(VARCHAR(120))
    start_km: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(8, 3))
    end_km: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(8, 3))
    region_name: Mapped[Optional[str]] = mapped_column(VARCHAR(100))

    road: Mapped["Road"] = relationship("Road", back_populates="road_sections")
    cctvs: Mapped[list["Cctv"]] = relationship("Cctv", back_populates="road_section")
    incidents: Mapped[list["Incident"]] = relationship("Incident", back_populates="road_section")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "`account_status` in ('ACTIVE','INACTIVE','LOCKED')", name="ck_users_account_status"
        ),
        ForeignKeyConstraint(
            ["deactivated_by_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_users_deactivated_by",
        ),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.organization_id"],
            ondelete="SET NULL",
            name="fk_users_organization",
        ),
        Index("fk_users_deactivated_by", "deactivated_by_user_id"),
        Index("fk_users_organization", "organization_id"),
        Index("ix_users_status_org", "account_status", "organization_id"),
        Index("uk_users_email", "email", unique=True),
        Index("uk_users_public_id", "public_id", unique=True),
    )

    user_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    email: Mapped[str] = mapped_column(VARCHAR(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    user_name: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    account_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'ACTIVE'")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    organization_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    phone_encrypted: Mapped[Optional[bytes]] = mapped_column(VARBINARY(512))
    last_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    deactivated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    deactivated_by_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))

    deactivated_by_user: Mapped[Optional["User"]] = relationship(
        "User", remote_side=[user_id], back_populates="deactivated_by_user_reverse"
    )
    deactivated_by_user_reverse: Mapped[list["User"]] = relationship(
        "User", remote_side=[deactivated_by_user_id], back_populates="deactivated_by_user"
    )
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization", back_populates="users"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="actor_user")
    files_created_by_users: Mapped[list["File"]] = relationship(
        "File", foreign_keys="[File.created_by_user_id]", back_populates="created_by_user"
    )
    files_deleted_by_users: Mapped[list["File"]] = relationship(
        "File", foreign_keys="[File.deleted_by_user_id]", back_populates="deleted_by_user"
    )
    notification_recipients: Mapped[list["NotificationRecipient"]] = relationship(
        "NotificationRecipient", back_populates="user"
    )
    responder_profiles: Mapped[list["ResponderProfile"]] = relationship(
        "ResponderProfile", back_populates="user"
    )
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="granted_by_user"
    )
    user_roles_assigned_by_users: Mapped[list["UserRole"]] = relationship(
        "UserRole", foreign_keys="[UserRole.assigned_by_user_id]", back_populates="assigned_by_user"
    )
    user_roles_users: Mapped[list["UserRole"]] = relationship(
        "UserRole", foreign_keys="[UserRole.user_id]", back_populates="user"
    )
    user_sessions: Mapped[list["UserSession"]] = relationship("UserSession", back_populates="user")
    incidents_acknowledged_by_users: Mapped[list["Incident"]] = relationship(
        "Incident",
        foreign_keys="[Incident.acknowledged_by_user_id]",
        back_populates="acknowledged_by_user",
    )
    incidents_current_controller_users: Mapped[list["Incident"]] = relationship(
        "Incident",
        foreign_keys="[Incident.current_controller_user_id]",
        back_populates="current_controller_user",
    )
    dispatch_requests_assigned_by_users: Mapped[list["DispatchRequest"]] = relationship(
        "DispatchRequest",
        foreign_keys="[DispatchRequest.assigned_by_user_id]",
        back_populates="assigned_by_user",
    )
    dispatch_requests_responder_users: Mapped[list["DispatchRequest"]] = relationship(
        "DispatchRequest",
        foreign_keys="[DispatchRequest.responder_user_id]",
        back_populates="responder_user",
    )
    incident_claims: Mapped[list["IncidentClaim"]] = relationship(
        "IncidentClaim", back_populates="controller_user"
    )
    incident_decisions: Mapped[list["IncidentDecision"]] = relationship(
        "IncidentDecision", back_populates="decided_by_user"
    )
    incident_files: Mapped[list["IncidentFile"]] = relationship(
        "IncidentFile", back_populates="uploaded_by_user"
    )
    incident_notes_created_by_users: Mapped[list["IncidentNote"]] = relationship(
        "IncidentNote",
        foreign_keys="[IncidentNote.created_by_user_id]",
        back_populates="created_by_user",
    )
    incident_notes_deleted_by_users: Mapped[list["IncidentNote"]] = relationship(
        "IncidentNote",
        foreign_keys="[IncidentNote.deleted_by_user_id]",
        back_populates="deleted_by_user",
    )
    incident_status_histories: Mapped[list["IncidentStatusHistory"]] = relationship(
        "IncidentStatusHistory", back_populates="actor_user"
    )
    dispatch_status_histories: Mapped[list["DispatchStatusHistory"]] = relationship(
        "DispatchStatusHistory", back_populates="actor_user"
    )
    field_action_reports: Mapped[list["FieldActionReport"]] = relationship(
        "FieldActionReport", back_populates="created_by_user"
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("`actor_type` in ('USER','SYSTEM','DEVICE')", name="ck_audit_logs_actor"),
        CheckConstraint(
            "`result_status` in ('SUCCESS','FAILURE','DENIED')", name="ck_audit_logs_result"
        ),
        ForeignKeyConstraint(
            ["actor_user_id"], ["users.user_id"], ondelete="SET NULL", name="fk_audit_logs_actor"
        ),
        Index("ix_audit_logs_actor_time", "actor_user_id", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_public_id", "created_at"),
        Index("uk_audit_logs_public_id", "public_id", unique=True),
    )

    audit_log_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    actor_type: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    action_code: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(VARCHAR(60), nullable=False)
    result_status: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    actor_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    resource_public_id: Mapped[Optional[str]] = mapped_column(CHAR(36))
    before_json: Mapped[Optional[object]] = mapped_column(JSON)
    after_json: Mapped[Optional[object]] = mapped_column(JSON)
    reason_text: Mapped[Optional[str]] = mapped_column(VARCHAR(1000))
    trace_id: Mapped[Optional[str]] = mapped_column(VARCHAR(100))
    request_ip_hash: Mapped[Optional[str]] = mapped_column(CHAR(64))

    actor_user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")


class Cctv(Base):
    __tablename__ = "cctvs"
    __table_args__ = (
        CheckConstraint(
            "`direction_code` in ('ASC','DESC','BOTH','UNKNOWN')", name="ck_cctvs_direction"
        ),
        CheckConstraint("`latitude` between -90 and 90", name="ck_cctvs_latitude"),
        CheckConstraint("`longitude` between -180 and 180", name="ck_cctvs_longitude"),
        CheckConstraint(
            "`operational_status` in ('NORMAL','DELAYED','FAULT','INACTIVE','UNKNOWN')",
            name="ck_cctvs_status",
        ),
        CheckConstraint("`source_type` in ('ITS','MANUAL','DEMO')", name="ck_cctvs_source_type"),
        ForeignKeyConstraint(
            ["road_section_id"], ["road_sections.road_section_id"], name="fk_cctvs_road_section"
        ),
        Index("ix_cctvs_location", "latitude", "longitude"),
        Index("ix_cctvs_section_status", "road_section_id", "operational_status", "is_active"),
        Index("uk_cctvs_code", "cctv_code", unique=True),
        Index("uk_cctvs_external_its_id", "external_its_cctv_id", unique=True),
        Index("uk_cctvs_public_id", "public_id", unique=True),
    )

    cctv_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    road_section_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    cctv_code: Mapped[str] = mapped_column(VARCHAR(60), nullable=False)
    cctv_name: Mapped[str] = mapped_column(VARCHAR(150), nullable=False)
    source_type: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    direction_code: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'UNKNOWN'")
    )
    latitude: Mapped[decimal.Decimal] = mapped_column(DECIMAL(10, 7), nullable=False)
    longitude: Mapped[decimal.Decimal] = mapped_column(DECIMAL(10, 7), nullable=False)
    operational_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'NORMAL'")
    )
    is_active: Mapped[int] = mapped_column(TINYINT(1), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    external_its_cctv_id: Mapped[Optional[str]] = mapped_column(VARCHAR(100))
    km_post: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(8, 3))
    last_successful_sync_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    metadata_json: Mapped[Optional[object]] = mapped_column(JSON)
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))

    road_section: Mapped["RoadSection"] = relationship("RoadSection", back_populates="cctvs")
    cctv_streams: Mapped[list["CctvStream"]] = relationship("CctvStream", back_populates="cctv")
    tracking_sessions: Mapped[list["TrackingSession"]] = relationship(
        "TrackingSession", back_populates="cctv"
    )
    video_frames: Mapped[list["VideoFrame"]] = relationship("VideoFrame", back_populates="cctv")
    tracked_objects: Mapped[list["TrackedObject"]] = relationship(
        "TrackedObject", back_populates="cctv"
    )
    incidents: Mapped[list["Incident"]] = relationship("Incident", back_populates="cctv")


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint(
            "`access_level` in ('RESTRICTED','INTERNAL','PUBLIC')", name="ck_files_access"
        ),
        CheckConstraint(
            "`file_status` in ('PENDING','ACTIVE','DELETED','MISSING','QUARANTINED')",
            name="ck_files_status",
        ),
        CheckConstraint("`size_bytes` > 0", name="ck_files_size"),
        CheckConstraint(
            "`storage_provider` in ('LOCAL','MINIO','S3','OTHER')", name="ck_files_provider"
        ),
        ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_files_created_by",
        ),
        ForeignKeyConstraint(
            ["deleted_by_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_files_deleted_by",
        ),
        Index("fk_files_created_by", "created_by_user_id"),
        Index("fk_files_deleted_by", "deleted_by_user_id"),
        Index("ix_files_hash", "sha256_hash", "size_bytes"),
        Index("uk_files_public_id", "public_id", unique=True),
        Index("uk_files_storage_key", "storage_provider", "bucket_name", "object_key", unique=True),
    )

    file_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    storage_provider: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    bucket_name: Mapped[str] = mapped_column(
        VARCHAR(120), nullable=False, server_default=text("''")
    )
    object_key: Mapped[str] = mapped_column(VARCHAR(500), nullable=False)
    original_file_name: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    mime_type: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    sha256_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    file_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'ACTIVE'")
    )
    access_level: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'RESTRICTED'")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    deleted_by_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    delete_reason: Mapped[Optional[str]] = mapped_column(VARCHAR(500))

    created_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_user_id], back_populates="files_created_by_users"
    )
    deleted_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[deleted_by_user_id], back_populates="files_deleted_by_users"
    )
    ai_model_versions: Mapped[list["AiModelVersion"]] = relationship(
        "AiModelVersion", back_populates="model_file"
    )
    video_frames_original_files: Mapped[list["VideoFrame"]] = relationship(
        "VideoFrame", foreign_keys="[VideoFrame.original_file_id]", back_populates="original_file"
    )
    video_frames_preprocessed_files: Mapped[list["VideoFrame"]] = relationship(
        "VideoFrame",
        foreign_keys="[VideoFrame.preprocessed_file_id]",
        back_populates="preprocessed_file",
    )
    inference_runs: Mapped[list["InferenceRun"]] = relationship(
        "InferenceRun", back_populates="annotated_file"
    )
    incident_files: Mapped[list["IncidentFile"]] = relationship(
        "IncidentFile", back_populates="file"
    )
    field_action_files: Mapped[list["FieldActionFile"]] = relationship(
        "FieldActionFile", back_populates="file"
    )


class NotificationRecipient(Base):
    __tablename__ = "notification_recipients"
    __table_args__ = (
        CheckConstraint(
            "`delivery_status` in ('PENDING','SENT','FAILED')",
            name="ck_notification_recipients_status",
        ),
        ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.notification_id"],
            ondelete="CASCADE",
            name="fk_notification_recipients_notification",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
            name="fk_notification_recipients_user",
        ),
        Index(
            "ix_notification_recipients_user_read",
            "user_id",
            "read_at",
            "notification_recipient_id",
        ),
        Index("uk_notification_recipients", "notification_id", "user_id", unique=True),
    )

    notification_recipient_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    notification_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    delivery_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'PENDING'")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    delivered_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    read_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    failure_reason: Mapped[Optional[str]] = mapped_column(VARCHAR(1000))

    notification: Mapped["Notification"] = relationship(
        "Notification", back_populates="notification_recipients"
    )
    user: Mapped["User"] = relationship("User", back_populates="notification_recipients")


class ResponderProfile(Base):
    __tablename__ = "responder_profiles"
    __table_args__ = (
        CheckConstraint(
            "`duty_status` in ('AVAILABLE','BUSY','OFF_DUTY','UNAVAILABLE')",
            name="ck_responder_profiles_status",
        ),
        ForeignKeyConstraint(["user_id"], ["users.user_id"], name="fk_responder_profiles_user"),
        Index("uk_responder_profiles_code", "responder_code", unique=True),
        Index("uk_responder_profiles_user", "user_id", unique=True),
    )

    responder_profile_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    responder_code: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    duty_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'OFF_DUTY'")
    )
    is_dispatch_enabled: Mapped[int] = mapped_column(
        TINYINT(1), nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    coverage_area: Mapped[Optional[str]] = mapped_column(VARCHAR(255))

    user: Mapped["User"] = relationship("User", back_populates="responder_profiles")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_role_permissions_granted_by",
        ),
        ForeignKeyConstraint(
            ["permission_id"], ["permissions.permission_id"], name="fk_role_permissions_permission"
        ),
        ForeignKeyConstraint(["role_id"], ["roles.role_id"], name="fk_role_permissions_role"),
        Index("fk_role_permissions_granted_by", "granted_by_user_id"),
        Index("fk_role_permissions_permission", "permission_id"),
        Index("uk_role_permissions", "role_id", "permission_id", unique=True),
    )

    role_permission_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    role_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    permission_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    granted_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    granted_by_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))

    granted_by_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="role_permissions"
    )
    permission: Mapped["Permission"] = relationship("Permission", back_populates="role_permissions")
    role: Mapped["Role"] = relationship("Role", back_populates="role_permissions")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assigned_by_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_user_roles_assigned_by",
        ),
        ForeignKeyConstraint(["role_id"], ["roles.role_id"], name="fk_user_roles_role"),
        ForeignKeyConstraint(["user_id"], ["users.user_id"], name="fk_user_roles_user"),
        Index("fk_user_roles_assigned_by", "assigned_by_user_id"),
        Index("fk_user_roles_role", "role_id"),
        Index("uk_user_roles", "user_id", "role_id", unique=True),
    )

    user_role_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    role_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    assigned_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    assigned_by_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))

    assigned_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[assigned_by_user_id], back_populates="user_roles_assigned_by_users"
    )
    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="user_roles_users"
    )


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        CheckConstraint(
            "`client_type` in ('WEB','WEBAPP','MOBILE','DEVICE')",
            name="ck_user_sessions_client_type",
        ),
        CheckConstraint("`expires_at` > `created_at`", name="ck_user_sessions_expiry"),
        ForeignKeyConstraint(
            ["user_id"], ["users.user_id"], ondelete="CASCADE", name="fk_user_sessions_user"
        ),
        Index("ix_user_sessions_user_expiry", "user_id", "expires_at", "revoked_at"),
        Index("uk_user_sessions_public_id", "public_id", unique=True),
        Index("uk_user_sessions_token_hash", "refresh_token_hash", unique=True),
    )

    user_session_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    client_type: Mapped[str] = mapped_column(
        VARCHAR(30), nullable=False, server_default=text("'WEB'")
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    ip_hash: Mapped[Optional[str]] = mapped_column(CHAR(64))
    user_agent_hash: Mapped[Optional[str]] = mapped_column(CHAR(64))
    revoked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    revoke_reason: Mapped[Optional[str]] = mapped_column(VARCHAR(300))

    user: Mapped["User"] = relationship("User", back_populates="user_sessions")


class AiModelVersion(Base):
    __tablename__ = "ai_model_versions"
    __table_args__ = (
        CheckConstraint(
            "`default_confidence_threshold` between 0 and 1", name="ck_ai_model_versions_threshold"
        ),
        CheckConstraint(
            "`input_width` > 0 and `input_height` > 0", name="ck_ai_model_versions_dimensions"
        ),
        CheckConstraint(
            "`runtime_status` in ('NOT_LOADED','LOADING','LOADED','ERROR','INACTIVE')",
            name="ck_ai_model_versions_runtime",
        ),
        ForeignKeyConstraint(
            ["ai_model_id"], ["ai_models.ai_model_id"], name="fk_ai_model_versions_model"
        ),
        ForeignKeyConstraint(
            ["model_file_id"], ["files.file_id"], name="fk_ai_model_versions_file"
        ),
        Index("fk_ai_model_versions_file", "model_file_id"),
        Index("uk_ai_model_versions_label", "ai_model_id", "version_label", unique=True),
        Index("uk_ai_model_versions_public_id", "public_id", unique=True),
    )

    ai_model_version_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    ai_model_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    version_label: Mapped[str] = mapped_column(VARCHAR(60), nullable=False)
    framework_name: Mapped[str] = mapped_column(
        VARCHAR(60), nullable=False, server_default=text("'YOLO'")
    )
    input_width: Mapped[int] = mapped_column(INTEGER(10, unsigned=True), nullable=False)
    input_height: Mapped[int] = mapped_column(INTEGER(10, unsigned=True), nullable=False)
    default_confidence_threshold: Mapped[decimal.Decimal] = mapped_column(
        DECIMAL(5, 4), nullable=False
    )
    runtime_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'NOT_LOADED'")
    )
    is_operational: Mapped[int] = mapped_column(
        TINYINT(1), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    model_file_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    artifact_secret_ref: Mapped[Optional[str]] = mapped_column(VARCHAR(255))
    loaded_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    last_inference_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    metadata_json: Mapped[Optional[object]] = mapped_column(JSON)

    ai_model: Mapped["AiModel"] = relationship("AiModel", back_populates="ai_model_versions")
    model_file: Mapped[Optional["File"]] = relationship("File", back_populates="ai_model_versions")
    inference_runs: Mapped[list["InferenceRun"]] = relationship(
        "InferenceRun", back_populates="ai_model_version"
    )
    model_version_classes: Mapped[list["ModelVersionClass"]] = relationship(
        "ModelVersionClass", back_populates="ai_model_version"
    )


class CctvStream(Base):
    __tablename__ = "cctv_streams"
    __table_args__ = (
        CheckConstraint(
            "`protocol_type` in ('RTSP','HLS','HTTP','FILE','OTHER')",
            name="ck_cctv_streams_protocol",
        ),
        CheckConstraint(
            "`stream_status` in ('ACTIVE','INACTIVE','ERROR')", name="ck_cctv_streams_status"
        ),
        CheckConstraint("`stream_type` in ('LIVE','DEMO')", name="ck_cctv_streams_type"),
        CheckConstraint(
            "`valid_to` is null or `valid_to` >= `valid_from`", name="ck_cctv_streams_period"
        ),
        ForeignKeyConstraint(["cctv_id"], ["cctvs.cctv_id"], name="fk_cctv_streams_cctv"),
        Index("fk_cctv_streams_cctv", "cctv_id"),
        Index("uk_cctv_streams_active_primary", "active_primary_key", unique=True),
        Index("uk_cctv_streams_public_id", "public_id", unique=True),
    )

    cctv_stream_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    cctv_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    stream_type: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    protocol_type: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    endpoint_secret_ref: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    stream_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'ACTIVE'")
    )
    is_primary: Mapped[int] = mapped_column(TINYINT(1), nullable=False, server_default=text("1"))
    valid_from: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    valid_to: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    active_primary_key: Mapped[Optional[str]] = mapped_column(
        VARCHAR(100),
        Computed(
            "(case when `is_primary` = 1 and `stream_status` = 'ACTIVE' and `valid_to` is null then concat(convert(cast(`cctv_id` as char charset utf8mb3) using utf8mb4),':',`stream_type`) else NULL end)",
            persisted=True,
        ),
    )

    cctv: Mapped["Cctv"] = relationship("Cctv", back_populates="cctv_streams")


class TrackingSession(Base):
    __tablename__ = "tracking_sessions"
    __table_args__ = (
        CheckConstraint(
            "`ended_at` is null or `ended_at` >= `started_at`", name="ck_tracking_sessions_period"
        ),
        CheckConstraint(
            "`tracking_status` in ('ACTIVE','ENDED','FAILED')", name="ck_tracking_sessions_status"
        ),
        ForeignKeyConstraint(["cctv_id"], ["cctvs.cctv_id"], name="fk_tracking_sessions_cctv"),
        Index("ix_tracking_sessions_cctv_status", "cctv_id", "tracking_status", "started_at"),
        Index("uk_tracking_sessions_key", "cctv_id", "session_key", unique=True),
        Index("uk_tracking_sessions_public_id", "public_id", unique=True),
    )

    tracking_session_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    cctv_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    session_key: Mapped[str] = mapped_column(VARCHAR(120), nullable=False)
    tracking_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'ACTIVE'")
    )
    started_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    ended_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    tracker_name: Mapped[Optional[str]] = mapped_column(VARCHAR(60))
    tracker_version: Mapped[Optional[str]] = mapped_column(VARCHAR(60))

    cctv: Mapped["Cctv"] = relationship("Cctv", back_populates="tracking_sessions")
    tracked_objects: Mapped[list["TrackedObject"]] = relationship(
        "TrackedObject", back_populates="tracking_session"
    )


class VideoFrame(Base):
    __tablename__ = "video_frames"
    __table_args__ = (
        CheckConstraint(
            "`capture_source` in ('LIVE','DEMO','UPLOAD')", name="ck_video_frames_source"
        ),
        CheckConstraint(
            "`frame_status` in ('CAPTURED','PREPROCESSED','FAILED','RETAINED','EXPIRED')",
            name="ck_video_frames_status",
        ),
        CheckConstraint(
            "`original_width` > 0 and `original_height` > 0", name="ck_video_frames_dimensions"
        ),
        ForeignKeyConstraint(["cctv_id"], ["cctvs.cctv_id"], name="fk_video_frames_cctv"),
        ForeignKeyConstraint(
            ["original_file_id"], ["files.file_id"], name="fk_video_frames_original_file"
        ),
        ForeignKeyConstraint(
            ["preprocessed_file_id"], ["files.file_id"], name="fk_video_frames_preprocessed_file"
        ),
        Index("fk_video_frames_original_file", "original_file_id"),
        Index("fk_video_frames_preprocessed_file", "preprocessed_file_id"),
        Index("ix_video_frames_cctv_time", "cctv_id", "captured_at"),
        Index("uk_video_frames_public_id", "public_id", unique=True),
        Index("uk_video_frames_sequence", "cctv_id", "captured_at", "frame_sequence", unique=True),
    )

    video_frame_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    cctv_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    capture_source: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    captured_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    frame_sequence: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    original_width: Mapped[int] = mapped_column(INTEGER(10, unsigned=True), nullable=False)
    original_height: Mapped[int] = mapped_column(INTEGER(10, unsigned=True), nullable=False)
    frame_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'CAPTURED'")
    )
    is_incident_evidence: Mapped[int] = mapped_column(
        TINYINT(1), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    input_width: Mapped[Optional[int]] = mapped_column(INTEGER(10, unsigned=True))
    input_height: Mapped[Optional[int]] = mapped_column(INTEGER(10, unsigned=True))
    original_file_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    preprocessed_file_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    retention_until: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    preprocessing_json: Mapped[Optional[object]] = mapped_column(JSON)

    cctv: Mapped["Cctv"] = relationship("Cctv", back_populates="video_frames")
    original_file: Mapped[Optional["File"]] = relationship(
        "File", foreign_keys=[original_file_id], back_populates="video_frames_original_files"
    )
    preprocessed_file: Mapped[Optional["File"]] = relationship(
        "File",
        foreign_keys=[preprocessed_file_id],
        back_populates="video_frames_preprocessed_files",
    )
    inference_runs: Mapped[list["InferenceRun"]] = relationship(
        "InferenceRun", back_populates="video_frame"
    )
    incident_evidences: Mapped[list["IncidentEvidence"]] = relationship(
        "IncidentEvidence", back_populates="video_frame"
    )


class InferenceRun(Base):
    __tablename__ = "inference_runs"
    __table_args__ = (
        CheckConstraint(
            "`completed_at` is null or `started_at` is null or `completed_at` >= `started_at`",
            name="ck_inference_runs_period",
        ),
        CheckConstraint(
            "`inference_status` in ('QUEUED','RUNNING','SUCCEEDED','FAILED','SKIPPED')",
            name="ck_inference_runs_status",
        ),
        ForeignKeyConstraint(
            ["ai_model_version_id"],
            ["ai_model_versions.ai_model_version_id"],
            name="fk_inference_runs_model_version",
        ),
        ForeignKeyConstraint(
            ["annotated_file_id"], ["files.file_id"], name="fk_inference_runs_annotated_file"
        ),
        ForeignKeyConstraint(
            ["video_frame_id"],
            ["video_frames.video_frame_id"],
            ondelete="CASCADE",
            name="fk_inference_runs_frame",
        ),
        Index("fk_inference_runs_annotated_file", "annotated_file_id"),
        Index("fk_inference_runs_model_version", "ai_model_version_id"),
        Index("ix_inference_runs_status_created", "inference_status", "created_at"),
        Index(
            "uk_inference_runs_frame_model", "video_frame_id", "ai_model_version_id", unique=True
        ),
        Index("uk_inference_runs_idempotency", "idempotency_key", unique=True),
        Index("uk_inference_runs_public_id", "public_id", unique=True),
    )

    inference_run_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    video_frame_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    ai_model_version_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(VARCHAR(160), nullable=False)
    execution_order: Mapped[int] = mapped_column(
        SMALLINT(5, unsigned=True), nullable=False, server_default=text("1")
    )
    inference_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'QUEUED'")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    processing_time_ms: Mapped[Optional[int]] = mapped_column(INTEGER(10, unsigned=True))
    annotated_file_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    ai_server_code: Mapped[Optional[str]] = mapped_column(VARCHAR(60))
    trace_id: Mapped[Optional[str]] = mapped_column(VARCHAR(100))
    error_code: Mapped[Optional[str]] = mapped_column(VARCHAR(80))
    error_message: Mapped[Optional[str]] = mapped_column(VARCHAR(1000))
    response_snapshot_json: Mapped[Optional[object]] = mapped_column(JSON)

    ai_model_version: Mapped["AiModelVersion"] = relationship(
        "AiModelVersion", back_populates="inference_runs"
    )
    annotated_file: Mapped[Optional["File"]] = relationship("File", back_populates="inference_runs")
    video_frame: Mapped["VideoFrame"] = relationship("VideoFrame", back_populates="inference_runs")
    detections: Mapped[list["Detection"]] = relationship(
        "Detection", back_populates="inference_run"
    )


class ModelVersionClass(Base):
    __tablename__ = "model_version_classes"
    __table_args__ = (
        CheckConstraint(
            "`confidence_threshold` is null or `confidence_threshold` between 0 and 1",
            name="ck_model_version_classes_threshold",
        ),
        ForeignKeyConstraint(
            ["ai_model_version_id"],
            ["ai_model_versions.ai_model_version_id"],
            name="fk_model_version_classes_version",
        ),
        ForeignKeyConstraint(
            ["object_class_id"],
            ["object_classes.object_class_id"],
            name="fk_model_version_classes_object_class",
        ),
        Index("fk_model_version_classes_object_class", "object_class_id"),
        Index(
            "uk_model_version_classes_class", "ai_model_version_id", "object_class_id", unique=True
        ),
        Index("uk_model_version_classes_index", "ai_model_version_id", "class_index", unique=True),
    )

    model_version_class_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    ai_model_version_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    class_index: Mapped[int] = mapped_column(INTEGER(10, unsigned=True), nullable=False)
    object_class_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    confidence_threshold: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(5, 4))

    ai_model_version: Mapped["AiModelVersion"] = relationship(
        "AiModelVersion", back_populates="model_version_classes"
    )
    object_clas: Mapped["ObjectClass"] = relationship(
        "ObjectClass", back_populates="model_version_classes"
    )


class TrackedObject(Base):
    __tablename__ = "tracked_objects"
    __table_args__ = (
        CheckConstraint(
            "`last_confidence` between 0 and 1 and `max_confidence` between 0 and 1 and `average_confidence` between 0 and 1",
            name="ck_tracked_objects_confidence",
        ),
        CheckConstraint(
            "`last_detected_at` >= `first_detected_at`", name="ck_tracked_objects_period"
        ),
        CheckConstraint(
            "`tracking_status` in ('ACTIVE','LOST','ENDED')", name="ck_tracked_objects_status"
        ),
        ForeignKeyConstraint(["cctv_id"], ["cctvs.cctv_id"], name="fk_tracked_objects_cctv"),
        ForeignKeyConstraint(
            ["object_class_id"], ["object_classes.object_class_id"], name="fk_tracked_objects_class"
        ),
        ForeignKeyConstraint(
            ["tracking_session_id"],
            ["tracking_sessions.tracking_session_id"],
            name="fk_tracked_objects_session",
        ),
        Index("fk_tracked_objects_class", "object_class_id"),
        Index(
            "ix_tracked_objects_cctv_status_time", "cctv_id", "tracking_status", "last_detected_at"
        ),
        Index(
            "uk_tracked_objects_external", "tracking_session_id", "external_track_id", unique=True
        ),
        Index("uk_tracked_objects_public_id", "public_id", unique=True),
    )

    tracked_object_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    tracking_session_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    cctv_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    external_track_id: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    object_class_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    tracking_status: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'ACTIVE'")
    )
    first_detected_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    last_detected_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    duration_ms: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), nullable=False, server_default=text("0")
    )
    detection_count: Mapped[int] = mapped_column(
        INTEGER(10, unsigned=True), nullable=False, server_default=text("1")
    )
    last_confidence: Mapped[decimal.Decimal] = mapped_column(DECIMAL(5, 4), nullable=False)
    max_confidence: Mapped[decimal.Decimal] = mapped_column(DECIMAL(5, 4), nullable=False)
    average_confidence: Mapped[decimal.Decimal] = mapped_column(DECIMAL(5, 4), nullable=False)
    version_no: Mapped[int] = mapped_column(
        INTEGER(10, unsigned=True), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )

    cctv: Mapped["Cctv"] = relationship("Cctv", back_populates="tracked_objects")
    object_clas: Mapped["ObjectClass"] = relationship(
        "ObjectClass", back_populates="tracked_objects"
    )
    tracking_session: Mapped["TrackingSession"] = relationship(
        "TrackingSession", back_populates="tracked_objects"
    )
    risk_evaluations: Mapped[list["RiskEvaluation"]] = relationship(
        "RiskEvaluation", back_populates="tracked_object"
    )
    track_observations: Mapped[list["TrackObservation"]] = relationship(
        "TrackObservation", back_populates="tracked_object"
    )
    incidents: Mapped[list["Incident"]] = relationship("Incident", back_populates="tracked_object")


class Detection(Base):
    __tablename__ = "detections"
    __table_args__ = (
        CheckConstraint(
            "`bbox_x` between 0 and 1 and `bbox_y` between 0 and 1 and `bbox_width` > 0 and `bbox_width` <= 1 and `bbox_height` > 0 and `bbox_height` <= 1 and `bbox_x` + `bbox_width` <= 1 and `bbox_y` + `bbox_height` <= 1",
            name="ck_detections_bbox",
        ),
        CheckConstraint("`confidence` between 0 and 1", name="ck_detections_confidence"),
        ForeignKeyConstraint(
            ["inference_run_id"],
            ["inference_runs.inference_run_id"],
            ondelete="CASCADE",
            name="fk_detections_inference_run",
        ),
        ForeignKeyConstraint(
            ["object_class_id"],
            ["object_classes.object_class_id"],
            name="fk_detections_object_class",
        ),
        Index("ix_detections_class_confidence", "object_class_id", "confidence", "detected_at"),
        Index("uk_detections_index", "inference_run_id", "detection_index", unique=True),
        Index("uk_detections_public_id", "public_id", unique=True),
    )

    detection_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    inference_run_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    detection_index: Mapped[int] = mapped_column(INTEGER(10, unsigned=True), nullable=False)
    object_class_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    class_index: Mapped[int] = mapped_column(INTEGER(10, unsigned=True), nullable=False)
    confidence: Mapped[decimal.Decimal] = mapped_column(DECIMAL(5, 4), nullable=False)
    bbox_x: Mapped[decimal.Decimal] = mapped_column(DECIMAL(8, 7), nullable=False)
    bbox_y: Mapped[decimal.Decimal] = mapped_column(DECIMAL(8, 7), nullable=False)
    bbox_width: Mapped[decimal.Decimal] = mapped_column(DECIMAL(8, 7), nullable=False)
    bbox_height: Mapped[decimal.Decimal] = mapped_column(DECIMAL(8, 7), nullable=False)
    is_threshold_passed: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    detected_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    raw_detection_json: Mapped[Optional[object]] = mapped_column(JSON)

    inference_run: Mapped["InferenceRun"] = relationship(
        "InferenceRun", back_populates="detections"
    )
    object_clas: Mapped["ObjectClass"] = relationship("ObjectClass", back_populates="detections")
    risk_evaluations: Mapped[list["RiskEvaluation"]] = relationship(
        "RiskEvaluation", back_populates="representative_detection"
    )
    track_observations: Mapped[list["TrackObservation"]] = relationship(
        "TrackObservation", back_populates="detection"
    )
    incidents: Mapped[list["Incident"]] = relationship(
        "Incident", back_populates="representative_detection"
    )
    incident_evidences: Mapped[list["IncidentEvidence"]] = relationship(
        "IncidentEvidence", back_populates="detection"
    )


class RiskEvaluation(Base):
    __tablename__ = "risk_evaluations"
    __table_args__ = (
        CheckConstraint(
            "`confidence_calculation_type` in ('LAST','MAX','AVERAGE')",
            name="ck_risk_evaluations_confidence_type",
        ),
        CheckConstraint(
            "`confidence_value` between 0 and 1", name="ck_risk_evaluations_confidence"
        ),
        CheckConstraint(
            "`object_category` in ('VEHICLE','DEBRIS','WILDLIFE')",
            name="ck_risk_evaluations_category",
        ),
        CheckConstraint(
            "`risk_grade` in ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_risk_evaluations_grade"
        ),
        CheckConstraint("`risk_score` between 0 and 100", name="ck_risk_evaluations_score"),
        ForeignKeyConstraint(
            ["representative_detection_id"],
            ["detections.detection_id"],
            name="fk_risk_evaluations_detection",
        ),
        ForeignKeyConstraint(
            ["tracked_object_id"],
            ["tracked_objects.tracked_object_id"],
            name="fk_risk_evaluations_object",
        ),
        Index("fk_risk_evaluations_detection", "representative_detection_id"),
        Index(
            "ix_risk_evaluations_candidate_time",
            "is_incident_candidate",
            "risk_grade",
            "evaluated_at",
        ),
        Index("uk_risk_evaluations_idempotency", "idempotency_key", unique=True),
        Index("uk_risk_evaluations_input", "tracked_object_id", "input_hash", unique=True),
        Index("uk_risk_evaluations_public_id", "public_id", unique=True),
    )

    risk_evaluation_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    tracked_object_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(VARCHAR(160), nullable=False)
    input_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    object_category: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    confidence_calculation_type: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    confidence_value: Mapped[decimal.Decimal] = mapped_column(DECIMAL(5, 4), nullable=False)
    duration_ms: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    repeat_count: Mapped[int] = mapped_column(INTEGER(10, unsigned=True), nullable=False)
    risk_score: Mapped[decimal.Decimal] = mapped_column(DECIMAL(5, 2), nullable=False)
    risk_grade: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    is_incident_candidate: Mapped[int] = mapped_column(TINYINT(1), nullable=False)
    rule_code: Mapped[str] = mapped_column(VARCHAR(60), nullable=False)
    rule_version_snapshot: Mapped[str] = mapped_column(VARCHAR(60), nullable=False)
    rule_snapshot_json: Mapped[object] = mapped_column(JSON, nullable=False)
    evaluated_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    representative_detection_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    exclusion_reason: Mapped[Optional[str]] = mapped_column(VARCHAR(80))

    representative_detection: Mapped[Optional["Detection"]] = relationship(
        "Detection", back_populates="risk_evaluations"
    )
    tracked_object: Mapped["TrackedObject"] = relationship(
        "TrackedObject", back_populates="risk_evaluations"
    )
    incidents: Mapped[list["Incident"]] = relationship(
        "Incident", back_populates="latest_risk_evaluation"
    )
    incident_evidences: Mapped[list["IncidentEvidence"]] = relationship(
        "IncidentEvidence", back_populates="risk_evaluation"
    )


class TrackObservation(Base):
    __tablename__ = "track_observations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["detection_id"], ["detections.detection_id"], name="fk_track_observations_detection"
        ),
        ForeignKeyConstraint(
            ["tracked_object_id"],
            ["tracked_objects.tracked_object_id"],
            ondelete="CASCADE",
            name="fk_track_observations_object",
        ),
        Index("ix_track_observations_object_time", "tracked_object_id", "observed_at"),
        Index("uk_track_observations_detection", "detection_id", unique=True),
        Index(
            "uk_track_observations_sequence",
            "tracked_object_id",
            "observation_sequence",
            unique=True,
        ),
    )

    track_observation_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    tracked_object_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    detection_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    observation_sequence: Mapped[int] = mapped_column(INTEGER(10, unsigned=True), nullable=False)
    observed_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )

    detection: Mapped["Detection"] = relationship("Detection", back_populates="track_observations")
    tracked_object: Mapped["TrackedObject"] = relationship(
        "TrackedObject", back_populates="track_observations"
    )


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "`current_risk_grade` in ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_incidents_grade"
        ),
        CheckConstraint("`current_risk_score` between 0 and 100", name="ck_incidents_score"),
        CheckConstraint(
            "`incident_status` in ('NEW','ACKNOWLEDGED','CLAIMED','UNDER_REVIEW','FALSE_POSITIVE','DISPATCH_REQUESTED','DISPATCHED','ON_SCENE','ACTION_IN_PROGRESS','ACTION_COMPLETED','CLOSED')",
            name="ck_incidents_status",
        ),
        CheckConstraint("`last_detected_at` >= `first_detected_at`", name="ck_incidents_period"),
        CheckConstraint(
            "`latitude_snapshot` between -90 and 90 and `longitude_snapshot` between -180 and 180",
            name="ck_incidents_location",
        ),
        CheckConstraint(
            "`object_category` in ('VEHICLE','DEBRIS','WILDLIFE','OTHER')",
            name="ck_incidents_category",
        ),
        CheckConstraint(
            "`source_type` in ('AI','MANUAL','CITIZEN_REPORT')", name="ck_incidents_source"
        ),
        ForeignKeyConstraint(
            ["acknowledged_by_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_incidents_acknowledged_by",
        ),
        ForeignKeyConstraint(["cctv_id"], ["cctvs.cctv_id"], name="fk_incidents_cctv"),
        ForeignKeyConstraint(
            ["current_controller_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_incidents_current_controller",
        ),
        ForeignKeyConstraint(
            ["latest_risk_evaluation_id"],
            ["risk_evaluations.risk_evaluation_id"],
            name="fk_incidents_latest_risk",
        ),
        ForeignKeyConstraint(
            ["object_class_id"],
            ["object_classes.object_class_id"],
            name="fk_incidents_object_class",
        ),
        ForeignKeyConstraint(
            ["representative_detection_id"],
            ["detections.detection_id"],
            name="fk_incidents_representative_detection",
        ),
        ForeignKeyConstraint(
            ["road_section_id"], ["road_sections.road_section_id"], name="fk_incidents_road_section"
        ),
        ForeignKeyConstraint(
            ["tracked_object_id"],
            ["tracked_objects.tracked_object_id"],
            name="fk_incidents_tracked_object",
        ),
        Index("fk_incidents_acknowledged_by", "acknowledged_by_user_id"),
        Index("fk_incidents_latest_risk", "latest_risk_evaluation_id"),
        Index("fk_incidents_object_class", "object_class_id"),
        Index("fk_incidents_representative_detection", "representative_detection_id"),
        Index("fk_incidents_road_section", "road_section_id"),
        Index("fk_incidents_tracked_object", "tracked_object_id"),
        Index("ix_incidents_cctv_time", "cctv_id", "detected_at"),
        Index(
            "ix_incidents_controller_status",
            "current_controller_user_id",
            "incident_status",
            "detected_at",
        ),
        Index("ix_incidents_list", "incident_status", "current_risk_grade", "detected_at"),
        Index("uk_incidents_active_track", "active_track_key", unique=True),
        Index("uk_incidents_no", "incident_no", unique=True),
        Index("uk_incidents_public_id", "public_id", unique=True),
    )

    incident_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    incident_no: Mapped[str] = mapped_column(VARCHAR(40), nullable=False)
    source_type: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'AI'")
    )
    cctv_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    road_section_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    object_category: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    incident_status: Mapped[str] = mapped_column(
        VARCHAR(30), nullable=False, server_default=text("'NEW'")
    )
    current_risk_score: Mapped[decimal.Decimal] = mapped_column(DECIMAL(5, 2), nullable=False)
    current_risk_grade: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    priority_order: Mapped[int] = mapped_column(
        SMALLINT(5, unsigned=True), nullable=False, server_default=text("100")
    )
    detected_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    first_detected_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    last_detected_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    detection_count: Mapped[int] = mapped_column(
        INTEGER(10, unsigned=True), nullable=False, server_default=text("1")
    )
    duration_ms: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), nullable=False, server_default=text("0")
    )
    cctv_name_snapshot: Mapped[str] = mapped_column(VARCHAR(150), nullable=False)
    road_name_snapshot: Mapped[str] = mapped_column(VARCHAR(120), nullable=False)
    road_section_name_snapshot: Mapped[str] = mapped_column(VARCHAR(150), nullable=False)
    direction_snapshot: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    latitude_snapshot: Mapped[decimal.Decimal] = mapped_column(DECIMAL(10, 7), nullable=False)
    longitude_snapshot: Mapped[decimal.Decimal] = mapped_column(DECIMAL(10, 7), nullable=False)
    version_no: Mapped[int] = mapped_column(
        INTEGER(10, unsigned=True), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    tracked_object_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    representative_detection_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    latest_risk_evaluation_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    object_class_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    current_controller_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    acknowledged_by_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    acknowledged_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    claimed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    location_description_snapshot: Mapped[Optional[str]] = mapped_column(VARCHAR(255))
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    active_track_key: Mapped[Optional[str]] = mapped_column(
        VARCHAR(100),
        Computed(
            "(case when `tracked_object_id` is not null and `incident_status` not in ('CLOSED','FALSE_POSITIVE') then concat(cast(`cctv_id` as char charset utf8mb3),':',cast(`tracked_object_id` as char charset utf8mb3)) else NULL end)",
            persisted=True,
        ),
    )

    acknowledged_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[acknowledged_by_user_id],
        back_populates="incidents_acknowledged_by_users",
    )
    cctv: Mapped["Cctv"] = relationship("Cctv", back_populates="incidents")
    current_controller_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[current_controller_user_id],
        back_populates="incidents_current_controller_users",
    )
    latest_risk_evaluation: Mapped[Optional["RiskEvaluation"]] = relationship(
        "RiskEvaluation", back_populates="incidents"
    )
    object_clas: Mapped[Optional["ObjectClass"]] = relationship(
        "ObjectClass", back_populates="incidents"
    )
    representative_detection: Mapped[Optional["Detection"]] = relationship(
        "Detection", back_populates="incidents"
    )
    road_section: Mapped["RoadSection"] = relationship("RoadSection", back_populates="incidents")
    tracked_object: Mapped[Optional["TrackedObject"]] = relationship(
        "TrackedObject", back_populates="incidents"
    )
    dispatch_requests: Mapped[list["DispatchRequest"]] = relationship(
        "DispatchRequest", back_populates="incident"
    )
    incident_claims: Mapped[list["IncidentClaim"]] = relationship(
        "IncidentClaim", back_populates="incident"
    )
    incident_decisions: Mapped[list["IncidentDecision"]] = relationship(
        "IncidentDecision", back_populates="incident"
    )
    incident_evidences: Mapped[list["IncidentEvidence"]] = relationship(
        "IncidentEvidence", back_populates="incident"
    )
    incident_files: Mapped[list["IncidentFile"]] = relationship(
        "IncidentFile", back_populates="incident"
    )
    incident_notes: Mapped[list["IncidentNote"]] = relationship(
        "IncidentNote", back_populates="incident"
    )
    incident_status_histories: Mapped[list["IncidentStatusHistory"]] = relationship(
        "IncidentStatusHistory", back_populates="incident"
    )


class DispatchRequest(Base):
    __tablename__ = "dispatch_requests"
    __table_args__ = (
        CheckConstraint(
            "`dispatch_status` in ('REQUESTED','ACCEPTED','REJECTED','DEPARTED','EN_ROUTE','ARRIVED','ACTION_IN_PROGRESS','ACTION_COMPLETED','CANCELLED')",
            name="ck_dispatch_requests_status",
        ),
        CheckConstraint(
            "`status_change_method` in ('MANUAL','DEVICE','AUTO')",
            name="ck_dispatch_requests_method",
        ),
        ForeignKeyConstraint(
            ["assigned_by_user_id"], ["users.user_id"], name="fk_dispatch_requests_assigned_by"
        ),
        ForeignKeyConstraint(
            ["incident_id"], ["incidents.incident_id"], name="fk_dispatch_requests_incident"
        ),
        ForeignKeyConstraint(
            ["previous_dispatch_request_id"],
            ["dispatch_requests.dispatch_request_id"],
            ondelete="SET NULL",
            name="fk_dispatch_requests_previous",
        ),
        ForeignKeyConstraint(
            ["responder_user_id"], ["users.user_id"], name="fk_dispatch_requests_responder"
        ),
        Index("fk_dispatch_requests_assigned_by", "assigned_by_user_id"),
        Index("fk_dispatch_requests_previous", "previous_dispatch_request_id"),
        Index("ix_dispatch_requests_incident", "incident_id", "attempt_no"),
        Index(
            "ix_dispatch_requests_responder_status",
            "responder_user_id",
            "dispatch_status",
            "requested_at",
        ),
        Index("uk_dispatch_requests_active_incident", "active_incident_id", unique=True),
        Index("uk_dispatch_requests_active_responder", "active_responder_id", unique=True),
        Index("uk_dispatch_requests_attempt", "incident_id", "attempt_no", unique=True),
        Index("uk_dispatch_requests_public_id", "public_id", unique=True),
    )

    dispatch_request_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    incident_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    attempt_no: Mapped[int] = mapped_column(
        SMALLINT(5, unsigned=True), nullable=False, server_default=text("1")
    )
    responder_user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    assigned_by_user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    dispatch_status: Mapped[str] = mapped_column(
        VARCHAR(30), nullable=False, server_default=text("'REQUESTED'")
    )
    status_change_method: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'MANUAL'")
    )
    requested_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    version_no: Mapped[int] = mapped_column(
        INTEGER(10, unsigned=True), nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    previous_dispatch_request_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    request_message: Mapped[Optional[str]] = mapped_column(VARCHAR(1000))
    rejection_reason: Mapped[Optional[str]] = mapped_column(VARCHAR(1000))
    accepted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    departed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    en_route_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    arrived_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    action_started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    action_completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    cancelled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    active_incident_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(20, unsigned=True),
        Computed(
            "(case when `dispatch_status` not in ('REJECTED','CANCELLED','ACTION_COMPLETED') then `incident_id` else NULL end)",
            persisted=True,
        ),
    )
    active_responder_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(20, unsigned=True),
        Computed(
            "(case when `dispatch_status` not in ('REJECTED','CANCELLED','ACTION_COMPLETED') then `responder_user_id` else NULL end)",
            persisted=True,
        ),
    )

    assigned_by_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[assigned_by_user_id],
        back_populates="dispatch_requests_assigned_by_users",
    )
    incident: Mapped["Incident"] = relationship("Incident", back_populates="dispatch_requests")
    previous_dispatch_request: Mapped[Optional["DispatchRequest"]] = relationship(
        "DispatchRequest",
        remote_side=[dispatch_request_id],
        back_populates="previous_dispatch_request_reverse",
    )
    previous_dispatch_request_reverse: Mapped[list["DispatchRequest"]] = relationship(
        "DispatchRequest",
        remote_side=[previous_dispatch_request_id],
        back_populates="previous_dispatch_request",
    )
    responder_user: Mapped["User"] = relationship(
        "User", foreign_keys=[responder_user_id], back_populates="dispatch_requests_responder_users"
    )
    dispatch_status_histories: Mapped[list["DispatchStatusHistory"]] = relationship(
        "DispatchStatusHistory", back_populates="dispatch_request"
    )
    field_action_reports: Mapped[list["FieldActionReport"]] = relationship(
        "FieldActionReport", back_populates="dispatch_request"
    )


class IncidentClaim(Base):
    __tablename__ = "incident_claims"
    __table_args__ = (
        CheckConstraint(
            "`released_at` is null or `released_at` >= `claimed_at`",
            name="ck_incident_claims_period",
        ),
        ForeignKeyConstraint(
            ["controller_user_id"], ["users.user_id"], name="fk_incident_claims_controller"
        ),
        ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.incident_id"],
            ondelete="CASCADE",
            name="fk_incident_claims_incident",
        ),
        Index("fk_incident_claims_controller", "controller_user_id"),
        Index("fk_incident_claims_incident", "incident_id"),
        Index("uk_incident_claims_active", "active_incident_id", unique=True),
        Index("uk_incident_claims_idempotency", "idempotency_key", unique=True),
        Index("uk_incident_claims_public_id", "public_id", unique=True),
    )

    incident_claim_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    incident_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    controller_user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(VARCHAR(160), nullable=False)
    claimed_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    released_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    release_reason: Mapped[Optional[str]] = mapped_column(VARCHAR(500))
    active_incident_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(20, unsigned=True),
        Computed(
            "(case when `released_at` is null then `incident_id` else NULL end)", persisted=True
        ),
    )

    controller_user: Mapped["User"] = relationship("User", back_populates="incident_claims")
    incident: Mapped["Incident"] = relationship("Incident", back_populates="incident_claims")


class IncidentDecision(Base):
    __tablename__ = "incident_decisions"
    __table_args__ = (
        CheckConstraint(
            "`decision_type` in ('REAL_RISK','FALSE_POSITIVE','NEEDS_REVIEW','NO_DISPATCH')",
            name="ck_incident_decisions_type",
        ),
        CheckConstraint(
            "`superseded_at` is null or `superseded_at` >= `decided_at`",
            name="ck_incident_decisions_period",
        ),
        ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.user_id"], name="fk_incident_decisions_user"
        ),
        ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.incident_id"],
            ondelete="CASCADE",
            name="fk_incident_decisions_incident",
        ),
        ForeignKeyConstraint(
            ["superseded_by_decision_id"],
            ["incident_decisions.incident_decision_id"],
            ondelete="SET NULL",
            name="fk_incident_decisions_superseded_by",
        ),
        Index("fk_incident_decisions_incident", "incident_id"),
        Index("fk_incident_decisions_superseded_by", "superseded_by_decision_id"),
        Index("fk_incident_decisions_user", "decided_by_user_id"),
        Index("uk_incident_decisions_active", "active_incident_id", unique=True),
        Index("uk_incident_decisions_idempotency", "idempotency_key", unique=True),
        Index("uk_incident_decisions_public_id", "public_id", unique=True),
    )

    incident_decision_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    incident_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    decision_type: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    decision_reason: Mapped[str] = mapped_column(VARCHAR(1000), nullable=False)
    decided_by_user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(VARCHAR(160), nullable=False)
    decided_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    superseded_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    superseded_by_decision_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    active_incident_id: Mapped[Optional[int]] = mapped_column(
        BIGINT(20, unsigned=True),
        Computed(
            "(case when `superseded_at` is null then `incident_id` else NULL end)", persisted=True
        ),
    )

    decided_by_user: Mapped["User"] = relationship("User", back_populates="incident_decisions")
    incident: Mapped["Incident"] = relationship("Incident", back_populates="incident_decisions")
    superseded_by_decision: Mapped[Optional["IncidentDecision"]] = relationship(
        "IncidentDecision",
        remote_side=[incident_decision_id],
        back_populates="superseded_by_decision_reverse",
    )
    superseded_by_decision_reverse: Mapped[list["IncidentDecision"]] = relationship(
        "IncidentDecision",
        remote_side=[superseded_by_decision_id],
        back_populates="superseded_by_decision",
    )


class IncidentEvidence(Base):
    __tablename__ = "incident_evidences"
    __table_args__ = (
        CheckConstraint(
            "`detection_id` is not null or `risk_evaluation_id` is not null or `video_frame_id` is not null",
            name="ck_incident_evidences_target",
        ),
        CheckConstraint(
            "`evidence_type` in ('PRIMARY','ADDITIONAL','MERGED','MANUAL')",
            name="ck_incident_evidences_type",
        ),
        ForeignKeyConstraint(
            ["detection_id"], ["detections.detection_id"], name="fk_incident_evidences_detection"
        ),
        ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.incident_id"],
            ondelete="CASCADE",
            name="fk_incident_evidences_incident",
        ),
        ForeignKeyConstraint(
            ["risk_evaluation_id"],
            ["risk_evaluations.risk_evaluation_id"],
            name="fk_incident_evidences_risk",
        ),
        ForeignKeyConstraint(
            ["video_frame_id"], ["video_frames.video_frame_id"], name="fk_incident_evidences_frame"
        ),
        Index("fk_incident_evidences_frame", "video_frame_id"),
        Index("fk_incident_evidences_incident", "incident_id"),
        Index("uk_incident_evidences_detection", "detection_id", unique=True),
        Index("uk_incident_evidences_risk", "risk_evaluation_id", unique=True),
    )

    incident_evidence_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    incident_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    evidence_type: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    is_primary: Mapped[int] = mapped_column(TINYINT(1), nullable=False, server_default=text("0"))
    added_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    detection_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    risk_evaluation_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    video_frame_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))

    detection: Mapped[Optional["Detection"]] = relationship(
        "Detection", back_populates="incident_evidences"
    )
    incident: Mapped["Incident"] = relationship("Incident", back_populates="incident_evidences")
    risk_evaluation: Mapped[Optional["RiskEvaluation"]] = relationship(
        "RiskEvaluation", back_populates="incident_evidences"
    )
    video_frame: Mapped[Optional["VideoFrame"]] = relationship(
        "VideoFrame", back_populates="incident_evidences"
    )


class IncidentFile(Base):
    __tablename__ = "incident_files"
    __table_args__ = (
        CheckConstraint(
            "`file_role` in ('ORIGINAL_FRAME','ANNOTATED_FRAME','VIDEO_CLIP','ATTACHMENT')",
            name="ck_incident_files_role",
        ),
        ForeignKeyConstraint(["file_id"], ["files.file_id"], name="fk_incident_files_file"),
        ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.incident_id"],
            ondelete="CASCADE",
            name="fk_incident_files_incident",
        ),
        ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_incident_files_uploaded_by",
        ),
        Index("fk_incident_files_file", "file_id"),
        Index("fk_incident_files_uploaded_by", "uploaded_by_user_id"),
        Index("uk_incident_files", "incident_id", "file_id", "file_role", unique=True),
    )

    incident_file_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    incident_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    file_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    file_role: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    uploaded_by_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))

    file: Mapped["File"] = relationship("File", back_populates="incident_files")
    incident: Mapped["Incident"] = relationship("Incident", back_populates="incident_files")
    uploaded_by_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="incident_files"
    )


class IncidentNote(Base):
    __tablename__ = "incident_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["created_by_user_id"], ["users.user_id"], name="fk_incident_notes_created_by"
        ),
        ForeignKeyConstraint(
            ["deleted_by_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_incident_notes_deleted_by",
        ),
        ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.incident_id"],
            ondelete="CASCADE",
            name="fk_incident_notes_incident",
        ),
        Index("fk_incident_notes_created_by", "created_by_user_id"),
        Index("fk_incident_notes_deleted_by", "deleted_by_user_id"),
        Index("ix_incident_notes_incident_time", "incident_id", "created_at"),
        Index("uk_incident_notes_public_id", "public_id", unique=True),
    )

    incident_note_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    incident_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    note_text: Mapped[str] = mapped_column(TEXT, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    deleted_by_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    delete_reason: Mapped[Optional[str]] = mapped_column(VARCHAR(500))

    created_by_user: Mapped["User"] = relationship(
        "User", foreign_keys=[created_by_user_id], back_populates="incident_notes_created_by_users"
    )
    deleted_by_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[deleted_by_user_id], back_populates="incident_notes_deleted_by_users"
    )
    incident: Mapped["Incident"] = relationship("Incident", back_populates="incident_notes")


class IncidentStatusHistory(Base):
    __tablename__ = "incident_status_histories"
    __table_args__ = (
        CheckConstraint(
            "`actor_type` in ('USER','SYSTEM','DEVICE')", name="ck_incident_status_histories_actor"
        ),
        CheckConstraint(
            "`change_source` in ('MANUAL','SYSTEM','DEVICE','AUTO')",
            name="ck_incident_status_histories_source",
        ),
        ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_incident_status_histories_actor",
        ),
        ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.incident_id"],
            ondelete="CASCADE",
            name="fk_incident_status_histories_incident",
        ),
        Index("fk_incident_status_histories_actor", "actor_user_id"),
        Index("ix_incident_status_histories_incident_time", "incident_id", "changed_at"),
        Index("uk_incident_status_histories_idempotency", "idempotency_key", unique=True),
        Index("uk_incident_status_histories_public_id", "public_id", unique=True),
    )

    incident_status_history_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    incident_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    to_status: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    actor_type: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    change_source: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'MANUAL'")
    )
    idempotency_key: Mapped[str] = mapped_column(VARCHAR(160), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    from_status: Mapped[Optional[str]] = mapped_column(VARCHAR(30))
    actor_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    reason_code: Mapped[Optional[str]] = mapped_column(VARCHAR(80))
    reason_text: Mapped[Optional[str]] = mapped_column(VARCHAR(1000))
    metadata_json: Mapped[Optional[object]] = mapped_column(JSON)

    actor_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="incident_status_histories"
    )
    incident: Mapped["Incident"] = relationship(
        "Incident", back_populates="incident_status_histories"
    )


class DispatchStatusHistory(Base):
    __tablename__ = "dispatch_status_histories"
    __table_args__ = (
        CheckConstraint(
            "`actor_type` in ('USER','SYSTEM','DEVICE')", name="ck_dispatch_status_histories_actor"
        ),
        CheckConstraint(
            "`change_method` in ('MANUAL','DEVICE','AUTO')",
            name="ck_dispatch_status_histories_method",
        ),
        ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.user_id"],
            ondelete="SET NULL",
            name="fk_dispatch_status_histories_actor",
        ),
        ForeignKeyConstraint(
            ["dispatch_request_id"],
            ["dispatch_requests.dispatch_request_id"],
            ondelete="CASCADE",
            name="fk_dispatch_status_histories_dispatch",
        ),
        Index("fk_dispatch_status_histories_actor", "actor_user_id"),
        Index("ix_dispatch_status_histories_dispatch_time", "dispatch_request_id", "changed_at"),
        Index("uk_dispatch_status_histories_idempotency", "idempotency_key", unique=True),
        Index("uk_dispatch_status_histories_public_id", "public_id", unique=True),
    )

    dispatch_status_history_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    dispatch_request_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    to_status: Mapped[str] = mapped_column(VARCHAR(30), nullable=False)
    actor_type: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    change_method: Mapped[str] = mapped_column(
        VARCHAR(20), nullable=False, server_default=text("'MANUAL'")
    )
    idempotency_key: Mapped[str] = mapped_column(VARCHAR(160), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    from_status: Mapped[Optional[str]] = mapped_column(VARCHAR(30))
    actor_user_id: Mapped[Optional[int]] = mapped_column(BIGINT(20, unsigned=True))
    reason_text: Mapped[Optional[str]] = mapped_column(VARCHAR(1000))
    metadata_json: Mapped[Optional[object]] = mapped_column(JSON)

    actor_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="dispatch_status_histories"
    )
    dispatch_request: Mapped["DispatchRequest"] = relationship(
        "DispatchRequest", back_populates="dispatch_status_histories"
    )


class FieldActionReport(Base):
    __tablename__ = "field_action_reports"
    __table_args__ = (
        CheckConstraint(
            "`action_completed_at` is null or `action_started_at` is null or `action_completed_at` >= `action_started_at`",
            name="ck_field_action_reports_period",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id"], ["users.user_id"], name="fk_field_action_reports_created_by"
        ),
        ForeignKeyConstraint(
            ["dispatch_request_id"],
            ["dispatch_requests.dispatch_request_id"],
            name="fk_field_action_reports_dispatch",
        ),
        Index("fk_field_action_reports_created_by", "created_by_user_id"),
        Index("uk_field_action_reports_dispatch", "dispatch_request_id", unique=True),
        Index("uk_field_action_reports_public_id", "public_id", unique=True),
    )

    field_action_report_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    public_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    dispatch_request_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    action_type: Mapped[str] = mapped_column(VARCHAR(60), nullable=False)
    action_detail: Mapped[str] = mapped_column(TEXT, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=text("current_timestamp(3) ON UPDATE current_timestamp(3)"),
    )
    action_started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))
    action_completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DATETIME(fsp=3))

    created_by_user: Mapped["User"] = relationship("User", back_populates="field_action_reports")
    dispatch_request: Mapped["DispatchRequest"] = relationship(
        "DispatchRequest", back_populates="field_action_reports"
    )
    field_action_files: Mapped[list["FieldActionFile"]] = relationship(
        "FieldActionFile", back_populates="field_action_report"
    )


class FieldActionFile(Base):
    __tablename__ = "field_action_files"
    __table_args__ = (
        CheckConstraint(
            "`photo_phase` in ('BEFORE','AFTER','OTHER')", name="ck_field_action_files_phase"
        ),
        ForeignKeyConstraint(
            ["field_action_report_id"],
            ["field_action_reports.field_action_report_id"],
            ondelete="CASCADE",
            name="fk_field_action_files_report",
        ),
        ForeignKeyConstraint(["file_id"], ["files.file_id"], name="fk_field_action_files_file"),
        Index("fk_field_action_files_file", "file_id"),
        Index("uk_field_action_files", "field_action_report_id", "file_id", unique=True),
    )

    field_action_file_id: Mapped[int] = mapped_column(
        BIGINT(20, unsigned=True), primary_key=True, autoincrement=True
    )
    field_action_report_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    file_id: Mapped[int] = mapped_column(BIGINT(20, unsigned=True), nullable=False)
    photo_phase: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    display_order: Mapped[int] = mapped_column(
        SMALLINT(5, unsigned=True), nullable=False, server_default=text("1")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("current_timestamp(3)")
    )

    field_action_report: Mapped["FieldActionReport"] = relationship(
        "FieldActionReport", back_populates="field_action_files"
    )
    file: Mapped["File"] = relationship("File", back_populates="field_action_files")


# MariaDB reflects explicit RESTRICT actions as an omitted default and UNIQUE
# constraints as indexes. Restore the source schema's explicit ORM semantics.
for _table in Base.metadata.tables.values():
    for _foreign_key_constraint in _table.foreign_key_constraints:
        if _foreign_key_constraint.ondelete is None:
            _foreign_key_constraint.ondelete = "RESTRICT"
            for _foreign_key in _foreign_key_constraint.elements:
                _foreign_key.ondelete = "RESTRICT"

    for _index in list(_table.indexes):
        if _index.unique and _index.name and _index.name.startswith("uk_"):
            _table.indexes.remove(_index)
            UniqueConstraint(*_index.columns, name=_index.name)
