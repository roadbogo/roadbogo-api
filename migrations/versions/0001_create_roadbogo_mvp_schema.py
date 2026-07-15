"""Create the verified Roadbogo MVP schema."""

import re
from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0001_roadbogo_mvp"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
SQL_FILES = (
    "mvp_schema.sql",
    "mvp_reference_seed.sql",
    "mvp_views.sql",
)


def _statements(filename: str) -> list[str]:
    sql = (SQL_DIR / filename).read_text(encoding="utf-8")
    sql = re.sub(r"(?m)^\s*USE\s+roadbogo\s*;\s*$", "", sql)
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("SET NAMES utf8mb3")
    try:
        for filename in SQL_FILES:
            for statement in _statements(filename):
                connection.exec_driver_sql(statement)
    finally:
        connection.exec_driver_sql("SET NAMES utf8mb4")


def downgrade() -> None:
    connection = op.get_bind()
    for view_name in (
        "v_unread_notification_counts",
        "v_responder_active_dispatches",
        "v_incident_dashboard",
    ):
        connection.exec_driver_sql(f"DROP VIEW IF EXISTS {view_name}")

    schema_sql = (SQL_DIR / "mvp_schema.sql").read_text(encoding="utf-8")
    table_names = re.findall(r"(?m)^CREATE TABLE\s+([a-z0-9_]+)", schema_sql)
    connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
    try:
        for table_name in reversed(table_names):
            connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table_name}")
    finally:
        connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")
