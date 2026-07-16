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
    SMALLINT,
    TINYINT,
    VARCHAR,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.file import File, VideoFrame
    from app.models.incident import Incident, IncidentEvidence
    from app.models.tracking import RiskEvaluation, TrackedObject, TrackObservation

__all__ = [
    "AiModel",
    "AiModelVersion",
    "Detection",
    "InferenceRun",
    "ModelVersionClass",
    "ObjectClass",
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
