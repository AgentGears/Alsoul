from __future__ import annotations

from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import func, insert, inspect, select

from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import FoundationBootstrapper
from alsoul.storage import create_sqlite_engine, schema


def _alembic_config(database):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    return config


def test_f5b_confirmed_effect_upgrade_preserves_existing_transport_state(tmp_path, now):
    database = tmp_path / "f5b-confirmed-effect-upgrade.db"
    config = _alembic_config(database)
    command.upgrade(config, "0012_personal_calendar_create_transport")

    engine = create_sqlite_engine(database)
    ids = FoundationBootstrapper(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).bootstrap(
        identity_namespace="f5b-confirmed-effect-migration",
        external_subject=str(uuid4()),
    )
    with engine.connect() as conn:
        relationship_before = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id == ids.relationship_id
            )
        ).mappings().one()
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_sqlite_engine(database)
    table_names = set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        relationship_after = conn.execute(
            select(schema.relationship_identity).where(
                schema.relationship_identity.c.relationship_id == ids.relationship_id
            )
        ).mappings().one()
    engine.dispose()

    assert relationship_after["relationship_id"] == relationship_before["relationship_id"]
    assert "personal_calendar_create_effect" in table_names
    assert "personal_calendar_create_effect_support" in table_names


def test_f5b_confirmed_effect_downgrade_clears_v13_receipts_and_tables(tmp_path, now):
    database = tmp_path / "f5b-confirmed-effect-downgrade.db"
    config = _alembic_config(database)
    command.upgrade(config, "head")

    scope = "AdmitPersonalCalendarCreateConfirmedEffect"
    engine = create_sqlite_engine(database)
    with engine.begin() as conn:
        conn.execute(
            insert(schema.operation_receipt).values(
                operation_scope=scope,
                operation_id=uuid4(),
                request_digest="0" * 64,
                result_kind="MigrationFixture",
                result_ref=uuid4(),
                result_json={"fixture": True},
                committed_at=now,
            )
        )
    engine.dispose()

    command.downgrade(config, "0012_personal_calendar_create_transport")

    engine = create_sqlite_engine(database)
    table_names = set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        remaining = conn.execute(
            select(func.count())
            .select_from(schema.operation_receipt)
            .where(schema.operation_receipt.c.operation_scope == scope)
        ).scalar_one()
    engine.dispose()

    assert remaining == 0
    assert "personal_calendar_create_effect" not in table_names
    assert "personal_calendar_create_effect_support" not in table_names
