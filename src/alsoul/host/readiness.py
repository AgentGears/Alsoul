from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from alsoul.host.config import FoundationHostConfig
from alsoul.storage import create_sqlite_engine, schema

EXPECTED_SCHEMA_ID = "f4-v1"


@dataclass(frozen=True, slots=True)
class HostReadiness:
    ready: bool
    expected_schema_id: str
    database_exists: bool
    database_accessible: bool
    schema_compatible: bool
    missing_tables: tuple[str, ...] = ()
    missing_columns: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()


class HostReadinessError(RuntimeError):
    def __init__(self, readiness: HostReadiness) -> None:
        super().__init__("Alsoul runtime host is not ready")
        self.readiness = readiness


def assess_host_readiness(config: FoundationHostConfig) -> HostReadiness:
    database_exists = config.database_path.is_file()
    if not database_exists:
        return HostReadiness(
            ready=False,
            expected_schema_id=EXPECTED_SCHEMA_ID,
            database_exists=False,
            database_accessible=False,
            schema_compatible=False,
            problems=("DATABASE_MISSING",),
        )

    engine = create_sqlite_engine(config.database_path)
    try:
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1").scalar_one()
                foreign_keys = conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
        except (OSError, SQLAlchemyError):
            return HostReadiness(
                ready=False,
                expected_schema_id=EXPECTED_SCHEMA_ID,
                database_exists=True,
                database_accessible=False,
                schema_compatible=False,
                problems=("DATABASE_UNAVAILABLE",),
            )

        try:
            inspector = inspect(engine)
            actual_tables = set(inspector.get_table_names())
            expected_tables = set(schema.metadata.tables)
            missing_tables = tuple(sorted(expected_tables - actual_tables))

            missing_columns: list[str] = []
            for table_name in sorted(expected_tables & actual_tables):
                expected = set(schema.metadata.tables[table_name].c.keys())
                actual = {column["name"] for column in inspector.get_columns(table_name)}
                missing_columns.extend(
                    f"{table_name}.{column}" for column in sorted(expected - actual)
                )
        except SQLAlchemyError:
            return HostReadiness(
                ready=False,
                expected_schema_id=EXPECTED_SCHEMA_ID,
                database_exists=True,
                database_accessible=True,
                schema_compatible=False,
                problems=("SCHEMA_INSPECTION_FAILED",),
            )

        problems: list[str] = []
        if missing_tables:
            problems.append("SCHEMA_TABLES_MISSING")
        if missing_columns:
            problems.append("SCHEMA_COLUMNS_MISSING")
        if foreign_keys != 1:
            problems.append("FOREIGN_KEYS_DISABLED")

        schema_compatible = not missing_tables and not missing_columns and foreign_keys == 1
        return HostReadiness(
            ready=schema_compatible,
            expected_schema_id=EXPECTED_SCHEMA_ID,
            database_exists=True,
            database_accessible=True,
            schema_compatible=schema_compatible,
            missing_tables=missing_tables,
            missing_columns=tuple(missing_columns),
            problems=tuple(problems),
        )
    finally:
        engine.dispose()


def require_host_readiness(config: FoundationHostConfig) -> HostReadiness:
    readiness = assess_host_readiness(config)
    if not readiness.ready:
        raise HostReadinessError(readiness)
    return readiness


__all__ = [
    "EXPECTED_SCHEMA_ID",
    "HostReadiness",
    "HostReadinessError",
    "assess_host_readiness",
    "require_host_readiness",
]
