from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from alsoul.domain.errors import fail
from alsoul.domain.personal_calendar import CALENDAR_EVENTS_READ
from alsoul.storage import schema


def select_read_permission(
    engine,
    *,
    relationship_id: UUID,
    companion_person_id: UUID,
    counterpart_id: UUID,
    resource_id: UUID,
    capability_contract,
    clock,
) -> UUID:
    now = _aware_utc(clock.now())
    with engine.connect() as conn:
        policy = _policy(conn, relationship_id, resource_id, capability_contract)
        grants = conn.execute(
            select(schema.permission_grant).where(
                schema.permission_grant.c.holder_companion_person_id == companion_person_id,
                schema.permission_grant.c.counterpart_id == counterpart_id,
                schema.permission_grant.c.relationship_id == relationship_id,
                schema.permission_grant.c.personal_resource_binding_id == resource_id,
                schema.permission_grant.c.capability_semantic_operation == CALENDAR_EVENTS_READ,
                schema.permission_grant.c.capability_contract_version == capability_contract.contract_version,
                schema.permission_grant.c.operation_class == "READ",
                schema.permission_grant.c.grantor_ref == counterpart_id,
                schema.permission_grant.c.grant_source == "FIRST_PARTY_COUNTERPART",
                schema.permission_grant.c.grant_policy_version == policy["permission_grant_policy_version"],
            )
        ).mappings().all()
        matches: list[UUID] = []
        for grant in grants:
            state = _state(conn, schema.permission_state, schema.permission_head, "permission_id", grant["permission_id"])
            if state is None or state["status"] != "ACTIVE":
                continue
            if grant["expires_at"] is not None and _aware_utc(grant["expires_at"]) <= now:
                continue
            matches.append(grant["permission_id"])
        if len(matches) != 1:
            fail(
                "PERSONAL_CALENDAR_RUNTIME_PERMISSION_AMBIGUOUS",
                "calendar interaction requires exactly one current eligible read Permission",
            )
        return matches[0]


def select_credential_binding(
    engine,
    *,
    relationship_id: UUID,
    resource_id: UUID,
    capability_contract,
) -> UUID:
    with engine.connect() as conn:
        policy = _policy(conn, relationship_id, resource_id, capability_contract)
        resource = conn.execute(
            select(schema.personal_resource_binding).where(
                schema.personal_resource_binding.c.personal_resource_binding_id == resource_id
            )
        ).mappings().one_or_none()
        if resource is None:
            fail("PERSONAL_CALENDAR_RUNTIME_RESOURCE_MISSING", "selected calendar resource is unavailable")
        matches: list[UUID] = []
        rows = conn.execute(
            select(schema.credential_binding).where(
                schema.credential_binding.c.external_system_ref == resource["external_system_ref"]
            )
        ).mappings().all()
        for row in rows:
            state = _state(conn, schema.credential_binding_state, schema.credential_binding_head, "credential_binding_id", row["credential_binding_id"])
            if state is not None and state["status"] == "ACTIVE" and policy["required_provider_scope"] in state["provider_scopes_json"]:
                matches.append(row["credential_binding_id"])
        if len(matches) != 1:
            fail(
                "PERSONAL_CALENDAR_RUNTIME_CREDENTIAL_AMBIGUOUS",
                "calendar interaction requires exactly one current usable credential binding",
            )
        return matches[0]


def _policy(conn, relationship_id, resource_id, capability_contract):
    head = conn.execute(
        select(schema.personal_calendar_read_policy_head).where(
            schema.personal_calendar_read_policy_head.c.relationship_id == relationship_id
        )
    ).mappings().one_or_none()
    if head is None:
        fail("PERSONAL_CALENDAR_RUNTIME_READ_POLICY_MISSING", "calendar interaction requires a current read policy")
    policy = conn.execute(
        select(schema.personal_calendar_read_policy_revision).where(
            schema.personal_calendar_read_policy_revision.c.relationship_id == relationship_id,
            schema.personal_calendar_read_policy_revision.c.revision == head["current_revision"],
        )
    ).mappings().one()
    if (
        policy["status"] != "ALLOW"
        or policy["capability_semantic_operation"] != CALENDAR_EVENTS_READ
        or policy["capability_contract_version"] != capability_contract.contract_version
        or str(resource_id) not in policy["allowed_resource_binding_ids_json"]
    ):
        fail("PERSONAL_CALENDAR_RUNTIME_READ_POLICY_DENIED", "current calendar read policy does not select this runtime contract/resource")
    return policy


def _state(conn, state_table, head_table, key_name: str, key_value: UUID):
    head = conn.execute(select(head_table).where(getattr(head_table.c, key_name) == key_value)).mappings().one_or_none()
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


__all__ = ["select_credential_binding", "select_read_permission"]
