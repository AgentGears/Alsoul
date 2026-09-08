from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from alsoul.domain.commands import AppendCounterpartInputCommand
from alsoul.services import (
    F4ConversationOpenLoopService,
    FoundationBootstrapper,
    FoundationServices,
)
from alsoul.services.foundation_v3 import FoundationServices as FoundationServicesV3
from alsoul.storage import create_sqlite_engine, schema

_ALIAS_ASSIGNMENT_RECEIPT_SCOPE = "ConversationOpenLoopAliasAssignment"


def _alembic_config(database: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    return config


def test_schema_v4_does_not_backfill_user_aliases(tmp_path, now):
    database = tmp_path / "alias-migration.db"
    config = _alembic_config(database)
    command.upgrade(config, "0003_open_loop_reference")

    engine = create_sqlite_engine(database)
    ids = FoundationBootstrapper(engine).bootstrap(
        identity_namespace="migration-alias",
        external_subject=str(uuid4()),
    )
    services = FoundationServicesV3(engine)
    opening = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="legacy-opening",
            content_text="I need to decide between A and B.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    F4ConversationOpenLoopService(services).consider_event(opening.event_id)
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_sqlite_engine(database)
    with engine.connect() as conn:
        loop_count = conn.execute(
            select(func.count()).select_from(schema.conversation_open_loop)
        ).scalar_one()
        reference_count = conn.execute(
            select(func.count()).select_from(schema.conversation_open_loop_reference)
        ).scalar_one()
        alias_count = conn.execute(
            select(func.count()).select_from(schema.conversation_open_loop_alias)
        ).scalar_one()
    engine.dispose()

    assert loop_count == 1
    assert reference_count == 1
    assert alias_count == 0


def test_schema_v4_downgrade_clears_alias_assignment_receipts(tmp_path, now):
    database = tmp_path / "alias-receipt-roundtrip.db"
    config = _alembic_config(database)
    command.upgrade(config, "head")

    engine = create_sqlite_engine(database)
    ids = FoundationBootstrapper(engine).bootstrap(
        identity_namespace="migration-alias-receipt",
        external_subject=str(uuid4()),
    )
    services = FoundationServices(engine)
    opening = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="opening",
            content_text="I need to decide between A and B.",
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    opened = F4ConversationOpenLoopService(services).consider_event(opening.event_id)
    label_event = services.append_counterpart_input(
        AppendCounterpartInputCommand(
            operation_id=uuid4(),
            companion_person_id=ids.companion_person_id,
            counterpart_id=ids.counterpart_id,
            relationship_id=ids.relationship_id,
            ingress_idempotency_key="label",
            content_text='Call the decision between A and B "work".',
            occurred_at=now,
            surface_binding_id=ids.surface_binding_id,
            channel_binding_id=ids.channel_binding_id,
        )
    )
    labeled = F4ConversationOpenLoopService(services).consider_event(label_event.event_id)
    old_alias_id = labeled.open_loop_alias_id
    assert old_alias_id is not None

    with engine.connect() as conn:
        receipt = conn.execute(
            select(schema.operation_receipt).where(
                schema.operation_receipt.c.operation_scope
                == _ALIAS_ASSIGNMENT_RECEIPT_SCOPE,
                schema.operation_receipt.c.operation_id == label_event.event_id,
            )
        ).mappings().one()
    assert receipt["result_ref"] == old_alias_id
    engine.dispose()

    command.downgrade(config, "0003_open_loop_reference")

    engine = create_sqlite_engine(database)
    with engine.connect() as conn:
        receipt_count = conn.execute(
            select(func.count())
            .select_from(schema.operation_receipt)
            .where(
                schema.operation_receipt.c.operation_scope
                == _ALIAS_ASSIGNMENT_RECEIPT_SCOPE
            )
        ).scalar_one()
    engine.dispose()
    assert receipt_count == 0

    command.upgrade(config, "head")

    engine = create_sqlite_engine(database)
    services = FoundationServices(engine)
    rebuilt = F4ConversationOpenLoopService(services).consider_event(label_event.event_id)

    assert not rebuilt.idempotent_replay
    assert rebuilt.open_loop_id == opened.open_loop_id
    assert rebuilt.open_loop_alias_id is not None
    assert rebuilt.open_loop_alias_id != old_alias_id

    with engine.connect() as conn:
        alias = conn.execute(
            select(schema.conversation_open_loop_alias).where(
                schema.conversation_open_loop_alias.c.source_event_id == label_event.event_id
            )
        ).mappings().one()
        receipt = conn.execute(
            select(schema.operation_receipt).where(
                schema.operation_receipt.c.operation_scope
                == _ALIAS_ASSIGNMENT_RECEIPT_SCOPE,
                schema.operation_receipt.c.operation_id == label_event.event_id,
            )
        ).mappings().one()
    engine.dispose()

    assert alias["open_loop_alias_id"] == rebuilt.open_loop_alias_id
    assert receipt["result_ref"] == rebuilt.open_loop_alias_id
