# ADR-003 — Durable Work, Commitments, Tasks, and Deliverables

**Status:** Accepted architecture checkpoint  
**Decision coverage:** 09.A–09.C  
**Publication:** GitHub-safe

## Context

Deferred work must survive process death without turning ordinary conversational requests, model-generated promises, schedules, procedures, runs, effects, and deliverables into one undifferentiated state machine.

The architecture must preserve:

```text
request
≠ DelegatedTask

DelegatedTask
≠ Commitment

Procedure
≠ Trigger

Trigger
≠ TriggerActivation

TriggerActivation
≠ WorkRun

WorkRun
≠ Action

Effect
≠ TaskCompletion

WorkArtifact
≠ WorkProduct

WorkProduct
≠ Delivery
```

## Decision

### DelegatedTask

`DelegatedTask` is durable accepted work that Alsoul must continue to track beyond transient cognition or interaction context.

A request is historical interaction first. It becomes a task only through explicit task admission.

```text
DelegatedTask {
    task_id
    companion_person_id
    relationship_id?
    requester_ref?
    source_ref
    objective
    completion_criteria?
    created_at
}
```

Synchronous conversational work need not create a durable task. Task admission is appropriate when work is deferred, multi-step, long-running, waiting on a dependency, scheduled, or otherwise required to survive current runtime state.

Task normalization may clarify a request but may not silently widen its scope.

### Commitment

`Commitment` is durable obligation state representing future follow-through undertaken by the CompanionPerson.

```text
Commitment {
    commitment_id
    companion_person_id
    beneficiary_ref?
    task_id?
    obligation
    source_ref
    created_at
}
```

A task does not automatically imply a social commitment, and a commitment does not grant Permission, Approval, capability availability, or external-effect authority.

Future-facing promise language is downstream of committed durable state. If Alsoul says it will take care of work later, the corresponding Task, Commitment, and future-continuation mechanism must already exist.

### Skill / Procedure

`Skill / Procedure` is reusable provider-independent know-how for performing a class of work.

```text
Procedure {
    procedure_id
    procedure_version
    purpose
    input_contract
    steps / orchestration_spec
    completion_contract
}
```

Procedure means how, not whether, why, or when work is authorized to run.

Procedure versions are immutable. A WorkRun pins the version it uses so later procedure changes do not rewrite historical execution semantics.

### Trigger and TriggerActivation

A `Trigger` is declarative activation policy describing when a Task becomes eligible for continuation. A time schedule is one kind of Trigger.

Trigger existence does not mean the Task executed. Trigger satisfaction produces an immutable `TriggerActivation` representing one logical activation opportunity.

```text
TriggerActivation {
    activation_id
    trigger_id
    task_id
    activation_key
    satisfied_at
    source_ref?
}
```

Reprocessing the same logical trigger occurrence resolves to the same activation. A normal activation may create at most one normal WorkRun.

### WorkRun

`WorkRun` is one bounded execution instance undertaken to advance one DelegatedTask.

```text
WorkRun {
    work_run_id
    task_id
    activation_id?
    procedure_id?
    procedure_version?
    started_at
    ended_at?
    run_origin
}
```

Internal model retries, transport retries, Action execution retries, and process restarts do not automatically create new WorkRuns. A new WorkRun represents a genuinely new bounded execution opportunity such as a new activation or explicit later retry.

A WorkRun can orchestrate multiple Investigations, Actions, Artifacts, outputs, and waiting states.

### Task lifecycle

Task lifecycle is append-oriented and derived from explicit lifecycle transitions rather than a single mutable status field.

Conceptual transitions include:

```text
TASK_ACCEPTED
TASK_ACTIVATED
TASK_BLOCKED
TASK_RESUMED
TASK_COMPLETED
TASK_CANCELLED
```

Current task state may be cached operationally, but lifecycle history remains authoritative.

Cancellation is additive history. It fences future normal activations and new task-driven Actions but does not erase prior requests, runs, or Effects and does not convert an already-dispatched unknown effect into confirmed no-effect.

### TaskCompletion

