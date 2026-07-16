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
    TINYINT,
    VARCHAR,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.ai import AiModelVersion, InferenceRun
    from app.models.auth import User
    from app.models.dispatch import FieldActionFile
    from app.models.incident import IncidentEvidence, IncidentFile
    from app.models.infrastructure import Cctv

__all__ = [
    "File",
    "VideoFrame",
]


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
