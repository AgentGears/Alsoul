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
    └── WORLD_QUESTION
        ↓
        world acquisition / model generation
        ↓
        CompanionOutput
        ↓
        local first-party presentation acceptance
        ↓
        COMPANION_PRESENTED_OUTPUT
        ↓
        browser renders accepted content
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
surface notice ≠ presented Timeline event
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

The surface consumes the existing host configuration for the canonical database plus configured world/model runtime routes. Model authorization remains environment-only runtime-secret state.

The surface replaces only the first-party presentation transport with an in-process durable local sink while preserving the existing presentation-acceptance contract. It does not bypass CompanionOutput adoption or Timeline presentation.

## Trusted identity and route

The local process receives the intended counterpart identity and presence route from operator arguments:

```text
identity_namespace
external_subject
surface_namespace / surface_ref
channel_namespace / channel_ref
```

Those values are not inferred from browser content. Every interaction passes through `FirstPartyIngress`, which resolves only pre-existing bindings.

After ingress, `ConfiguredFoundationRuntime.interact` fences purpose classification to the exact admitted relationship, surface binding, and channel binding. A canonical event cannot be paired with a different route merely because a caller supplies different IDs.

```text
external subject assertion ≠ CounterpartPerson creation
route configuration ≠ presence creation
canonical input on route A ≠ valid continuation on route B
```

If identity or route resolution fails, interaction fails closed.

## Bounded interaction-purpose behavior

The browser does not classify intent. The semantic runtime does so from the already-canonical input through `F4InteractionPurposeGate`.

For the bounded memory form:

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

No Investigation, WorldResult, ContextProjection, ModelInvocation, GeneratedOutput, CompanionOutput, or `COMPANION_PRESENTED_OUTPUT` is created solely because the memory was admitted.

The browser may display deterministic operational status such as:

```text
Memory updated
Memory corrected
Memory already current
```

That status is surface UI, not Alsoul speech. It is rendered as status rather than as an Alsoul message bubble.

For the bounded checked question:

```text
Would the current software run on my machine?
```

the existing checked-response chain executes and can recover previously admitted memory.

Unsupported or mixed interactions fail closed at the high-level F4 purpose gate after trusted ingress has preserved the canonical input. They are not sent to a model to guess a route.

## Surface session request fencing

At process start the surface generates an ephemeral high-entropy session token. The token is embedded only in the served first-party page and is required on interaction requests through `X-Alsoul-Surface-Token`.

This is local request fencing, not counterpart identity authority.

The browser API accepts only:

```text
content_text
transport_event_id?
```

The browser response exposes surface-level content/status, bounded purpose, and transport replay state rather than internal Person, Relationship, evidence, memory, or cognition identifiers.

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

For a memory-only replay, the same input and admitted memory are recovered without provider work. For a checked response replay, the existing runtime recovery rules continue from the furthest trustworthy durable stage.

## Presentation acceptance across restart

For checked responses, the local presentation sink persists acceptance under the same restart-stable presentation key derived from exact CompanionOutput and surface/channel route.

Exact replay returns the existing acceptance receipt; semantic key reuse with different content is rejected. The runtime commits `COMPANION_PRESENTED_OUTPUT` only after a valid acceptance receipt.

Memory-only interactions do not cross this boundary because they create no CompanionOutput.

## Complete surface/runtime recomposition

The acceptance suite proves two complementary paths.

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

Completed checked-response replay still preserves the same input event, CompanionOutput, and presented Timeline event without duplicate acquisition, generation, or local presentation acceptance.

## Browser UI

The dependency-free page:

- renders user messages and actual CompanionOutput text;
- keeps memory-only operational acknowledgement in surface status rather than a companion message bubble;
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
7. establish the bounded F4 personal memory naturally through a supported memory statement
8. ask the supported current-world question when needed
```

No manual pre-seeding of the F4 memory claim is required for the natural local path.

## Deliberate exclusions

This checkpoint does not add:

- public network access;
- remote user authentication;
- multi-user or multi-relationship surface routing;
- automatic identity bootstrap or schema migration;
- model-based identity or purpose selection;
- general conversational routing;
- mixed memory-and-question utterances;
- general-purpose memory admission;
- read/heard/understood receipts;
- multi-channel fallback;
- voice or rich embodiment;
- external Actions;
- delegated work; or
- schedules/proactivity.

The purpose remains narrow: expose the bounded F4 interaction through a real local surface without turning the surface into a second identity, routing, cognition, memory, or persistence authority.
