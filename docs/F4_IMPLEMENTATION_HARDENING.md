# F4 Implementation Hardening

## Purpose

This checkpoint hardens the first executable walking skeleton without widening its semantic scope.

The implementation still proves the same path:

```text
CompanionPerson / Self / Relationship
→ Timeline
→ admitted personal memory
→ fresh Investigation / Observation / WorldSourceCapture
→ EvidenceItem / WorldResult
→ ContextProjection
→ ModelInvocation
→ GeneratedOutput
→ CompanionOutput
→ presented Timeline event
```

The changes in this checkpoint make the boundary safer to extend toward real acquisition and cognition providers.

## Explicit bootstrap boundary

Foundation identity creation is now separated from ordinary application services.

```text
FoundationBootstrapper
    explicit one-time creation

FoundationServices
    operate only on already-existing canonical state
```

`FoundationServices.bootstrap_foundation(...)` fails closed. Recovery may not treat missing Person, Self, Counterpart, Relationship, or presence bindings as permission to create replacements.

This preserves:

```text
missing identity during recovery
≠ create a new identity
```

## Provider-independent adapter boundary

The adapter package now exposes semantic contracts for:

```text
WorldAcquisitionAdapter
ModelProviderAdapter
```

Deterministic acceptance adapters implement those contracts.

A generic HTTP world-acquisition adapter is also available. It acquires source material and source metadata only. It does not create or admit:

```text
Observation
EvidenceItem
WorldResult
```

Those remain semantic service boundaries. Therefore transport success cannot become current world truth by itself.

The HTTP adapter accepts only explicit `http` / `https` locators and positive timeouts.

## Recovery acceptance

The recovery coordinator is now exercised at every currently implemented response stage:

```text
INPUT_ADMITTED
→ PROJECTION_READY
→ GENERATED
→ ADOPTED
→ PRESENTED
```

These remain derived states. No mutable turn-status aggregate is introduced.

At each stage, recovery derives progress from canonical durable rows and continues from the furthest trustworthy committed boundary.

## Continuous verification

The repository now continuously verifies:

```text
source/test compilation
acceptance and regression tests
migration upgrade
migration downgrade
```

The verification workflow is intentionally narrow: it checks the executable foundation contract rather than introducing unrelated build complexity.

## Scope remains narrow

This checkpoint does not implement:

```text
Permission / Approval / Action / Effect
DelegatedTask / Commitment / Trigger / WorkRun
proactive contact
rich modality / streaming presentation
AffectState
ConversationOpenLoop persistence
```

Those remain governed by the existing architecture decisions and can be added only without weakening the F4 trust boundaries.

## Next implementation boundary

The next safe increment is to move from adapter readiness to controlled real-provider integration while preserving the same durable sequence:

```text
persist semantic attempt identity
→ call replaceable adapter
→ persist exact acquired/generated material
→ validate semantic admission
→ only then allow downstream claims or presentation
```

No provider runtime becomes identity, memory, world truth, or shared-history authority.
