from typing import TYPE_CHECKING, Optional
import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.mysql import (
    BIGINT,
    CHAR,
    DATETIME,
    INTEGER,
    VARCHAR,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.auth import User

__all__ = [
    "AuditLog",
    "EventOutbox",
    "IdempotencyKey",
    "Notification",
    "NotificationRecipient",
]


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
