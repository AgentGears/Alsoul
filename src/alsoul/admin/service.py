from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from alsoul.domain.models import FoundationIds
from alsoul.services.bootstrap import FoundationBootstrapper
from alsoul.storage import create_sqlite_engine, schema

FoundationState = Literal["NOT_READY", "EMPTY", "BOOTSTRAPPED", "INCONSISTENT"]


class AdministrationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class StoreStatus:
    database_path: Path
    database_exists: bool
    database_accessible: bool
    schema_revision: str | None
    schema_head_revision: str
    schema_at_head: bool
    missing_tables: tuple[str, ...]
    foundation_state: FoundationState
    companion_person_count: int = 0
    counterpart_person_count: int = 0
    relationship_count: int = 0


@dataclass(frozen=True, slots=True)
class InitializeStoreResult:
    database_path: Path
    schema_revision: str


@dataclass(frozen=True, slots=True)
class MigrateStoreResult:
    database_path: Path
    previous_revision: str | None
    schema_revision: str
    changed: bool


class FoundationAdministrator:
    """Explicit administration boundary for F4 persistence and identity creation.

    This service is intentionally separate from the runtime host. Runtime recovery
    must never call it to repair missing canonical identity by manufacturing a new
    Person, CounterpartPerson, or RelationshipState.
    """

    def initialize_store(self, database_path: str | Path) -> InitializeStoreResult:
        path = _resolve_database_path(database_path)
        if not path.parent.is_dir():
            raise AdministrationError(
                "ADMIN_DATABASE_PARENT_MISSING",
                "database parent directory does not exist",
            )
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        except FileExistsError as exc:
            raise AdministrationError(
                "ADMIN_DATABASE_ALREADY_EXISTS",
                "database path already exists; initialization never overwrites it",
            ) from exc
        except OSError as exc:
            raise AdministrationError(
                "ADMIN_DATABASE_CREATE_FAILED",
                "database file could not be reserved for initialization",
            ) from exc

        try:
            self._upgrade_to_head(path)
            status = self.status(path)
            if not status.schema_at_head or status.schema_revision is None:
                raise AdministrationError(
                    "ADMIN_SCHEMA_INITIALIZATION_FAILED",
                    "initialized database did not reach the packaged schema head",
                )
            return InitializeStoreResult(path, status.schema_revision)
        except Exception:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def migrate_store(self, database_path: str | Path) -> MigrateStoreResult:
        path = _resolve_database_path(database_path)
        before = self.status(path)
        if not before.database_exists:
            raise AdministrationError(
                "ADMIN_DATABASE_MISSING",
                "database does not exist; use initialize-store for first creation",
            )
        if not before.database_accessible:
            raise AdministrationError(
                "ADMIN_DATABASE_UNAVAILABLE",
                "database cannot be opened for migration",
            )
        self._upgrade_to_head(path)
        after = self.status(path)
        if not after.schema_at_head or after.schema_revision is None:
            raise AdministrationError(
                "ADMIN_SCHEMA_MIGRATION_FAILED",
                "database did not reach the packaged schema head",
            )
        return MigrateStoreResult(
            database_path=path,
            previous_revision=before.schema_revision,
            schema_revision=after.schema_revision,
            changed=before.schema_revision != after.schema_revision,
        )

    def bootstrap_foundation(
        self,
        database_path: str | Path,
        *,
        identity_namespace: str,
        external_subject: str,
        surface_namespace: str = "alsoul.first_party",
        surface_ref: str = "primary-text-surface",
        channel_namespace: str = "alsoul.first_party",
        channel_ref: str = "primary-text-channel",
    ) -> FoundationIds:
        path = _resolve_database_path(database_path)
        before = self.status(path)
        if not before.database_exists or not before.database_accessible:
            raise AdministrationError(
                "ADMIN_DATABASE_NOT_READY",
                "database must be initialized before foundation bootstrap",
            )
        if not before.schema_at_head:
            raise AdministrationError(
                "ADMIN_SCHEMA_NOT_AT_HEAD",
                "database schema must be migrated to the packaged head before bootstrap",
            )
        if before.foundation_state != "EMPTY":
            raise AdministrationError(
                "ADMIN_FOUNDATION_NOT_EMPTY",
                "foundation bootstrap requires an empty initialized identity graph",
            )
        for field_name, value in (
            ("identity_namespace", identity_namespace),
            ("external_subject", external_subject),
            ("surface_namespace", surface_namespace),
            ("surface_ref", surface_ref),
            ("channel_namespace", channel_namespace),
            ("channel_ref", channel_ref),
        ):
            if not isinstance(value, str) or not value.strip():
                raise AdministrationError(
                    "ADMIN_BOOTSTRAP_ARGUMENT_INVALID",
                    f"{field_name} must be a non-empty string",
                )

        engine = create_sqlite_engine(path)
        try:
            ids = FoundationBootstrapper(engine).bootstrap(
                identity_namespace=identity_namespace.strip(),
                external_subject=external_subject.strip(),
                surface_namespace=surface_namespace.strip(),
                surface_ref=surface_ref.strip(),
                channel_namespace=channel_namespace.strip(),
                channel_ref=channel_ref.strip(),
            )
        except SQLAlchemyError as exc:
            raise AdministrationError(
                "ADMIN_FOUNDATION_BOOTSTRAP_FAILED",
                "foundation identity graph could not be committed",
            ) from exc
        finally:
            engine.dispose()

        after = self.status(path)
        if after.foundation_state != "BOOTSTRAPPED":
            raise AdministrationError(
                "ADMIN_FOUNDATION_BOOTSTRAP_INCONSISTENT",
                "foundation bootstrap did not produce the expected F4 identity graph",
            )
        return ids

    def status(self, database_path: str | Path) -> StoreStatus:
        path = _resolve_database_path(database_path)
        head = self.schema_head_revision()
        if not path.is_file():
            return StoreStatus(
                database_path=path,
                database_exists=False,
                database_accessible=False,
                schema_revision=None,
                schema_head_revision=head,
                schema_at_head=False,
                missing_tables=tuple(sorted(schema.metadata.tables)),
                foundation_state="NOT_READY",
            )

        engine = create_sqlite_engine(path)
        try:
            try:
                with engine.connect() as conn:
                    conn.exec_driver_sql("SELECT 1").scalar_one()
                    inspector = inspect(conn)
                    actual_tables = set(inspector.get_table_names())
                    expected_tables = set(schema.metadata.tables)
                    missing_tables = tuple(sorted(expected_tables - actual_tables))
                    revision = _read_schema_revision(conn, actual_tables)
                    if missing_tables:
                        return StoreStatus(
                            database_path=path,
                            database_exists=True,
                            database_accessible=True,
                            schema_revision=revision,
                            schema_head_revision=head,
                            schema_at_head=False,
                            missing_tables=missing_tables,
                            foundation_state="NOT_READY",
                        )
                    companion_count = conn.execute(
                        select(func.count()).select_from(schema.companion_person)
                    ).scalar_one()
                    counterpart_count = conn.execute(
                        select(func.count()).select_from(schema.counterpart_person)
                    ).scalar_one()
                    relationship_count = conn.execute(
                        select(func.count()).select_from(schema.relationship_identity)
                    ).scalar_one()
                    foundation_state = _foundation_state(
                        conn,
                        companion_count=companion_count,
                        counterpart_count=counterpart_count,
                        relationship_count=relationship_count,
                    )
            except (OSError, SQLAlchemyError):
                return StoreStatus(
                    database_path=path,
                    database_exists=True,
                    database_accessible=False,
                    schema_revision=None,
                    schema_head_revision=head,
                    schema_at_head=False,
                    missing_tables=(),
                    foundation_state="NOT_READY",
                )
        finally:
            engine.dispose()

        return StoreStatus(
            database_path=path,
            database_exists=True,
            database_accessible=True,
            schema_revision=revision,
            schema_head_revision=head,
            schema_at_head=revision == head,
            missing_tables=(),
            foundation_state=foundation_state if revision == head else "NOT_READY",
            companion_person_count=int(companion_count),
            counterpart_person_count=int(counterpart_count),
            relationship_count=int(relationship_count),
        )

    def schema_head_revision(self) -> str:
        script = ScriptDirectory.from_config(_migration_config(None))
        head = script.get_current_head()
        if head is None:
            raise AdministrationError(
                "ADMIN_MIGRATION_HEAD_MISSING",
                "packaged migration environment has no head revision",
            )
        return head

    def _upgrade_to_head(self, path: Path) -> None:
        try:
            command.upgrade(_migration_config(path), "head")
        except Exception as exc:
            raise AdministrationError(
                "ADMIN_SCHEMA_MIGRATION_FAILED",
                "schema migration to packaged head failed",
            ) from exc


