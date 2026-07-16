from typing import TYPE_CHECKING, Optional
import datetime
import decimal

from sqlalchemy import (
    CheckConstraint,
    DATE,
    ForeignKeyConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.mysql import (
    BIGINT,
    CHAR,
    DATETIME,
    DECIMAL,
    TINYINT,
    VARCHAR,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.incident import Incident
    from app.models.infrastructure import Cctv

__all__ = [
    "BusinessSequence",
    "Road",
    "RoadSection",
]


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
