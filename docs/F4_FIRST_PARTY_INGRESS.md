# F4 Trusted First-Party Ingress

**Status:** Implemented foundation checkpoint

The process-hosted F4 slice now accepts a trusted first-party counterpart input without requiring the caller to know canonical Person, Counterpart, Relationship, SurfaceBinding, or ChannelBinding identifiers.

The ingress boundary exists to convert an authenticated transport assertion into one canonical `COUNTERPART_INPUT` event while preserving identity, relationship, presence, and idempotency semantics.

## Core boundary

```text
authenticated first-party transport assertion
        ↓
TrustedCounterpartInputEnvelope
        ↓
pre-existing CounterpartIdentityBinding
        +
pre-existing ChannelBinding
        +
pre-existing SurfaceBinding
        ↓
pre-existing RelationshipState
        ↓
COUNTERPART_INPUT InteractionEvent
        ↓
FoundationResponseCoordinator
```

Permanent distinctions:

```text
transport assertion ≠ identity inference
external subject ≠ CounterpartPerson
CounterpartIdentityBinding ≠ RelationshipState
SurfaceBinding ≠ ChannelBinding
binding availability ≠ authority
transport event ≠ InteractionEvent until admission commits
new conversation/thread ≠ new relationship
input admission ≠ cognition
```

The model never participates in identity resolution.

## Trust assumption

`TrustedCounterpartInputEnvelope` is intentionally named to make the trust boundary explicit. The process caller must authenticate the external subject before constructing the envelope.

The F4 host does not itself implement a public network authentication protocol. It consumes a trusted assertion from a first-party host/transport boundary.

Therefore:

```text
untrusted payload claiming subject X
        ≠
trusted assertion that subject X authenticated
```

An untrusted network service must not expose this local process command directly and treat caller-supplied `external_subject` as proof of identity.

## Input envelope

`ingest` and `interact` read one strict JSON object from standard input:

```json
{
  "identity_namespace": "first-party-account",
  "external_subject": "subject-123",
  "surface_namespace": "alsoul.first_party",
  "surface_ref": "primary-text-surface",
  "channel_namespace": "alsoul.first_party",
  "channel_ref": "primary-text-channel",
  "transport_event_id": "message-456",
  "content_text": "Would the current software run on my machine?",
  "occurred_at": "2026-09-06T12:00:00+00:00",
  "conversation_id": "thread-b"
}
```

Unknown fields fail closed. Required strings must be non-empty. `occurred_at` must be timezone-aware. `conversation_id` is optional and does not own relationship identity.

## Resolution

Ingress resolves only existing bindings:

```text
(channel_namespace, channel_ref)
    → ChannelBinding

(surface_namespace, surface_ref)
    → SurfaceBinding

(identity_namespace, external_subject)
    → CounterpartIdentityBinding

(ChannelBinding.companion_person_id,
 CounterpartIdentityBinding.counterpart_id)
    → RelationshipState
```

The resolved SurfaceBinding and ChannelBinding must belong to the same `CompanionPerson`.

Missing identity, relationship, surface, or channel state is a blocker. Ingress never calls bootstrap and never creates replacement identity roots during recovery or ordinary interaction.

## Semantic ingress identity

Transport redelivery is expected. The same logical source event must collapse to one canonical `InteractionEvent`.

F4 derives a stable semantic ingress identity from:

```text
ChannelBinding
+ identity namespace
+ external subject
+ transport_event_id
```

That identity produces both:

- a stable operation identity for the admission transaction; and
- a relationship-scoped ingress idempotency key.

Exact redelivery returns the original event with `idempotent_replay = true`.

If the same semantic transport identity is reused with different content, occurrence time, route, or conversation metadata, the deterministic operation receipt rejects the conflicting request rather than silently mutating or reinterpreting the original event.

```text
same semantic source event + same request
    → one InteractionEvent

same semantic source event + different request
    → idempotency conflict
```

## Canonical ordering

The input event commits before any fresh-world acquisition or model invocation:

```text
trusted transport assertion
↓
identity / relationship / presence resolution
↓
COUNTERPART_INPUT committed to Timeline
↓
only then: Investigation
↓
Observation / WorldSourceCapture / WorldResult
↓
ContextProjection
↓
ModelInvocation
```

This preserves the cognition boundary: current input is historical truth before it becomes model context.

## Host commands

### Admit only

```text
cat envelope.json | alsoul-host --config ./host.json ingest
```

The command returns canonical identifiers and timeline sequence, not the input text.

### Admit and respond

```text
cat envelope.json | alsoul-host --config ./host.json interact
```

`interact` composes:

```text
ingest
↓
FoundationResponseCoordinator.respond
```

It returns separate `ingress` and `response` identifier objects. The process-control response does not echo counterpart input or generated presentation prose.

Replaying the same completed `interact` envelope reuses the same input event and the already-presented semantic response; it does not repeat world acquisition, model generation, adoption, or presentation.

## Process-loss behavior

Because admission is durable and idempotent, a process may die after input commit and before response work begins.

A later process can replay the same envelope:

```text
process A
  ingest E1
  commit I1
  die

process B
  interact E1
  recover I1
  continue response from canonical state
```

No duplicate counterpart event is required to recover the interaction.

The existing `--after-process-loss` response option remains available when recovery must reconcile provider attempts whose external dispatch may already have begun.

## Thread continuity

`conversation_id` is interaction provenance only.

Changing it does not create a new CounterpartPerson or RelationshipState:

```text
thread A ─┐
thread B ─┼→ same RelationshipState / same Timeline
thread C ─┘
```

This gives the host an executable proof of `Person ≠ Thread` and `Relationship ≠ Thread`.

## Acceptance evidence

The foundation suite now proves:

- known trusted external identity resolves to the existing CounterpartPerson and RelationshipState;
- exact transport redelivery produces one logical `InteractionEvent`;
- conflicting reuse of one semantic source-event identity fails closed;
- unknown external identity creates no new CounterpartPerson, RelationshipState, or Timeline event;
- a new conversation reference preserves the same RelationshipState;
- a separate host process can admit input, terminate, and a later process can resume the same interaction;
- `interact` reaches real HTTPS world acquisition and model generation through the already-established configured runtime;
- replay after presentation causes no duplicate world acquisition, model generation, or presentation;
- process-control output does not echo user input or provider secrets.

## Deliberate exclusions

This checkpoint does not add:

- public network authentication;
- automatic counterpart registration;
- relationship creation on first contact;
- model-based identity resolution;
- channel fallback;
- binding lifecycle/revocation changes;
- external Actions;
- proactive contact;
- multi-party/shared-channel disambiguation;
- rich embodiment.

Those require broader authority, presence, or identity contracts. F4 remains a trusted first-party, one-counterpart reactive slice.
