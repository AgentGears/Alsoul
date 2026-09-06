# ADR-001 — Context and Output Boundary

**Status:** Accepted architecture checkpoint  
**Decision coverage:** 07.A–07.B  
**Publication:** GitHub-safe

## Context

Alsoul's persistent identity, relationship, history, memory, and world evidence are owned by Alsoul-domain state rather than by a model session or provider transcript.

The cognition boundary must therefore prevent provider context from becoming an accidental second source of truth. The output boundary must also distinguish what a model generated from what Alsoul adopted and what actually entered shared interaction history.

## Decision

### ContextProjection

`ContextProjection` is an immutable, invocation-scoped, provider-independent semantic snapshot of the exact Alsoul-owned state selected for one cognition invocation.

```text
canonical / admitted / evidence-backed state
        ↓
eligibility + relevance selection
        ↓
ContextProjection
        ↓
provider-specific rendering
        ↓
ModelInvocation
```

A projection is derived and rebuildable. Projections actually used by material model invocations should be retained as immutable attribution manifests.

A foundation projection binds at least:

```text
ContextProjection {
    projection_id
    created_at
    projection_schema_version

    companion_person_id
    relationship_id
    current_input_event_id

    source_self_revision
    source_relationship_revision
    source_timeline_frontier

    selected_event_refs[]
    personal_context_items[]
    world_context_items[]
}
```

`source_timeline_frontier` records what canonical relationship history existed at build time. `selected_event_refs[]` records which historical events cognition actually saw. They are deliberately different.

A projection pins immutable source revisions and references. Rendering must not silently re-read mutable current heads after projection creation.

```text
not projected
≠ forgotten
≠ deleted
≠ false
```

Eligibility precedes relevance. An out-of-scope, forgotten, superseded, contradicted, unsupported, or stale item cannot become valid merely because retrieval ranks it highly.

### Epistemic projection

The projection preserves source semantics rather than flattening all context into generic facts.

Foundation examples:

```text
PersonClaim C1
→ COUNTERPART_STATED_MEMORY

WorldResult W1
→ CURRENT_CHECKED
```

Use-relative epistemic classifications belong to the projection rather than being permanently written onto canonical source objects.

For current checked world information, the projection may classify a `WorldResult` as current checked only after validating its support, contradiction state, temporal fit, freshness, and same-Investigation evidence lineage.

### Provider rendering

Provider messages or prompts are transport serialization of `ContextProjection` plus applicable control policy. They are not canonical state.

```text
ContextProjection
↓
ProviderContextRenderer
↓
provider request
```

Changing provider or renderer may change serialization without changing the semantic projection.

Credential secrets and other execution-only material do not enter the projection.

### ModelInvocation

One `ModelInvocation` binds exactly one immutable `ContextProjection`.

```text
ModelInvocation {
    model_invocation_id
    context_projection_id
    provider_binding_ref
    model_ref
    renderer_version
    provider_request_digest
    started_at
    completed_at?
    outcome
}
```

A turn may create multiple projections and invocations. New memory, world evidence, or canonical revisions create a new projection for a later invocation rather than mutating an existing projection.

### GeneratedOutput

A successful invocation may produce immutable candidate material:

```text
GeneratedOutput {
    generated_output_id
    model_invocation_id
    content_ref
    content_digest
    received_at
}
```

`GeneratedOutput` is authoritative only about generation. It is not canonical truth, companion adoption, presentation, or external effect.

```text
model generated X
≠ Alsoul said X
```

### CompanionOutput

`CompanionOutput` is the adoption boundary: content Alsoul has accepted as its intended user-facing expression for one semantic output target.

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

`output_origin_ref` records why the output exists. `output_target` identifies the response or notification purpose for idempotent adoption.

For a reactive response:

```text
origin = RESPONSE_TO_EVENT / I3
target = I3 / FINAL_RESPONSE
```

Later proactive work may use a durable work origin and activation-scoped notification target.

At most one final adopted output should fill one exclusive output target unless a specific product policy defines otherwise.

### Presentation

Adoption is not presentation.

For the foundation first-party text path, a companion output becomes canonical shared interaction history only when an idempotent `COMPANION_PRESENTED_OUTPUT` `InteractionEvent` is committed.

```text
GeneratedOutput
↓
adoption
↓
CompanionOutput
↓
presentation
↓
InteractionEvent
    kind = COMPANION_PRESENTED_OUTPUT
    actor_ref = CompanionPerson
```

The Timeline actor is the durable `CompanionPerson`, not the model/provider that generated the candidate.

The full lineage is:

```text
InteractionEvent
↓
CompanionOutput
↓
GeneratedOutput
↓
ModelInvocation
↓
ContextProjection
↓
selected canonical / evidence-backed sources
```

## Invariants

```text
Companion ≠ Model
ContextProjection ≠ provider prompt
Generated Output ≠ Adopted Output
Adopted Output ≠ Presented Output
Presented Output ≠ Heard Output
provider retry ≠ companion identity change
model-generated assertion ≠ admitted fact
```

Generated or presented output does not independently support the truth of its own external assertions. It may establish that the model generated, Alsoul adopted, or Alsoul presented the relevant statement, depending on which source record is used.

## Failure and retry behavior

- A failed or unknown model execution does not create a presented output.
- Provider retries are separate `ModelInvocation`s, even when they use the same projection.
- Concurrent candidate outputs for the same exclusive output target are fenced so one adoption wins.
- A late provider result cannot replace an already adopted response automatically.
- Presentation retries reuse the same adopted `CompanionOutput` and must not append duplicate Timeline events.
- A crash after adoption but before presentation resumes from the adopted output rather than regenerating by default.
- A crash after presentation does not present the same output again.

## Consequences

Provider context can be destroyed and rebuilt without becoming a continuity store. Model replacement changes the cognition engine, not the companion person. User-facing statements about memory, checked world information, and task/effect state can be traced through the exact projection and durable sources that produced the adopted output.
