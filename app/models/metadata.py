from sqlalchemy import UniqueConstraint
from sqlalchemy.sql.schema import MetaData


def normalize_mariadb_metadata(metadata: MetaData) -> None:
    """Preserve schema semantics that MariaDB reflection omits or changes."""
    for table in metadata.tables.values():
        for constraint in table.foreign_key_constraints:
            if constraint.ondelete is None:
                constraint.ondelete = "RESTRICT"
                for foreign_key in constraint.elements:
                    foreign_key.ondelete = "RESTRICT"

        for index in list(table.indexes):
            if index.unique and index.name and index.name.startswith("uk_"):
                table.indexes.remove(index)
                UniqueConstraint(*index.columns, name=index.name)
