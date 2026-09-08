# F5 Executable Checkpoint — Normative Addendum

**Status:** Normative amendment to the F5 executable checkpoint  
**Publication:** GitHub-safe  
**Applies to:** [F5 Executable Checkpoint — Personal World + Trust](F5_EXECUTABLE_CHECKPOINT.md)

This addendum is part of the F5 executable checkpoint contract. An implementation does not satisfy F5.A or F5.B unless it satisfies both the primary checkpoint and this addendum. Where this addendum is more specific, this addendum governs.

The addendum closes trust ambiguities that are material at the personal-world boundary:

```text
calendar-window endpoint instants ≠ calendar-window membership semantics
bounded personal-world read ≠ unbounded provider-query superset
Permission field match ≠ trusted Permission grant
Approval bound to Action ≠ Approval issued by an authorized approver
committed projection ≠ indefinitely fresh current-state context
provider mutation response ≠ durable effect evidence
```

# A. Canonical calendar-window membership and bounded acquisition

F5.A already requires one exact interval derived from trusted calendar timezone/rules metadata. The result contract additionally requires one provider-independent membership predicate and a bounded provider query that is complete for that predicate.

## Canonical interval

For a requested local calendar date `D`, after both trusted local-midnight boundaries have resolved to unique exact instants, define:

```text
window_start = exact instant for D 00:00
window_end   = exact instant for (D + 1 day) 00:00
window       = [window_start, window_end)
```

The interval is half-open: `window_start` is inclusive and `window_end` is exclusive.

## Timed-event membership

A normalized timed event occupies the half-open interval:

```text
event = [event_start, event_end)
```

A timed event belongs to the requested calendar-day result exactly when the intervals overlap:

```text
event_start < window_end
AND
event_end > window_start
```

Therefore:

- an event ending exactly at `window_start` is excluded;
- an event starting exactly at `window_end` is excluded;
- an event starting exactly at `window_start` is included when it has positive duration;
- an event ending exactly at `window_end` is included when it overlaps before that boundary;
- an event spanning midnight is included in every requested day whose exact interval it overlaps.

Zero-duration timed items are outside the first F5.A event contract unless a later capability version defines point-event semantics explicitly. The adapter must not invent inclusion semantics for them.

## All-day-event normalization

An all-day event is normalized from provider calendar-date semantics before membership evaluation. For an all-day event with provider dates:

```text
all_day_start_date
all_day_end_date_exclusive
```

use the same trusted `calendar_timezone` and `timezone_rules_version` pinned to the selected PersonalResourceBinding to resolve the local-midnight boundaries for those dates. The normalized event interval is:

```text
[exact midnight(all_day_start_date),
 exact midnight(all_day_end_date_exclusive))
```

Both boundaries must resolve to unique valid instants under the pinned rules. If a required all-day boundary is ambiguous or nonexistent, the acquired item is not eligible for admission under F5.A; the host fails closed rather than accepting provider/process default offset behavior.

Provider-specific inclusive end dates, duration fields, or local-time representations must be normalized into this exclusive-end form before the canonical predicate is evaluated.

## Complete but bounded provider query

Provider query behavior is not authoritative for Alsoul membership semantics, and F5.A does not permit an unbounded history fetch merely to make overlap evaluation complete.

For the first executable slice, a calendar adapter is eligible only when its trusted capability contract proves that the provider-side query can return **all** events overlapping the exact requested interval without requiring arbitrarily old calendar history. In practice the provider/adapter query semantics must be equivalent to the canonical overlap relation for the bounded resource/window, even if provider syntax differs.

The host still normalizes returned events and reapplies the canonical predicate before result admission. Provider filtering is a completeness/minimization mechanism, not semantic authority.

A provider that exposes only `event_start within requested window` and cannot otherwise enumerate all overlapping events with a finite trusted bound is **not eligible** for the first F5.A capability. The runtime must not compensate by fetching unbounded prior history.

If a later capability version introduces a finite maximum event-duration/span contract to permit a larger but bounded query, that maximum must be explicit trusted capability metadata, versioned, enforced before dispatch, and included in authority/request provenance. Such a later adapter must discard non-overlapping candidates in the trusted adapter/normalization boundary before `WorldSourceCapture` or provider context so unrelated out-of-window personal data is neither canonically captured nor projected.

