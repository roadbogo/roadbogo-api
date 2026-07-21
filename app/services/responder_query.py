from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models.auth import Organization, ResponderProfile, Role, User, UserRole
from app.models.dispatch import DispatchRequest
from app.services.query_common import pagination


def list_responders(
    db: Session,
    *,
    page: int,
    size: int,
    keyword: str | None,
    duty_status: str | None,
    available_only: bool,
) -> dict:
    active_dispatch = (
        select(DispatchRequest.dispatch_request_id)
        .where(
            DispatchRequest.responder_user_id == User.user_id,
            DispatchRequest.active_responder_id.is_not(None),
        )
        .exists()
    )
    conditions = [
        User.account_status == "ACTIVE",
        User.deleted_at.is_(None),
        Role.role_code == "RESPONDER",
        Role.is_active == 1,
        ResponderProfile.is_dispatch_enabled == 1,
    ]
    normalized_keyword = keyword.strip() if keyword else ""
    if normalized_keyword:
        pattern = f"%{normalized_keyword}%"
        conditions.append(
            or_(
                User.user_name.like(pattern),
                ResponderProfile.responder_code.like(pattern),
                ResponderProfile.coverage_area.like(pattern),
            )
        )
    if duty_status:
        conditions.append(ResponderProfile.duty_status == duty_status)
    if available_only:
        conditions.extend(
            [ResponderProfile.duty_status == "AVAILABLE", ~active_dispatch]
        )

    base = (
        select(User.user_id)
        .join(ResponderProfile, ResponderProfile.user_id == User.user_id)
        .join(UserRole, UserRole.user_id == User.user_id)
        .join(Role, Role.role_id == UserRole.role_id)
        .where(*conditions)
        .distinct()
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    duty_order = case(
        (ResponderProfile.duty_status == "AVAILABLE", 1),
        (ResponderProfile.duty_status == "BUSY", 2),
        (ResponderProfile.duty_status == "OFF_DUTY", 3),
        else_=4,
    )
    rows = db.execute(
        select(User, ResponderProfile, Organization, active_dispatch.label("has_active"))
        .join(ResponderProfile, ResponderProfile.user_id == User.user_id)
        .join(UserRole, UserRole.user_id == User.user_id)
        .join(Role, Role.role_id == UserRole.role_id)
        .outerjoin(Organization, Organization.organization_id == User.organization_id)
        .where(*conditions)
        .distinct()
        .order_by(duty_order, User.user_name.asc(), User.user_id.asc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    items = []
    for user, profile, organization, has_active in rows:
        items.append(
            {
                "public_id": user.public_id,
                "user_name": user.user_name,
                "responder_code": profile.responder_code,
                "duty_status": profile.duty_status,
                "is_dispatch_enabled": bool(profile.is_dispatch_enabled),
                "coverage_area": profile.coverage_area,
                "organization": (
                    {
                        "public_id": organization.public_id,
                        "organization_name": organization.organization_name,
                    }
                    if organization
                    else None
                ),
                "has_active_dispatch": bool(has_active),
            }
        )
    return {"items": items, "pagination": pagination(page, size, total)}
