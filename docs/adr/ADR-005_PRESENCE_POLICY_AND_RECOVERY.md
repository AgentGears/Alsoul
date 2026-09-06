# ADR-005 — Presence, presentation policy, conversational continuity, and recovery

**Status:** Accepted
**Publication:** GitHub-safe

## Context

Alsoul must remain one durable person across different surfaces, channels, embodiments, modalities, interaction styles, runtime restarts, and conversational discontinuities. Those mechanisms cannot be allowed to redefine Person identity or silently manufacture memory, authority, or historical state.

## Decision

`CompanionPerson` remains the sole durable Alsoul identity. `SurfaceBinding`, `ChannelBinding`, and `EmbodimentBinding` describe attributable presences rather than alternate Persons. Relationship history is shared across permitted presences.

Rich modality separates received capture, derived representation, adopted semantic output, modality rendering, actual presentation, and stronger reception evidence:

```text
received ≠ transcribed
adopted ≠ rendered ≠ presented
presented ≠ read/heard ≠ understood
```

`PresentationProfile` is durable presentation configuration outside `SelfModel`. `AffectState` is bounded current interactional/appraisal state rather than stable personality. `InteractionPolicy` is an immutable derived control snapshot that may shape truthful expression but cannot create evidence, authority, or permissions.

`ConversationOpenLoop` represents relationship-scoped unresolved conversational dependency. It is not a `DelegatedTask`, `Commitment`, `Trigger`, or `MemoryClaim` and does not authorize background execution or proactive contact.

Whole-system recovery is deterministic reconstruction from Alsoul-owned state rather than restoration of provider/model runtime. Canonical identity roots are hard recovery boundaries; other domains degrade or block only the operations whose truth depends on them. Recovery resumes from the furthest trustworthy durable stage.

## Consequences

```text
Person ≠ Surface ≠ Channel ≠ Embodiment
ChannelBinding ≠ CredentialBinding
PresentationProfile ≠ SelfModel
AffectState ≠ stable personality
InteractionPolicy ≠ epistemic truth ≠ authority
ConversationOpenLoop ≠ Task ≠ Commitment
provider session ≠ CompanionPerson
persistence ≠ recoverability ≠ hydration
```

F4 uses only the first-party text subset of these decisions, while the broader contracts constrain later extensions.