The first F5.A slice therefore requires overlap-complete bounded query semantics rather than relying on that future extension.

## F5.A acceptance additions for membership/query semantics

F5.A is not complete until executable tests additionally prove:

1. a timed event ending exactly at `window_start` is excluded;
2. a timed event starting exactly at `window_end` is excluded;
3. an event spanning `window_start` is included;
4. an event spanning `window_end` is included for the requested day but not because the end boundary itself is inclusive;
5. a multi-day timed event is included for every requested day whose exact interval it overlaps;
6. all-day events are normalized from calendar dates to exact half-open intervals using the selected resource's pinned timezone/rules metadata;
7. ambiguous/nonexistent all-day boundaries fail closed rather than using library/provider defaults;
8. provider query semantics are complete for the canonical overlap predicate while remaining bounded to the declared personal-world capability contract;
9. a `start-within-window`-only provider cannot pass F5.A by silently omitting long-running overlapping events or by fetching unbounded history;
10. non-overlapping provider material is not admitted into `WorldSourceCapture`, WorldResult, or model context merely because provider query mechanics returned it.

# B. Trusted Permission provenance and authorized grantor

F5.A and F5.B require current Permission. A field-level match on holder, capability, resource, and operation class is necessary but not sufficient. A Permission is authoritative only when it was admitted through a trusted Permission boundary by a grantor authorized for that relationship/resource and operation class.

## Permission provenance

Conceptually, an admitted Permission retains immutable provenance sufficient to answer:

```text
which CompanionPerson holds the grant?
which capability / operation class is granted?
which PersonalResourceBinding is in scope?
which relationship/counterpart authorized the grant?
which trusted first-party grant ceremony/source supplied authority?
when was the grant admitted?
what grant-policy/version governed admission?
what expiry/constraints apply?
```

A client-supplied Permission row, provider account field, credential owner, model/tool claim, historical conversation statement, or copied identifier is not trusted Permission provenance.

## Authorized-grantor predicate

For the first F5 slice, the authorized Permission grantor is the counterpart bound to the relationship/resource through the trusted first-party identity path. Broader delegation, shared-resource grantors, guardianship, organization administrators, and multi-party grants remain outside the slice unless separately specified.

Before a Permission authorizes a read or write, trusted validation includes:

```text
Permission is present and readable
AND Permission was admitted through a trusted Permission boundary
AND Permission holder == current CompanionPerson
AND Permission capability / operation class matches
AND Permission resource == selected PersonalResourceBinding
AND Permission relationship/counterpart provenance matches that resource
AND grantor_ref resolves to the policy-authorized grantor
AND grant-policy/version is recognized
AND Permission is current / unexpired / unrevoked
AND all Permission constraints hold
```

For every new external dispatch, the runtime rechecks current relationship/resource association and Permission validity. A previously valid record cannot become a cross-relationship dispatch token merely because its identifiers remain durable.

## Cross-relationship/resource isolation

A Permission from another counterpart, relationship, resource, or capability is invalid even when the same CompanionPerson, provider account, or CredentialBinding can technically reach the target.

If Permission provenance is missing, unreadable, forged, or cannot establish the authorized-grantor relationship/resource match, the runtime fails closed before connector dispatch.

## F5 acceptance additions for Permission provenance

The relevant F5.A and F5.B authority suites must additionally prove:

1. a structurally matching Permission from an unauthorized `grantor_ref` does not authorize access;
2. a Permission admitted for another relationship cannot authorize this resource;
3. a Permission admitted for another personal resource cannot authorize this resource;
4. read Permission cannot be forged into write Permission by changing capability/operation fields outside the trusted grant boundary;
5. credential/provider account identity cannot substitute for Permission grantor identity;
6. current resource/relationship mismatch or grant revocation blocks a new dispatch/retry;
7. valid Permission retains immutable provenance linking holder, capability, operation class, resource, relationship/counterpart, trusted grant source, authorized grantor, policy/version, admission time, expiry, and constraints.

# C. Trusted Approval provenance and authorized approver

F5.B already requires a current Approval bound to the exact immutable Action. That is necessary but not sufficient. The host must also prove that the Approval was produced through a trusted approval-admission boundary by a person authorized to approve this Action for the selected personal resource.

## Approval provenance

Conceptually, an admitted Approval retains enough immutable provenance to answer:

