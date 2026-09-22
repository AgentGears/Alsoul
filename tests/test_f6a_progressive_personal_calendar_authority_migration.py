from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select

from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import ProgressivePresentationServices
from alsoul.storage import create_sqlite_engine, schema
from test_f5_personal_calendar_presentation import _adopted_calendar_output
from test_f6a_progressive_personal_calendar_authority import (
    _PersonalProgressiveAdapter,
    _dispatch_command,
    _fence,
    _make_multiframe_output,
    _open,
    _set_disclosure_policy,
)


def _alembic_config(database):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    return config


def test_f6a_progressive_personal_calendar_authority_migration_round_trip_empty(
    tmp_path,
):
    database = tmp_path / "f6a-progressive-calendar-authority-empty.db"
    config = _alembic_config(database)
    command.upgrade(config, "0020_progressive_presentation_interruption_history")
    command.upgrade(config, "head")

    engine = create_sqlite_engine(database)
    try:
        assert (
            "progressive_personal_calendar_frame_authority"
            in set(inspect(engine).get_table_names())
        )
    finally:
        engine.dispose()

    command.downgrade(
        config, "0020_progressive_presentation_interruption_history"
    )
    engine = create_sqlite_engine(database)
    try:
        assert (
            "progressive_personal_calendar_frame_authority"
            not in set(inspect(engine).get_table_names())
        )
    finally:
        engine.dispose()


def test_f6a_progressive_personal_calendar_authority_downgrade_refuses_evidence_loss(
    tmp_path, now
):
    database = tmp_path / "f6a-progressive-calendar-authority-evidence.db"
    config = _alembic_config(database)
    command.upgrade(config, "head")
    engine = create_sqlite_engine(database)

    ctx = _adopted_calendar_output(engine, now)
    _make_multiframe_output(engine, ctx)
    _set_disclosure_policy(engine, now, ctx)
    adapter = _PersonalProgressiveAdapter(now)
    service = ProgressivePresentationServices(
        engine,
        adapter=adapter,
        clock=FixedClock(now),
        ids=UUIDGenerator(),
    )
    session = _open(service, ctx)
    attempt = _fence(service, session)
    service.dispatch_personal_calendar_frame(_dispatch_command(ctx, attempt, 1))
    engine.dispose()

    with pytest.raises(
        RuntimeError,
        match="cannot downgrade F6.A personal-calendar frame authority",
    ):
        command.downgrade(
            config, "0020_progressive_presentation_interruption_history"
        )

    engine = create_sqlite_engine(database)
    try:
        with engine.connect() as conn:
            authority_count = conn.execute(
                select(func.count()).select_from(
                    schema.progressive_personal_calendar_frame_authority
                )
            ).scalar_one()
            version = conn.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
        assert int(authority_count) == 1
        assert version == "0021_progressive_personal_calendar_authority"
    finally:
        engine.dispose()
