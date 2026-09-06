# F4 First-Party Presentation Acceptance

**Status:** Implemented foundation checkpoint

The F4 reactive slice now separates adoption of Alsoul's intended output from acceptance by the configured first-party presentation surface and from the canonical Timeline event that records successful presentation.

## Core boundary

```text
GeneratedOutput
↓
CompanionOutput adoption
↓
first-party presentation attempt
↓
first-party sink acceptance
↓
COMPANION_PRESENTED_OUTPUT Timeline commit
```

Permanent distinctions:

```text
GeneratedOutput ≠ CompanionOutput
CompanionOutput ≠ presentation attempt
presentation attempt ≠ sink acceptance
sink acceptance ≠ Timeline presentation commit
presented ≠ read/heard/understood
unknown presentation outcome ≠ confirmed presentation
```

A `COMPANION_PRESENTED_OUTPUT` event therefore means that the configured first-party sink positively accepted the exact adopted output. It does not mean that the counterpart read, heard, noticed, understood, or agreed with it.

## Why the boundary is explicit

Before this checkpoint, the response coordinator could move directly from an adopted `CompanionOutput` to a presented Timeline event. That preserved generated/adopted/presented distinctions inside the data model, but the process boundary did not yet prove that a real presentation surface had accepted the output.

The implemented path now requires an external acceptance boundary before shared history advances:

```text
CompanionOutput CO1
↓
load exact content + digest
↓
derive stable presentation key
↓
first-party presentation adapter
↓
validated acceptance receipt
↓
PresentCompanionOutput
↓
InteractionEvent kind=COMPANION_PRESENTED_OUTPUT
```

A failed, rejected, malformed, or uncertain sink operation cannot directly create the Timeline presentation event.

## First-party presentation contract

The provider-independent adapter contract receives:

```text
presentation_key
companion_output_id
surface_binding_id
channel_binding_id
content_text
content_digest
```

and must return an acceptance receipt carrying:

```text
presentation_key
receipt_ref
content_digest
```

The returned key and digest must exactly match the request. A receipt for different content is not admissible as presentation evidence for the adopted output.

The receipt is intentionally narrow. It establishes:

> the configured first-party sink accepted this exact output under this semantic presentation key.

It does not establish read/heard/understood state.

## Stable presentation identity

F4 derives one restart-stable semantic presentation key from:

```text
CompanionOutput identity
+
SurfaceBinding identity
+
ChannelBinding identity
+
F4 presentation-contract version
```

Conceptually:

```text
presentation_key = semantic_identity(
    companion_output_id,
    surface_binding_id,
    channel_binding_id,
    presentation_contract_version,
)
```

The key is not a payload hash. Two distinct `CompanionOutput` objects may contain identical bytes and still represent distinct semantic presentations.

The exact route is part of the key because presentation on one surface/channel route is not automatically presentation on another.

## Idempotency requirement

A conforming first-party sink must implement:

```text
same presentation_key + same content
    → same logical presentation acceptance

same presentation_key + different content
    → reject conflict
```

This is required because a process may lose the acceptance response after the sink already accepted the output.

The retry path is therefore:

```text
CO1
↓
presentation key K1
↓
sink accepts K1
↓
process loses response
↓
no Timeline presentation committed
↓
process restarts
↓
recover CO1
↓
retry K1 with exact same content
↓
sink returns acceptance for existing logical presentation
↓
commit one COMPANION_PRESENTED_OUTPUT
```

The network may observe two transport attempts while the presentation domain observes one logical accepted presentation.

## Unknown outcome semantics

Transport loss after dispatch is treated as an unknown presentation outcome.

```text
request definitely rejected
    → no presentation

acceptance receipt validated
    → sink acceptance established

transport outcome unknown
    → do not claim presentation
    → do not create presented Timeline event
    → retry only with same semantic key
```

This follows the broader Alsoul rule:

```text
failed effect ≠ uncertain effect
```

For the first-party F4 sink, safe retry is possible only because the sink contract explicitly guarantees idempotency by `presentation_key`.

## Timeline commit

After acceptance, the coordinator invokes the existing semantic `PresentCompanionOutput` boundary using a stable application-operation identity for the response's presentation commit.

This creates exactly one canonical event:

```text
InteractionEvent {
    kind = COMPANION_PRESENTED_OUTPUT
    actor = CompanionPerson
    companion_output_id = CO1
    surface_binding_id = exact accepted surface
    channel_binding_id = exact accepted channel
}
```

The Timeline remains the authoritative shared interaction history. The presentation adapter receipt does not replace the Timeline event; it gates whether that event is allowed to exist.

## Recovery cases

### Failure before sink acceptance

```text
CompanionOutput exists
sink rejects / fails definitively
↓
no presented Timeline event
```

### Unknown sink outcome

```text
CompanionOutput exists
sink may have accepted
receipt lost
↓
no presented Timeline event yet
↓
retry same presentation key
```

### Crash after acceptance, before Timeline commit

```text
sink accepted K1
process dies before Timeline commit
↓
recover adopted output
↓
retry K1
↓
receive idempotent acceptance
↓
commit one Timeline event
```

### Crash after Timeline commit

```text
COMPANION_PRESENTED_OUTPUT already exists
↓
recovery returns existing response
↓
no sink redispatch
```

## Configured HTTPS adapter

The configured runtime uses an HTTPS JSON presentation endpoint. The adapter:

- requires an absolute HTTPS endpoint;
- does not permit cross-origin resolution;
- sends the exact adopted content and digest;
- validates the response schema, key, digest, and acceptance status;
- treats transport uncertainty as `AdapterOutcomeUnknown`;
- does not reinterpret an uncertain transport result as success.

Host configuration version 2 therefore includes:

```json
{
  "presentation": {
    "endpoint": "https://surface.example.invalid/present",
    "timeout_seconds": 10
  }
}
```

This endpoint is process configuration. It is not CompanionPerson identity, RelationshipState, Permission, or memory.

## Process-level acceptance

The executable acceptance suite proves two important cases.

Normal path:

```text
trusted input
↓
world acquisition
↓
model generation
↓
CompanionOutput
↓
first-party sink accepts once
↓
COMPANION_PRESENTED_OUTPUT
↓
completed replay causes no second sink request
```

Uncertain-response path:

```text
sink accepts presentation
↓
connection disappears before acceptance response reaches host
↓
host reports unknown outcome
↓
Timeline still has zero presented events
↓
new host process retries same semantic key
↓
sink recognizes existing logical presentation
↓
one Timeline presentation is committed
```

This makes the user's shared-history semantics correspond to an actual first-party presentation boundary rather than an internal function call.

## Deliberate exclusions

F4 still does not implement:

- read receipts;
- heard/playback-complete receipts;
- comprehension or attention state;
- external-channel delivery semantics;
- multi-channel fallback;
- proactive contact;
- rich embodiment;
- a general notification aggregate.

Those concerns require broader channel and delivery contracts. The F4 checkpoint is intentionally narrower: one adopted response, one first-party route, one idempotent acceptance, and one canonical presented Timeline event.
