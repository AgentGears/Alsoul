# F5.B Calendar Mutation Result Presentation Increment

This increment advances an adopted, evidence-backed calendar mutation completion into first-party presentation truth. It preserves the distinction between `CompanionOutput`, payload dispatch, sink acceptance, and the canonical `COMPANION_PRESENTED_OUTPUT` Timeline event.

## Admission boundary

Only a `CompanionOutput` produced by the mechanically constrained mutation-completion path may enter this presentation service. Before any payload send, the host revalidates the exact durable chain:

```text
immutable calendar-create Action
→ exact ExecutionAttempt / dispatch fence
→ SUPPORTS-linked provider evidence
→ CONFIRMED_EFFECT
→ mutation-completion ContextProjection
→ validated structured result plan
→ deterministic mutation adoption
→ CompanionOutput
```

The adopted output must still match the immutable Action-derived rendering and the exact Action/Effect/evidence lineage. A tampered Effect, evidence row, completion projection, generated result, adoption row, target, semantic payload, or deterministic content digest fails closed before transport.

## Historical effect truth, not a fresh calendar read

The mutation result says that the exact create Effect was established. It does not claim that the calendar is still in the same current state at presentation time.

Therefore this boundary does not manufacture a calendar-read Permission or current-state schedule freshness decision. Revoking a historical write Permission or Approval after an already-confirmed Effect also does not rewrite that Effect. Those authorities governed mutation execution, not later disclosure of established historical truth.

Every new payload-bearing presentation attempt does, however, require current disclosure authority:

- the personal-world relationship is still ACTIVE;
- the exact selected `PersonalResourceBinding` is still ACTIVE and associated with the same relationship/counterpart;
- the current first-party personal-calendar disclosure policy ALLOWs the exact originating surface/channel and presentation/status contracts; and
- the surface/channel bindings belong to the same `CompanionPerson`.

The relationship, resource, and disclosure-policy heads are compare-and-swap fenced in the same transaction that durably records the disclosure decision and presentation-attempt fence. If revocation or unbinding linearizes first, no new payload crosses the presentation boundary.

## Presentation attempt truth

Before payload transport, the host durably records:

```text
stable semantic presentation_key
exact presentation_attempt_generation
exact presentation_transport_fence_scope_id
exact sink_binding_ref
presentation/status contract versions
payload digest
current disclosure-decision provenance
```

A successful sink response is admitted only when it binds the exact key, generation, fence, and status contract. `NOT_ACCEPTED` is terminal only under `LINEARIZABLE_SETTLED_GENERATION_V1` with the exact `SETTLED_GENERATION` proof shape. A point-in-time or otherwise non-terminal negative cannot unlock another payload send.

`UNKNOWN` remains durable uncertainty. Another payload attempt is blocked until content-free status reconciliation resolves that exact fenced generation. Recovery sends no content and cannot become a bearer authorization for a resend.

## Canonical presentation

Sink acceptance is not yet canonical presentation. Only after durable exact-generation `ACCEPTED` evidence does the host append `COMPANION_PRESENTED_OUTPUT` to the relationship Timeline.

The mutation `CompanionOutput` remains targeted to the immutable Action. Timeline conversational linkage is separately bound to the Action's validated source counterpart interaction; an Action ID is never substituted for an `InteractionEvent` ID. The Timeline append is replay-safe and is followed by durable provenance binding the canonical event to the exact presentation attempt, fence, sink identity, status evidence, receipt, and acceptance time.

If the process loses state after durable sink acceptance but before the Timeline append, replay or content-free recovery repairs the historical presentation record without redisclosing the payload. Later authority revocation does not erase an already accepted presentation.

## Safety properties

This increment preserves the following invariants:

```text
adopted output != presentation attempt
presentation attempt != sink acceptance
sink acceptance != canonical presented Timeline event
UNKNOWN != permission to resend
NOT_ACCEPTED != terminal unless exact generation settlement is proven
presentation failure != mutation failure
presentation retry != Action retry
historical CONFIRMED_EFFECT != current calendar-state claim
```

Presentation/model failure after `CONFIRMED_EFFECT` cannot execute the Action again. No presentation path has access to mutation transport authority or retry consumption.

## Explicit boundary

This increment implements first-party presentation and content-free recovery for adopted `CONFIRMED_EFFECT` calendar-create results, including schema v17 and migration coverage.

It does not broaden F5.B into richer mutation types, delegated/shared approval, compensation workflows, connector-general execution, current-state post-mutation verification, or richer modality. Runtime orchestration and the final F5.B/F5 closure audit remain subsequent work under `docs/F5_EXECUTABLE_CHECKPOINT.md`.
