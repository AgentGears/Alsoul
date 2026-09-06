# ADR-002 — Authority, Action, Execution, and Effect

**Status:** Accepted architecture checkpoint  
**Decision coverage:** 08.A–08.B  
**Publication:** GitHub-safe

## Context

Externally consequential behavior must not collapse technical ability, authentication, standing authority, operation-specific approval, semantic intent, execution, and external effect into one tool call.

The architecture must make the following distinctions mechanically enforceable:

```text
host can technically do X
≠ Alsoul may do X

Alsoul may generally do X
≠ this exact operation is approved now

operation was attempted
≠ external effect occurred
```

## Decision

### Capability

`Capability` is a provider-independent semantic operation contract describing what the host can potentially perform.

Examples are semantic operation families rather than provider tool names:

```text
world.search
calendar.event.create
mail.send
file.write
```

Capability existence does not imply current availability, permission, credential feasibility, approval, execution, or effect.

Read-only acquisition can use capabilities through the `Investigation → Observation` world path without becoming an effectful `Action`, although read access may still require authority.

### CredentialBinding

`CredentialBinding` records how an external system can be authenticated.

Conceptually:

```text
CredentialBinding {
    credential_binding_id
    external_system_ref
    external_principal_ref
    secret_ref
    provider_scope_snapshot?
    status
}
```

Credential possession and provider scopes are technical ceilings, not Alsoul permission.

```text
CredentialBinding ≠ CounterpartPerson
provider scope ≠ Permission
```

Credential secrets never enter model cognition. The trusted executor resolves them only after authority checks.

### Permission

`Permission` is durable scoped standing authority for a `CompanionPerson` to perform a class of operations under defined constraints.

Conceptually:

```text
Permission {
    permission_id
    holder_companion_person_id
    grantor_ref
    capability_scope
    resource_scope
    constraints
    granted_at
    expires_at?
}
```

Permission must be explicit authority state. It cannot be inferred from memory, trust, relationship experience, prior behavior, model prediction, delegated tasks, or commitments.

Historical authorization does not become current Permission merely because it remains in the Timeline or Memory.

### Approval

`Approval` is bounded consent for a specific immutable `Action` when current policy requires operation-specific confirmation.

```text
Approval {
    approval_id
    action_id
    approver_ref
    granted_at
    expires_at?
    evidence_ref?
}
```

Approval does not widen Permission or higher policy.

Approval binds immutable semantic action intent, not mutable tool arguments. A materially changed target, amount, recipient, or other operation parameter requires a new Action and therefore new approval where required.

### Action

`Action` is an immutable provider-independent representation of one intended externally consequential operation.

```text
Action {
    action_id
    companion_person_id
    relationship_id?
    capability_id
    source_ref
    operation
    target_ref
    canonical_parameters
    action_digest
    created_at
}
```

A model/provider function call is only an action proposal until Alsoul's host normalizes and validates it into an `Action`.

```text
model tool call
→ candidate action proposal

not
→ external dispatch
```

Credential choice normally belongs to execution rather than Action semantics, so credential rotation can preserve the same semantic Action when the target/resource identity is unchanged.

### Execution-time authority gate

Before every effectful dispatch, evaluate current authority against the immutable Action:

```text
capability available
AND host/product policy permits
AND usable credential exists
AND provider technical scopes suffice
AND current Permission permits
AND required Approval is valid for this Action
AND all Action constraints still hold
```

No one lower layer can widen another required layer.

Authorization is re-evaluated before retries; an Action that was previously executable does not become permanently executable.

### ExecutionAttempt

`ExecutionAttempt` is one immutable concrete attempt to execute an already-defined Action through a particular adapter, credential binding, and execution channel.

```text
ExecutionAttempt {
    execution_attempt_id
    action_id
    attempt_seq
    capability_id
    capability_contract_version
    adapter_ref
    credential_binding_id
    permission_refs[]
    approval_refs[]
    external_idempotency_key?
    started_at
    dispatch_started_at?
    completed_at?
    transport_outcome
    response_ref?
}
```

Retries create new ExecutionAttempts but preserve the same `action_id` because they remain attempts to realize the same semantic operation.

### Idempotency

Where the external capability supports stable idempotency, retries of one Action reuse one external operation identity derived from or stored against `action_id`.

```text
A1
├── X1 → K(A1)
└── X2 → K(A1)
```

The key must not be derived solely from semantic payload hashing because two intentionally distinct Actions may have identical parameters.

Provider idempotency limitations such as time windows remain part of the capability execution contract; they are not assumed universal.

### Effect

`Effect` is an immutable evidence-grounded record that a capability-specific externally observable consequence associated with an Action has actually been established.

```text
Effect {
    effect_id
    action_id
    effect_kind
    external_effect_ref?
    occurred_at?
    confirmed_at
}
```

with recoverable support:

```text
EffectEvidence {
    effect_id
    evidence_id
    relation = SUPPORTS
}
```

A tool result may support an Effect when the capability contract says the response semantics are sufficient. A tool result is not automatically an Effect.

### Effect-state distinction

Execution must preserve three materially different states:

```text
CONFIRMED_EFFECT
CONFIRMED_NO_EFFECT
UNKNOWN_EFFECT
```

`UNKNOWN_EFFECT` is first-class and survives restart.

```text
UNKNOWN_EFFECT ≠ failure
UNKNOWN_EFFECT ≠ success
```

A timeout after possible dispatch does not justify blind retry when duplicate external consequences are possible.

### Reconciliation

Unknown effects are reconciled using read-side evidence where possible:

```text
UNKNOWN_EFFECT
↓
Investigation
↓
Observation
↓
WorldSourceCapture
↓
EvidenceItem
↓
Effect confirmation
or confirmed no-effect
or still unknown
```

Reconciliation is observation, not a second effectful Action unless an actual new external mutation is intentionally required.

## Invariants

```text
Capability ≠ current availability
Capability ≠ Permission
Credential ≠ Permission
Permission ≠ Approval
Approval ≠ Action
Action ≠ ExecutionAttempt
ExecutionAttempt ≠ Effect
failed effect ≠ uncertain effect
Commitment ≠ Permission
Procedure ≠ Permission
conversation claim ≠ external effect
```

## Completion-language contract

Strong completion language is downstream of Effect state.

```text
Action intended
≠ Action attempted
≠ Effect established
```

Statements such as:

```text
"Done."
"I sent it."
"I created it."
```

are warranted only when recoverable evidence establishes the capability-specific effect corresponding to the verb being used.

A weaker effect must use weaker language. For example, an accepted outbound request does not automatically establish external delivery.

## Failure and recovery behavior

- Persist an ExecutionAttempt and its idempotency identity before crossing an external dispatch boundary.
- Persist response/acquisition evidence before admitting an Effect.
- Persist an Effect atomically enough that its required SUPPORTS evidence exists from the first committed state.
- A crash with `UNKNOWN_EFFECT` must recover that uncertainty and must not blindly recreate the Action.
- A confirmed primary Effect stops ordinary retries of the same Action.
- Output/presentation failure after Effect confirmation does not undo the Effect and must not cause the Action to be re-executed.
- Cancellation of a higher-level Task does not retroactively erase an already-dispatched Action or convert unknown effect state into confirmed no-effect.

## Consequences

Alsoul can explain not only what it intended to do, but why execution was authorized, what concrete attempts occurred, and what external consequence is actually known. Technical connectors and model tool syntax remain replaceable implementation details beneath stable semantic Action and Effect contracts.
