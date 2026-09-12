from __future__ import annotations

from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select

from alsoul.domain.personal_calendar_cognition import (
    RegisterPersonalCalendarModelRouteCommand,
    SetPersonalCalendarFreshnessPolicyCommand,
    SetPersonalCalendarModelEgressPolicyCommand,
)
from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import FoundationBootstrapper
from alsoul.services.personal_calendar_cognition import PersonalCalendarCognitionServices
from alsoul.storage import create_sqlite_engine, schema


def _config(database):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    return config


def test_f5_cognition_upgrade_and_downgrade_preserve_boundary(tmp_path, now):
    database = tmp_path / "f5-cognition-migration.db"
    config = _config(database)
    command.upgrade(config, "0006_personal_calendar_acquisition")
    engine = create_sqlite_engine(database)
    before = set(inspect(engine).get_table_names())
    engine.dispose()
    assert "personal_calendar_context_projection" not in before

    command.upgrade(config, "head")
    engine = create_sqlite_engine(database)
    ids = FoundationBootstrapper(
        engine, clock=FixedClock(now), ids=UUIDGenerator()
    ).bootstrap(
        identity_namespace="f5-cognition-migration",
        external_subject=str(uuid4()),
    )
    cognition = PersonalCalendarCognitionServices(
        engine, clock=FixedClock(now), ids=UUIDGenerator()
    )
    cognition.set_freshness_policy(
        SetPersonalCalendarFreshnessPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ids.relationship_id,
            policy_version="migration-freshness-v1",
            max_age_seconds=60,
        )
    )
    route = cognition.register_model_route(
        RegisterPersonalCalendarModelRouteCommand(
            operation_id=uuid4(),
            provider_binding_ref="migration/model-route",
            model_ref="migration-model-v1",
            route_contract_version="migration-route-v1",
            data_handling_contract_version="migration-data-v1",
            retention_class="NO_RETAIN",
            residency_class="TRUSTED_BOUNDARY_A",
        )
    )
    cognition.set_model_egress_policy(
        SetPersonalCalendarModelEgressPolicyCommand(
            operation_id=uuid4(),
            relationship_id=ids.relationship_id,
            policy_version="migration-egress-v1",
            allowed_route_binding_ids=(route.route_binding_id,),
            required_retention_class="NO_RETAIN",
            required_residency_class="TRUSTED_BOUNDARY_A",
        )
    )
    after = set(inspect(engine).get_table_names())
    assert "personal_calendar_context_projection" in after
    assert "personal_calendar_model_egress_decision" in after
    engine.dispose()

    command.downgrade(config, "0006_personal_calendar_acquisition")
    engine = create_sqlite_engine(database)
    tables = set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        remaining_receipts = conn.execute(
            select(func.count())
            .select_from(schema.operation_receipt)
            .where(
                schema.operation_receipt.c.operation_scope.in_(
                    (
                        "SetPersonalCalendarFreshnessPolicy",
                        "RegisterPersonalCalendarModelRoute",
                        "SetPersonalCalendarModelEgressPolicy",
                    )
                )
            )
        ).scalar_one()
    engine.dispose()
    assert remaining_receipts == 0
    assert "personal_calendar_freshness_policy_revision" not in tables
    assert "personal_calendar_model_route_binding" not in tables
    assert "personal_calendar_model_egress_policy_revision" not in tables
    assert "personal_calendar_context_projection" not in tables
