from __future__ import annotations

from sqlalchemy import Engine, func, insert, select

from alsoul.domain.errors import fail
from alsoul.domain.models import FoundationIds
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.storage import schema


class FoundationBootstrapper:
    """Explicit one-time creation boundary for the F4 foundation identity graph.

    Recovery and ordinary application services must never call this boundary when
    canonical identity state is missing. Missing identity during recovery is a
    blocker, not an invitation to recreate a new Person or Relationship.
    """

    def __init__(
        self,
        engine: Engine,
        *,
        clock: Clock | None = None,
        ids: IdGenerator | None = None,
    ) -> None:
        self.engine = engine
        self.clock = clock or SystemClock()
        self.ids = ids or UUIDGenerator()

    def bootstrap(
        self,
        *,
        identity_namespace: str,
        external_subject: str,
        surface_namespace: str = "alsoul.first_party",
        surface_ref: str = "primary-text-surface",
        channel_namespace: str = "alsoul.first_party",
        channel_ref: str = "primary-text-channel",
    ) -> FoundationIds:
        now = self.clock.now()
        person_id = self.ids.new()
        counterpart_id = self.ids.new()
        identity_binding_id = self.ids.new()
        relationship_id = self.ids.new()
        surface_binding_id = self.ids.new()
        channel_binding_id = self.ids.new()

        with self.engine.begin() as conn:
            existing_identity_roots = sum(
                int(conn.execute(select(func.count()).select_from(table)).scalar_one())
                for table in (
                    schema.companion_person,
                    schema.counterpart_person,
                    schema.relationship_identity,
                )
            )
            if existing_identity_roots:
                fail(
                    "FOUNDATION_ALREADY_BOOTSTRAPPED",
                    "foundation bootstrap requires an empty canonical identity graph",
                )

            conn.execute(
                insert(schema.companion_person).values(
                    person_id=person_id,
                    created_at=now,
                )
            )
            conn.execute(
                insert(schema.self_revision).values(
                    person_id=person_id,
                    revision=1,
                    parent_revision=None,
                    role="PERSONAL_COMPANION",
                    preferred_name="Alsoul",
                    committed_at=now,
                )
            )
            conn.execute(
                insert(schema.self_head).values(
                    person_id=person_id,
                    current_revision=1,
                )
            )
            conn.execute(
                insert(schema.counterpart_person).values(
                    counterpart_id=counterpart_id,
                    created_at=now,
                )
            )
            conn.execute(
                insert(schema.counterpart_identity_binding).values(
                    binding_id=identity_binding_id,
                    counterpart_id=counterpart_id,
                    identity_namespace=identity_namespace,
                    external_subject=external_subject,
                    bound_at=now,
                )
            )
            conn.execute(
                insert(schema.relationship_identity).values(
                    relationship_id=relationship_id,
                    companion_person_id=person_id,
                    counterpart_id=counterpart_id,
                    created_at=now,
                )
            )
            conn.execute(
                insert(schema.relationship_revision).values(
                    relationship_id=relationship_id,
                    revision=1,
                    parent_revision=None,
                    companion_person_id=person_id,
                    counterpart_id=counterpart_id,
                    committed_at=now,
                )
            )
            conn.execute(
                insert(schema.relationship_head).values(
                    relationship_id=relationship_id,
                    current_revision=1,
                )
            )
            conn.execute(
                insert(schema.relationship_timeline_head).values(
                    relationship_id=relationship_id,
                    last_timeline_seq=0,
                )
            )
            conn.execute(
                insert(schema.surface_binding).values(
                    surface_binding_id=surface_binding_id,
                    companion_person_id=person_id,
                    surface_namespace=surface_namespace,
                    surface_ref=surface_ref,
                    bound_at=now,
                )
            )
            conn.execute(
                insert(schema.channel_binding).values(
                    channel_binding_id=channel_binding_id,
                    companion_person_id=person_id,
                    channel_namespace=channel_namespace,
                    companion_endpoint_ref=channel_ref,
                    bound_at=now,
                )
            )

        return FoundationIds(
            person_id,
            counterpart_id,
            relationship_id,
            surface_binding_id,
            channel_binding_id,
        )


__all__ = ["FoundationBootstrapper"]
