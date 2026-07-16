from typing import TYPE_CHECKING, Optional
import datetime
import decimal

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
    DECIMAL,
    INTEGER,
    TINYINT,
    VARCHAR,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.ai import Detection, ObjectClass
    from app.models.incident import Incident, IncidentEvidence
    from app.models.infrastructure import Cctv

__all__ = [
    "RiskEvaluation",
    "TrackedObject",
    "TrackingSession",
    "TrackObservation",
]


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
