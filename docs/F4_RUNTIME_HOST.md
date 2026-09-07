# F4 Runtime Host

**Status:** Implemented foundation checkpoint

The configured F4 slice has a narrow process-facing host. The host turns persistence, recovery, trusted first-party ingress, bounded interaction-purpose routing, bounded conversational context selection, provider execution, and presentation acceptance into an executable process without creating a second source of semantic authority.

## Boundary

```text
process configuration
+
ephemeral transport secret
+
pre-existing compatible F4 database
    ↓
alsoul-host
    ├── readiness / diagnostics
    ├── trusted first-party ingress
    ├── bounded high-level interaction
    │   ├── MEMORY_STATEMENT        → governed memory admission → stop
    │   ├── CONVERSATIONAL_RESPONSE → bounded context → generation → adoption → presentation
    │   └── WORLD_QUESTION          → fresh-world checked response path
    └── lower-level WORLD_QUESTION response/recovery
```

The host is deliberately not a bootstrapper, schema creator, public network authentication service, task scheduler, or authority service.

Permanent distinctions:

```text
runtime configuration ≠ canonical companion state
runtime configuration ≠ credential
credential ≠ identity
host readiness ≠ provider readiness
operator diagnostic ≠ canonical runtime state
trusted transport assertion ≠ model inference
interaction classification ≠ model authority
memory admission ≠ response obligation
conversation ≠ fresh-world investigation
conversation ≠ memory admission
Timeline context ≠ MemoryClaim
reference resolution ≠ model-selected history
prior Companion output ≠ factual source authority
GeneratedOutput ≠ CompanionOutput
CompanionOutput ≠ presentation attempt ≠ sink acceptance ≠ Timeline presentation
presented ≠ read/heard/understood
bootstrap administration ≠ ordinary runtime
```

## Host configuration

The host reads one strict JSON document. Unknown fields fail closed. Relative filesystem paths are resolved relative to the configuration file.

Configuration version 2 requires the existing database plus explicit world, model, and first-party presentation routes. HTTPS trust is process infrastructure rather than evidence, identity, permission, or canonical companion state.

The model authorization token remains absent from the configuration file and, if needed, is supplied only through:

```text
ALSOUL_MODEL_AUTHORIZATION_TOKEN
```

The host does not persist or emit it.

## Readiness

`ready` performs local startup checks only:

```text
configuration parses
↓
database file already exists
↓
database readable
↓
required F4 tables/columns exist
↓
foreign-key enforcement active
↓
READY
```

It performs no world, model, or presentation I/O. A structurally compatible but identity-empty store may pass structural readiness, while trusted ingress still fails closed until required identity and presence bindings exist.

## Commands

### Readiness

```text
alsoul-host --config ./host.json ready
```

### Trusted first-party input admission

```text
cat envelope.json | alsoul-host --config ./host.json ingest
```

`ingest` resolves pre-existing identity, relationship, surface, and channel bindings and commits exactly one canonical `COUNTERPART_INPUT`. The model never participates in identity resolution.

### High-level one-shot interaction

```text
cat envelope.json | alsoul-host --config ./host.json interact
```

`interact` means:

```text
trusted transport assertion
↓
COUNTERPART_INPUT committed
↓
ConfiguredFoundationRuntime.interact
↓
F4InteractionPurposeGate
├── MEMORY_STATEMENT
│   ↓
│   evidence-grounded memory admission
│   ↓
│   successful interaction ends without Companion speech
│
├── CONVERSATIONAL_RESPONSE
│   ↓
│   ContextProjection
│       Self + Relationship + current input
│       optional exact immediately-prior presented exchange
│       no personal/world proposition items
│   ↓
│   ModelInvocation / GeneratedOutput
│   ↓
│   explicit conversational adoption
│   ↓
│   first-party presentation acceptance
│   ↓
│   COMPANION_PRESENTED_OUTPUT
│
└── WORLD_QUESTION
    ↓
    fresh Investigation / Observation / WorldResult
    ↓
    evidence-bearing ContextProjection
    ↓
    ModelInvocation / GeneratedOutput
    ↓
    CompanionOutput adoption
    ↓
    first-party presentation acceptance
    ↓
    COMPANION_PRESENTED_OUTPUT
```

The purpose gate derives classification from the immutable canonical event and fences the event to the exact admitted relationship, surface binding, and channel binding. Route mismatch fails before semantic continuation.

For `MEMORY_STATEMENT`, `interaction.memory_admission` is populated and `interaction.response` is null. No Investigation, ModelInvocation, CompanionOutput, presentation attempt, or presented Timeline event is required.

For `CONVERSATIONAL_RESPONSE`, `interaction.response` contains a conversational response result. Self-contained forms project the current interaction only. The narrow contextual `that`/`it` grammar may project exactly the immediately preceding completed presented exchange. Selection is performed by Alsoul-owned semantic services, not by host CLI code or the model. Both forms perform model generation and presentation but no fresh-world acquisition and no memory admission.

The model contract requires exactly one unsourced `COMPANION_EXPRESSION`. Selected prior Timeline events remain historical conversational context rather than remembered/checked source attribution.

For `WORLD_QUESTION`, `interaction.response` contains the checked response result with personal-memory and fresh-world provenance.

Unsupported high-level input remains canonical Timeline history but fails with `INTERACTION_PURPOSE_UNSUPPORTED` before provider work. The host does not send unsupported input to a model to guess intent or history.

