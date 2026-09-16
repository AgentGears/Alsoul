from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar_action import CALENDAR_EVENT_CREATE
from alsoul.services.calendar_runtime_model_selection import select_model_route
from alsoul.storage import schema


def select_create_resource(
    engine,
    *,
    relationship_id: UUID,
    counterpart_id: UUID,
    capability_contract_version: str,
) -> UUID:
    with engine.connect() as conn:
        policy = _policy(conn, relationship_id, capability_contract_version)
        allowed = {UUID(str(value)) for value in policy["allowed_resource_binding_ids_json"]}
        resources = conn.execute(
            select(schema.personal_resource_binding).where(
                schema.personal_resource_binding.c.relationship_id == relationship_id,
                schema.personal_resource_binding.c.counterpart_id == counterpart_id,
                schema.personal_resource_binding.c.resource_kind == "CALENDAR",
            )
        ).mappings().all()
        matches: list[UUID] = []
        for resource in resources:
            resource_id = resource["personal_resource_binding_id"]
            if resource_id not in allowed:
                continue
            state = _state(
                conn,
                schema.personal_resource_binding_state,
                schema.personal_resource_binding_head,
                "personal_resource_binding_id",
                resource_id,
            )
            if state is not None and state["status"] == "ACTIVE":
                matches.append(resource_id)
        if len(matches) != 1:
            fail(
                "PERSONAL_CALENDAR_MUTATION_RUNTIME_RESOURCE_AMBIGUOUS",
                "calendar mutation requires exactly one current active authorized calendar resource",
            )
        return matches[0]


def select_write_permission(
    engine,
    *,
    relationship_id: UUID,
    companion_person_id: UUID,
    counterpart_id: UUID,
    resource_id: UUID,
    capability_contract_version: str,
    clock,
) -> UUID:
    now = _aware_utc(clock.now())
    with engine.connect() as conn:
        policy = _policy(conn, relationship_id, capability_contract_version)
        if resource_id not in {
            UUID(str(value)) for value in policy["allowed_resource_binding_ids_json"]
        }:
            fail(
                "PERSONAL_CALENDAR_MUTATION_RUNTIME_POLICY_DENIED",
                "current calendar-create policy does not authorize the selected resource",
            )
        grants = conn.execute(
            select(schema.personal_calendar_write_permission_grant).where(
                schema.personal_calendar_write_permission_grant.c.holder_companion_person_id
                == companion_person_id,
                schema.personal_calendar_write_permission_grant.c.counterpart_id
                == counterpart_id,
                schema.personal_calendar_write_permission_grant.c.relationship_id
                == relationship_id,
                schema.personal_calendar_write_permission_grant.c.personal_resource_binding_id
                == resource_id,
                schema.personal_calendar_write_permission_grant.c.capability_semantic_operation
                == CALENDAR_EVENT_CREATE,
                schema.personal_calendar_write_permission_grant.c.capability_contract_version
                == capability_contract_version,
                schema.personal_calendar_write_permission_grant.c.operation_class
                == "WRITE",
                schema.personal_calendar_write_permission_grant.c.grantor_ref
                == counterpart_id,
                schema.personal_calendar_write_permission_grant.c.grant_source
                == "FIRST_PARTY_COUNTERPART",
                schema.personal_calendar_write_permission_grant.c.grant_policy_version
                == policy["permission_grant_policy_version"],
            )
        ).mappings().all()
        matches: list[UUID] = []
        for grant in grants:
            state = _state(
                conn,
                schema.personal_calendar_write_permission_state,
                schema.personal_calendar_write_permission_head,
                "permission_id",
                grant["permission_id"],
            )
            if state is None or state["status"] != "ACTIVE":
                continue
            if grant["expires_at"] is not None and _aware_utc(grant["expires_at"]) <= now:
                continue
            matches.append(grant["permission_id"])
        if len(matches) != 1:
            fail(
                "PERSONAL_CALENDAR_MUTATION_RUNTIME_PERMISSION_AMBIGUOUS",
                "calendar mutation requires exactly one current eligible write Permission",
            )
        return matches[0]


def select_create_credential(
    engine,
    *,
    relationship_id: UUID,
    resource_id: UUID,
    capability_contract_version: str,
) -> UUID:
    with engine.connect() as conn:
        policy = _policy(conn, relationship_id, capability_contract_version)
        resource = conn.execute(
            select(schema.personal_resource_binding).where(
                schema.personal_resource_binding.c.personal_resource_binding_id == resource_id,
                schema.personal_resource_binding.c.relationship_id == relationship_id,
            )
        ).mappings().one_or_none()
        if resource is None:
            fail(
                "PERSONAL_CALENDAR_MUTATION_RUNTIME_RESOURCE_MISSING",
                "selected calendar mutation resource is unavailable",
            )
        matches: list[UUID] = []
        credentials = conn.execute(
            select(schema.credential_binding).where(
                schema.credential_binding.c.external_system_ref
                == resource["external_system_ref"]
            )
        ).mappings().all()
        for credential in credentials:
            state = _state(
                conn,
                schema.credential_binding_state,
                schema.credential_binding_head,
                "credential_binding_id",
                credential["credential_binding_id"],
            )
            if (
                state is not None
                and state["status"] == "ACTIVE"
                and policy["required_provider_scope"] in state["provider_scopes_json"]
            ):
                matches.append(credential["credential_binding_id"])
        if len(matches) != 1:
            fail(
                "PERSONAL_CALENDAR_MUTATION_RUNTIME_CREDENTIAL_AMBIGUOUS",
                "calendar mutation requires exactly one current usable credential binding",
            )
        return matches[0]


def select_mutation_model_route(engine, *, relationship_id: UUID, model_adapter) -> UUID:
    return select_model_route(
        engine,
        relationship_id=relationship_id,
        model_adapter=model_adapter,
    )


def _policy(conn, relationship_id: UUID, capability_contract_version: str):
    head = conn.execute(
        select(schema.personal_calendar_create_policy_head).where(
            schema.personal_calendar_create_policy_head.c.relationship_id == relationship_id
        )
    ).mappings().one_or_none()
    if head is None:
        fail(
            "PERSONAL_CALENDAR_MUTATION_RUNTIME_POLICY_MISSING",
            "calendar mutation requires a current create policy",
        )
    policy = conn.execute(
        select(schema.personal_calendar_create_policy_revision).where(
            schema.personal_calendar_create_policy_revision.c.relationship_id
            == relationship_id,
            schema.personal_calendar_create_policy_revision.c.revision
            == head["current_revision"],
        )
    ).mappings().one()
    if (
        policy["status"] != "ALLOW"
        or policy["capability_semantic_operation"] != CALENDAR_EVENT_CREATE
        or policy["capability_contract_version"] != capability_contract_version
        or policy["capability_effect_class"] != "WRITE"
    ):
        fail(
            "PERSONAL_CALENDAR_MUTATION_RUNTIME_POLICY_DENIED",
            "current calendar-create policy does not authorize this runtime contract",
        )
    return policy


def _state(conn, state_table, head_table, key_name: str, key_value: UUID):
    head = conn.execute(
        select(head_table).where(getattr(head_table.c, key_name) == key_value)
    ).mappings().one_or_none()
    if head is None:
        return None
    return conn.execute(
        select(state_table).where(
            getattr(state_table.c, key_name) == key_value,
            state_table.c.revision == head["current_revision"],
        )
    ).mappings().one_or_none()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "select_create_credential",
    "select_create_resource",
    "select_mutation_model_route",
    "select_write_permission",
]
