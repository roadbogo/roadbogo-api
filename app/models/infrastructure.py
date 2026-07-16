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
    TINYINT,
    VARCHAR,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.file import VideoFrame
    from app.models.incident import Incident
    from app.models.road import RoadSection
    from app.models.tracking import TrackedObject, TrackingSession

__all__ = [
    "Cctv",
    "CctvStream",
    "ItsSyncRun",
]


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
