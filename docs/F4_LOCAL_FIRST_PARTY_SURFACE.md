# F4 Local First-Party Surface

**Status:** Implemented foundation checkpoint

The reactive F4 slice now has a minimal local first-party web surface. It provides an actual user-facing interaction boundary while preserving the existing separation between presence, trusted identity resolution, canonical runtime state, cognition, and presentation acceptance.

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
ConfiguredFoundationRuntime
    ↓
world acquisition / model generation
    ↓
CompanionOutput
    ↓
local first-party presentation acceptance
    ↓
COMPANION_PRESENTED_OUTPUT
    ↓
local browser renders accepted content
```

Permanent distinctions:

```text
Surface ≠ CompanionPerson
Surface ≠ CounterpartPerson identity authority
Surface ≠ RelationshipState
Surface ≠ cognition
Surface ≠ canonical persistence authority
surface operational state ≠ canonical companion state
browser request ≠ identity inference
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

The process binds only to:

```text
127.0.0.1
```

It refuses non-loopback bind addresses. The default browser URL is therefore:

```text
http://127.0.0.1:8765/
```

The local HTTP listener is a first-party process boundary, not a public network API. Public authentication, remote access, reverse-proxy deployment, and multi-user hosting remain outside F4.

## Existing host configuration

The local surface consumes the existing host configuration for:

```text
database path
world route
model route
runtime timeouts
```

Model authorization continues to come only from the process environment through the existing runtime-secret boundary.

The local surface replaces only the first-party presentation transport with an in-process durable local sink while preserving the same `JsonFirstPartyPresentationAdapter` acceptance contract. It does not bypass CompanionOutput adoption or Timeline presentation.

## Trusted identity

The local process receives the intended counterpart identity and presence route from operator arguments:

```text
identity_namespace
external_subject
surface_namespace / surface_ref
channel_namespace / channel_ref
```

Those values are not inferred from browser content. Every interaction still passes through `FirstPartyIngress`, which resolves only pre-existing bindings.

Therefore:

```text
configured external subject
    ≠ automatically created CounterpartPerson

configured surface/channel refs
    ≠ automatically created presence bindings
```

If the configured identity or route does not exist, interaction fails closed.

## Surface session request fencing

At process start the local surface generates an ephemeral high-entropy session token. The token is embedded only in the served first-party page and is required on interaction requests through:

```text
X-Alsoul-Surface-Token
```

This is local request fencing, not counterpart identity authority. The durable counterpart identity remains the existing `CounterpartIdentityBinding` selected by the operator configuration.

The browser API accepts only:

```text
content_text
transport_event_id?
```

The browser response exposes only surface-level response content and transport replay state rather than internal Person, Relationship, claim, evidence, or cognition identifiers.

## Durable local operational state

The surface uses a separate SQLite file supplied by `--state`.

This file is deliberately not part of the canonical Alsoul schema. It contains two operational concerns only:

```text
inbound transport replay identity
first-party presentation acceptance
```

It may contain local input/output text because exact replay and exact presentation acceptance must be checked semantically. It therefore belongs with local user data and should be protected accordingly.

Canonical distinctions remain:

```text
local surface state
    ≠ Timeline
    ≠ EvidenceItem
    ≠ MemoryClaim
    ≠ PersonClaim
    ≠ WorldResult
    ≠ CompanionOutput authority
```

Deleting the local surface state does not delete canonical Timeline or companion identity, although it can remove local transport/presentation replay knowledge needed for the strongest restart-idempotency guarantees of that surface.

## Input replay across process restart

A browser interaction has one `transport_event_id`. Before semantic ingress, the local surface durably reserves the exact transport semantics:

```text
transport_event_id
identity / route assertion
content
conversation binding
occurred_at
```

If the same transport ID is retried after process restart, the surface reuses the original `occurred_at` instead of generating a new one. That allows the existing ingress idempotency contract to see an exact semantic replay.

If the same transport ID is reused with different content, identity, route, or conversation semantics, the local surface rejects it before canonical ingress.

Therefore:

```text
same transport_event_id + same request
    → same canonical COUNTERPART_INPUT

same transport_event_id + different request
    → conflict
```

## Presentation acceptance across process restart

The local presentation sink persists acceptance under the same restart-stable presentation key already used by the runtime:

```text
CompanionOutput
+ SurfaceBinding
+ ChannelBinding
    ↓
presentation key
```

On first acceptance the local sink stores:

```text
presentation key
CompanionOutput identity
surface/channel route
exact content
content digest
acceptance receipt
acceptance time
```

An exact replay returns the existing acceptance receipt. Reusing the key with different semantic content is rejected.

The runtime still commits `COMPANION_PRESENTED_OUTPUT` only after the local sink returns a valid acceptance receipt.

## Complete surface-process recomposition

The acceptance suite proves this sequence:

```text
existing F4 Person / counterpart / relationship / memory
↓
start local surface application
↓
admit current input
↓
perform world acquisition
↓
perform model generation
↓
adopt CompanionOutput
↓
local sink accepts exact output
↓
commit presented Timeline event
↓
close entire surface/runtime composition
↓
construct a new surface/runtime composition
↓
replay exact transport_event_id
↓
same input event
same Person
same counterpart
same RelationshipState
same CompanionOutput
same presented Timeline event
no second world acquisition
no second model generation
one local presentation acceptance
```

This makes browser/surface process replacement a presence/runtime event rather than a Person or Relationship replacement.

## Browser UI

The page is intentionally small and dependency-free. It:

- renders a text conversation surface;
- generates a transport event ID for each submitted message;
- sends only to the same loopback process;
- includes no external assets or remote script dependencies;
- renders returned content using text nodes rather than HTML injection;
- exposes a small local health endpoint;
- suppresses request logging by default;
- sends restrictive browser security headers.

The UI does not directly write the canonical database. All semantic writes still occur through existing ingress/runtime services.

## First-run sequence

The local surface starts only after explicit administration:

```text
1. alsoul-admin initialize-store ...
2. alsoul-admin bootstrap-foundation ...
3. create host configuration
4. establish the narrow F4 personal-memory prerequisite through the existing semantic path
5. alsoul-host --config ./host.json ready
6. alsoul-surface --config ./host.json --state ./surface-state.db ...
7. open the printed loopback URL
```

The current F4 response coordinator still requires the walking-skeleton personal-memory predicate used by the foundation acceptance scenario. Natural-language memory extraction/admission from arbitrary new conversation is not added by this surface checkpoint.

## Deliberate exclusions

This checkpoint does not add:

- public network access;
- remote user authentication;
- multi-user or multi-relationship surface routing;
- automatic identity bootstrap;
- schema migration during surface startup;
- model-based identity matching;
- general natural-language memory admission;
- read/heard/understood receipts;
- multi-channel fallback;
- voice or rich embodiment;
- external Actions;
- delegated work;
- schedules or proactivity.

The purpose is narrow: put a real local first-party interaction surface in front of the already-converged reactive F4 runtime while keeping one durable companion and relationship authoritative underneath surface and process replacement.
