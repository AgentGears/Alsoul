# F4 Evidence-Grounded Memory Admission

## Status

This checkpoint closes the remaining manual-memory fixture in the first-party F4 interaction slice.

The implemented boundary is deliberately narrow. It supports one factual relationship-scoped predicate:

```text
primary_machine.memory_gb
```

The purpose is not to implement general memory extraction. It is to prove that a trusted counterpart statement can become durable memory only through explicit evidence-grounded admission, and that correction remains an append-only claim transition rather than a rewrite of history.

The later interaction-purpose gate preserves this admission boundary while allowing a pure memory statement to terminate successfully after durable admission rather than being forced through unrelated world/cognition work.

## Core invariant

```text
counterpart statement
≠ extracted candidate
≠ memory proposal
≠ admitted memory
```

The implemented memory path is:

```text
trusted first-party input
↓
COUNTERPART_INPUT InteractionEvent
↓
bounded deterministic extraction
↓
F4MemoryCandidate
↓
source binding
↓
F4MemoryProposal
↓
relationship/current-claim validation under admission fence
↓
F4CounterpartMemoryAdmission transaction
↓
COUNTERPART_STATEMENT EvidenceItem
+
FACTUAL PersonClaim / relationship-scoped MemoryClaim semantics
↓
future retrieval into ContextProjection when relevant
```

A model is not asked to decide whether the statement is memory-worthy, which predicate it represents, who the statement is about, or whether an existing claim should be replaced.

## Bounded extraction

The extractor accepts only explicit first-person assertions tying a positive integer memory quantity to the counterpart's own primary machine/computer memory. Examples include:

```text
My machine has 16 GB RAM.
My computer has 16 GB of memory.
My RAM is 16 GB.
```

An explicit correction can be expressed with bounded correction language, for example:

```text
Actually, my machine has 32 GB RAM.
Instead, my machine has 32 GB RAM.
```

The extractor does not produce a candidate for questions, unrelated storage quantities, third-party machines, or generic `GB` mentions. Examples that do not become candidates include:

```text
Does my machine have 16 GB RAM?
My USB drive has 16 GB RAM.
Their machine has 16 GB RAM.
```

Absence of a candidate does not alter history. The original InteractionEvent remains canonical Timeline state.

## Candidate is not proposal

`F4MemoryCandidate` is a non-authoritative semantic interpretation of statement text. It contains only:

```text
predicate
value
explicit_correction
```

It has no source-event identity and therefore cannot itself become admissible memory.

A separate source-binding step creates `F4MemoryProposal`:

```text
F4MemoryProposal {
    source_event_id
    predicate
    value
    explicit_correction
}
```

This boundary makes provenance explicit: the same semantic candidate is not yet a memory proposal until it is bound to one canonical source event.

## Proposal is not admission

`F4MemoryProposal` remains non-authoritative. It does not itself create an EvidenceItem, Claim, memory scope, or current PersonModel state.

Admission occurs only through the governed F4 memory-admission transaction. That transaction revalidates the relationship, source event, counterpart actor, predicate, value, and statement support before atomically writing:

```text
EvidenceItem(origin=COUNTERPART_STATEMENT)
+
Claim(domain=PERSON, kind=FACTUAL)
+
ClaimEvidence(SUPPORTS)
```

The claim remains scoped to the existing relationship.

This checkpoint deliberately leaves the older lower-level claim-admission primitive available to existing foundation tests and internal callers. The natural first-party memory path is the bounded path defined here; it does not imply that arbitrary callers or model output may create memory directly.

## Concurrent admission fencing

The F4 predicate is singleton and relationship-scoped. Two different source events must not race from the same prior current state and both become unsuperseded current claims.

Every proposal that may write therefore crosses a relationship-scoped database write fence before current claim state is treated as authoritative for admission:

```text
proposal
↓
acquire relationship write fence
↓
recheck exact-source replay
↓
resolve current claim inside same transaction
↓
validate correction/current-state transition
↓
write Evidence + Claim + optional supersession
↓
commit
```

For the current relational F4 implementation, the durable relationship Timeline-head row is updated to its existing value solely to obtain the database write/row lock. Its sequence value is not advanced, and this fence is not a Timeline event or semantic relationship revision.

The consequence is important:

```text
concurrent proposal A + proposal B
≠ two current claims
```

One transaction establishes the current state first. A waiting transaction must then re-resolve that committed state and either remain unchanged, create an explicit correction, or fail closed.

## Admission ordering and interaction routing

Memory admission occurs only after trusted input persistence:

```text
COUNTERPART_INPUT committed
↓
interaction-purpose classification
↓
MEMORY_STATEMENT
↓
extracted candidate
↓
memory proposal
↓
Claim/Evidence admission
```

For a pure bounded `MEMORY_STATEMENT`, that is a complete successful interaction. The runtime does not create a ContextProjection or invoke a model merely because memory was admitted.

This preserves:

```text
current context ≠ durable memory
memory proposal ≠ memory admission
memory admission ≠ response obligation
```

When a later supported world question needs the personal fact, retrieval happens from admitted memory into that later cognition path:

