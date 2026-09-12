from __future__ import annotations

from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import func, insert, inspect, select

from alsoul.storage import create_sqlite_engine, schema


def _alembic_config(database):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    return config


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