A Task is complete only when declared completion criteria are satisfied by durable canonical evidence.

```text
TaskCompletion {
    task_completion_id
    task_id
    completion_evidence_refs[]
    completed_at
}
```

Examples:

```text
reminder task
→ presented reminder InteractionEvent

create-resource task
→ required Effect

research-and-deliver task
→ adopted WorkProduct + required Delivery
```

WorkRun success alone is insufficient.

### CommitmentDischarge

Commitment discharge is distinct from Task completion.

```text
CommitmentDischarge {
    discharge_id
    commitment_id
    discharge_kind
    source_ref
    discharged_at
}
```

A Commitment may end because it was fulfilled, released by the beneficiary, superseded, or otherwise governed. Completion and discharge must therefore remain separate.

### WorkArtifact

`WorkArtifact` is immutable durable material produced, acquired, or transformed within a WorkRun.

```text
WorkArtifact {
    work_artifact_id
    work_run_id
    task_id
    artifact_kind
    media_type
    content_ref
    content_digest
    source_refs[]
    created_at
}
```

Generated model content or transient execution material does not automatically become a WorkArtifact. Artifact materialization is an explicit host/domain transition.

Artifacts are immutable; later versions are new artifacts with explicit derivation or supersession relationships where needed.

### WorkProduct

`WorkProduct` is a durable task-level deliverable adopted by the CompanionPerson from one or more WorkArtifacts.

```text
WorkProduct {
    work_product_id
    task_id
    producing_work_run_id?
    product_kind
    artifact_refs[]
    adopted_at
}
```

`WorkProduct` is the work-result analogue of `CompanionOutput`: it identifies the deliverable Alsoul intends to stand behind without implying external persistence or delivery.

A corrected deliverable becomes a new WorkProduct with explicit relation to the earlier version rather than mutating the old product.

### External save and Delivery

Saving a WorkProduct to an external destination remains an Action/Effect problem.

```text
WorkProduct persisted internally
≠ saved externally
```

`WorkProductDelivery` records that an exact product version crossed a defined delivery boundary to an intended recipient or destination.

```text
WorkProductDelivery {
    delivery_id
    work_product_id
    recipient_ref
    delivery_channel
    destination_ref?
    delivered_at
    source_ref
}
```

Delivery is channel-specific and does not imply the recipient read, heard, or understood the product.

A first-party text presentation may provide the delivery evidence for an attached/referenced WorkProduct. External channels may rely on capability-specific Effects.

## Durable language contracts

User-facing claims map to distinct durable state:

```text
"I've saved this as a task."
→ DelegatedTask exists

"I'll take care of it."
→ Commitment exists

"It's scheduled for later."
→ durable Trigger/binding exists

"I'm working on it."
→ relevant WorkRun exists and is active

"I drafted it."
→ relevant WorkArtifact exists

"I produced it."
→ adopted WorkProduct exists

"I saved it to X."
→ external persistence Effect exists

"I delivered it."
→ delivery boundary is satisfied

"It's finished."
→ TaskCompletion exists
```

Promise, scheduling, completion, save, and delivery language must not be presented before the corresponding durable state commits.

## Failure and recovery behavior

- Provider transcript text is never the scheduler or task database.
- A crash after TriggerActivation but before WorkRun creation resumes from the activation and creates at most one normal WorkRun if the Task remains runnable.
- A crash after WorkRun creation resumes that run rather than creating another merely because process state was lost.
- Waiting and blocked dependency state must survive restart.
- A cancelled Task cannot be resurrected from old request text or stale Trigger delivery.
- A crash after WorkProduct adoption but before delivery reuses the same product rather than regenerating it by default.
- A crash after Delivery but before TaskCompletion evaluates completion without redelivering.
- A crash after TaskCompletion or CommitmentDischarge does not redo completed work merely because the user-facing completion message was not presented.

## Consequences

Alsoul can own long-lived work without pretending that every request is a promise or every scheduled wake-up is successful execution. Task, commitment, procedure, activation, run, external effect, artifact, product, delivery, completion, and obligation discharge remain independently auditable and recoverable.
