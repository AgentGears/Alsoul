from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, and_, insert, select, update
from sqlalchemy.exc import IntegrityError

from alsoul.domain.commands import (
    AdmitPersonMemoryClaimCommand,
    AdmitWorldResultCommand,
    AdoptCompanionOutputCommand,
    AppendCounterpartInputCommand,
    BuildContextProjectionCommand,
    CompleteModelInvocationCommand,
    PresentCompanionOutputCommand,
    RecordObservationSuccessCommand,
    ResolveOutputTargetCommand,
    StartInvestigationCommand,
    StartModelInvocationCommand,
    StartObservationCommand,
)
from alsoul.domain.errors import DomainError, fail
from alsoul.domain.models import (
    AdmitPersonMemoryClaimResult,
    AdmitWorldResultResult,
    AdoptCompanionOutputResult,
    AppendCounterpartInputResult,
    BuildContextProjectionResult,
    CompleteModelInvocationResult,
    FoundationIds,
    FoundationResponseDraft,
    PresentCompanionOutputResult,
    RecordObservationSuccessResult,
    ResolveOutputTargetResult,
    StartInvestigationResult,
    StartModelInvocationResult,
    StartObservationResult,
)
from alsoul.domain.types import Clock, IdGenerator, SystemClock, UUIDGenerator
from alsoul.services.common import (
    canonical_json,
    load_operation_receipt,
    request_digest,
    save_operation_receipt,
    sha256_text,
)
from alsoul.storage import schema

RAM_PREDICATE = "primary_machine.memory_gb"
WORLD_MEMORY_REQUIREMENT_PREDICATE = "software.minimum_memory_gb"


