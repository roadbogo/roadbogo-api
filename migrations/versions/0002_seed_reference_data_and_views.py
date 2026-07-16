"""Seed reference data and create application views.

Revision ID: 0002_seed_views
Revises: 0001_models
"""

import re
from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0002_seed_views"
down_revision: str | Sequence[str] | None = "0001_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
SQL_FILES = ("reference_seed.sql", "application_views.sql")
VIEW_NAMES = (
    "v_unread_notification_counts",
    "v_responder_active_dispatches",
    "v_incident_dashboard",
)


def _statements(filename: str) -> list[str]:
    sql = (SQL_DIR / filename).read_text(encoding="utf-8")
    sql = re.sub(r"(?m)^\s*USE\s+roadbogo\s*;\s*$", "", sql)
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


def upgrade() -> None:
    op.execute("SET NAMES utf8mb3")
    try:
        for filename in SQL_FILES:
            for statement in _statements(filename):
                op.execute(statement)
    finally:
        op.execute("SET NAMES utf8mb4")


def downgrade() -> None:
    for view_name in VIEW_NAMES:
        op.execute(f"DROP VIEW IF EXISTS {view_name}")

    op.execute(
        """
        DELETE rp
        FROM role_permissions AS rp
        JOIN roles AS r ON r.role_id = rp.role_id
        JOIN permissions AS p ON p.permission_id = rp.permission_id
        WHERE r.role_code IN (
            'SYSTEM_ADMIN', 'CONTROL_MANAGER', 'CONTROLLER', 'RESPONDER',
            'GENERAL_USER', 'AI_MODEL_USER'
        )
        """
    )
    op.execute("DELETE FROM dispatch_state_transitions")
    op.execute("DELETE FROM incident_state_transitions")
    op.execute(
        """
        DELETE FROM object_classes
        WHERE class_code IN (
            'CAR', 'BUS', 'TRUCK', 'MOTORCYCLE', 'BOX', 'TIRE', 'CARGO', 'WILDLIFE'
        )
        """
    )
    op.execute(
        """
        DELETE FROM permissions
        WHERE permission_code IN (
            'USER.READ_ALL', 'USER.WRITE', 'ROLE.MANAGE', 'CCTV.READ', 'CCTV.MANAGE',
            'INCIDENT.READ_ALL', 'INCIDENT.READ_ASSIGNED', 'INCIDENT.CLAIM',
            'INCIDENT.DECIDE', 'INCIDENT.CLOSE', 'DISPATCH.ASSIGN', 'DISPATCH.READ_OWN',
            'DISPATCH.UPDATE_OWN', 'FILE.READ_ASSIGNED', 'FILE.UPLOAD_ACTION',
            'NOTIFICATION.READ_OWN', 'AUDIT.READ', 'DB.STATUS.READ'
        )
        """
    )
    op.execute(
        """
        DELETE FROM roles
        WHERE role_code IN (
            'SYSTEM_ADMIN', 'CONTROL_MANAGER', 'CONTROLLER', 'RESPONDER',
            'GENERAL_USER', 'AI_MODEL_USER'
        )
        """
    )
