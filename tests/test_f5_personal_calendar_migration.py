from __future__ import annotations

from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import func, insert, select

from alsoul.storage import create_sqlite_engine, schema

_F5_RECEIPT_SCOPES = (
    "RegisterPersonalCalendarResource",
    "BindCalendarCredential",
    "GrantCalendarReadPermission",
    "ConsumeCalendarReadPermissionGrantEvent",
    "SetPersonalCalendarReadPolicy",
    "SetPersonalWorldRelationshipStatus",
    "SetPersonalResourceBindingStatus",
    "SetCredentialBindingStatus",
    "SetPermissionStatus",
    "BindPersonalCalendarObservationRequest",
    "PreparePersonalCalendarObservation",
    "ReservePersonalCalendarReadPageAttempt",
    "FencePersonalCalendarReadPage",
)


def _alembic_config(database):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    return config


def test_f5_downgrade_clears_v5_operation_receipts(tmp_path, now):
    database = tmp_path / "f5-authority-downgrade.db"
    config = _alembic_config(database)
    command.upgrade(config, "head")

    engine = create_sqlite_engine(database)
    with engine.begin() as conn:
        for scope in _F5_RECEIPT_SCOPES:
            operation_id = uuid4()
            conn.execute(
                insert(schema.operation_receipt).values(
                    operation_scope=scope,
                    operation_id=operation_id,
                    request_digest="0" * 64,
                    result_kind="F5MigrationFixture",
                    result_ref=uuid4(),
                    result_json={"scope": scope},
                    committed_at=now,
                )
            )
    engine.dispose()

    command.downgrade(config, "0004_open_loop_user_alias")

    engine = create_sqlite_engine(database)
    with engine.connect() as conn:
        remaining = conn.execute(
            select(func.count())
            .select_from(schema.operation_receipt)
            .where(schema.operation_receipt.c.operation_scope.in_(_F5_RECEIPT_SCOPES))
        ).scalar_one()
    engine.dispose()

    assert remaining == 0