```text
later WORLD_QUESTION
↓
recover current admitted memory
↓
fresh world Investigation
↓
ContextProjection
↓
model invocation
```

The remembered fact is therefore usable only because the durable Claim/Evidence transaction committed earlier; it is not carried forward by transcript convention.

## Correction and supersession

A different value does not silently replace current memory.

If a current claim exists with another value, the new statement must carry an explicit correction signal. The admitted correction creates a new immutable claim and an append-only supersession edge:

```text
C1: primary_machine.memory_gb = 16
↓
explicit counterpart correction
↓
C2: primary_machine.memory_gb = 32
↓
ClaimSupersession(C2 CORRECTS C1)
```

Historical evidence and C1 remain recoverable. Future current-memory projection resolves C2 because C1 is explicitly superseded.

A different-value assertion without explicit correction fails closed rather than guessing whether it represents a correction, upgrade, temporal change, or contradiction.

The F4 slice does not yet implement a separate `TEMPORALLY_SUCCEEDS` natural-language path for hardware upgrades. That distinction remains available in the architecture but is intentionally outside this bounded checkpoint.

## Repetition and replay

Two different repetition cases are distinct.

### Exact transport/source replay

If the same canonical source InteractionEvent is processed again after process loss, the memory admission service recovers the claim already supported by that event. It does not create another claim or another EvidenceItem.

A write-capable worker also rechecks exact-source admission after acquiring the relationship fence, so two concurrent processors of the same source event cannot duplicate the admitted state.

Under the high-level interaction-purpose gate, replaying the same memory-only transport event also remains provider-free: no fresh-world acquisition, model invocation, or CompanionOutput is introduced just because the process restarted.

### New statement with unchanged value

If a new counterpart input states the same current value, the service returns `UNCHANGED`. The Timeline retains the new statement, while no second current claim is created merely because the fact was repeated.

This preserves:

```text
repeated statement ≠ new fact
transport replay ≠ new memory admission
```

## Recovery

The memory path is restart-safe at both durable boundaries:

```text
input committed
↓
process loss
↓
replay same source event
↓
candidate / proposal / admission can still occur
```

and:

```text
claim admitted
↓
process loss before caller observes result
↓
replay same source event
↓
existing admitted claim recovered
```

No transcript reconstruction or model inference is required.

The recovered memory can then be used by a different later interaction after complete surface/runtime recomposition because retrieval follows the durable Claim/Evidence graph rather than process-local conversational state.

## First-party F4 behavior

The first-party path now branches after canonical input admission:

```text
browser / host input
↓
trusted ingress
↓
canonical COUNTERPART_INPUT
↓
F4InteractionPurposeGate
├── MEMORY_STATEMENT
│   ↓
│   F4CounterpartMemoryAdmission
│   ↓
│   durable Claim/Evidence state
│   ↓
│   no CompanionOutput required
│
└── WORLD_QUESTION
    ↓
    recover admitted personal memory
    ↓
    configured reactive runtime
    ↓
    fresh world evidence + WorldResult
    ↓
    ContextProjection / model generation
    ↓
    CompanionOutput / presentation acceptance
    ↓
    presented Timeline event
```

The local browser may show deterministic operational status such as `Memory updated` after the memory-only path. That status is not CompanionPerson speech, is not a CompanionOutput, and does not become a presented Timeline event.

The current F4 contract remains intentionally fixed and narrow. General conversational routing, general-purpose memory extraction, memory forgetting UI, temporal upgrade interpretation, and model-proposed memory are not introduced by this checkpoint.

## Acceptance contract

The executable suite must prove at least:

1. an explicit primary-machine RAM statement produces one bounded extracted candidate;
2. the candidate is a distinct object from the source-bound memory proposal;
3. questions and unrelated `GB` statements produce no candidate;
4. declared bounded correction forms, including `Instead, ...`, produce explicit-correction candidates;
5. one source event creates one evidence-grounded admitted claim;
6. replaying the same source event does not duplicate Claim or EvidenceItem state;
7. two concurrent different initial proposals cannot create two current claims;
8. an explicit correction creates a new claim and `CORRECTS` edge;
9. a different value without explicit correction fails closed;
10. a repeated same value leaves one current claim;
11. current-memory retrieval resolves the corrected claim rather than the historical one;
12. a pure memory statement completes without Investigation, ModelInvocation, CompanionOutput, or presented Timeline output;
13. replaying the same memory-only transport event remains idempotent and performs no provider work; and
14. after complete surface/runtime recomposition, a later supported world question retrieves the admitted memory into its ContextProjection and checked response path.

## Scope boundary

This checkpoint does not implement:

- general autobiographical memory;
- model-selected memory predicates;
- inferred personality traits;
- relationship-experience inference;
- temporal hardware-upgrade classification;
- memory forgetting or suppression UI;
- cross-relationship memory scope;
- general conversational intent routing;
- mixed memory-and-question utterances;
- external Actions;
- delegated background work; or
- proactive monitoring.

The checkpoint exists to make one statement-to-memory path mechanically honest before the implementation widens beyond F4.
