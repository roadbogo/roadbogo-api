from __future__ import annotations

import argparse
import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy import Connection, text
from sqlalchemy.engine import URL, create_engine

from app.core.config import settings

REFERENCE_DB = "roadbogo_test"
MIGRATION_DB = "roadbogo_orm_test"
IGNORED_TABLES = {"alembic_version"}
SEED_TABLES = (
    "roles",
    "permissions",
    "role_permissions",
    "object_classes",
    "incident_state_transitions",
    "dispatch_state_transitions",
)


def _normalize(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return re.sub(r"\s+", " ", value.replace("`", "").strip()).lower()


def _rows(connection: Connection, query: str, **params: Any) -> list[tuple[Any, ...]]:
    return [
        tuple(_normalize(value) for value in row) for row in connection.execute(text(query), params)
    ]


def _tables(connection: Connection, database: str) -> list[tuple[Any, ...]]:
    return _rows(
        connection,
        """
        SELECT table_name, engine, table_collation
        FROM information_schema.tables
        WHERE table_schema = :database
          AND table_type = 'BASE TABLE'
          AND table_name <> 'alembic_version'
        ORDER BY table_name
        """,
        database=database,
    )


def _columns(connection: Connection, database: str) -> list[tuple[Any, ...]]:
    return _rows(
        connection,
        """
        SELECT
            table_name,
            ordinal_position,
            column_name,
            column_type,
            is_nullable,
            column_default,
            extra,
            generation_expression,
            character_set_name,
            collation_name
        FROM information_schema.columns
        WHERE table_schema = :database
          AND table_name <> 'alembic_version'
        ORDER BY table_name, ordinal_position
        """,
        database=database,
    )


def _foreign_keys(connection: Connection, database: str) -> list[tuple[Any, ...]]:
    return _rows(
        connection,
        """
        SELECT
            k.table_name,
            k.constraint_name,
            k.ordinal_position,
            k.column_name,
            k.referenced_table_name,
            k.referenced_column_name,
            r.delete_rule,
            r.update_rule
        FROM information_schema.key_column_usage k
        JOIN information_schema.referential_constraints r
          ON r.constraint_schema = k.constraint_schema
         AND r.constraint_name = k.constraint_name
         AND r.table_name = k.table_name
        WHERE k.constraint_schema = :database
        ORDER BY k.table_name, k.constraint_name, k.ordinal_position
        """,
        database=database,
    )


def _constraints(connection: Connection, database: str) -> list[tuple[Any, ...]]:
    return _rows(
        connection,
        """
        SELECT
            tc.table_name,
            tc.constraint_name,
            tc.constraint_type,
            cc.check_clause
        FROM information_schema.table_constraints tc
        LEFT JOIN information_schema.check_constraints cc
          ON cc.constraint_schema = tc.constraint_schema
         AND cc.constraint_name = tc.constraint_name
        WHERE tc.constraint_schema = :database
          AND tc.table_name <> 'alembic_version'
          AND tc.constraint_type IN ('CHECK', 'UNIQUE')
        ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name
        """,
        database=database,
    )


def _indexes(connection: Connection, database: str) -> list[tuple[Any, ...]]:
    return _rows(
        connection,
        """
        SELECT
            table_name,
            index_name,
            non_unique,
            seq_in_index,
            column_name,
            collation,
            sub_part,
            index_type
        FROM information_schema.statistics
        WHERE table_schema = :database
          AND table_name <> 'alembic_version'
        ORDER BY table_name, index_name, seq_in_index
        """,
        database=database,
    )


def _views(connection: Connection, database: str) -> list[tuple[Any, ...]]:
    rows = _rows(
        connection,
        """
        SELECT table_name, view_definition, check_option, is_updatable
        FROM information_schema.views
        WHERE table_schema = :database
        ORDER BY table_name
        """,
        database=database,
    )
    return [
        (name, definition.replace(f"{database}.", ""), check_option, is_updatable)
        for name, definition, check_option, is_updatable in rows
    ]


def _primary_key_columns(connection: Connection, database: str, table: str) -> list[str]:
    rows = connection.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.key_column_usage
            WHERE constraint_schema = :database
              AND table_name = :table
              AND constraint_name = 'PRIMARY'
            ORDER BY ordinal_position
            """
        ),
        {"database": database, "table": table},
    )
    return [row[0] for row in rows]


def _seed_rows(connection: Connection, database: str, table: str) -> list[tuple[Any, ...]]:
    primary_key = _primary_key_columns(connection, database, table)
    columns = connection.execute(
        text(
            """
            SELECT column_name, column_default
            FROM information_schema.columns
            WHERE table_schema = :database
              AND table_name = :table
            ORDER BY ordinal_position
            """
        ),
        {"database": database, "table": table},
    )
    comparable_columns = [
        column_name
        for column_name, column_default in columns
        if not (isinstance(column_default, str) and "current_timestamp" in column_default.lower())
    ]
    select_columns = ", ".join(f"`{column}`" for column in comparable_columns)
    order_by = ", ".join(f"`{column}`" for column in primary_key)
    query = f"SELECT {select_columns} FROM `{database}`.`{table}` ORDER BY {order_by}"
    return _rows(connection, query)


def _compare_section(
    label: str,
    reference: Iterable[tuple[Any, ...]],
    migration: Iterable[tuple[Any, ...]],
) -> bool:
    reference_rows = list(reference)
    migration_rows = list(migration)
    if reference_rows == migration_rows:
        print(f"PASS {label}: {len(reference_rows)}")
        return True

    reference_only = sorted(set(reference_rows) - set(migration_rows), key=repr)
    migration_only = sorted(set(migration_rows) - set(reference_rows), key=repr)
    print(f"FAIL {label}")
    for row in reference_only[:10]:
        print(f"  reference-only: {row}")
    for row in migration_only[:10]:
        print(f"  migration-only: {row}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", default=REFERENCE_DB)
    parser.add_argument("--migration", default=MIGRATION_DB)
    args = parser.parse_args()

    url = URL.create(
        "mysql+pymysql",
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
    )
    engine = create_engine(url)

    checks: list[bool] = []
    with engine.connect() as connection:
        sections = (
            ("tables", _tables),
            ("columns", _columns),
            ("foreign keys", _foreign_keys),
            ("CHECK/UNIQUE constraints", _constraints),
            ("indexes", _indexes),
            ("views", _views),
        )
        for label, loader in sections:
            checks.append(
                _compare_section(
                    label,
                    loader(connection, args.reference),
                    loader(connection, args.migration),
                )
            )

        reference_lookup_indexes = {
            (row[0], row[1])
            for row in _indexes(connection, args.reference)
            if row[1].startswith("ix_")
        }
        migration_lookup_indexes = {
            (row[0], row[1])
            for row in _indexes(connection, args.migration)
            if row[1].startswith("ix_")
        }
        checks.append(
            _compare_section(
                "additional lookup indexes",
                sorted(reference_lookup_indexes),
                sorted(migration_lookup_indexes),
            )
        )
        checks.append(
            _compare_section(
                "expected lookup index count",
                [(26,)],
                [(len(migration_lookup_indexes),)],
            )
        )

        for table in SEED_TABLES:
            checks.append(
                _compare_section(
                    f"seed {table}",
                    _seed_rows(connection, args.reference, table),
                    _seed_rows(connection, args.migration, table),
                )
            )

    engine.dispose()
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