Exact replay recovers the same canonical input and furthest durable semantic response stage. Memory-only replay performs no provider work; conversational replay does not duplicate generation, adoption, or presentation; checked-response replay does not duplicate acquisition, generation, adoption, or presentation.

For contextual conversation, a committed ContextProjection owns the exact selected event set. Recovery does not perform a fresh Timeline lookup.

See [F4 Interaction Purpose Gate](F4_INTERACTION_PURPOSE_GATE.md), [F4 Conversational Response Path](F4_CONVERSATIONAL_RESPONSE.md), [F4 Prior-Timeline Context Selection](F4_PRIOR_TIMELINE_CONTEXT.md), [F4 Trusted First-Party Ingress](F4_FIRST_PARTY_INGRESS.md), and [F4 First-Party Presentation Acceptance](F4_FIRST_PARTY_PRESENTATION.md).

### Content-free recovery diagnostic

```text
alsoul-host --config ./host.json diagnose \
  --relationship-id <relationship-id> \
  --current-input-event-id <event-id>
```

Diagnostics derive response recovery state from canonical rows without returning counterpart text, selected prior Timeline text, captured source bodies, generated prose, or credentials. For conversational responses the same generic response stages apply, but no Investigation or WorldResult is required.

### Model contract probe

```text
alsoul-host --config ./host.json probe-model-contract
```

The current operator probe verifies the checked-response provider wire contract using synthetic non-canonical context. It creates no CompanionPerson cognition, Timeline, memory, or presentation state. Conversational response behavior is verified through executable interaction acceptance rather than by turning the operator probe into canonical cognition.

### Lower-level checked-response execution/recovery

```text
alsoul-host --config ./host.json respond \
  --relationship-id <relationship-id> \
  --current-input-event-id <event-id> \
  --surface-binding-id <surface-binding-id> \
  --channel-binding-id <channel-binding-id>
```

`respond` remains the lower-level primitive only for an interaction already classified as `WORLD_QUESTION`. It re-validates that bounded purpose before dispatching world or model work.

```text
interact = select and execute one implemented F4 semantic path
respond  = execute/resume the checked WORLD_QUESTION path only
```

A caller therefore cannot use the lower-level command to force a greeting, contextual utterance, memory statement, or unsupported input through fresh-world acquisition.

After a known complete process-loss boundary, `--after-process-loss` allows the provider-recovery coordinator to reconcile unresolved provider attempts before any retry decision.

## First-party presentation acceptance

Presentation applies to both conversational and checked responses because both create `CompanionOutput`. It does not apply to a memory-only interaction.

A configured first-party sink must positively accept the exact adopted output under a stable semantic presentation key before `COMPANION_PRESENTED_OUTPUT` is committed.

```text
same presentation key + same content
    → same logical acceptance

same presentation key + different content
    → conflict
```

A lost acceptance response leaves shared history unadvanced. A later process retries the same semantic key and may then commit exactly one canonical presentation after receiving the matching acceptance receipt.

## Administration and bootstrap separation

The host contains no schema-initialization, migration, or foundation-bootstrap command.

```text
alsoul-admin initialize-store / migrate-store
    ≠
alsoul-admin bootstrap-foundation
    ≠
alsoul-host trusted ingress
    ≠
alsoul-host interaction
    ≠
provider recovery
```

Missing Person, CounterpartPerson, RelationshipState, or required presence bindings are hard runtime failures rather than implicit bootstrap triggers.

## Output contract

Successful commands emit one compact JSON object to stdout. Failures emit one JSON error object to stderr with a non-zero exit code. Tracebacks are not emitted by default.

`interact` keeps ingress and semantic execution distinct:

```text
ingress = what canonical input was admitted
interaction = which bounded semantic path ran and what durable result it produced
```

Process-control output returns identifiers and structured outcomes rather than treating host stdout as first-party presentation. User-visible Companion content is governed by the configured presentation boundary.

## Acceptance contract

The executable suite must preserve at least:

1. memory-only host interaction can complete with provider routes unreachable and performs no provider work;
2. bounded conversational input routes to `CONVERSATIONAL_RESPONSE` without creating Investigation or WorldResult;
3. bounded contextual conversation either selects exactly the immediately prior completed presented exchange or fails before provider execution;
4. selected Timeline context is not promoted into MemoryClaim or factual source attribution;
5. conversational output is generated, explicitly adopted, accepted by the first-party sink, and only then written to canonical Timeline history;
6. conversational replay after process replacement does not duplicate context selection, model generation, adoption, or presentation;
7. checked-response process recovery still preserves acquisition/generation/presentation idempotency;
8. lower-level `respond` rejects non-`WORLD_QUESTION` canonical inputs before provider work;
9. unsupported high-level input is preserved as canonical input but fails before provider execution; and
10. route mismatch cannot continue a canonical event under another relationship, surface, or channel.

## Deliberate exclusions

This checkpoint does not add general conversational intent classification, model-selected routing/context retrieval, arbitrary small talk, general pronoun/coreference resolution, generic transcript windows, semantic Timeline search, cross-thread/channel contextual resolution, general question answering, mixed memory-and-question utterances, read/heard/understood receipts, public network authentication, automatic counterpart or relationship creation, external Actions, durable delegated tasks, schedules/proactivity, multi-channel fallback, or rich embodiment.

The host remains a narrow executable boundary for one durable companion: canonical input comes first, bounded purpose and bounded contextual selection occur without model authority, memory can be admitted without fabricated speech, conversation can use exact selected history without pretending that history is memory or world evidence, and fresh-world questions retain explicit evidence and recovery semantics.
