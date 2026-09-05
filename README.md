# Alsoul

> **A companion with a world, not a chatbot with tools.**

Alsoul is a persistent personal companion architecture designed to remain one continuous person across model, process, thread, surface, and provider changes.

The project is currently in **foundation convergence**: the identity, history, memory, evidence, person-understanding, and fresh-world boundaries are being fixed before broad implementation begins.

## Product thesis

Alsoul should feel like someone who knows you, lives in your world, and knows the limits of what they know and can do.

Its internal architecture may be sophisticated. The user's mental model should remain simple:

```text
                    Alsoul
                      │
       ┌──────────────┼──────────────┐
       │              │              │
   knows me       has a world      can help me
       │              │              │
   remembers        can check      can act
   understands      can notice     can work
   our history      can observe    can follow up
```

The primary trust quality is **felt honesty**. When Alsoul says it remembers, checked, observed, inferred, acted, or is uncertain, those words should correspond to real internal state.

## Foundation principles

```text
Companion ≠ Model
Self ≠ Relationship ≠ World
Memory ≠ Observation
Historical Evidence ≠ Derived Memory
Observation ≠ Interpretation
Fact about a person ≠ PersonModel claim ≠ Interaction Policy
Search result ≠ Companion belief
Person ≠ Thread ≠ Surface ≠ Channel ≠ Embodiment
Identity ≠ Credential ≠ Authority
Capability availability ≠ permission ≠ approval ≠ effect
Failed effect ≠ uncertain effect
Context reset ≠ historical deletion
Memory proposal ≠ memory admission
Generated output ≠ presented output ≠ heard output
Authoritative result ≠ context projection
```

## Current architecture map

```text
CompanionPerson
    │
    ├── SelfModel
    │
    └── RelationshipState ─── CounterpartPerson
                                │
                                └── PersonClaim / PersonModel

RelationshipState
    │
    └── Canonical Timeline
            │
            └── EvidenceItem
                    │
                    └── MemoryClaim / PersonClaim

Fresh world question
    │
    └── Investigation
            │
            └── Observation
                    │
                    └── WorldSourceCapture
                            │
                            └── EvidenceItem
                                    │
                                    └── WorldResult

Memory / PersonModel / WorldResult
    │
    └── ContextProjection
            │
            └── cognition
```

## Foundation walking skeleton

The first vertical slice proves one continuous companion that can:

1. recover the same durable person and relationship after complete process death;
2. recover one evidence-grounded personal memory;
3. receive a question requiring current external information;
4. perform a real investigation and preserve what was actually checked;
5. derive an evidence-backed world result;
6. combine remembered personal context with fresh world evidence; and
7. present memory, checked information, and interpretation as distinct epistemic classes.

The target interaction should be mechanically capable of meaning:

```text
"You told me ..."
"I checked ..."
"My take is ..."
```

without those distinctions being prompt conventions or stylistic guesses.

## Documentation

- [Product Constitution](docs/PRODUCT_CONSTITUTION.md)
- [Architecture Convergence](docs/ARCHITECTURE_CONVERGENCE.md)
- [Foundation Walking Skeleton](docs/FOUNDATION_WALKING_SKELETON.md)
- [Decision Ledger](docs/DECISION_LEDGER.md)

## Status

Pre-implementation foundation. Public documents contain Alsoul-native product and architecture decisions. Detailed implementation contracts and ADRs will be added as convergence decisions harden into code-facing interfaces and acceptance tests.
