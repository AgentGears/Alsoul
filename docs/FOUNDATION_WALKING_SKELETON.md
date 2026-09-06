# Alsoul Foundation Walking Skeleton

**Status:** F4 target contract  
**Publication:** GitHub-safe

The first vertical slice is intentionally narrow. It exists to prove the architecture boundaries that make Alsoul one persistent companion with honest memory, fresh world access, and attributable cognition/output.

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

## 5. Current input

The new counterpart question enters canonical history before cognition.

```text
InteractionEvent I3
    relationship = R1
    actor = U1
    kind = COUNTERPART_INPUT
    content = current compatibility question
```

The model must not receive the current input solely through an untracked provider request path.

## 6. Fresh-world path

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
    investigation = Q1
    actual external acquisition succeeds
```

Every Observation belongs to exactly one Investigation. If search discovery is followed by opening an authoritative source, these are separate Observations, and each is explicitly bound to Q1.

### Source capture

```text
WorldSourceCapture S1
    observation = O1
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

For W1 to qualify as a current checked result, its supporting evidence must trace:

```text
W1
→ E2
→ S1
→ O1
→ Q1
```

and `O1.investigation_id` must equal `W1.investigation_id`. Evidence captured by an older or different Investigation cannot be reused to make Q1 appear to have checked the world now.

Q1 is successful only once a sufficient evidence-backed result exists.

## 7. ContextProjection

The recovered personal claim, current input, and current world result remain distinct inside one immutable invocation-scoped projection.

Conceptually:

```text
ContextProjection CP1 {
    companion_person_id = P1
    relationship_id = R1
    current_input_event_id = I3

    source_self_revision = current Self revision
    source_relationship_revision = current R1 revision
    source_timeline_frontier = current R1 timeline frontier

    selected_event_refs = [I3]

    personal_context_items = [
        C1 {
            epistemic_basis = COUNTERPART_STATED_MEMORY
            support = E1
        }
    ]

    world_context_items = [
        W1 {
            epistemic_mode = CURRENT_CHECKED
            investigation = Q1
            support = E2
        }
    ]
}
```

The Timeline frontier records what canonical history existed when the projection was built. `selected_event_refs` records what historical interaction cognition actually saw.

```text
not projected
≠ forgotten
≠ deleted
≠ false
```

The provider-facing representation may be prose or another provider-specific encoding, but the runtime must retain the canonical source references and pinned revisions that produced it.

Provider rendering must not silently re-read newer Self/Relationship heads or replace exact claim/world refs after CP1 is created.

## 8. Model invocation and output lineage

One model invocation binds exactly one ContextProjection:

```text
ModelInvocation MI1
    context_projection_id = CP1
```

The model returns candidate content:

```text
GeneratedOutput G1
    model_invocation_id = MI1
```

At this point:

```text
model generated G1
```

is true, but:

```text
Alsoul presented G1 to U1
```

is not yet established.

After output validation/adoption:

```text
CompanionOutput CO1
    source_generated_output_id = G1
    output_origin = RESPONSE_TO_EVENT / I3
    output_target = I3 / FINAL_RESPONSE
```

CO1 is Alsoul's intended response, but shared history still begins only at presentation.

For the first-party non-streaming text slice, presentation commits:

```text
InteractionEvent I4
    relationship = R1
    actor = P1
    kind = COMPANION_PRESENTED_OUTPUT
    companion_output_id = CO1
    reply_to_event_id = I3
```

The complete output lineage is:

```text
I4
↓
CO1
↓
G1
↓
MI1
↓
CP1
├── C1 → E1 → I1
└── W1 → E2 → S1 → O1 → Q1
```

## 9. Required user-facing epistemic distinction

The architecture must be capable of supporting an answer with three distinct meanings:

```text
"You told me your machine has 16 GB RAM."
    ← admitted durable personal claim grounded in counterpart evidence

"I checked the current requirements; this configuration needs 24 GB."
    ← current Investigation + actual Observation + recoverable world evidence

"My take is that this configuration is not a good fit for your current machine."
    ← current cognition over personal and world state
```

The exact wording is not the contract. The underlying distinctions are.

The final response must also be attributable as:

```text
generated by a specific ModelInvocation
adopted as one CompanionOutput
presented as one canonical Timeline event
```

## 10. Retry and crash behavior

The foundation response path must not duplicate social history.

```text
provider/model retry
→ new ModelInvocation as needed

same semantic final response target
→ at most one adopted CompanionOutput

presentation retry of CO1
→ same presented Timeline event
```

If the process dies:

```text
after G1 but before CO1
→ G1 remains generated-but-unadopted

after CO1 but before I4
→ recover CO1 and present it idempotently

after I4
→ do not present CO1 again
```

## 11. Required failure behavior

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

Observation evidence traces to a different Investigation than the WorldResult
→ do not classify the result as a current checked result

Observation succeeded but no supported WorldResult exists
→ do not claim a checked conclusion

historical WorldResult recovered without a fresh acquisition
→ do not relabel it as a current check

unresolved material contradiction
→ do not present the claim/result as settled truth

ContextProjection cannot resolve mandatory pinned state
→ do not silently substitute provider transcript/summary prose

GeneratedOutput exists but adoption fails
→ do not append a presented companion event

CompanionOutput exists but presentation has not committed
→ do not claim Alsoul already presented it
```

## 12. Deliberate exclusions

The foundation walking skeleton does not require:

```text
broad autonomous memory extraction
personality or psychological graph
RelationshipExperience engine
global WorldModel
multi-agent orchestration
effectful external Actions
background delegated work
proactive WorldSignal/Trigger processing
rich embodiment
voice interruption reconciliation
generalized source ranking
numeric confidence/freshness scoring
full forgetting subsystem
multi-channel delivery
```

The architecture defines several of these boundaries for future work, but they are not implementation requirements for F4.

## 13. Acceptance summary

The slice succeeds when the system proves all of the following in one coherent path:

```text
same CompanionPerson after restart
same CounterpartPerson after restart
same RelationshipState after restart
canonical history survives context loss
durable memory survives process death with recoverable evidence
PersonModel can be rebuilt rather than restored as opaque profile text
current counterpart input enters canonical history before cognition
fresh world information is actually acquired
every Observation is bound to its Investigation
WorldResult support traces to Observations from that same Investigation
what was checked is durably captured
WorldResult is evidence-backed
ContextProjection pins exact Self/Relationship revisions and source refs
Timeline frontier and actually selected events remain distinct
epistemic provenance survives into ContextProjection
one ModelInvocation binds the exact projection it saw
GeneratedOutput is not automatically CompanionOutput
CompanionOutput is not automatically presented history
presentation creates one idempotent COMPANION_PRESENTED_OUTPUT event
model/provider replacement does not redefine personhood
memory, checked world information, interpretation, generation, adoption, and presentation remain distinct
```

That is the minimum foundation for a companion with a world rather than a chatbot whose apparent continuity depends on one prompt or thread.
