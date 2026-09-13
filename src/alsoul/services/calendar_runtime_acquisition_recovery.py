from __future__ import annotations

from sqlalchemy import select

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar_acquisition import (
    AcquirePersonalCalendarObservationResult,
)
from alsoul.storage import schema


def recover_acquisition(engine, observation_id):
    """Return one completed acquisition without requiring current provider feasibility."""

    with engine.connect() as conn:
        rows = conn.execute(
            select(schema.personal_calendar_world_result).where(
                schema.personal_calendar_world_result.c.observation_id == observation_id
            )
        ).mappings().all()
        if not rows:
            return None
        if len(rows) != 1:
            fail(
                "PERSONAL_CALENDAR_RUNTIME_ACQUISITION_AMBIGUOUS",
                "calendar Observation has multiple admitted personal-world results",
            )
        personal = rows[0]
        capture = conn.execute(
            select(schema.personal_calendar_source_capture).where(
                schema.personal_calendar_source_capture.c.source_capture_id
                == personal["source_capture_id"]
            )
        ).mappings().one_or_none()
        supports = conn.execute(
            select(schema.world_result_evidence.c.evidence_id).where(
                schema.world_result_evidence.c.world_result_id
                == personal["world_result_id"],
                schema.world_result_evidence.c.relation == "SUPPORTS",
            )
        ).scalars().all()
    if capture is None or len(supports) != 1:
        fail(
            "PERSONAL_CALENDAR_RUNTIME_ACQUISITION_INCOMPLETE",
            "recovered calendar WorldResult lacks unique canonical capture evidence",
        )
    return AcquirePersonalCalendarObservationResult(
        source_capture_id=personal["source_capture_id"],
        evidence_id=supports[0],
        world_result_id=personal["world_result_id"],
        page_count=int(capture["page_count"]),
        event_count=int(capture["event_count"]),
        snapshot_ref=capture["snapshot_ref"],
        freshness_anchor_at=capture["freshness_anchor_at"],
        freshness_anchor_basis=capture["freshness_anchor_basis"],
    )


__all__ = ["recover_acquisition"]
