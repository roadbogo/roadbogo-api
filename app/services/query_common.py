from datetime import UTC, datetime
from decimal import Decimal


def utc_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def number(value: Decimal | int | float | None) -> float | None:
    return None if value is None else float(value)


def pagination(page: int, size: int, total: int) -> dict[str, int]:
    return {
        "page": page,
        "size": size,
        "total_elements": total,
        "total_pages": (total + size - 1) // size if total else 0,
    }


def file_url(file: object | None) -> str | None:
    if (
        file is None
        or getattr(file, "file_status", None) != "ACTIVE"
        or getattr(file, "deleted_at", None) is not None
    ):
        return None
    return f"/api/v1/files/{getattr(file, 'public_id')}/content"
