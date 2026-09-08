# F4 Exit Audit

**Status:** PASSED — executable F4 checkpoint closed  
**Publication:** GitHub-safe  
**Audit anchor:** `main` at `9c4fd24cd672673fbca053060bddff81f710c86d`  
**Verification anchor:** Foundation CI run #132 — success

This audit records whether the executable F4 walking skeleton has enough evidence to close the checkpoint without widening it into later authority, task, proactivity, modality, or personal-world work.

## Exit bar

F4 is considered complete when the implemented first-party path can support the user-facing distinction:

> My companion looked this up for me rather than merely generating an answer.

The implementation must preserve continuity, source truth, and output/presentation provenance while remaining intentionally narrow.

## Evidence

### 1. One continuous companion survives runtime death and recomposition — PASS

`tests/test_f4_walking_skeleton.py` destroys the original service/runtime object, reconstructs from the same durable store, resolves the same `CompanionPerson`, `CounterpartPerson`, and `RelationshipState`, continues in a later thread, and completes the response through presentation.

`tests/test_local_surface.py` repeats the stronger first-party surface boundary: after complete application recomposition, replay of the same transport event returns the same canonical input, CompanionOutput, presented Timeline event, Person, and Relationship without repeating world acquisition or model generation.

### 2. Remembered personal context is evidence-grounded and revisable — PASS

`tests/test_memory_admission.py` verifies that the bounded F4 memory path admits only the supported explicit counterpart statement, creates one Claim plus supporting EvidenceItem, replays the same source idempotently, requires an explicit correction signal for a changed value, and represents correction through append-only supersession rather than overwrite.

`tests/test_f4_walking_skeleton.py` verifies that the remembered claim used for cognition remains traceable through Claim → ClaimEvidence → EvidenceItem → canonical source InteractionEvent.

### 3. Fresh-world claims require real acquisition before checked language — PASS

`tests/test_configured_runtime.py` exercises the configured reactive path through an actual world transport call, Observation, WorldSourceCapture, EvidenceItem, WorldResult, ContextProjection, model generation, adoption, and first-party presentation.

The accepted response distinguishes:

```text
REMEMBERED_COUNTERPART_STATEMENT
CURRENT_CHECKED_WORLD
COMPANION_INTERPRETATION
```

and renders the corresponding user-facing forms `You told me...`, `I checked...`, and `My take...`.

The same suite rejects unsuitable acquired material before WorldResult admission and produces no presentation from that failed path. Checked language therefore depends on admitted current-world provenance rather than model assertion alone.

### 4. Fresh findings and remembered context are selected independently — PASS

`ContextProjection` pins the exact personal Claim and WorldResult used for one cognition attempt. `tests/test_f4_walking_skeleton.py` verifies both projection lineages and their epistemic classifications:

```text
personal → COUNTERPART_STATED_MEMORY
world    → CURRENT_CHECKED
```

The provider receives a rendering of that immutable projection rather than authority to search memory or world state itself.

### 5. Personal interpretation remains separate from evidence-backed propositions — PASS

The response contract carries companion interpretation as a distinct semantic segment with no fabricated evidence source. The acceptance path can therefore combine a remembered machine fact and a freshly checked software requirement into a personal conclusion without relabeling interpretation as memory or observation.

### 6. The user sees a bounded investigation transition without fabricated Companion speech — PASS

The local first-party surface enters a neutral operational `Working…` state while an interaction is in flight. That state is surface UI, not a `CompanionOutput`, and therefore does not create canonical shared speech or claim that world acquisition has occurred before the host has actually performed it.

For a successful world question, the eventual presented CompanionOutput may say `I checked...` only after the acquisition/result path has completed.

### 7. No worker/tool persona replaces Alsoul — PASS

World and model adapters remain implementation boundaries. The canonical presented result is adopted as one `CompanionOutput` owned by the same CompanionPerson and then admitted to the shared Timeline only after presentation acceptance. Provider binding, model identity, transport credentials, and acquisition mechanics do not become a visible second persona.

### 8. Generated, adopted, and presented output remain distinct — PASS

The walking-skeleton acceptance chain preserves:

```text
ContextProjection
↓
ModelInvocation
↓
GeneratedOutput
↓
CompanionOutput
↓
presentation acceptance
↓
COMPANION_PRESENTED_OUTPUT
```

Recovery derives the furthest trustworthy durable stage and does not treat generated content as shared history before presentation.

### 9. Bounded conversational continuity does not broaden F4 authority — PASS

The current F4 implementation additionally supports self-contained conversational response, exact immediate-prior Timeline context, and relationship-scoped `DECISION` ConversationOpenLoops with deterministic source references and explicit counterpart-authored aliases.

Those additions preserve the same boundary:

```text
ConversationOpenLoop
≠ MemoryClaim
≠ DelegatedTask
≠ Commitment
≠ Trigger
```

No open conversational matter grants background-work or proactive-contact authority.

## Closure decision

The executable evidence is sufficient to close F4.

F4 has demonstrated the intended foundation behavior:

```text
persistent Person / Relationship
+
canonical shared history
+
evidence-grounded selective memory
+
real fresh-world acquisition
+
explicit epistemic separation
+
immutable cognition provenance
+
adoption and presentation truth
+
restart/recomposition continuity
+
bounded conversational continuity
```

Further expansion of memory breadth, open-loop semantics, transcript retrieval, or conversational grammar is not required to keep F4 open.

## Boundary after F4

The following remain intentionally outside the closed F4 checkpoint:

- personal digital-world connectors such as calendar, files, messages, contacts, and device state;
- explicit capability/resource/permission/approval enforcement for those resources;
- effectful external Actions and ExecutionAttempt/Effect reconciliation;
- durable delegated Tasks, Commitments, Procedures, Triggers, and WorkRuns;
- proactive WorldSignal-driven behavior;
- rich modality, streaming reception truth, and embodiment;
- AffectState and broader presentation-policy implementation;
- semantic history search, semantic open-loop matching, and generic model-selected retrieval.

The next executable gate is therefore **F5 — Personal World + Trust**, beginning with read/observe semantics before write/act semantics.
