# F4 Local First-Party Surface

**Status:** Implemented foundation checkpoint

The F4 slice has a minimal loopback first-party web surface. It provides an actual user-facing interaction boundary while preserving separation between presence, trusted identity resolution, canonical runtime state, interaction-purpose routing, cognition, and presentation acceptance.

## Core boundary

```text
local browser surface
    ↓
operator-configured local identity assertion
    ↓
FirstPartyIngress
    ↓
existing CounterpartIdentityBinding / RelationshipState
    ↓
COUNTERPART_INPUT
    ↓
ConfiguredFoundationRuntime.interact
    ↓
F4InteractionPurposeGate
    ├── MEMORY_STATEMENT
    │   ↓
    │   evidence-grounded memory admission
    │   ↓
    │   operational surface notice only
    │
    ├── CONVERSATIONAL_RESPONSE
    │   ↓
    │   source-free ContextProjection
    │   ↓
    │   model generation / conversational adoption
    │   ↓
    │   local first-party presentation acceptance
    │   ↓
    │   COMPANION_PRESENTED_OUTPUT
    │   ↓
    │   browser renders Companion expression
    │
    └── WORLD_QUESTION
        ↓
        fresh world acquisition / evidence-backed result
        ↓
        model generation / checked-response adoption
        ↓
        local first-party presentation acceptance
        ↓
        COMPANION_PRESENTED_OUTPUT
        ↓
        browser renders checked response
```

Permanent distinctions:

```text
Surface ≠ CompanionPerson
Surface ≠ CounterpartPerson identity authority
Surface ≠ RelationshipState
Surface ≠ interaction-purpose authority
Surface ≠ cognition
Surface ≠ canonical persistence authority
surface operational state ≠ canonical companion state
browser request ≠ identity inference
surface notice ≠ CompanionOutput
conversation ≠ fresh-world investigation
conversation ≠ memory admission
GeneratedOutput ≠ CompanionOutput
presentation sink acceptance ≠ read/heard/understood
surface startup ≠ schema initialization ≠ identity bootstrap
```

The surface does not create schema, CompanionPerson, CounterpartPerson, RelationshipState, SurfaceBinding, or ChannelBinding. Those must already exist through explicit administration.

## Process command

The installed package exposes:

```text
alsoul-surface
```

A typical invocation is:

```text
alsoul-surface \
  --config ./host.json \
  --state ./surface-state.db \
  --identity-namespace local.first_party \
  --external-subject user-1 \
  --port 8765
```

The process binds only to `127.0.0.1`. The local listener is a first-party process boundary, not a public network API. Public authentication, remote access, reverse-proxy deployment, and multi-user hosting remain outside F4.

## Existing host configuration

The surface consumes the existing host configuration for the canonical database plus configured world/model routes. Model authorization remains environment-only runtime-secret state.

The surface replaces only the configured first-party presentation transport with an in-process durable local sink while preserving the same presentation-acceptance contract. It does not bypass `GeneratedOutput → CompanionOutput → presentation` semantics.

## Trusted identity and route

The local process receives the intended counterpart identity and presence route from operator arguments:

```text
identity_namespace
external_subject
surface_namespace / surface_ref
channel_namespace / channel_ref
```

Those values are not inferred from browser content. Every interaction passes through `FirstPartyIngress`, which resolves only pre-existing bindings.

After ingress, `ConfiguredFoundationRuntime.interact` fences purpose classification to the exact admitted relationship, surface binding, and channel binding.

```text
external subject assertion ≠ CounterpartPerson creation
route configuration ≠ presence creation
canonical input on route A ≠ valid continuation on route B
```

If identity or route resolution fails, interaction fails closed.

## Bounded interaction-purpose behavior

The browser does not classify intent. The semantic runtime classifies the already-canonical input through `F4InteractionPurposeGate`.

### Memory statement

For a bounded memory form such as:

```text
My machine has 16 GB RAM.
```

the successful path is:

```text
COUNTERPART_INPUT
↓
MEMORY_STATEMENT
↓
F4MemoryCandidate
↓
F4MemoryProposal
↓
EvidenceItem + admitted Claim
↓
return
```

No Investigation, ContextProjection, ModelInvocation, GeneratedOutput, CompanionOutput, or `COMPANION_PRESENTED_OUTPUT` is created solely because the memory was admitted.

The browser may display deterministic operational status such as:

```text
Memory updated
Memory corrected
Memory already current
```

That status is surface UI, not Alsoul speech. It is rendered as status rather than as a Companion message bubble.

### Conversational response

For bounded self-contained social forms such as:

```text
Hello.
Thanks.
How are you?
Goodbye.
```

the runtime selects `CONVERSATIONAL_RESPONSE` and executes:

```text
COUNTERPART_INPUT
↓
source-free ContextProjection
    pinned Self revision
    pinned Relationship revision
    current input
    Timeline frontier
    no projected personal Claim
    no projected WorldResult
↓
ModelInvocation
↓
GeneratedOutput
    one COMPANION_EXPRESSION
    source_ref = null
↓
explicit conversational adoption
↓
CompanionOutput
↓
local presentation acceptance
↓
COMPANION_PRESENTED_OUTPUT
↓
browser message bubble
```

