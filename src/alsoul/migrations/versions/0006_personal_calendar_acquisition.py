"""Add coherent F5.A personal-calendar acquisition lineage.

Revision ID: 0006_personal_calendar_acquisition
Revises: 0005_personal_calendar_authority
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import delete, func, select, update

from alsoul.storage import schema_v6
from alsoul.storage.schema_v5 import metadata as v5_metadata
from alsoul.storage.schema_v6 import metadata as v6_metadata

revision = "0006_personal_calendar_acquisition"
down_revision = "0005_personal_calendar_authority"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v6_metadata.tables).difference(v5_metadata.tables)
_ACQUIRE_SCOPE = "AcquirePersonalCalendarObservation"
_CAPTURE_SOURCE_TYPE = "PERSONAL_CALENDAR_WORLD_SOURCE_CAPTURE"


def upgrade() -> None:
    # Personal-world observation is not a search result. Evolve the generic evidence
    # origin vocabulary before any v6 calendar evidence can be admitted.
    with op.batch_alter_table("evidence_item", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_evidence_origin_f4", type_="check")
        batch_op.create_check_constraint(
            "ck_evidence_origin_f5",
            "origin_kind IN ('COUNTERPART_STATEMENT', 'SEARCH_RESULT', 'PERSONAL_WORLD_CAPTURE')",
        )

    bind = op.get_bind()
    for table in v6_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()

    capture_rows = bind.execute(
        select(
            schema_v6.personal_calendar_source_capture.c.source_capture_id,
            schema_v6.personal_calendar_source_capture.c.observation_id,
        )
    ).all()
    capture_ids = [row.source_capture_id for row in capture_rows]
    observation_ids = [row.observation_id for row in capture_rows]

    result_ids = list(
        bind.execute(
            select(schema_v6.personal_calendar_world_result.c.world_result_id)
        ).scalars()
    )

    content_digests: list[str] = []
    if capture_ids:
        content_digests = list(
            bind.execute(
                select(schema_v6.world_source_capture.c.content_digest).where(
                    schema_v6.world_source_capture.c.source_capture_id.in_(capture_ids)
                )
            ).scalars()
        )

    investigation_ids = []
    if observation_ids:
        investigation_ids = list(
            bind.execute(
                select(schema_v6.observation.c.investigation_id).where(
                    schema_v6.observation.c.observation_id.in_(observation_ids)
                )
            ).scalars()
        )

    # Remove specialized children before their generic canonical parents so foreign-key
    # enforcement remains valid during downgrade cleanup.
    if result_ids:
        bind.execute(
            delete(schema_v6.personal_calendar_world_result).where(
                schema_v6.personal_calendar_world_result.c.world_result_id.in_(result_ids)
            )
        )
        bind.execute(
            delete(schema_v6.world_result_evidence).where(
                schema_v6.world_result_evidence.c.world_result_id.in_(result_ids)
            )
        )
        bind.execute(
            delete(schema_v6.world_result).where(
                schema_v6.world_result.c.world_result_id.in_(result_ids)
            )
        )

    if capture_ids:
        evidence_ids = list(
            bind.execute(
                select(schema_v6.evidence_item.c.evidence_id).where(
                    schema_v6.evidence_item.c.source_type == _CAPTURE_SOURCE_TYPE,
                    schema_v6.evidence_item.c.source_id.in_(capture_ids),
                )
            ).scalars()
        )
        if evidence_ids:
            bind.execute(
                delete(schema_v6.world_result_evidence).where(
                    schema_v6.world_result_evidence.c.evidence_id.in_(evidence_ids)
                )
            )
            bind.execute(
                delete(schema_v6.evidence_item).where(
                    schema_v6.evidence_item.c.evidence_id.in_(evidence_ids)
                )
            )
        bind.execute(
            delete(schema_v6.personal_calendar_source_capture).where(
                schema_v6.personal_calendar_source_capture.c.source_capture_id.in_(capture_ids)
            )
        )
        bind.execute(
            delete(schema_v6.world_source_capture).where(
                schema_v6.world_source_capture.c.source_capture_id.in_(capture_ids)
            )
        )

    for digest in set(content_digests):
        still_referenced = bind.execute(
            select(func.count())
            .select_from(schema_v6.world_source_capture)
            .where(schema_v6.world_source_capture.c.content_digest == digest)
        ).scalar_one()
        if still_referenced == 0:
            bind.execute(
                delete(schema_v6.content_blob).where(
                    schema_v6.content_blob.c.content_digest == digest
                )
            )

    if observation_ids:
        bind.execute(
            update(schema_v6.observation)
            .where(
                schema_v6.observation.c.observation_id.in_(observation_ids),
                schema_v6.observation.c.status == "SUCCEEDED",
            )
            .values(status="FAILED")
        )
    for investigation_id in set(investigation_ids):
        remaining_results = bind.execute(
            select(func.count())
            .select_from(schema_v6.world_result)
            .where(schema_v6.world_result.c.investigation_id == investigation_id)
        ).scalar_one()
        if remaining_results == 0:
            bind.execute(
                update(schema_v6.investigation)
                .where(
                    schema_v6.investigation.c.investigation_id == investigation_id,
                    schema_v6.investigation.c.status == "SUCCEEDED",
                )
                .values(status="FAILED")
            )

    bind.execute(
        delete(schema_v6.operation_receipt).where(
            schema_v6.operation_receipt.c.operation_scope == _ACQUIRE_SCOPE
        )
    )

    for table in reversed(v6_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)

    # At this point all PERSONAL_WORLD_CAPTURE evidence has been removed, so the frozen
    # v5 evidence vocabulary can be restored without losing representable state.
    with op.batch_alter_table("evidence_item", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_evidence_origin_f5", type_="check")
        batch_op.create_check_constraint(
            "ck_evidence_origin_f4",
            "origin_kind IN ('COUNTERPART_STATEMENT', 'SEARCH_RESULT')",
        )
