"""Create one local-only controller account using seeded roles and permissions."""

from __future__ import annotations

import os
from uuid import uuid4

ALLOWED_ENVIRONMENTS = {"local", "test"}
DEFAULT_EMAIL = "dev.controller@roadbogo.local"
LOCAL_CONTROL_CENTER_CODE = "LOCAL_CONTROL_CENTER"


def require_development_environment(app_env: str | None) -> None:
    if app_env is None or app_env.lower() not in ALLOWED_ENVIRONMENTS:
        raise RuntimeError(
            "Development controller bootstrap requires APP_ENV to be explicitly set "
            "to local or test."
        )


def bootstrap() -> None:
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models.auth import Organization, Role, User, UserRole
    from app.services.auth import collect_user_summary

    configured_app_env = (
        settings.app_env if "app_env" in settings.model_fields_set else None
    )
    require_development_environment(configured_app_env)
    email = os.getenv("DEV_CONTROLLER_EMAIL", DEFAULT_EMAIL).strip().lower()
    password = os.getenv("DEV_CONTROLLER_PASSWORD", "")
    if not password:
        raise RuntimeError("DEV_CONTROLLER_PASSWORD must be set for this one-time command.")

    with SessionLocal() as db:
        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is not None:
            summary = collect_user_summary(db, existing)
            print(
                f"Controller bootstrap skipped: {email} already exists "
                f"(roles={','.join(summary.roles) or 'none'})."
            )
            return

        role = db.execute(
            select(Role).where(Role.role_code == "CONTROLLER", Role.is_active == 1)
        ).scalar_one_or_none()
        if role is None:
            raise RuntimeError("Seeded CONTROLLER role was not found. Run Alembic migrations first.")

        organization = db.execute(
            select(Organization)
            .where(
                Organization.organization_type == "CONTROL_CENTER",
                Organization.is_active == 1,
            )
            .order_by(Organization.organization_id)
        ).scalars().first()
        if organization is None:
            organization = Organization(
                public_id=str(uuid4()),
                organization_code=LOCAL_CONTROL_CENTER_CODE,
                organization_name="로컬 개발 관제센터",
                organization_type="CONTROL_CENTER",
                is_active=1,
            )
            db.add(organization)
            db.flush()

        user = User(
            public_id=str(uuid4()),
            email=email,
            password_hash=hash_password(password),
            user_name="로컬 개발 관제자",
            account_status="ACTIVE",
            organization_id=organization.organization_id,
        )
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.user_id, role_id=role.role_id))
        db.commit()
        db.refresh(user)
        summary = collect_user_summary(db, user)
        print(
            f"Created local controller {email}; "
            f"organization={organization.organization_name}; "
            f"roles={','.join(summary.roles)}; "
            f"permissions={','.join(summary.permissions)}"
        )


if __name__ == "__main__":
    bootstrap()