```text
which Action was approved?
which counterpart/person authorized it?
which relationship/resource authority made that person an eligible approver?
which trusted interaction or first-party approval ceremony supplied consent?
when was approval admitted?
what policy/version governed approver eligibility?
```

A provider/model field named `approver`, a tool argument, a client-supplied arbitrary identifier, or possession of the Action ID is not trusted Approval provenance.

## Authorized-approver predicate

Before every effectful dispatch, current Approval validation includes:

```text
Approval is present and readable
AND Approval is current / unexpired / unrevoked
AND Approval.action_id == exact Action.action_id
AND Approval was admitted through a trusted approval boundary
AND Approval.approver_ref resolves to an approver authorized by current policy
AND approver authorization is valid for the Action's relationship
AND approver authorization is valid for the selected PersonalResourceBinding
AND approver authorization is valid for calendar.event.create
```

For the first F5.B slice, the authorized approver is the counterpart bound to the Action's relationship/resource under the trusted first-party identity path. Broader delegation, shared-calendar approval, guardianship, organizational approval, and multi-party authorization remain outside the slice unless separately specified.

The host must not infer approver authority from credential ownership, provider account identity, historical conversation content, memory, relationship familiarity, or model claims.

## Cross-relationship isolation

An Approval admitted for another counterpart, relationship, or personal resource is invalid even if:

```text
its Action ID was copied or forged,
the semantic event fields are identical,
the same external provider account is reachable,
or the same CompanionPerson serves both relationships.
```

The authority gate fails closed before connector dispatch when approval provenance cannot establish the authorized-approver relationship/resource match.

## Dispatch-time revalidation

Authorized-approver validity is part of the same immediate pre-dispatch authority gate as Capability, AI policy, Resource Scope, Permission, Approval freshness, Action constraints, CredentialBinding, and provider technical scope.

A previously valid approver decision does not become a permanent dispatch token. If approver eligibility is revoked or becomes unreadable before a retry, the retry is blocked.

## F5.B acceptance additions for Approval provenance

F5.B is not complete until executable tests additionally prove:

1. an Approval for the exact Action but from an unauthorized `approver_ref` does not authorize dispatch;
2. an Approval admitted for a different relationship cannot authorize this Action;
3. an Approval admitted for a different personal calendar resource cannot authorize this Action;
4. copying or forging an `action_id` into an otherwise unrelated Approval does not satisfy trusted approval provenance;
5. credential/external-account identity cannot substitute for approver identity;
6. approver eligibility is re-evaluated before every concrete dispatch/retry;
7. revocation or unreadability of approver eligibility between attempts blocks retry before the connector call;
8. a valid Approval retains immutable provenance linking exact Action, trusted approval ceremony/source, authorized approver, relationship/resource scope, policy/version, and admission time.

# D. Freshness revalidation before new model generation

A committed `ContextProjection` is immutable provenance for what was selected; it is not proof that a current-state personal-world observation remains fresh indefinitely.

For F5.A, every admitted personal-calendar WorldResult used for a current-state answer carries or deterministically derives trusted freshness metadata:

```text
captured_at
freshness_policy_version
fresh_until
source interaction id
selected PersonalResourceBinding
exact requested interval
```

The trusted freshness policy is host/capability policy, not model or provider suggestion. Missing or unreadable freshness metadata makes the result ineligible for a new current-state model generation.

Before starting a **new** ModelInvocation from a previously committed personal-calendar projection that has no durable GeneratedOutput, the runtime revalidates:

```text
same originating interaction
AND same selected resource/request interval
AND trusted freshness policy/version recognized
AND now <= fresh_until
AND no other projection-eligibility invariant has become invalid
```

If freshness fails, the old projection remains immutable historical provenance but is not reused for new cognition. The runtime re-evaluates current read authority, performs a new Observation/acquisition, admits a new WorldResult, and builds a new ContextProjection.

If a GeneratedOutput, adopted CompanionOutput, or presented output is already durably committed, deterministic downstream recovery may continue from that committed stage without pretending that a new calendar read occurred. This rule prevents process loss between projection and generation from turning an expired observation into a newly generated "current" answer.

## F5.A acceptance additions for freshness/recovery

F5.A recovery tests must additionally prove:

