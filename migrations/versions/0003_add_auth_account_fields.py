"""add auth account fields

Revision ID: 0003_add_auth_account_fields
Revises: 0002_seed_views
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0003_add_auth_account_fields"
down_revision: str | Sequence[str] | None = "0002_seed_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_reset_token_hash", mysql.CHAR(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_reset_token_expires_at", mysql.DATETIME(fsp=3), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_changed_at", mysql.DATETIME(fsp=3), nullable=True),
    )
    op.create_index(
        "uk_users_password_reset_token_hash",
        "users",
        ["password_reset_token_hash"],
        unique=True,
    )
    op.add_column(
        "user_sessions",
        sa.Column(
            "is_persistent",
            mysql.TINYINT(display_width=1),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_sessions", "is_persistent")
    op.drop_index("uk_users_password_reset_token_hash", table_name="users")
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "password_reset_token_expires_at")
    op.drop_column("users", "password_reset_token_hash")
