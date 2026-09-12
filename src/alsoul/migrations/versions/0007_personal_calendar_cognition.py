"""Add F5.A personal-calendar cognition and model-egress provenance.

Revision ID: 0007_personal_calendar_cognition
Revises: 0006_personal_calendar_acquisition
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete, func, select

from alsoul.storage import schema_v7
from alsoul.storage.schema_v6 import metadata as v6_metadata
from alsoul.storage.schema_v7 import metadata as v7_metadata

revision = "0007_personal_calendar_cognition"
down_revision = "0006_personal_calendar_acquisition"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v7_metadata.tables).difference(v6_metadata.tables)
_RECEIPT_SCOPES = (
    "SetPersonalCalendarFreshnessPolicy",
    "RegisterPersonalCalendarModelRoute",
    "SetPersonalCalendarModelRouteStatus",
    "SetPersonalCalendarModelEgressPolicy",
    "BuildPersonalCalendarProjection",
    "GeneratePersonalCalendarAnswerPlan",
    "AdoptPersonalCalendarScheduleOutput",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v7_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()

    companion_rows = bind.execute(
        select(
            schema_v7.personal_calendar_companion_output.c.companion_output_id,
            schema_v7.personal_calendar_companion_output.c.generated_output_id,
        )
    ).all()
    companion_ids = [row.companion_output_id for row in companion_rows]

    output_target_ids = []
    if companion_ids:
        output_target_ids = list(
            bind.execute(
                select(schema_v7.companion_output.c.output_target_id).where(
                    schema_v7.companion_output.c.companion_output_id.in_(companion_ids)
                )
            ).scalars()
        )
        bind.execute(
            delete(schema_v7.personal_calendar_companion_output).where(
                schema_v7.personal_calendar_companion_output.c.companion_output_id.in_(companion_ids)
            )
        )
        bind.execute(
            delete(schema_v7.companion_output).where(
                schema_v7.companion_output.c.companion_output_id.in_(companion_ids)
            )
        )

    for output_target_id in set(output_target_ids):
        remaining = bind.execute(
            select(func.count())
            .select_from(schema_v7.companion_output)
            .where(schema_v7.companion_output.c.output_target_id == output_target_id)
        ).scalar_one()
        if remaining == 0:
            bind.execute(
                delete(schema_v7.output_target).where(
                    schema_v7.output_target.c.output_target_id == output_target_id
                )
            )

    generated_ids = list(
        bind.execute(
            select(schema_v7.personal_calendar_generated_output.c.generated_output_id)
        ).scalars()
    )
    if generated_ids:
        bind.execute(
            delete(schema_v7.personal_calendar_generated_output).where(
                schema_v7.personal_calendar_generated_output.c.generated_output_id.in_(generated_ids)
            )
        )
        bind.execute(
            delete(schema_v7.generated_output).where(
                schema_v7.generated_output.c.generated_output_id.in_(generated_ids)
            )
        )

    invocation_ids = list(
        bind.execute(
            select(schema_v7.personal_calendar_model_invocation.c.model_invocation_id)
        ).scalars()
    )
    if invocation_ids:
        bind.execute(
            delete(schema_v7.personal_calendar_model_invocation).where(
                schema_v7.personal_calendar_model_invocation.c.model_invocation_id.in_(invocation_ids)
            )
        )
        bind.execute(
            delete(schema_v7.model_invocation).where(
                schema_v7.model_invocation.c.model_invocation_id.in_(invocation_ids)
            )
        )

    # Model-egress decisions point at personal projections, so clear them only after
    # specialized ModelInvocation rows no longer reference the decisions and before
    # deleting projection lineage.
    bind.execute(delete(schema_v7.personal_calendar_model_egress_decision))

    projection_ids = list(
        bind.execute(
            select(schema_v7.personal_calendar_context_projection.c.projection_id)
        ).scalars()
    )
    if projection_ids:
        bind.execute(
            delete(schema_v7.personal_calendar_projection_occurrence).where(
                schema_v7.personal_calendar_projection_occurrence.c.projection_id.in_(projection_ids)
            )
        )
        bind.execute(
            delete(schema_v7.context_projection_world_support).where(
                schema_v7.context_projection_world_support.c.projection_id.in_(projection_ids)
            )
        )
        bind.execute(
            delete(schema_v7.context_projection_world_item).where(
                schema_v7.context_projection_world_item.c.projection_id.in_(projection_ids)
            )
        )
        bind.execute(
            delete(schema_v7.context_projection_event).where(
                schema_v7.context_projection_event.c.projection_id.in_(projection_ids)
            )
        )
        bind.execute(
            delete(schema_v7.personal_calendar_context_projection).where(
                schema_v7.personal_calendar_context_projection.c.projection_id.in_(projection_ids)
            )
        )
        bind.execute(
            delete(schema_v7.context_projection).where(
                schema_v7.context_projection.c.projection_id.in_(projection_ids)
            )
        )

    # Projection rows hold the remaining freshness-decision references.
    bind.execute(delete(schema_v7.personal_calendar_freshness_decision))

    bind.execute(
        delete(schema_v7.operation_receipt).where(
            schema_v7.operation_receipt.c.operation_scope.in_(_RECEIPT_SCOPES)
        )
    )

    for table in reversed(v7_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
