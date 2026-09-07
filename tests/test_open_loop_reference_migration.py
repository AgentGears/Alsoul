from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import insert, select

from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.services import FoundationBootstrapper
from alsoul.services.foundation_v2 import FoundationServices as FoundationServicesV2
from alsoul.storage import create_sqlite_engine, schema


def _alembic_config(database: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    return config


def test_schema_v3_backfills_only_mechanically_reconstructable_v2_reference(tmp_path, now):
    database = tmp_path / "migration.db"
    config = _alembic_config(database)
    command.upgrade(config, "0002_conversation_open_loop")

    engine = create_sqlite_engine(database)
    ids = FoundationBootstrapper(engine).bootstrap(
        identity_namespace="migration-open-loop",
        external_subject=str(uuid4()),
    )
    services = FoundationServicesV2(engine)
    opening = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="legacy-opening",
            content_text="I need to decide between B and A.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    open_loop_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            insert(schema.conversation_open_loop).values(
                open_loop_id=open_loop_id,
                relationship_id=ids.relationship_id,
                loop_kind="DECISION",
                opened_by_event_id=opening.event_id,
                opened_at=now,
            )
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_sqlite_engine(database)
    with engine.connect() as conn:
        reference = conn.execute(
            select(schema.conversation_open_loop_reference).where(
                schema.conversation_open_loop_reference.c.open_loop_id == open_loop_id
            )
        ).mappings().one()
    engine.dispose()

    assert reference["reference_kind"] == "DECISION_OPTION_PAIR"
    assert reference["reference_contract_version"] == "DECISION_OPTION_PAIR_V1"
    assert reference["canonical_reference_key"] == '["a","b"]'
    assert reference["source_event_id"] == opening.event_id
