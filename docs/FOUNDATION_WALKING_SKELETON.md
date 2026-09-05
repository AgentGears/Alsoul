# Alsoul Foundation Walking Skeleton

**Status:** F4 target contract  
**Publication:** GitHub-safe

The first vertical slice is intentionally narrow. It exists to prove the architecture boundaries that make Alsoul one persistent companion with honest memory and fresh world access.

## 1. Scenario

The foundation test uses one durable companion person, one durable counterpart, and one durable relationship.

```text
CompanionPerson P1
    SelfModel:
        role = PERSONAL_COMPANION
        preferred_name = "Alsoul"

CounterpartPerson U1

RelationshipState R1
    companion = P1
    counterpart = U1
```

U1 provides one factual piece of personal context that is worth carrying forward, for example:

```text
"My machine has 16 GB RAM."
```

Alsoul later receives a question whose answer requires current external information, for example whether a current software/model configuration is suitable for that machine.

## 2. Personal-memory path

### Historical input

```text
InteractionEvent I1
    relationship = R1
    actor = U1
    kind = COUNTERPART_INPUT
    content = "My machine has 16 GB RAM."
```

### Evidence

```text
EvidenceItem E1
    origin = COUNTERPART_STATEMENT
    source = I1
    actor = U1
```

### Durable claim

```text
Claim C1
    holder = P1
    memory_scope = RELATIONSHIP(R1)
    domain = PERSON
    subject = U1
    kind = FACTUAL
    predicate = primary_machine.memory_gb
    value = 16
```

with:

```text
E1 SUPPORTS C1
```

The same physical proposition satisfies both foundation semantics:

```text
MemoryClaim
    durable admitted recall

PersonClaim
    proposition about U1 used by PersonModel
```

## 3. Complete runtime death

Destroy all replaceable runtime state:

```text
model process
provider session/thread context
PersonModelView
ContextProjection
retrieval caches/indexes
in-memory objects
```

Do not preserve continuity by retaining a live cognition process.

## 4. Recovery

Before the next model call, recover and validate:

```text
P1
SelfModel current revision
U1
R1 current revision
canonical Timeline access
C1
E1
E1 → I1 source resolution
SUPPORTS(E1,C1)
```

Then rebuild:

```text
PersonModelView(P1 → U1)
    current_claim_refs = [C1]
```

The model/provider that serves the recovered turn may differ from the one that served the original interaction.

## 5. Fresh-world path

The new question has a current/freshness requirement.

Foundation policy is deterministic:

```text
current volatile external question
→ perform a new Investigation now
```

### Investigation

```text
Investigation Q1
    objective = determine the current external requirement relevant to the question
```

### Acquisition

```text
Observation O1
    actual external acquisition succeeds
```

If search discovery is followed by opening an authoritative source, these are separate Observations.

### Source capture

```text
WorldSourceCapture S1
    exact acquired source material
    capture time
    source identity
    content digest
```

### World evidence

```text
EvidenceItem E2
    origin = SEARCH_RESULT
    source = S1 / relevant locator
```

### World result

```text
WorldResult W1
    investigation = Q1
    kind = FACTUAL
    predicate = target.minimum_memory_gb
    value = 24
```

with:

```text
E2 SUPPORTS W1
```

Q1 is successful only once a sufficient evidence-backed result exists.

## 6. Context projection

The recovered personal claim and current world result remain distinct inside the turn projection.

Conceptually:

```text
ContextProjection

PERSONAL_MEMORY
    claim_ref = C1
    epistemic basis = counterpart statement

CURRENT_CHECKED_WORLD
    world_result_ref = W1
    investigation_ref = Q1
    evidence_ref = E2

INTERPRETATION
    produced by current cognition
```

The provider-facing representation may be prose, but the runtime must retain the canonical source references that produced it.

## 7. Required user-facing epistemic distinction

The architecture must be capable of supporting an answer with three distinct meanings:

```text
"You told me your machine has 16 GB RAM."
    ← admitted durable personal claim grounded in counterpart evidence

"I checked the current requirements; this configuration needs 24 GB."
    ← current Investigation + actual Observation + recoverable world evidence

"My take is that this configuration is not a good fit for your current machine."
    ← current interpretation over personal and world state
```

The exact wording is not the contract. The underlying distinctions are.

## 8. Required failure behavior

The slice must fail honestly.

```text
missing canonical Self
→ cognition as P1 does not proceed

missing expected RelationshipState
→ do not silently create a replacement relationship

MemoryClaim exists but evidence/source is unrecoverable
→ do not use it as fully evidence-grounded remembered fact

Investigation started but no Observation succeeded
→ do not say "I checked"

Observation succeeded but no supported WorldResult exists
→ do not claim a checked conclusion

historical WorldResult recovered without a fresh acquisition
→ do not relabel it as a current check

unresolved material contradiction
→ do not present the claim/result as settled truth
```

## 9. Deliberate exclusions

The foundation walking skeleton does not require:

```text
broad autonomous memory extraction
personality or psychological graph
RelationshipExperience engine
global WorldModel
multi-agent orchestration
background delegated work
rich embodiment
voice interruption reconciliation
generalized source ranking
numeric confidence/freshness scoring
full forgetting subsystem
```

Those may be introduced only when a concrete product requirement forces them.

## 10. Acceptance summary

The slice succeeds when the system proves all of the following in one coherent path:

```text
same CompanionPerson after restart
same CounterpartPerson after restart
same RelationshipState after restart
canonical history survives context loss
durable memory survives process death with recoverable evidence
PersonModel can be rebuilt rather than restored as opaque profile text
fresh world information is actually acquired
what was checked is durably captured
WorldResult is evidence-backed
epistemic provenance survives into ContextProjection
model/provider replacement does not redefine personhood
memory, checked world information, and interpretation remain distinct
```

That is the minimum foundation for a companion with a world rather than a chatbot whose apparent continuity depends on one prompt or thread.