This path performs no fresh-world acquisition and no memory admission. The resulting source-free expression is Companion-owned wording; it does not claim remembered or checked provenance.

Contextual/deictic requests such as:

```text
Tell me what you think about this.
```

remain unsupported because the current F4 projection does not yet define a bounded prior-history selection policy for resolving `this`.

### Checked world question

For the bounded checked question:

```text
Would the current software run on my machine?
```

the existing checked-response chain executes, recovers eligible personal memory, acquires fresh world evidence, and maintains remembered/checked/interpretation distinctions.

Unsupported or mixed interactions fail closed at the high-level purpose gate after trusted ingress has preserved the canonical input. They are not sent to a model to guess a route.

## Surface session request fencing

At process start the surface generates an ephemeral high-entropy session token. The token is embedded only in the served first-party page and is required on interaction requests through `X-Alsoul-Surface-Token`.

This is local request fencing, not counterpart identity authority.

The browser API accepts only:

```text
content_text
transport_event_id?
```

The browser response exposes user-facing content/status, bounded purpose, and transport replay state rather than internal Person, Relationship, evidence, memory, or cognition identifiers.

## Durable local operational state

The surface uses a separate SQLite file supplied by `--state`. It is deliberately not part of the canonical Alsoul schema and owns only:

```text
inbound transport replay identity
first-party presentation acceptance
```

It may contain local input/output text because exact replay and exact presentation acceptance require semantic equality checks. It belongs with local user data and should be protected accordingly.

```text
local surface state
    ≠ Timeline
    ≠ EvidenceItem
    ≠ MemoryClaim
    ≠ PersonClaim
    ≠ WorldResult
    ≠ CompanionOutput authority
```

## Input replay across restart

Before semantic ingress, the surface durably reserves the exact transport occurrence, including identity/route assertion, content, conversation binding, and original occurrence time.

```text
same transport_event_id + same semantics
    → same canonical COUNTERPART_INPUT

same transport_event_id + different semantics
    → conflict
```

Memory replay recovers the same admitted Claim/Evidence without provider work. Conversational and checked-response replay resume from the furthest trustworthy canonical response stage rather than regenerating already-durable work.

## Presentation acceptance across restart

For any response-producing interaction, the local presentation sink persists acceptance under the restart-stable presentation key derived from exact `CompanionOutput` and surface/channel route.

Exact replay returns the existing acceptance receipt; semantic key reuse with different content is rejected. The runtime commits `COMPANION_PRESENTED_OUTPUT` only after a valid acceptance receipt.

Memory-only interactions do not cross this boundary because they create no `CompanionOutput`.

## Complete surface/runtime recomposition

The acceptance suite proves complementary paths.

Memory then checked question:

```text
start surface/runtime composition
↓
"My machine has 16 GB RAM."
↓
admit one durable memory
↓
no world/model/output/presentation work
↓
close entire composition
↓
construct new composition over same canonical + surface stores
↓
"Would the current software run on my machine?"
↓
recover same Person / counterpart / RelationshipState / memory
↓
perform fresh checked response
```

Conversational restart/replay:

```text
"Hello."
↓
CONVERSATIONAL_RESPONSE
↓
model generation / adoption / local presentation
↓
close complete surface/runtime composition
↓
construct new composition over same stores
↓
replay same transport occurrence
↓
same canonical input
same CompanionOutput
same presented Timeline event
no duplicate model dispatch
no duplicate logical presentation
```

Completed checked-response replay retains its existing stronger acquisition/generation/presentation idempotency guarantees.

## Browser UI

The dependency-free page:

- renders counterpart messages and actual `CompanionOutput` text;
- keeps memory-only operational acknowledgement in surface status rather than a Companion message bubble;
- renders conversational and checked responses only after canonical presentation succeeds;
- generates a transport-event ID for each submitted message;
- sends only to the same loopback process;
- includes no remote assets;
- renders returned strings as text rather than HTML;
- exposes a small health endpoint;
- suppresses request logging; and
- sends restrictive browser security headers.

The UI performs no direct canonical semantic writes.

## First-run sequence

The local surface starts only after explicit administration:

```text
1. alsoul-admin initialize-store ...
2. alsoul-admin bootstrap-foundation ...
3. create host configuration
4. alsoul-host --config ./host.json ready
5. alsoul-surface --config ./host.json --state ./surface-state.db ...
6. open the printed loopback URL
7. optionally establish the bounded F4 personal memory through a supported memory statement
8. use a bounded self-contained conversational form or the supported current-world question
```

No manual pre-seeding of the F4 memory claim is required for the natural local path.

## Deliberate exclusions

This checkpoint does not add public network access, remote user authentication, multi-user routing, automatic identity bootstrap, schema migration, model-based identity/purpose selection, general conversational routing, arbitrary small talk, deictic prior-turn resolution, mixed memory-and-question utterances, general-purpose memory admission, arbitrary fresh-world questions, read/heard/understood receipts, multi-channel fallback, voice/rich embodiment, external Actions, delegated work, or schedules/proactivity.

The purpose remains narrow: expose implemented F4 semantic paths through a real local surface without turning the browser or surface process into a second identity, routing, cognition, memory, epistemic, or persistence authority.
