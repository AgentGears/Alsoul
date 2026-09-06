# ADR-004 — World Signals, Triggers, and Proactive Initiation

**Status:** Accepted architecture checkpoint  
**Decision coverage:** 10.A–10.B  
**Publication:** GitHub-safe

## Context

A persistent companion may need to continue work or initiate contact when the counterpart is not actively talking to it. That behavior must remain bounded, explainable, restart-safe, and independent of model personality or provider session state.

The architecture must prevent these collapses:

```text
WorldSignal
≠ Observation

signal received
≠ world fact established

Trigger satisfied
≠ work completed

background work
≠ proactive contact

proactive model text
≠ authorized presented notification
```

## Decision

### WorldSignal

`WorldSignal` is an immutable durable record that the host received an external or system-originated stimulus relevant to possible world-state evaluation or future work.

```text
WorldSignal {
    world_signal_id
    signal_source_binding_id
    external_event_namespace?
    external_event_id?
    signal_kind
    resource_ref?
    emitted_at?
    received_at
    payload_ref?
    payload_digest?
}
```

A signal is authoritative about its own admitted receipt and source provenance. It is not automatically an `Observation`, `WorldResult`, Trigger satisfaction event, Permission, Approval, or instruction to act.

Signal payload is external data. It does not become control policy or authority merely because it contains imperative text.

### Signal ingestion and deduplication

Signal admission validates source authentication, schema, resource namespace, integrity where applicable, and source-specific event identity before creating a canonical WorldSignal.

When the source contract provides stable semantic event identity, canonical signal identity is scoped to that source binding and the source's documented event-identity namespace.

```text
source binding + source event identity
→ one logical WorldSignal
```

Content similarity is not treated as definitive event identity. Two distinct source events may legitimately contain identical payloads.

Invalid or unauthenticated transport deliveries remain operational records and do not become WorldSignals or trigger evaluation input.

### WorldSignal versus Observation

A wake-up stimulus is not automatically the fact it is about.

```text
WorldSignal
→ may stimulate Investigation

Investigation
→ Observation
→ WorldSourceCapture
→ EvidenceItem
→ WorldResult
```

If an accepted push-event payload itself is a valid source of world information, an Investigation may create an Observation over that signal payload. The Observation still belongs to exactly one Investigation and remains distinct from the signal.

### Trigger

`Trigger` is provider-independent declarative activation policy bound to durable work. It defines when a Task becomes eligible for continuation.

Conceptual trigger condition classes include:

```text
TIME
SIGNAL_OCCURRENCE
WORLD_CONDITION
DEPENDENCY
```

Committed Triggers should be bounded semantic state rather than open-ended free-form model prompts.

A Trigger does not contain the Procedure, grant authority, or constitute execution.

### TriggerEvaluation

`TriggerEvaluation` is an immutable derivation record describing how one Trigger condition evaluated against a specific evidentiary/state basis.

```text
TriggerEvaluation {
    trigger_evaluation_id
    trigger_id
    task_id
    evaluated_at
    source_signal_refs[]
    world_result_refs[]
    dependency_refs[]
    outcome
    condition_value?
}
```

World-condition evaluation uses three semantic outcomes:

```text
SATISFIED
NOT_SATISFIED
UNRESOLVED
```

`UNRESOLVED` means current admissible evidence is insufficient; it is not falsehood.

A signal-occurrence Trigger may be satisfied directly by a valid accepted source event. A world-condition Trigger may require a fresh Investigation and temporally appropriate WorldResult before satisfaction can be established.

### Recurring condition state

Recurring world-condition Triggers maintain rebuildable three-valued condition state from accepted evaluations.

Default edge-triggered semantics are:

```text
NOT_SATISFIED → SATISFIED
    activate

SATISFIED → SATISFIED
    no activation

SATISFIED → UNRESOLVED → SATISFIED
    no activation

SATISFIED → NOT_SATISFIED
    rearm

NOT_SATISFIED → SATISFIED
    activate again
```

A previously satisfied condition rearms only after a later admissible resolved `NOT_SATISFIED` evaluation unless the Trigger explicitly defines another policy. Temporary uncertainty therefore does not create duplicate alerts.

### TriggerActivation identity

`TriggerActivation` remains the durable occurrence that makes Task continuation eligible.

Activation identity depends on Trigger semantics:

