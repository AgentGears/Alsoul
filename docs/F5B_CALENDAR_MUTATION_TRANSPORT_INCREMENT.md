# F5.B Calendar Mutation-Transport Increment

This increment advances the executable `calendar.event.create` path across the first real provider mutation boundary while preserving the previously landed Action, Approval, ExecutionAttempt, and dispatch-fence semantics.

## Implemented boundary

The current transport entry begins from one `PREPARED` ExecutionAttempt. It first qualifies the concrete mutation adapter against the current trusted execution binding, then advances that same attempt through the existing current-authority fence, and only within that same bounded call may the newly created `DISPATCH_FENCED` attempt proceed toward provider transport.

A dispatch fence that already exists when a fresh transport command begins is **not** reusable execution authority. It is a surviving may-have-dispatched fence and therefore recovers conservatively to `UNKNOWN_EFFECT` without a provider call. This prevents a persisted fence from being replayed after restart, delayed until authority has changed, or consumed by a replacement transport process as if it were a standing mutation token.

Before the adapter call can exist, the host also commits one structural mutation-dispatch row for that newly fenced ExecutionAttempt. That row contains no title, time, resource target, correlation value, credential reference, approval material, or raw request payload. Its existence is the one-shot transport claim: a surviving claim without durable normalized response evidence recovers conservatively as `UNKNOWN_EFFECT` and cannot be sent again.

After the one-shot claim commits, the trusted host constructs a bounded host-to-adapter envelope from canonical state. It contains opaque host-side Action/ExecutionAttempt references plus only the semantic/provider material required to reconstruct the exact request:

```text
opaque ExecutionAttempt / Action references for trusted host-side control flow
exact external system/resource target
Action title/summary
Action normalized start/end instants
Action-specific correlation key
credential secret reference
exact capability / adapter contract versions
fixed mutation-request contract version
```

The opaque canonical references are not provider-wire fields. The adapter may place on the provider wire only the exact routing, title/time, correlation, fixed provider-operation metadata, and ephemeral authentication material required by the pinned create contract. Permission, Approval, consent text, conversation history, model context, unrelated personal data, raw credential material, and provider defaults are not part of the provider-bound mutation payload.

The concrete mutation adapter must match the exact adapter binding, adapter contract, capability contract, external system, and execution semantics selected before the fresh fence and then pinned by that fence. A replacement or mismatched adapter cannot create or consume the transport handoff.

## Minimized response evidence

A positive provider response is eligible for durable capture only after the trusted adapter has reduced it to the bounded mutation-response contract. Durable evidence contains only:

```text
ExecutionAttempt / Action identity
Action correlation value
external effect reference
external system/resource proof
normalized title/summary proof
normalized start/end proof
provider status = CREATED
receipt reference
observation time
fixed evidence schema version
```

Raw provider responses and unrelated provider fields do not become canonical mutation evidence.

The host compares this minimized response with the immutable Action. Exact correlation plus exact target/title/start/end semantics produces `MATCHED_EFFECT_EVIDENCE`. A structurally valid correlated response with effect-relevant semantic divergence produces `DIVERGENT_EFFECT_EVIDENCE`, advances the unresolved attempt to `UNKNOWN_EFFECT`, and keeps the Action dispatch-locked.

Neither result is an `Effect` in this increment.

## Recovery and uncertainty

The increment preserves these distinctions:

```text
mutation dispatch claim != provider Effect
provider response != durable evidence
matched durable evidence != admitted Effect
correlated divergence != confirmed no-effect
UNKNOWN_EFFECT != retry authority
```

An adapter-level unknown/rejected outcome after the one-shot transport claim becomes `UNKNOWN_EFFECT`; this increment does not infer terminal no-effect from transport failure or rejection. A malformed normalized response also leaves the attempt unknown and is not persisted as effect evidence.

If process loss occurs after `DISPATCH_FENCED` but before the one-shot mutation-dispatch claim, the surviving fence is not consumed by a later transport command; it becomes `UNKNOWN_EFFECT` without provider dispatch.

If process loss occurs after the structural mutation-dispatch claim but before durable normalized response evidence exists, later dispatch entry detects the surviving claim, performs no provider call, and moves the attempt conservatively to `UNKNOWN_EFFECT`.

If matched evidence is durable but Effect admission has not yet occurred, the Action remains dispatch-locked. Existing conservative fenced-attempt recovery may move the attempt to `UNKNOWN_EFFECT`, but the durable matched evidence remains available for the subsequent Effect-admission increment; no redispatch occurs.

## Explicit boundary

This increment does **not** admit `CONFIRMED_EFFECT`, does not implement terminal `CONFIRMED_NO_EFFECT`, does not consume a no-effect state for retry, does not perform authorized read-side reconciliation, and does not generate mutation-completion cognition or strong completion language.

The next F5.B increment must consume durable minimized mutation evidence into capability-sufficient terminal Effect truth. `CONFIRMED_EFFECT` must become visible only with its required supporting evidence already durable and must atomically terminalize the per-Action mutation guard. Reconciliation, terminal no-effect proof, retry consumption, and mutation-completion presentation remain subsequent work under `docs/F5_EXECUTABLE_CHECKPOINT.md`.