class FoundationServices:
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

    def bootstrap_foundation(
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
        p1 = self.ids.new()
        u1 = self.ids.new()
        identity_binding_id = self.ids.new()
        r1 = self.ids.new()
        sb1 = self.ids.new()
        ch1 = self.ids.new()
        with self.engine.begin() as conn:
            conn.execute(insert(schema.companion_person).values(person_id=p1, created_at=now))
            conn.execute(
                insert(schema.self_revision).values(
                    person_id=p1,
                    revision=1,
                    parent_revision=None,
                    role="PERSONAL_COMPANION",
                    preferred_name="Alsoul",
                    committed_at=now,
                )
            )
            conn.execute(insert(schema.self_head).values(person_id=p1, current_revision=1))
            conn.execute(insert(schema.counterpart_person).values(counterpart_id=u1, created_at=now))
            conn.execute(
                insert(schema.counterpart_identity_binding).values(
                    binding_id=identity_binding_id,
                    counterpart_id=u1,
                    identity_namespace=identity_namespace,
                    external_subject=external_subject,
                    bound_at=now,
                )
            )
            conn.execute(
                insert(schema.relationship_identity).values(
                    relationship_id=r1,
                    companion_person_id=p1,
                    counterpart_id=u1,
                    created_at=now,
                )
            )
            conn.execute(
                insert(schema.relationship_revision).values(
                    relationship_id=r1,
                    revision=1,
                    parent_revision=None,
                    companion_person_id=p1,
                    counterpart_id=u1,
                    committed_at=now,
                )
            )
            conn.execute(insert(schema.relationship_head).values(relationship_id=r1, current_revision=1))
            conn.execute(
                insert(schema.relationship_timeline_head).values(
                    relationship_id=r1,
                    last_timeline_seq=0,
                )
            )
            conn.execute(
                insert(schema.surface_binding).values(
                    surface_binding_id=sb1,
                    companion_person_id=p1,
                    surface_namespace=surface_namespace,
                    surface_ref=surface_ref,
                    bound_at=now,
                )
            )
            conn.execute(
                insert(schema.channel_binding).values(
                    channel_binding_id=ch1,
                    companion_person_id=p1,
                    channel_namespace=channel_namespace,
                    companion_endpoint_ref=channel_ref,
                    bound_at=now,
                )
            )
        return FoundationIds(p1, u1, r1, sb1, ch1)

    def resolve_inbound_identity(
        self,
        *,
        channel_namespace: str,
        channel_ref: str,
        identity_namespace: str,
        external_subject: str,
    ) -> tuple[UUID, UUID, UUID]:
        with self.engine.connect() as conn:
            channel = conn.execute(
                select(schema.channel_binding).where(
                    schema.channel_binding.c.channel_namespace == channel_namespace,
                    schema.channel_binding.c.companion_endpoint_ref == channel_ref,
                )
            ).mappings().one_or_none()
            if channel is None:
                fail("IDENTITY_BINDING_NOT_FOUND", "destination channel binding does not exist")
            identity = conn.execute(
                select(schema.counterpart_identity_binding).where(
                    schema.counterpart_identity_binding.c.identity_namespace == identity_namespace,
                    schema.counterpart_identity_binding.c.external_subject == external_subject,
                )
            ).mappings().one_or_none()
            if identity is None:
                fail("IDENTITY_BINDING_NOT_FOUND", "counterpart identity binding does not exist")
            relationship = conn.execute(
                select(schema.relationship_identity).where(
                    schema.relationship_identity.c.companion_person_id == channel["companion_person_id"],
                    schema.relationship_identity.c.counterpart_id == identity["counterpart_id"],
                )
            ).mappings().one_or_none()
            if relationship is None:
                fail("RELATIONSHIP_NOT_FOUND", "existing relationship could not be resolved")
            return (
                channel["companion_person_id"],
                identity["counterpart_id"],
                relationship["relationship_id"],
            )

    def append_counterpart_input(self, command: AppendCounterpartInputCommand) -> AppendCounterpartInputResult:
        scope = "AppendCounterpartInput"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                expected_request_digest=req,
            )
            if replay:
                return AppendCounterpartInputResult(
                    event_id=UUID(replay["event_id"]),
                    timeline_seq=int(replay["timeline_seq"]),
                    idempotent_replay=True,
                )
            self._validate_relationship(conn, command.companion_person_id, command.counterpart_id, command.relationship_id)
            self._validate_presence(conn, command.companion_person_id, command.surface_binding_id, command.channel_binding_id)
            existing = conn.execute(
                select(schema.interaction_event).where(
                    schema.interaction_event.c.relationship_id == command.relationship_id,
                    schema.interaction_event.c.ingress_idempotency_key == command.ingress_idempotency_key,
                )
            ).mappings().one_or_none()
            if existing is not None:
                if existing["content_text"] != command.content_text:
                    fail("INGRESS_IDEMPOTENCY_CONFLICT", "ingress key was reused with different content")
                result = AppendCounterpartInputResult(existing["event_id"], existing["timeline_seq"], True)
                save_operation_receipt(
                    conn,
                    scope=scope,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="InteractionEvent",
                    result_ref=existing["event_id"],
                    result_json={"event_id": str(existing["event_id"]), "timeline_seq": existing["timeline_seq"]},
                    committed_at=self.clock.now(),
                )
                return result
            timeline_head = conn.execute(
                select(schema.relationship_timeline_head).where(
                    schema.relationship_timeline_head.c.relationship_id == command.relationship_id
                )
            ).mappings().one_or_none()
            if timeline_head is None:
                fail("RELATIONSHIP_NOT_FOUND", "relationship timeline head is missing")
            next_seq = int(timeline_head["last_timeline_seq"]) + 1
            event_id = self.ids.new()
            recorded_at = self.clock.now()
            conn.execute(
                insert(schema.interaction_event).values(
                    event_id=event_id,
                    relationship_id=command.relationship_id,
                    timeline_seq=next_seq,
                    actor_kind="COUNTERPART",
                    actor_ref=command.counterpart_id,
                    event_kind="COUNTERPART_INPUT",
                    content_text=command.content_text,
                    occurred_at=command.occurred_at,
                    recorded_at=recorded_at,
                    conversation_id=command.conversation_id,
                    surface_binding_id=command.surface_binding_id,
                    channel_binding_id=command.channel_binding_id,
                    ingress_idempotency_key=command.ingress_idempotency_key,
                )
            )
            updated = conn.execute(
                update(schema.relationship_timeline_head)
                .where(
                    schema.relationship_timeline_head.c.relationship_id == command.relationship_id,
                    schema.relationship_timeline_head.c.last_timeline_seq == timeline_head["last_timeline_seq"],
                )
                .values(last_timeline_seq=next_seq)
            )
            if updated.rowcount != 1:
                fail("TIMELINE_SEQUENCE_CONFLICT", "relationship timeline advanced concurrently")
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="InteractionEvent",
                result_ref=event_id,
                result_json={"event_id": str(event_id), "timeline_seq": next_seq},
                committed_at=recorded_at,
            )
            return AppendCounterpartInputResult(event_id, next_seq)

    def admit_person_memory_claim(self, command: AdmitPersonMemoryClaimCommand) -> AdmitPersonMemoryClaimResult:
        scope = "AdmitPersonMemoryClaim"
        req = request_digest(asdict(command))
        if command.predicate != RAM_PREDICATE:
            fail("CLAIM_PREDICATE_UNSUPPORTED", f"unsupported F4 predicate: {command.predicate}")
        if not isinstance(command.value, int) or isinstance(command.value, bool) or command.value <= 0:
            fail("CLAIM_VALUE_INVALID", "primary_machine.memory_gb must be a positive integer")
        with self.engine.begin() as conn:
            replay = load_operation_receipt(conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req)
            if replay:
                return AdmitPersonMemoryClaimResult(
                    claim_id=UUID(replay["claim_id"]),
                    corrected_claim_id=UUID(replay["corrected_claim_id"]) if replay.get("corrected_claim_id") else None,
                    idempotent_replay=True,
                )
            self._validate_relationship(
                conn,
                command.holder_companion_person_id,
                command.subject_counterpart_id,
                command.relationship_id,
            )
            source_event = conn.execute(
                select(schema.interaction_event).where(schema.interaction_event.c.event_id == command.source_event_id)
            ).mappings().one_or_none()
            if source_event is None:
                fail("CLAIM_SUPPORT_NOT_FOUND", "source interaction event does not exist")
            if source_event["relationship_id"] != command.relationship_id or source_event["actor_ref"] != command.subject_counterpart_id or source_event["event_kind"] != "COUNTERPART_INPUT":
                fail("CLAIM_SUPPORT_SEMANTICALLY_INVALID", "source event is not a counterpart statement in the target relationship")
            if self._extract_ram_gb(source_event["content_text"]) != command.value:
                fail("CLAIM_SUPPORT_SEMANTICALLY_INVALID", "source statement does not support the proposed RAM value")
            if command.correction_of_claim_id is not None:
                old = conn.execute(select(schema.claim).where(schema.claim.c.claim_id == command.correction_of_claim_id)).mappings().one_or_none()
                if old is None:
                    fail("CLAIM_CORRECTION_TARGET_INVALID", "correction target does not exist")
                if (
                    old["holder_companion_person_id"] != command.holder_companion_person_id
                    or old["subject_counterpart_id"] != command.subject_counterpart_id
                    or old["predicate"] != command.predicate
                    or old["memory_scope_ref"] != command.relationship_id
                ):
                    fail("CLAIM_CORRECTION_TARGET_INVALID", "correction target belongs to a different claim scope")
                already_corrected = conn.execute(
                    select(schema.claim_supersession).where(
                        schema.claim_supersession.c.older_claim_id == command.correction_of_claim_id,
                        schema.claim_supersession.c.relation == "CORRECTS",
                    )
                ).mappings().all()
                if already_corrected:
                    fail("CLAIM_ADMISSION_CONFLICT", "target claim already has a correction")
            evidence_id = self.ids.new()
            claim_id = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.evidence_item).values(
                    evidence_id=evidence_id,
                    origin_kind="COUNTERPART_STATEMENT",
                    source_type="INTERACTION_EVENT",
                    source_id=command.source_event_id,
                    source_actor_ref=command.subject_counterpart_id,
                    recorded_at=now,
                )
            )
            conn.execute(
                insert(schema.claim).values(
                    claim_id=claim_id,
                    holder_companion_person_id=command.holder_companion_person_id,
                    subject_counterpart_id=command.subject_counterpart_id,
                    memory_scope_kind="RELATIONSHIP",
                    memory_scope_ref=command.relationship_id,
                    claim_domain="PERSON",
                    claim_kind="FACTUAL",
                    predicate=command.predicate,
                    value_json=command.value,
                    valid_from=command.valid_from,
                    admitted_at=now,
                )
            )
            conn.execute(insert(schema.claim_evidence).values(claim_id=claim_id, evidence_id=evidence_id, relation="SUPPORTS"))
            if command.correction_of_claim_id is not None:
                conn.execute(
                    insert(schema.claim_supersession).values(
                        newer_claim_id=claim_id,
                        older_claim_id=command.correction_of_claim_id,
                        relation="CORRECTS",
                        created_at=now,
                    )
                )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="Claim",
                result_ref=claim_id,
                result_json={
                    "claim_id": str(claim_id),
                    "corrected_claim_id": str(command.correction_of_claim_id) if command.correction_of_claim_id else None,
                },
                committed_at=now,
            )
            return AdmitPersonMemoryClaimResult(claim_id, command.correction_of_claim_id)

    def start_investigation(self, command: StartInvestigationCommand) -> StartInvestigationResult:
        scope = "StartInvestigation"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req)
            if replay:
                return StartInvestigationResult(UUID(replay["investigation_id"]))
            if conn.execute(select(schema.companion_person.c.person_id).where(schema.companion_person.c.person_id == command.initiated_by_companion_person_id)).scalar_one_or_none() is None:
                fail("COMPANION_PERSON_NOT_FOUND", "investigating companion person does not exist")
            if command.relationship_id is not None and conn.execute(select(schema.relationship_identity.c.relationship_id).where(schema.relationship_identity.c.relationship_id == command.relationship_id)).scalar_one_or_none() is None:
                fail("RELATIONSHIP_NOT_FOUND", "investigation relationship does not exist")
            qid = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.investigation).values(
                    investigation_id=qid,
                    initiated_by_companion_person_id=command.initiated_by_companion_person_id,
                    relationship_id=command.relationship_id,
                    conversation_id=command.conversation_id,
                    objective=command.objective,
                    started_at=now,
                    status="OPEN",
                )
            )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="Investigation",
                result_ref=qid,
                result_json={"investigation_id": str(qid)},
                committed_at=now,
            )
            return StartInvestigationResult(qid)

    def start_observation(self, command: StartObservationCommand) -> StartObservationResult:
        scope = "StartObservation"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req)
            if replay:
                return StartObservationResult(UUID(replay["observation_id"]))
            inv = conn.execute(select(schema.investigation).where(schema.investigation.c.investigation_id == command.investigation_id)).mappings().one_or_none()
            if inv is None:
                fail("INVESTIGATION_NOT_FOUND", "investigation does not exist")
            if inv["status"] != "OPEN":
                fail("INVESTIGATION_NOT_OPEN", "cannot start an observation under a terminal investigation")
            oid = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.observation).values(
                    observation_id=oid,
                    investigation_id=command.investigation_id,
                    acquisition_kind=command.acquisition_kind,
                    request_descriptor_json=command.request_descriptor,
                    observed_at=now,
                    status="STARTED",
                )
            )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="Observation",
                result_ref=oid,
                result_json={"observation_id": str(oid)},
                committed_at=now,
            )
            return StartObservationResult(oid)

    def record_observation_success(self, command: RecordObservationSuccessCommand) -> RecordObservationSuccessResult:
        scope = "RecordObservationSuccess"
        req = request_digest(asdict(command))
        digest = sha256_text(command.content_text)
        with self.engine.begin() as conn:
            replay = load_operation_receipt(conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req)
            if replay:
                return RecordObservationSuccessResult(UUID(replay["source_capture_id"]), UUID(replay["evidence_id"]))
            obs = conn.execute(select(schema.observation).where(schema.observation.c.observation_id == command.observation_id)).mappings().one_or_none()
            if obs is None:
                fail("OBSERVATION_NOT_FOUND", "observation does not exist")
            if obs["status"] != "STARTED":
                fail("OBSERVATION_ALREADY_TERMINAL", "observation is already terminal")
            existing_capture = conn.execute(select(schema.world_source_capture).where(schema.world_source_capture.c.observation_id == command.observation_id)).mappings().one_or_none()
            if existing_capture is not None:
                fail("CAPTURE_ALREADY_ACCEPTED", "observation already has an accepted capture")
            now = self.clock.now()
            blob_exists = conn.execute(
                select(schema.content_blob.c.content_digest).where(
                    schema.content_blob.c.content_digest == digest
                )
            ).scalar_one_or_none()
            if blob_exists is None:
                conn.execute(
                    insert(schema.content_blob).values(
                        content_digest=digest,
                        content_text=command.content_text,
                        recorded_at=now,
                    )
                )
            capture_id = self.ids.new()
            evidence_id = self.ids.new()
            content_ref = f"sha256:{digest}"
            conn.execute(
                insert(schema.world_source_capture).values(
                    source_capture_id=capture_id,
                    observation_id=command.observation_id,
                    capture_kind="TEXT",
                    source_identity=command.source_identity,
                    requested_locator=command.requested_locator,
                    resolved_locator=command.resolved_locator,
                    source_version=command.source_version,
                    source_published_at=command.source_published_at,
                    source_modified_at=command.source_modified_at,
                    captured_at=command.captured_at,
                    content_ref=content_ref,
                    content_digest=digest,
                )
            )
            conn.execute(
                insert(schema.evidence_item).values(
                    evidence_id=evidence_id,
                    origin_kind="SEARCH_RESULT",
                    source_type="WORLD_SOURCE_CAPTURE",
                    source_id=capture_id,
                    source_locator=command.resolved_locator or command.source_identity,
                    recorded_at=now,
                )
            )
            conn.execute(update(schema.observation).where(schema.observation.c.observation_id == command.observation_id).values(status="SUCCEEDED"))
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="WorldSourceCapture",
                result_ref=capture_id,
                result_json={"source_capture_id": str(capture_id), "evidence_id": str(evidence_id)},
                committed_at=now,
            )
            return RecordObservationSuccessResult(capture_id, evidence_id)

    def record_observation_failure(self, *, operation_id: UUID, observation_id: UUID) -> None:
        scope = "RecordObservationFailure"
        req = request_digest({"operation_id": operation_id, "observation_id": observation_id})
        with self.engine.begin() as conn:
            replay = load_operation_receipt(conn, scope=scope, operation_id=operation_id, expected_request_digest=req)
            if replay:
                return
            obs = conn.execute(select(schema.observation).where(schema.observation.c.observation_id == observation_id)).mappings().one_or_none()
            if obs is None:
                fail("OBSERVATION_NOT_FOUND", "observation does not exist")
            if obs["status"] != "STARTED":
                fail("OBSERVATION_ALREADY_TERMINAL", "observation is already terminal")
            conn.execute(update(schema.observation).where(schema.observation.c.observation_id == observation_id).values(status="FAILED"))
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=operation_id,
                req_digest=req,
                result_kind="Observation",
                result_ref=observation_id,
                result_json={"observation_id": str(observation_id), "status": "FAILED"},
                committed_at=self.clock.now(),
            )

    def admit_world_result(self, command: AdmitWorldResultCommand) -> AdmitWorldResultResult:
        scope = "AdmitWorldResult"
        req = request_digest(asdict(command))
        if command.predicate != WORLD_MEMORY_REQUIREMENT_PREDICATE:
            fail("WORLD_RESULT_SUPPORT_INVALID", f"unsupported F4 world predicate: {command.predicate}")
        if not isinstance(command.value, int) or isinstance(command.value, bool) or command.value <= 0:
            fail("WORLD_RESULT_SUPPORT_INVALID", "software.minimum_memory_gb must be a positive integer")
        if not command.support_evidence_ids:
            fail("WORLD_RESULT_SUPPORT_REQUIRED", "WorldResult requires supporting evidence")
        with self.engine.begin() as conn:
            replay = load_operation_receipt(conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req)
            if replay:
                return AdmitWorldResultResult(UUID(replay["world_result_id"]))
            inv = conn.execute(select(schema.investigation).where(schema.investigation.c.investigation_id == command.investigation_id)).mappings().one_or_none()
            if inv is None:
                fail("INVESTIGATION_NOT_FOUND", "investigation does not exist")
            for evidence_id in command.support_evidence_ids:
                self._validate_world_evidence(conn, evidence_id, command.investigation_id, command.predicate, command.value)
            wid = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.world_result).values(
                    world_result_id=wid,
                    investigation_id=command.investigation_id,
                    result_kind=command.result_kind,
                    predicate=command.predicate,
                    value_json=command.value,
                    valid_as_of=command.valid_as_of,
                    derived_at=now,
                )
            )
            for evidence_id in command.support_evidence_ids:
                conn.execute(insert(schema.world_result_evidence).values(world_result_id=wid, evidence_id=evidence_id, relation="SUPPORTS"))
            for evidence_id in command.contradiction_evidence_ids:
                conn.execute(insert(schema.world_result_evidence).values(world_result_id=wid, evidence_id=evidence_id, relation="CONTRADICTS"))
            conn.execute(update(schema.investigation).where(schema.investigation.c.investigation_id == command.investigation_id).values(status="SUCCEEDED"))
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="WorldResult",
                result_ref=wid,
                result_json={"world_result_id": str(wid)},
                committed_at=now,
            )
            return AdmitWorldResultResult(wid)

    def build_context_projection(self, command: BuildContextProjectionCommand) -> BuildContextProjectionResult:
        scope = "BuildContextProjection"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req)
            if replay:
                return BuildContextProjectionResult(
                    projection_id=UUID(replay["projection_id"]),
                    source_self_revision=int(replay["source_self_revision"]),
                    source_relationship_revision=int(replay["source_relationship_revision"]),
                    source_timeline_frontier=int(replay["source_timeline_frontier"]),
                    manifest_digest=replay["manifest_digest"],
                )
            relationship = conn.execute(select(schema.relationship_identity).where(schema.relationship_identity.c.relationship_id == command.relationship_id)).mappings().one_or_none()
            if relationship is None:
                fail("RELATIONSHIP_NOT_FOUND", "projection relationship does not exist")
            if relationship["companion_person_id"] != command.companion_person_id:
                fail("PROJECTION_RELATIONSHIP_REVISION_INVALID", "projection companion does not own relationship")
            self_head_row = conn.execute(select(schema.self_head).where(schema.self_head.c.person_id == command.companion_person_id)).mappings().one_or_none()
            if self_head_row is None:
                fail("SELF_HEAD_NOT_FOUND", "SelfHead missing")
            self_rev = conn.execute(
                select(schema.self_revision).where(
                    schema.self_revision.c.person_id == command.companion_person_id,
                    schema.self_revision.c.revision == self_head_row["current_revision"],
                )
            ).mappings().one_or_none()
            if self_rev is None:
                fail("SELF_REVISION_NOT_FOUND", "SelfHead points to missing SelfRevision")
            rel_head = conn.execute(select(schema.relationship_head).where(schema.relationship_head.c.relationship_id == command.relationship_id)).mappings().one_or_none()
            if rel_head is None:
                fail("RELATIONSHIP_HEAD_NOT_FOUND", "RelationshipHead missing")
            rel_rev = conn.execute(
                select(schema.relationship_revision).where(
                    schema.relationship_revision.c.relationship_id == command.relationship_id,
                    schema.relationship_revision.c.revision == rel_head["current_revision"],
                )
            ).mappings().one_or_none()
            if rel_rev is None:
                fail("RELATIONSHIP_REVISION_NOT_FOUND", "RelationshipHead points to missing revision")
            input_event = conn.execute(select(schema.interaction_event).where(schema.interaction_event.c.event_id == command.current_input_event_id)).mappings().one_or_none()
            if input_event is None or input_event["relationship_id"] != command.relationship_id or input_event["event_kind"] != "COUNTERPART_INPUT":
                fail("PROJECTION_CURRENT_INPUT_INVALID", "current input is not a counterpart input in projection relationship")
            timeline = conn.execute(select(schema.relationship_timeline_head).where(schema.relationship_timeline_head.c.relationship_id == command.relationship_id)).mappings().one_or_none()
            if timeline is None or int(input_event["timeline_seq"]) > int(timeline["last_timeline_seq"]):
                fail("PROJECTION_INPUT_OUTSIDE_TIMELINE_FRONTIER", "current input lies outside selected Timeline frontier")
            personal_items: list[tuple[dict[str, Any], list[UUID]]] = []
            for predicate in command.required_personal_predicates:
                item = self._resolve_current_claim(conn, command.companion_person_id, relationship["counterpart_id"], command.relationship_id, predicate)
                if item is None:
                    fail("PROJECTION_CLAIM_INELIGIBLE", f"required claim {predicate} is unavailable")
                personal_items.append(item)
            world_items: list[tuple[dict[str, Any], list[UUID]]] = []
            for world_result_id in command.required_world_result_ids:
                item = self._validate_world_result_for_projection(conn, world_result_id, input_event)
                world_items.append(item)
            manifest = {
                "projection_schema_version": 1,
                "purpose": "RESPOND_TO_INTERACTION",
                "companion_person_id": str(command.companion_person_id),
                "relationship_id": str(command.relationship_id),
                "current_input_event_id": str(command.current_input_event_id),
                "source_self_revision": int(self_head_row["current_revision"]),
                "source_relationship_revision": int(rel_head["current_revision"]),
                "source_timeline_frontier": int(timeline["last_timeline_seq"]),
                "selected_event_refs": [str(command.current_input_event_id)],
                "personal_context_items": [
                    {
                        "claim_id": str(row["claim_id"]),
                        "epistemic_basis": "COUNTERPART_STATED_MEMORY",
                        "support_evidence_refs": [str(e) for e in evidence_ids],
                    }
                    for row, evidence_ids in personal_items
                ],
                "world_context_items": [
                    {
                        "world_result_id": str(row["world_result_id"]),
                        "investigation_id": str(row["investigation_id"]),
                        "epistemic_mode": "CURRENT_CHECKED",
                        "support_evidence_refs": [str(e) for e in evidence_ids],
                    }
                    for row, evidence_ids in world_items
                ],
            }
            digest = sha256_text(canonical_json(manifest))
            projection_id = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.context_projection).values(
                    projection_id=projection_id,
                    projection_schema_version=1,
                    purpose="RESPOND_TO_INTERACTION",
                    created_at=now,
                    companion_person_id=command.companion_person_id,
                    relationship_id=command.relationship_id,
                    current_input_event_id=command.current_input_event_id,
                    source_self_revision=self_head_row["current_revision"],
                    source_relationship_revision=rel_head["current_revision"],
                    source_timeline_frontier=timeline["last_timeline_seq"],
                    manifest_digest=digest,
                )
            )
            conn.execute(insert(schema.context_projection_event).values(projection_id=projection_id, ordinal=0, event_id=command.current_input_event_id))
            for ordinal, (row, evidence_ids) in enumerate(personal_items):
                conn.execute(
                    insert(schema.context_projection_personal_item).values(
                        projection_id=projection_id,
                        ordinal=ordinal,
                        claim_id=row["claim_id"],
                        epistemic_basis="COUNTERPART_STATED_MEMORY",
                    )
                )
                for evidence_id in evidence_ids:
                    conn.execute(
                        insert(schema.context_projection_personal_support).values(
                            projection_id=projection_id,
                            personal_ordinal=ordinal,
                            evidence_id=evidence_id,
                        )
                    )
            for ordinal, (row, evidence_ids) in enumerate(world_items):
                conn.execute(
                    insert(schema.context_projection_world_item).values(
                        projection_id=projection_id,
                        ordinal=ordinal,
                        world_result_id=row["world_result_id"],
                        investigation_id=row["investigation_id"],
                        epistemic_mode="CURRENT_CHECKED",
                    )
                )
                for evidence_id in evidence_ids:
                    conn.execute(
                        insert(schema.context_projection_world_support).values(
                            projection_id=projection_id,
                            world_ordinal=ordinal,
                            evidence_id=evidence_id,
                        )
                    )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="ContextProjection",
                result_ref=projection_id,
                result_json={
                    "projection_id": str(projection_id),
                    "source_self_revision": int(self_head_row["current_revision"]),
                    "source_relationship_revision": int(rel_head["current_revision"]),
                    "source_timeline_frontier": int(timeline["last_timeline_seq"]),
                    "manifest_digest": digest,
                },
                committed_at=now,
            )
            return BuildContextProjectionResult(
                projection_id,
                int(self_head_row["current_revision"]),
                int(rel_head["current_revision"]),
                int(timeline["last_timeline_seq"]),
                digest,
            )

    def render_provider_context(self, projection_id: UUID) -> dict[str, Any]:
        with self.engine.connect() as conn:
            cp = conn.execute(select(schema.context_projection).where(schema.context_projection.c.projection_id == projection_id)).mappings().one_or_none()
            if cp is None:
                fail("CONTEXT_PROJECTION_NOT_FOUND", "ContextProjection does not exist")
            self_rev = conn.execute(
                select(schema.self_revision).where(
                    schema.self_revision.c.person_id == cp["companion_person_id"],
                    schema.self_revision.c.revision == cp["source_self_revision"],
                )
            ).mappings().one()
            current_input = conn.execute(select(schema.interaction_event).where(schema.interaction_event.c.event_id == cp["current_input_event_id"])).mappings().one()
            personal_rows = conn.execute(
                select(schema.context_projection_personal_item, schema.claim.c.predicate, schema.claim.c.value_json)
                .join(schema.claim, schema.context_projection_personal_item.c.claim_id == schema.claim.c.claim_id)
                .where(schema.context_projection_personal_item.c.projection_id == projection_id)
                .order_by(schema.context_projection_personal_item.c.ordinal)
            ).mappings().all()
            world_rows = conn.execute(
                select(schema.context_projection_world_item, schema.world_result.c.predicate, schema.world_result.c.value_json)
                .join(schema.world_result, schema.context_projection_world_item.c.world_result_id == schema.world_result.c.world_result_id)
                .where(schema.context_projection_world_item.c.projection_id == projection_id)
                .order_by(schema.context_projection_world_item.c.ordinal)
            ).mappings().all()
            return {
                "person": {
                    "person_id": str(cp["companion_person_id"]),
                    "role": self_rev["role"],
                    "preferred_name": self_rev["preferred_name"],
                    "self_revision": cp["source_self_revision"],
                },
                "relationship_id": str(cp["relationship_id"]),
                "current_input": current_input["content_text"],
                "personal_context": [
                    {
                        "claim_id": str(row["claim_id"]),
                        "predicate": row["predicate"],
                        "value": row["value_json"],
                        "epistemic_basis": row["epistemic_basis"],
                    }
                    for row in personal_rows
                ],
                "world_context": [
                    {
                        "world_result_id": str(row["world_result_id"]),
                        "predicate": row["predicate"],
                        "value": row["value_json"],
                        "epistemic_mode": row["epistemic_mode"],
                    }
                    for row in world_rows
                ],
            }

    def start_model_invocation(self, command: StartModelInvocationCommand) -> StartModelInvocationResult:
        scope = "StartModelInvocation"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req)
            if replay:
                return StartModelInvocationResult(UUID(replay["model_invocation_id"]))
            if conn.execute(select(schema.context_projection.c.projection_id).where(schema.context_projection.c.projection_id == command.context_projection_id)).scalar_one_or_none() is None:
                fail("CONTEXT_PROJECTION_NOT_FOUND", "ContextProjection does not exist")
            mid = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.model_invocation).values(
                    model_invocation_id=mid,
                    context_projection_id=command.context_projection_id,
                    provider_binding_ref=command.provider_binding_ref,
                    model_ref=command.model_ref,
                    renderer_version=command.renderer_version,
                    provider_request_digest=command.provider_request_digest,
                    started_at=now,
                    outcome="IN_PROGRESS",
                )
            )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="ModelInvocation",
                result_ref=mid,
                result_json={"model_invocation_id": str(mid)},
                committed_at=now,
            )
            return StartModelInvocationResult(mid)

    def complete_model_invocation(self, command: CompleteModelInvocationCommand) -> CompleteModelInvocationResult:
        scope = "CompleteModelInvocation"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req)
            if replay:
                return CompleteModelInvocationResult(UUID(replay["generated_output_id"]))
            mi = conn.execute(select(schema.model_invocation).where(schema.model_invocation.c.model_invocation_id == command.model_invocation_id)).mappings().one_or_none()
            if mi is None:
                fail("MODEL_INVOCATION_NOT_FOUND", "ModelInvocation does not exist")
            existing = conn.execute(select(schema.generated_output).where(schema.generated_output.c.model_invocation_id == command.model_invocation_id)).mappings().one_or_none()
            if existing is not None:
                if existing["content_digest"] != command.content_digest:
                    fail("MODEL_OUTPUT_ALREADY_RECORDED", "different output already recorded for invocation")
                return CompleteModelInvocationResult(existing["generated_output_id"])
            if mi["outcome"] not in ("IN_PROGRESS", "UNKNOWN"):
                fail("MODEL_INVOCATION_ALREADY_TERMINAL", f"cannot complete invocation from {mi['outcome']}")
            if sha256_text(command.content_text) != command.content_digest:
                fail("MODEL_COMPLETION_WITHOUT_OUTPUT", "content digest does not match output")
            gid = self.ids.new()
            conn.execute(
                insert(schema.generated_output).values(
                    generated_output_id=gid,
                    model_invocation_id=command.model_invocation_id,
                    content_text=command.content_text,
                    content_digest=command.content_digest,
                    semantic_payload_json=command.semantic_payload,
                    received_at=command.received_at,
                )
            )
            conn.execute(
                update(schema.model_invocation)
                .where(schema.model_invocation.c.model_invocation_id == command.model_invocation_id)
                .values(outcome="SUCCEEDED", completed_at=command.received_at)
            )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="GeneratedOutput",
                result_ref=gid,
                result_json={"generated_output_id": str(gid)},
                committed_at=command.received_at,
            )
            return CompleteModelInvocationResult(gid)

    def fail_model_invocation(self, model_invocation_id: UUID, *, unknown: bool = False) -> None:
        with self.engine.begin() as conn:
            mi = conn.execute(select(schema.model_invocation).where(schema.model_invocation.c.model_invocation_id == model_invocation_id)).mappings().one_or_none()
            if mi is None:
                fail("MODEL_INVOCATION_NOT_FOUND", "ModelInvocation does not exist")
            if mi["outcome"] != "IN_PROGRESS":
                fail("MODEL_INVOCATION_ALREADY_TERMINAL", "ModelInvocation is already terminal")
            conn.execute(
                update(schema.model_invocation)
                .where(schema.model_invocation.c.model_invocation_id == model_invocation_id)
                .values(outcome="UNKNOWN" if unknown else "FAILED", completed_at=self.clock.now())
            )

    def resolve_output_target(self, command: ResolveOutputTargetCommand) -> ResolveOutputTargetResult:
        scope = "ResolveOutputTarget"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req)
            if replay:
                return ResolveOutputTargetResult(UUID(replay["output_target_id"]), bool(replay["created"]))
            target_event = conn.execute(select(schema.interaction_event).where(schema.interaction_event.c.event_id == command.target_ref)).mappings().one_or_none()
            if command.target_kind != "INTERACTION_EVENT" or target_event is None or target_event["relationship_id"] != command.relationship_id:
                fail("OUTPUT_TARGET_NOT_FOUND", "F4 output target must be an InteractionEvent in the relationship")
            existing = conn.execute(
                select(schema.output_target).where(
                    schema.output_target.c.relationship_id == command.relationship_id,
                    schema.output_target.c.target_kind == command.target_kind,
                    schema.output_target.c.target_ref == command.target_ref,
                    schema.output_target.c.purpose == command.purpose,
                )
            ).mappings().one_or_none()
            created = existing is None
            if existing is None:
                otid = self.ids.new()
                now = self.clock.now()
                conn.execute(
                    insert(schema.output_target).values(
                        output_target_id=otid,
                        relationship_id=command.relationship_id,
                        target_kind=command.target_kind,
                        target_ref=command.target_ref,
                        purpose=command.purpose,
                        created_at=now,
                    )
                )
            else:
                otid = existing["output_target_id"]
                now = self.clock.now()
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="OutputTarget",
                result_ref=otid,
                result_json={"output_target_id": str(otid), "created": created},
                committed_at=now,
            )
            return ResolveOutputTargetResult(otid, created)

    def adopt_companion_output(self, command: AdoptCompanionOutputCommand) -> AdoptCompanionOutputResult:
        scope = "AdoptCompanionOutput"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req)
            if replay:
                return AdoptCompanionOutputResult(UUID(replay["companion_output_id"]))
            target = conn.execute(select(schema.output_target).where(schema.output_target.c.output_target_id == command.output_target_id)).mappings().one_or_none()
            if target is None:
                fail("OUTPUT_TARGET_NOT_FOUND", "OutputTarget does not exist")
            if target["relationship_id"] != command.relationship_id or target["target_ref"] != command.origin_ref:
                fail("OUTPUT_ORIGIN_INVALID", "output origin does not match target")
            generated = conn.execute(select(schema.generated_output).where(schema.generated_output.c.generated_output_id == command.generated_output_id)).mappings().one_or_none()
            if generated is None:
                fail("GENERATED_OUTPUT_NOT_FOUND", "GeneratedOutput does not exist")
            mi = conn.execute(select(schema.model_invocation).where(schema.model_invocation.c.model_invocation_id == generated["model_invocation_id"])).mappings().one()
            cp = conn.execute(select(schema.context_projection).where(schema.context_projection.c.projection_id == mi["context_projection_id"])).mappings().one()
            if cp["companion_person_id"] != command.companion_person_id or cp["relationship_id"] != command.relationship_id or cp["current_input_event_id"] != command.origin_ref:
                fail("GENERATED_OUTPUT_NOT_ELIGIBLE", "GeneratedOutput was produced from a different semantic response context")
            self._validate_foundation_response_payload(conn, cp["projection_id"], generated["semantic_payload_json"])
            existing = conn.execute(select(schema.companion_output).where(schema.companion_output.c.output_target_id == command.output_target_id)).mappings().one_or_none()
            if existing is not None:
                fail("OUTPUT_TARGET_ALREADY_FILLED", "OutputTarget already has an adopted CompanionOutput")
            coid = self.ids.new()
            now = self.clock.now()
            conn.execute(
                insert(schema.companion_output).values(
                    companion_output_id=coid,
                    companion_person_id=command.companion_person_id,
                    relationship_id=command.relationship_id,
                    output_target_id=command.output_target_id,
                    origin_kind=command.origin_kind,
                    origin_ref=command.origin_ref,
                    source_generated_output_id=command.generated_output_id,
                    content_text=generated["content_text"],
                    content_digest=generated["content_digest"],
                    semantic_payload_json=generated["semantic_payload_json"],
                    adopted_at=now,
                )
            )
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="CompanionOutput",
                result_ref=coid,
                result_json={"companion_output_id": str(coid)},
                committed_at=now,
            )
            return AdoptCompanionOutputResult(coid)

    def present_companion_output(self, command: PresentCompanionOutputCommand) -> PresentCompanionOutputResult:
        scope = "PresentCompanionOutput"
        req = request_digest(asdict(command))
        with self.engine.begin() as conn:
            replay = load_operation_receipt(conn, scope=scope, operation_id=command.operation_id, expected_request_digest=req)
            if replay:
                return PresentCompanionOutputResult(
                    UUID(replay["interaction_event_id"]),
                    int(replay["timeline_seq"]),
                    True,
                )
            co = conn.execute(select(schema.companion_output).where(schema.companion_output.c.companion_output_id == command.companion_output_id)).mappings().one_or_none()
            if co is None:
                fail("COMPANION_OUTPUT_NOT_FOUND", "CompanionOutput does not exist")
            self._validate_presence(conn, co["companion_person_id"], command.surface_binding_id, command.channel_binding_id)
            existing = conn.execute(select(schema.interaction_event).where(schema.interaction_event.c.companion_output_id == command.companion_output_id)).mappings().one_or_none()
            if existing is not None:
                save_operation_receipt(
                    conn,
                    scope=scope,
                    operation_id=command.operation_id,
                    req_digest=req,
                    result_kind="InteractionEvent",
                    result_ref=existing["event_id"],
                    result_json={"interaction_event_id": str(existing["event_id"]), "timeline_seq": existing["timeline_seq"]},
                    committed_at=self.clock.now(),
                )
                return PresentCompanionOutputResult(existing["event_id"], existing["timeline_seq"], True)
            target = conn.execute(select(schema.output_target).where(schema.output_target.c.output_target_id == co["output_target_id"])).mappings().one()
            timeline = conn.execute(select(schema.relationship_timeline_head).where(schema.relationship_timeline_head.c.relationship_id == co["relationship_id"])).mappings().one()
            next_seq = int(timeline["last_timeline_seq"]) + 1
            event_id = self.ids.new()
            conn.execute(
                insert(schema.interaction_event).values(
                    event_id=event_id,
                    relationship_id=co["relationship_id"],
                    timeline_seq=next_seq,
                    actor_kind="COMPANION",
                    actor_ref=co["companion_person_id"],
                    event_kind="COMPANION_PRESENTED_OUTPUT",
                    content_text=co["content_text"],
                    occurred_at=command.presented_at,
                    recorded_at=self.clock.now(),
                    surface_binding_id=command.surface_binding_id,
                    channel_binding_id=command.channel_binding_id,
                    companion_output_id=command.companion_output_id,
                    reply_to_event_id=target["target_ref"],
                )
            )
            updated = conn.execute(
                update(schema.relationship_timeline_head)
                .where(
                    schema.relationship_timeline_head.c.relationship_id == co["relationship_id"],
                    schema.relationship_timeline_head.c.last_timeline_seq == timeline["last_timeline_seq"],
                )
                .values(last_timeline_seq=next_seq)
            )
            if updated.rowcount != 1:
                fail("TIMELINE_SEQUENCE_CONFLICT", "relationship Timeline advanced concurrently")
            save_operation_receipt(
                conn,
                scope=scope,
                operation_id=command.operation_id,
                req_digest=req,
                result_kind="InteractionEvent",
                result_ref=event_id,
                result_json={"interaction_event_id": str(event_id), "timeline_seq": next_seq},
                committed_at=self.clock.now(),
            )
            return PresentCompanionOutputResult(event_id, next_seq)

    def get_current_memory_claim(self, *, companion_person_id: UUID, counterpart_id: UUID, relationship_id: UUID, predicate: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            resolved = self._resolve_current_claim(conn, companion_person_id, counterpart_id, relationship_id, predicate)
            return resolved[0] if resolved else None

    def _validate_relationship(self, conn, companion_person_id: UUID, counterpart_id: UUID, relationship_id: UUID) -> None:
        row = conn.execute(select(schema.relationship_identity).where(schema.relationship_identity.c.relationship_id == relationship_id)).mappings().one_or_none()
        if row is None:
            fail("RELATIONSHIP_NOT_FOUND", "relationship does not exist")
        if row["companion_person_id"] != companion_person_id or row["counterpart_id"] != counterpart_id:
            fail("EVENT_RELATIONSHIP_MISMATCH", "relationship does not bind the supplied companion/counterpart")

    def _validate_presence(self, conn, companion_person_id: UUID, surface_binding_id: UUID, channel_binding_id: UUID) -> None:
        sb = conn.execute(select(schema.surface_binding).where(schema.surface_binding.c.surface_binding_id == surface_binding_id)).mappings().one_or_none()
        ch = conn.execute(select(schema.channel_binding).where(schema.channel_binding.c.channel_binding_id == channel_binding_id)).mappings().one_or_none()
        if sb is None or ch is None or sb["companion_person_id"] != companion_person_id or ch["companion_person_id"] != companion_person_id:
            fail("PRESENTATION_ROUTE_INVALID", "surface/channel binding does not belong to companion")

    @staticmethod
    def _extract_ram_gb(content: str) -> int | None:
        match = re.search(r"\b(\d+)\s*GB\b", content, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _resolve_current_claim(self, conn, companion_person_id: UUID, counterpart_id: UUID, relationship_id: UUID, predicate: str) -> tuple[dict[str, Any], list[UUID]] | None:
        candidates = conn.execute(
            select(schema.claim).where(
                schema.claim.c.holder_companion_person_id == companion_person_id,
                schema.claim.c.subject_counterpart_id == counterpart_id,
                schema.claim.c.memory_scope_kind == "RELATIONSHIP",
                schema.claim.c.memory_scope_ref == relationship_id,
                schema.claim.c.predicate == predicate,
            )
        ).mappings().all()
        if not candidates:
            return None
        superseded = {
            row["older_claim_id"]
            for row in conn.execute(
                select(schema.claim_supersession).where(
                    schema.claim_supersession.c.older_claim_id.in_([row["claim_id"] for row in candidates])
                )
            ).mappings().all()
        }
        current = [dict(row) for row in candidates if row["claim_id"] not in superseded]
        if len(current) != 1:
            fail("CLAIM_ADMISSION_CONFLICT", "claim graph is ambiguous or contested")
        row = current[0]
        supports = conn.execute(
            select(schema.claim_evidence.c.evidence_id).where(
                schema.claim_evidence.c.claim_id == row["claim_id"],
                schema.claim_evidence.c.relation == "SUPPORTS",
            )
        ).scalars().all()
        if not supports:
            fail("PROJECTION_CLAIM_SUPPORT_INVALID", "current claim lacks support")
        valid_supports: list[UUID] = []
        for eid in supports:
            ev = conn.execute(select(schema.evidence_item).where(schema.evidence_item.c.evidence_id == eid)).mappings().one_or_none()
            if ev is None or ev["origin_kind"] != "COUNTERPART_STATEMENT" or ev["source_type"] != "INTERACTION_EVENT":
                continue
            src = conn.execute(select(schema.interaction_event).where(schema.interaction_event.c.event_id == ev["source_id"])).mappings().one_or_none()
            if src is None or src["relationship_id"] != relationship_id or src["actor_ref"] != counterpart_id:
                continue
            if predicate == RAM_PREDICATE and self._extract_ram_gb(src["content_text"]) != row["value_json"]:
                continue
            valid_supports.append(eid)
        if not valid_supports:
            fail("PROJECTION_CLAIM_SUPPORT_INVALID", "claim support is not recoverable or semantically valid")
        return row, valid_supports

    def _validate_world_evidence(self, conn, evidence_id: UUID, investigation_id: UUID, predicate: str, value: Any) -> None:
        ev = conn.execute(select(schema.evidence_item).where(schema.evidence_item.c.evidence_id == evidence_id)).mappings().one_or_none()
        if ev is None or ev["origin_kind"] != "SEARCH_RESULT" or ev["source_type"] != "WORLD_SOURCE_CAPTURE":
            fail("WORLD_RESULT_SUPPORT_INVALID", "support is not a world source capture EvidenceItem")
        capture = conn.execute(select(schema.world_source_capture).where(schema.world_source_capture.c.source_capture_id == ev["source_id"])).mappings().one_or_none()
        if capture is None:
            fail("WORLD_RESULT_SUPPORT_INVALID", "WorldSourceCapture is missing")
        obs = conn.execute(select(schema.observation).where(schema.observation.c.observation_id == capture["observation_id"])).mappings().one_or_none()
        if obs is None or obs["status"] != "SUCCEEDED":
            fail("WORLD_RESULT_SUPPORT_INVALID", "support Observation is not successful")
        if obs["investigation_id"] != investigation_id:
            fail("WORLD_RESULT_WRONG_INVESTIGATION", "support came from another Investigation")
        blob = conn.execute(select(schema.content_blob).where(schema.content_blob.c.content_digest == capture["content_digest"])).mappings().one_or_none()
        if blob is None:
            fail("CAPTURE_CONTENT_UNAVAILABLE", "captured source content is unavailable")
        if sha256_text(blob["content_text"]) != capture["content_digest"]:
            fail("CAPTURE_CONTENT_UNAVAILABLE", "captured source digest mismatch")
        if predicate == WORLD_MEMORY_REQUIREMENT_PREDICATE:
            try:
                payload = json.loads(blob["content_text"])
            except json.JSONDecodeError as exc:
                raise DomainError("WORLD_RESULT_SUPPORT_INVALID", "captured world source is not valid JSON") from exc
            if payload.get("minimum_memory_gb") != value:
                fail("WORLD_RESULT_SUPPORT_INVALID", "captured source does not support proposed world value")

    def _validate_world_result_for_projection(self, conn, world_result_id: UUID, current_input_event: dict[str, Any]) -> tuple[dict[str, Any], list[UUID]]:
        row = conn.execute(select(schema.world_result).where(schema.world_result.c.world_result_id == world_result_id)).mappings().one_or_none()
        if row is None:
            fail("PROJECTION_WORLD_RESULT_INELIGIBLE", "WorldResult does not exist")
        inv = conn.execute(select(schema.investigation).where(schema.investigation.c.investigation_id == row["investigation_id"])).mappings().one_or_none()
        if inv is None or inv["status"] != "SUCCEEDED":
            fail("PROJECTION_WORLD_RESULT_INELIGIBLE", "WorldResult Investigation is not successful")
        if inv["relationship_id"] != current_input_event["relationship_id"]:
            fail("PROJECTION_WORLD_RESULT_INELIGIBLE", "WorldResult belongs to another relationship")
        if inv["started_at"] < current_input_event["recorded_at"]:
            fail("PROJECTION_FRESHNESS_REQUIREMENT_FAILED", "F4 current checked result must come from an Investigation started after current input")
        supports = conn.execute(
            select(schema.world_result_evidence.c.evidence_id).where(
                schema.world_result_evidence.c.world_result_id == world_result_id,
                schema.world_result_evidence.c.relation == "SUPPORTS",
            )
        ).scalars().all()
        if not supports:
            fail("PROJECTION_WORLD_SUPPORT_INVALID", "WorldResult lacks support")
        for eid in supports:
            self._validate_world_evidence(conn, eid, row["investigation_id"], row["predicate"], row["value_json"])
        contradictions = conn.execute(
            select(schema.world_result_evidence.c.evidence_id).where(
                schema.world_result_evidence.c.world_result_id == world_result_id,
                schema.world_result_evidence.c.relation == "CONTRADICTS",
            )
        ).scalars().all()
        if contradictions:
            fail("PROJECTION_WORLD_RESULT_INELIGIBLE", "F4 does not project contradicted WorldResults as settled")
        return dict(row), list(supports)

    def _validate_foundation_response_payload(self, conn, projection_id: UUID, payload: dict[str, Any]) -> None:
        try:
            draft = FoundationResponseDraft.from_payload(payload)
        except Exception as exc:
            raise DomainError("OUTPUT_CONTENT_POLICY_REJECTED", "generated semantic payload is invalid") from exc
        allowed_claims = set(
            conn.execute(
                select(schema.context_projection_personal_item.c.claim_id).where(
                    schema.context_projection_personal_item.c.projection_id == projection_id
                )
            ).scalars().all()
        )
        allowed_world = set(
            conn.execute(
                select(schema.context_projection_world_item.c.world_result_id).where(
                    schema.context_projection_world_item.c.projection_id == projection_id
                )
            ).scalars().all()
        )
        kinds = [segment.epistemic_kind for segment in draft.segments]
        if kinds.count("REMEMBERED_COUNTERPART_STATEMENT") != 1 or kinds.count("CURRENT_CHECKED_WORLD") != 1 or kinds.count("COMPANION_INTERPRETATION") != 1:
            fail("OUTPUT_CONTENT_POLICY_REJECTED", "F4 response requires one remembered, one checked, and one interpretation segment")
        for segment in draft.segments:
            if segment.epistemic_kind == "REMEMBERED_COUNTERPART_STATEMENT" and segment.source_ref not in allowed_claims:
                fail("OUTPUT_CONTENT_POLICY_REJECTED", "remembered segment must cite a projected Claim")
            if segment.epistemic_kind == "CURRENT_CHECKED_WORLD" and segment.source_ref not in allowed_world:
                fail("OUTPUT_CONTENT_POLICY_REJECTED", "checked segment must cite a projected WorldResult")
            if segment.epistemic_kind == "COMPANION_INTERPRETATION" and segment.source_ref is not None:
                fail("OUTPUT_CONTENT_POLICY_REJECTED", "interpretation segment does not masquerade as a source proposition")
