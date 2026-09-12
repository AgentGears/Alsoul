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


def test_f5_acquisition_upgrade_preserves_referenced_f4_evidence(tmp_path, now):
    database = tmp_path / "f5-acquisition-upgrade.db"
    config = _alembic_config(database)
    command.upgrade(config, "0005_personal_calendar_authority")

    engine = create_sqlite_engine(database)
    ids = FoundationBootstrapper(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    ).bootstrap(
        identity_namespace="f5-acquisition-migration",
        external_subject=str(uuid4()),
    )
    investigation_id = uuid4()
    evidence_id = uuid4()
    world_result_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            insert(schema.investigation).values(
                investigation_id=investigation_id,
                initiated_by_companion_person_id=ids.companion_person_id,
                relationship_id=ids.relationship_id,
                conversation_id="migration-fixture",
                objective="Preserve referenced F4 evidence through v6 migration.",
                started_at=now,
                status="OPEN",
            )
        )
        conn.execute(
            insert(schema.evidence_item).values(
                evidence_id=evidence_id,
                origin_kind="SEARCH_RESULT",
                source_type="MIGRATION_FIXTURE",
                source_id=uuid4(),
                source_locator="fixture://f4-evidence",
                source_actor_ref=None,
                recorded_at=now,
            )
        )
        conn.execute(
            insert(schema.world_result).values(
                world_result_id=world_result_id,
                investigation_id=investigation_id,
                result_kind="MIGRATION_FIXTURE",
                predicate="migration.fixture",
                value_json={"preserved": True},
                valid_as_of=now,
                derived_at=now,
            )
        )
        conn.execute(
            insert(schema.world_result_evidence).values(
                world_result_id=world_result_id,
                evidence_id=evidence_id,
                relation="SUPPORTS",
            )
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_sqlite_engine(database)
    with engine.connect() as conn:
        evidence = conn.execute(
            select(schema.evidence_item).where(
                schema.evidence_item.c.evidence_id == evidence_id
            )
        ).mappings().one()
        support_count = conn.execute(
            select(func.count())
            .select_from(schema.world_result_evidence)
            .where(
                schema.world_result_evidence.c.world_result_id == world_result_id,
                schema.world_result_evidence.c.evidence_id == evidence_id,
                schema.world_result_evidence.c.relation == "SUPPORTS",
            )
        ).scalar_one()
    engine.dispose()

    assert evidence["origin_kind"] == "SEARCH_RESULT"
    assert support_count == 1


def test_f5_acquisition_downgrade_clears_v6_receipt_and_tables(tmp_path, now):
    database = tmp_path / "f5-acquisition-downgrade.db"
    config = _alembic_config(database)
    command.upgrade(config, "head")

    engine = create_sqlite_engine(database)
    with engine.begin() as conn:
        conn.execute(
            insert(schema.operation_receipt).values(
                operation_scope="AcquirePersonalCalendarObservation",
                operation_id=uuid4(),
                request_digest="0" * 64,
                result_kind="PersonalCalendarWorldResult",
                result_ref=uuid4(),
                result_json={"fixture": True},
                committed_at=now,
            )
        )
    engine.dispose()

    command.downgrade(config, "0005_personal_calendar_authority")

    engine = create_sqlite_engine(database)
    table_names = set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        remaining_receipts = conn.execute(
            select(func.count())
            .select_from(schema.operation_receipt)
            .where(
                schema.operation_receipt.c.operation_scope
                == "AcquirePersonalCalendarObservation"
            )
        ).scalar_one()
    engine.dispose()

    assert remaining_receipts == 0
    assert "personal_calendar_acquisition_attempt" not in table_names
    assert "personal_calendar_acquisition_page" not in table_names
    assert "personal_calendar_source_capture" not in table_names
    assert "personal_calendar_world_result" not in table_names