def _migration_config(database_path: Path | None) -> Config:
    config = Config()
    migration_root = Path(__file__).resolve().parents[1] / "migrations"
    config.set_main_option("script_location", str(migration_root))
    if database_path is not None:
        url = URL.create("sqlite+pysqlite", database=str(database_path))
        config.set_main_option(
            "sqlalchemy.url",
            url.render_as_string(hide_password=False),
        )
    return config


def _read_schema_revision(conn, actual_tables: set[str]) -> str | None:
    if "alembic_version" not in actual_tables:
        return None
    rows = conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalars().all()
    if len(rows) > 1:
        return None
    return rows[0] if rows else None


def _foundation_state(
    conn,
    *,
    companion_count: int,
    counterpart_count: int,
    relationship_count: int,
) -> FoundationState:
    identity_binding_count = conn.execute(
        select(func.count()).select_from(schema.counterpart_identity_binding)
    ).scalar_one()
    self_head_count = conn.execute(select(func.count()).select_from(schema.self_head)).scalar_one()
    relationship_head_count = conn.execute(
        select(func.count()).select_from(schema.relationship_head)
    ).scalar_one()
    timeline_head_count = conn.execute(
        select(func.count()).select_from(schema.relationship_timeline_head)
    ).scalar_one()
    surface_count = conn.execute(
        select(func.count()).select_from(schema.surface_binding)
    ).scalar_one()
    channel_count = conn.execute(
        select(func.count()).select_from(schema.channel_binding)
    ).scalar_one()

    counts = (
        int(companion_count),
        int(counterpart_count),
        int(relationship_count),
        int(identity_binding_count),
        int(self_head_count),
        int(relationship_head_count),
        int(timeline_head_count),
        int(surface_count),
        int(channel_count),
    )
    if all(count == 0 for count in counts):
        return "EMPTY"
    if all(count == 1 for count in counts):
        return "BOOTSTRAPPED"
    return "INCONSISTENT"


def _resolve_database_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


__all__ = [
    "AdministrationError",
    "FoundationAdministrator",
    "InitializeStoreResult",
    "MigrateStoreResult",
    "StoreStatus",
]
