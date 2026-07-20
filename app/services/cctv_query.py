from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.exceptions import AppException
from app.models.infrastructure import Cctv, CctvStream, ItsSyncRun
from app.models.road import RoadSection
from app.services.query_common import number, pagination, utc_z


def _stream(cctv: Cctv, now: datetime) -> CctvStream | None:
    candidates = [
        stream
        for stream in cctv.cctv_streams
        if stream.is_primary
        and stream.stream_status == "ACTIVE"
        and (stream.valid_to is None or stream.valid_to > now)
    ]
    return max(candidates, key=lambda stream: stream.valid_from, default=None)


def _road(cctv: Cctv) -> tuple[dict, dict]:
    section = cctv.road_section
    road = section.road
    return (
        {"public_id": road.public_id, "road_code": road.road_code, "road_name": road.road_name},
        {
            "public_id": section.public_id,
            "section_code": section.section_code,
            "section_name": section.section_name,
        },
    )


def list_cctvs(db: Session, *, page: int, size: int, filters: dict, sort: str) -> dict:
    conditions = [Cctv.deleted_at.is_(None)]
    if filters.get("keyword"):
        conditions.append(Cctv.cctv_name.contains(filters["keyword"]))
    for key in ("direction_code", "operational_status", "source_type"):
        if filters.get(key):
            conditions.append(getattr(Cctv, key) == filters[key])
    section_filters = []
    if filters.get("road_section_public_id"):
        section_filters.append(RoadSection.public_id == str(filters["road_section_public_id"]))
    if filters.get("road_public_id"):
        section_filters.append(RoadSection.road.has(public_id=str(filters["road_public_id"])))
    if section_filters:
        conditions.append(Cctv.road_section.has(and_(*section_filters)))
    bounds = (
        ("min_latitude", Cctv.latitude, ">="),
        ("max_latitude", Cctv.latitude, "<="),
        ("min_longitude", Cctv.longitude, ">="),
        ("max_longitude", Cctv.longitude, "<="),
    )
    for key, column, operation in bounds:
        if filters.get(key) is not None:
            conditions.append(column >= filters[key] if operation == ">=" else column <= filters[key])

    total = db.scalar(select(func.count()).select_from(Cctv).where(*conditions)) or 0
    sort_map = {"cctv_name,asc": Cctv.cctv_name.asc()}
    stmt = (
        select(Cctv)
        .where(*conditions)
        .options(
            joinedload(Cctv.road_section).joinedload(RoadSection.road),
            selectinload(Cctv.cctv_streams),
        )
        .order_by(sort_map[sort], Cctv.cctv_id.asc())
        .offset((page - 1) * size)
        .limit(size)
    )
    now = datetime.utcnow()
    items = []
    for cctv in db.scalars(stmt).unique():
        road, section = _road(cctv)
        items.append(
            {
                "public_id": cctv.public_id,
                "cctv_code": cctv.cctv_code,
                "cctv_name": cctv.cctv_name,
                "source_type": cctv.source_type,
                "direction_code": cctv.direction_code,
                "latitude": number(cctv.latitude),
                "longitude": number(cctv.longitude),
                "km_post": number(cctv.km_post),
                "operational_status": cctv.operational_status,
                "is_active": bool(cctv.is_active),
                "has_stream": _stream(cctv, now) is not None,
                "road": road,
                "road_section": section,
                "last_successful_sync_at": utc_z(cctv.last_successful_sync_at),
            }
        )
    latest_sync = db.scalars(
        select(ItsSyncRun).order_by(ItsSyncRun.started_at.desc()).limit(1)
    ).first()
    return {
        "items": items,
        "pagination": pagination(page, size, total),
        "fallback_used": bool(latest_sync and latest_sync.used_fallback_data),
    }


def get_cctv(db: Session, public_id: str) -> dict:
    cctv = db.scalars(
        select(Cctv)
        .where(Cctv.public_id == public_id, Cctv.deleted_at.is_(None))
        .options(
            joinedload(Cctv.road_section).joinedload(RoadSection.road),
            selectinload(Cctv.cctv_streams),
        )
    ).unique().first()
    if cctv is None:
        raise AppException(404, "CCTV_NOT_FOUND", "CCTV 정보를 찾을 수 없습니다.")
    stream = _stream(cctv, datetime.utcnow())
    road, section = _road(cctv)
    return {
        "public_id": cctv.public_id,
        "cctv_code": cctv.cctv_code,
        "external_its_cctv_id": cctv.external_its_cctv_id,
        "cctv_name": cctv.cctv_name,
        "source_type": cctv.source_type,
        "direction_code": cctv.direction_code,
        "latitude": number(cctv.latitude),
        "longitude": number(cctv.longitude),
        "km_post": number(cctv.km_post),
        "operational_status": cctv.operational_status,
        "is_active": bool(cctv.is_active),
        "road": road,
        "road_section": section,
        "stream": {
            "available": stream is not None,
            "stream_type": stream.stream_type if stream else None,
            "protocol_type": stream.protocol_type if stream else None,
            "stream_status": stream.stream_status if stream else None,
        },
        "last_successful_sync_at": utc_z(cctv.last_successful_sync_at),
        "created_at": utc_z(cctv.created_at),
        "updated_at": utc_z(cctv.updated_at),
    }