```text
ONCE
    → at most one activation for the Trigger

SIGNAL_OCCURRENCE
    → trigger + distinct accepted WorldSignal

CONDITION_EDGE
    → trigger + accepted evaluation that enters SATISFIED

TIME
    → trigger + logical scheduled occurrence
```

Repeated evaluation or transport replay may occur; the same logical activation must not be created twice.

### Proactive work versus proactive contact

Proactive work means Alsoul begins or resumes durable work without a new counterpart input immediately preceding that work.

Proactive contact means Alsoul initiates a presentation into a relationship/channel without that presentation being a direct response to a current counterpart input.

These are separate authority domains.

```text
TriggerActivation
→ Task may continue

not
→ counterpart may always be interrupted
```

Background work may proceed under Task, capability, Permission, and other applicable policies while social contact remains disallowed or deferred.

### Contact authority

A future-notification request may establish bounded contact authority for a specific Task, Relationship, purpose, and permitted channel policy. It must not become a global `proactive_contact = true` flag.

Commitment, RelationshipExperience, PersonModel, remembered preferences, and Trigger existence do not independently grant contact authority.

Proactive presentation still requires an existing durable RelationshipState and applicable channel/surface policy.

### Proactive output target

A proactive message uses the same generated/adopted/presented output architecture as reactive conversation, but it does not fabricate a counterpart message to serve as its origin.

Conceptually:

```text
CompanionOutput {
    companion_output_id
    output_origin_ref
    output_target
    source_generated_output_id
    content_ref
    content_digest
    adopted_at
}
```

For a simple proactive monitor:

```text
origin = WORK_RUN / WR1
target = TriggerActivation A1 / FINAL_NOTIFICATION
```

The output target is the semantic communication purpose. At most one final CompanionOutput may be adopted for one exclusive notification purpose.

Presentation remains separately idempotent, so model retries do not create duplicate notifications and presentation retries do not create duplicate Timeline events.

### Layered idempotency

Proactive behavior uses separate semantic identities at each boundary:

```text
source event identity
↓
WorldSignal identity
↓
TriggerEvaluation basis
↓
TriggerActivation identity
↓
WorkRun identity
↓
output target identity
↓
CompanionOutput adoption
↓
presentation identity
```

One global idempotency key is insufficient because each layer owns different semantics.

### Missed signals and reconciliation

No signal is not evidence that no world event occurred.

Reliability-sensitive monitoring may combine:

```text
push signals for low-latency wake-up
+
periodic Investigation for reconciliation
```

Polling/reconciliation produces world evidence directly; it does not need to synthesize fake WorldSignals.

### Quiet hours and delayed contact

A monitored condition may become satisfied and work may complete while proactive contact is deferred by contact policy.

```text
condition satisfied_at
≠ notification presented_at
```

The pending notification purpose must remain durable. Later contact resumes the same purpose rather than creating a new world-condition activation.

## Invariants

```text
WorldSignal ≠ Observation
WorldSignal ≠ WorldResult
signal receipt ≠ Trigger satisfaction
TriggerEvaluation ≠ TriggerActivation
TriggerActivation ≠ WorkRun
TriggerActivation ≠ Permission
background work ≠ proactive contact
OutputTarget ≠ contact Permission
GeneratedOutput ≠ proactive notification
presented notification ≠ read/heard notification
no signal ≠ condition false
```

## Failure and recovery behavior

- Duplicate source delivery resolves to the same WorldSignal when the source contract supplies authoritative event identity.
- Repeated true evaluations do not create repeated condition-edge activations.
- `UNRESOLVED` does not rearm a previously satisfied recurring condition.
- A cancelled/completed Task prevents stale activations from creating normal new work.
- A crash after WorldSignal admission resumes evaluation without re-ingestion.
- A crash after satisfied TriggerEvaluation may create the missing TriggerActivation idempotently.
- A crash after TriggerActivation creates/reuses one WorkRun under Task lifecycle rules.
- A crash after proactive output adoption presents the same CompanionOutput rather than generating another notification purpose.
- A crash after presentation does not notify again.
- Missed webhooks may be detected through reconciliation without inventing signal history.
- External-channel uncertain presentation must not trigger blind fallback where duplicate-contact risk is unacceptable.

## Consequences

Alsoul can notice, monitor, continue work, and initiate bounded follow-up without giving model salience or external payload text uncontrolled autonomy. Every proactive contact remains traceable to durable Task/Trigger state, the condition basis that caused activation, current authority, the WorkRun that produced the result, and the exact presentation that entered shared history.
