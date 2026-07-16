from typing import TYPE_CHECKING, Optional
import datetime
import decimal

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
    DECIMAL,
    INTEGER,
    SMALLINT,
    TEXT,
    TINYINT,
    VARCHAR,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.ai import Detection, ObjectClass
    from app.models.auth import User
    from app.models.dispatch import DispatchRequest
    from app.models.file import File, VideoFrame
    from app.models.infrastructure import Cctv
    from app.models.road import RoadSection
    from app.models.tracking import RiskEvaluation, TrackedObject

__all__ = [
    "Incident",
    "IncidentClaim",
    "IncidentDecision",
    "IncidentEvidence",
    "IncidentFile",
    "IncidentNote",
    "IncidentStateTransition",
    "IncidentStatusHistory",
]


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
