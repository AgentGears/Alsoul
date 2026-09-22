from __future__ import annotations

from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select

from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import FoundationBootstrapper, FoundationServices
from alsoul.storage import create_sqlite_engine, schema
from test_f6a_progressive_presentation_interruption_history import (
    _append_interrupt,
    _interrupt,
    _setup,
    _settle_terminal,
)


def _alembic_config(database):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    return config


def test_f6a_downgrade_refuses_to_discard_canonical_interruption_truth(tmp_path, now):
    database = tmp_path / "f6a-downgrade-safety.db"
    config = _alembic_config(database)
    command.upgrade(config, "head")

    engine = create_sqlite_engine(database)
    services = FoundationServices(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    bootstrapper = FoundationBootstrapper(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    ctx, _adapter, service, _session, attempt = _setup(
        services,
        bootstrapper,
        engine,
        now,
        "interrupted presentation must survive operator migration choices",
    )
    canonical = _append_interrupt(services, ctx, now)
    _interrupt(service, attempt, canonical.event_id)
    engine.dispose()

    with pytest.raises(RuntimeError, match="cannot downgrade F6.A"):
        command.downgrade(config, "0019_progressive_presentation_reception")

    engine = create_sqlite_engine(database)
    try:
        table_names = set(inspect(engine).get_table_names())
        with engine.connect() as conn:
            interruption_count = conn.execute(
                select(func.count()).select_from(
                    schema.progressive_presentation_interruption
                )
            ).scalar_one()
            version = conn.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
    finally:
        engine.dispose()

    assert "progressive_presentation_interruption" in table_names
    assert int(interruption_count) == 1
    assert version == "0020_progressive_presentation_interruption_history"


def test_f6a_downgrade_refuses_to_discard_terminal_ordering_frontier(tmp_path, now):
    database = tmp_path / "f6a-terminal-frontier-downgrade-safety.db"
    config = _alembic_config(database)
    command.upgrade(config, "head")

    engine = create_sqlite_engine(database)
    services = FoundationServices(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    bootstrapper = FoundationBootstrapper(
        engine,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    _ctx, adapter, service, _session, attempt = _setup(
        services,
        bootstrapper,
        engine,
        now,
        "terminal ordering evidence must survive operator migration choices",
    )
    terminal = _settle_terminal(
        service,
        adapter,
        attempt,
        presented=0,
        received=0,
        suffix="downgrade-terminal-frontier",
    )

    with engine.connect() as conn:
        frontier_count = conn.execute(
            select(func.count()).select_from(
                schema.progressive_presentation_terminal_timeline_frontier
            )
        ).scalar_one()
        interruption_count = conn.execute(
            select(func.count()).select_from(
                schema.progressive_presentation_interruption
            )
        ).scalar_one()
    engine.dispose()

    assert terminal.state == "TERMINAL"
    assert int(frontier_count) == 1
    assert int(interruption_count) == 0

    with pytest.raises(RuntimeError, match="cannot downgrade F6.A"):
        command.downgrade(config, "0019_progressive_presentation_reception")

    engine = create_sqlite_engine(database)
    try:
        table_names = set(inspect(engine).get_table_names())
        with engine.connect() as conn:
            preserved_frontier_count = conn.execute(
                select(func.count()).select_from(
                    schema.progressive_presentation_terminal_timeline_frontier
                )
            ).scalar_one()
            version = conn.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
    finally:
        engine.dispose()

    assert "progressive_presentation_terminal_timeline_frontier" in table_names
    assert int(preserved_frontier_count) == 1
    assert version == "0020_progressive_presentation_interruption_history"
