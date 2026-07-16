from typing import TYPE_CHECKING, Optional
import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Computed,
    ForeignKeyConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.mysql import (
    BIGINT,
    CHAR,
    DATETIME,
    INTEGER,
    SMALLINT,
    TEXT,
    TINYINT,
    VARCHAR,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.auth import User
    from app.models.file import File
    from app.models.incident import Incident

__all__ = [
    "DispatchRequest",
    "DispatchStateTransition",
    "DispatchStatusHistory",
    "FieldActionFile",
    "FieldActionReport",
]


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
