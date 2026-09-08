# F5 Executable Checkpoint — Normative Addendum

**Status:** Normative amendment to the F5 executable checkpoint  
**Publication:** GitHub-safe  
**Applies to:** [F5 Executable Checkpoint — Personal World + Trust](F5_EXECUTABLE_CHECKPOINT.md)

This addendum is part of the F5 executable checkpoint contract. An implementation does not satisfy F5.A or F5.B unless it satisfies both the primary checkpoint and this addendum. Where this addendum is more specific, this addendum governs.

The addendum closes two trust ambiguities that are material at the personal-world boundary:

```text
calendar-window endpoint instants ≠ calendar-window membership semantics
Approval bound to Action ≠ Approval issued by an authorized approver
```

# A. Canonical calendar-window membership

F5.A already requires one exact interval derived from trusted calendar timezone/rules metadata. The result contract additionally requires one provider-independent membership predicate for events returned for that interval.

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
- an event ending exactly at `window_end` is included when it overlaps the interval before that boundary;
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

Both boundaries must resolve to unique valid instants under the pinned rules. If a required all-day boundary is ambiguous or nonexistent, the acquired item is not eligible for admission under F5.A; the host must fail closed for that item/window rather than accept provider/process default offset behavior.

Provider-specific inclusive end dates, duration fields, or local-time representations must be normalized into this exclusive-end form before the canonical predicate is evaluated.

## Adapter boundary

Provider query syntax may differ, but provider query behavior is not authoritative for Alsoul membership semantics. The trusted host must either:

1. request a superset and apply the canonical predicate after normalization; or
2. prove by capability-contract tests that the adapter/provider query has semantics equivalent to the canonical predicate for the bounded slice.

An adapter must not silently substitute `start-within-window`, inclusive-end, provider-default all-day, or account-local semantics.

## F5.A acceptance additions

F5.A is not complete until executable tests additionally prove:

1. a timed event ending exactly at `window_start` is excluded;
2. a timed event starting exactly at `window_end` is excluded;
3. an event spanning `window_start` is included;
4. an event spanning `window_end` is included for the requested day but not because the end boundary itself is inclusive;
5. a multi-day timed event is included for every requested day whose exact interval it overlaps;
6. all-day events are normalized from calendar dates to exact half-open intervals using the selected resource's pinned timezone/rules metadata;
7. ambiguous/nonexistent all-day boundaries fail closed rather than using library/provider defaults;
8. provider query semantics cannot widen or narrow the canonical membership predicate without an explicit capability-contract version change.

# B. Trusted Approval provenance and authorized approver

F5.B already requires a current Approval bound to the exact immutable Action. That is necessary but not sufficient. The host must also prove that the approval was produced through a trusted approval-admission boundary by a person authorized to approve this Action for the selected personal resource.

## Approval provenance

Conceptually, an admitted Approval must retain enough immutable provenance to answer:

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

Before every effectful dispatch, current Approval validation must include all of the following:

```text
Approval is present and readable
AND Approval is current / unexpired / unrevoked
AND Approval.action_id == exact Action.action_id
AND Approval was admitted through a trusted approval boundary
AND Approval.approver_ref resolves to an approver authorized by current policy
AND the approver authorization is valid for the Action's relationship
AND the approver authorization is valid for the selected PersonalResourceBinding
AND the approver authorization is valid for calendar.event.create
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

The authority gate must fail closed before connector dispatch when approval provenance cannot establish the authorized-approver relationship/resource match.

## Dispatch-time revalidation

Authorized-approver validity is part of the same immediate pre-dispatch authority gate as Capability, AI policy, Resource Scope, Permission, Approval freshness, Action constraints, CredentialBinding, and provider technical scope.

A previously valid approver decision does not become a permanent dispatch token. If approver eligibility is revoked or becomes unreadable before a retry, the retry is blocked.

## F5.B acceptance additions

F5.B is not complete until executable tests additionally prove:

1. an Approval for the exact Action but from an unauthorized `approver_ref` does not authorize dispatch;
2. an Approval admitted for a different relationship cannot authorize this Action;
3. an Approval admitted for a different personal calendar resource cannot authorize this Action;
4. copying or forging an `action_id` into an otherwise unrelated Approval does not satisfy trusted approval provenance;
5. credential/external-account identity cannot substitute for approver identity;
6. approver eligibility is re-evaluated before every concrete dispatch/retry;
7. revocation or unreadability of approver eligibility between attempts blocks retry before the connector call;
8. a valid Approval retains immutable provenance linking exact Action, trusted approval ceremony/source, authorized approver, relationship/resource scope, policy/version, and admission time.

# Closure consequence

The F5 closure bar therefore additionally requires:

```text
exact personal-calendar windows
+
canonical provider-independent event membership
+
trusted Approval admission
+
authorized-approver provenance
+
cross-relationship/resource isolation
```

This preserves the intended trust boundary:

```text
what belongs to the requested personal-world view
must not depend on adapter defaults

and

who approved an external mutation
must not depend on an untrusted identifier
```