1. process loss after projection commit but before model generation rechecks freshness before a new ModelInvocation;
2. an unexpired same-interaction projection may be reused without duplicate acquisition;
3. an expired/missing/unreadable freshness state causes a new authority check and new Observation rather than stale projection reuse;
4. the stale projection remains immutable and is not rewritten into freshness;
5. already durable GeneratedOutput/adopted/presented stages remain deterministic downstream recovery stages and do not trigger an unnecessary calendar mutation or fabricated re-check claim.

# E. Pre-dispatch correlation and atomic Effect evidence

F5.B requires recoverable Action-correlated evidence. For the first mutation slice, correlation that exists only in an ephemeral successful provider response is not sufficient because process loss can destroy the only identifier needed to reconcile the Action.

## Pre-dispatch recoverable correlation

Before crossing the external dispatch boundary, the host must durably establish an Action-specific external operation/correlation identity tied to `action_id`, for example a provider-supported idempotency key, client-chosen event/operation identifier, or equivalent capability-specific correlation marker that remains usable for reconciliation after process loss.

```text
Action A1
↓
K(A1) durably established
↓
ExecutionAttempt records K(A1)
↓
dispatch
```

`K(A1)` must be unique to the Action and must not be derived solely from semantic payload equality. Retries of the same Action reuse the same external operation identity when capability semantics permit them.

A provider integration whose only unique Action-correlated identifier is first learned from the create response and cannot be recovered through any pre-dispatch durable correlation mechanism is **not eligible** for the first F5.B capability. A response-learned provider event ID may strengthen evidence, but it cannot be the sole recovery correlation.

## Durability ordering

After dispatch, provider response/correlation evidence is persisted before Effect admission. The first committed `CONFIRMED_EFFECT` state must already have recoverable supporting evidence linked to it.

Conceptually:

```text
provider response / reconciliation observation
↓
durable EvidenceItem / response evidence with Action correlation
↓
Effect + required SUPPORTS relation committed atomically enough
that no visible Effect state exists without its support
```

The storage design may use one database transaction, foreign-key-enforced dependent insertion, or another mechanism with equivalent crash semantics. It must not commit an Effect first and attach evidence later.

If evidence is durable but the process dies before Effect admission, recovery admits the Effect from that durable evidence without redispatching the Action. If dispatch may have occurred but no conclusive response evidence was persisted, the pre-dispatch `K(A1)` supports read-side reconciliation and the state remains `UNKNOWN_EFFECT` until adequate evidence exists.

## Required crash-boundary behavior

```text
crash before dispatch
    → no external effect assumed; ordinary authority/retry rules apply

crash after dispatch, before conclusive response evidence commit
    → UNKNOWN_EFFECT; reconcile using durable Action correlation; no blind retry

crash after response/correlation evidence commit, before Effect commit
    → recover evidence and admit Effect if sufficient; do not redispatch

crash after Effect commit
    → Effect and its SUPPORTS evidence are both already recoverable
```

## F5.B acceptance additions for Effect durability

F5.B is not complete until executable tests additionally prove:

1. Action-specific external correlation is durably established before every mutation dispatch;
2. an adapter relying solely on a response-learned unique event ID with no recoverable pre-dispatch correlation is rejected for the first F5.B capability;
3. crash after dispatch but before response-evidence commit recovers as `UNKNOWN_EFFECT` and reconciles through the durable Action correlation without blind retry;
4. provider response/reconciliation evidence becomes durable before Effect admission;
5. crash after evidence commit but before Effect commit recovers and can admit the Effect without redispatch;
6. the first visible committed Effect state already has its required Action-correlated SUPPORTS evidence;
7. no crash boundary can expose a confirmed Effect without recoverable supporting evidence;
8. strong completion language remains blocked until that evidence-backed Effect state is committed.

# Closure consequence

The F5 closure bar therefore additionally requires:

```text
exact personal-calendar windows
+
canonical provider-independent event membership
+
bounded overlap-complete personal-world acquisition
+
trusted Permission admission / authorized grantor
+
trusted Approval admission / authorized approver
+
cross-relationship/resource isolation
+
freshness revalidation before new cognition
+
pre-dispatch Action correlation
+
atomic evidence-backed Effect confirmation
```

This preserves the intended trust boundary:

```text
what belongs to the requested personal-world view
must not depend on adapter defaults or unbounded access

standing authority and per-action consent
must not depend on untrusted identifiers

and

confirmed external effect
must never exist ahead of its recoverable proof
```
