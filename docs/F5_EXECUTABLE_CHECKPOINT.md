# F5 Executable Checkpoint — Personal World + Trust

**Status:** Converged implementation contract; implementation pending  
**Publication:** GitHub-safe  
**Predecessor:** [F4 Exit Audit](F4_EXIT_AUDIT.md)  
**Architecture basis:** Decisions 06.A–06.C, 07.A–07.B, 08.A–08.B, 11.A, 14.A, and 15.A–15.B

F5 begins after the executable F4 foundation is closed. Its purpose is not to add a broad connector surface. Its purpose is to prove that Alsoul can enter the counterpart's personal digital world under explicit authority while preserving Person continuity, epistemic honesty, provenance, minimization, recovery, and fail-closed behavior.

This document is the complete normative F5 executable checkpoint. No separate amendment or precedence chain is required.

# 1. Governing boundary

The trust progression is deliberately staged:

```text
public-world observation
↓
selected personal-world read
↓
prepared external action
↓
explicitly approved bounded mutation
↓
effect confirmation / reconciliation
```

Read authority does not imply write authority. Access to one personal resource does not imply access to another. Access to personal data does not make that data durable personal memory. Prior authority does not guarantee later disclosure or later dispatch authority.

The governing distinctions are:

```text
CompanionPerson ≠ external account
CounterpartPerson ≠ external principal
PersonalResourceBinding ≠ CounterpartPerson
PersonalResourceBinding ≠ CredentialBinding
Credential possession ≠ Permission
provider technical scope ≠ Permission
Capability availability ≠ Permission
Permission ≠ Approval
read / observe ≠ write / act
personal-world observation ≠ MemoryClaim
WorldSourceCapture ≠ general memory eligibility
Action ≠ ExecutionAttempt ≠ Effect
failed effect ≠ unknown effect
historical authority ≠ current authority
historical freshness ≠ current freshness eligibility
provider/tool identity ≠ semantic capability
execution isolation ≠ capability authorization
process-local timezone ≠ trusted calendar time semantics
semantic event match ≠ proof of this Action's Effect
Action correlation ≠ semantic correctness of the Effect
Approval record match ≠ faithful consent presentation
prepared attempt ≠ transport may have started
provider response ≠ durable Effect evidence
one logical Observation ≠ one transport request
terminal page token ≠ coherent snapshot
snapshot completion time ≠ snapshot freshness age
canonical minimization ≠ permission to persist raw provider payload elsewhere
first generation ≠ indefinitely authorized first presentation
presentation payload dispatch ≠ sink acceptance
unknown presentation outcome ≠ presented
unknown presentation outcome ≠ definitely undisclosed
Action correlation ≠ concurrency/idempotency fence
```

Authority is monotonic narrowing:

```text
Host Capability
∩ AI Capability Policy
∩ Resource Scope
∩ User Permission
∩ operation-specific Approval when required
= maximum authority for this operation
```

No lower layer may manufacture authority that is absent, unreadable, expired, revoked, mismatched, or denied above it.

F5 is split into two executable tranches:

```text
F5.A  personal-world observation
F5.B  bounded external action + effect reconciliation
```

F5.A is the immediate implementation target. F5.B starts only after the read-side authority, provenance, minimization, completeness, coherent-snapshot, disclosure, presentation-reconciliation, and recovery boundary is executable. F5 is not closed until both tranches satisfy their acceptance bars.

# 2. F5.A — Read-only personal calendar observation

## 2.1 Objective and grammar

Answer one bounded current-state calendar question by actually reading one explicitly selected calendar resource under current authority.

The first executable grammar is intentionally narrow:

```text
"What's on my calendar on YYYY-MM-DD?"
"What do I have on my calendar on YYYY-MM-DD?"
```

The date denotes one local calendar day in trusted time semantics pinned to the selected calendar resource. It is not interpreted in process-local time, host locale, model locale, account defaults, or adapter defaults.

Relative-date expressions, natural-language recurrence reasoning, free-form calendar search, email, contacts, files, multiple-calendar aggregation, and cross-resource search remain outside the first slice.

## 2.2 Semantic path

```text
trusted COUNTERPART_INPUT
↓
bounded PERSONAL_CALENDAR_QUESTION classification
↓
resolve one selected PersonalResourceBinding
↓
derive one exact calendar-day interval from trusted time metadata
↓
evaluate current read authority
↓
Investigation
↓
Observation
↓
one logical personal-calendar acquisition
    └── one or more bounded transport page requests if required
↓
trusted coherent-snapshot / normalization / minimization / completeness validation
↓
WorldSourceCapture
↓
EvidenceItem
↓
WorldResult
↓
ContextProjection
↓
ModelInvocation / GeneratedOutput
↓
CompanionOutput adoption
↓
current freshness + personal-data disclosure eligibility
↓
first-party presentation dispatch / acceptance reconciliation
↓
first accepted presentation
```

The connector performs acquisition only. It does not decide semantic routing, resource selection, permission, memory admission, time interpretation, completeness policy, projection eligibility, disclosure authority, presentation truth, or what the model may see.

## 2.3 Capability contract

The first semantic capability is:

```text
calendar.events.read
```

This is a provider-independent operation family. Provider method names, plugin names, transport endpoints, credential types, or model tool names cannot define authority.

Trusted capability metadata declares at least:

```text
semantic operation
contract version
access/effect class = READ_ONLY
supported resource kind = CALENDAR
request constraints
response semantics
pagination/completeness semantics
pagination snapshot/coherency semantics
snapshot as-of / freshness-anchor semantics
recurrence-expansion semantics
field-normalization schema version
raw-response minimization/telemetry contract
freshness-policy binding/version
```

A missing or unreadable capability declaration blocks dispatch. The runtime must not infer read/write/effect class from a tool or function name.

An adapter is ineligible for the first slice when it cannot provide a bounded complete and coherent view of the requested window, cannot provide a trustworthy freshness anchor for that coherent view, cannot enforce the field-minimization contract before persistence/telemetry, or cannot prove the required authority and provenance semantics.

## 2.4 Personal resource identity and trusted time semantics

The selected calendar is represented separately from Person identity and credential identity.

Conceptually:

```text
PersonalResourceBinding {
    personal_resource_binding_id
    counterpart_id
    relationship_id
    resource_kind = CALENDAR
    external_system_ref
    external_resource_ref
    calendar_timezone
    timezone_rules_version
    display_label?
    status
}
```

`calendar_timezone` and `timezone_rules_version` are trusted resource/host metadata established and validated before the resource becomes active. They are not supplied by the model and are not inherited from process-local defaults.

For an input date `D`, the host resolves:

```text
D 00:00
(D + 1 day) 00:00
```

under the pinned timezone and rules version. F5.A accepts the date only when both boundaries resolve to exactly one valid instant. If either boundary is nonexistent or ambiguous under those rules, the request fails closed before connector dispatch. The first slice does not guess an offset, roll a boundary, or accept library-specific default behavior.

For an accepted date:

```text
window_start = exact instant for D 00:00
window_end   = exact instant for (D + 1 day) 00:00
window       = [window_start, window_end)
```

The canonical request records:

```text
calendar_timezone
timezone_rules_version
window_start exact instant / offset
window_end exact instant / offset
```

The first slice requires exactly one configured active calendar resource for the relationship. Zero resources fail unavailable. More than one active resource fails ambiguous until an explicit resource-selector contract exists.

## 2.5 Credential binding

A `CredentialBinding` establishes how the trusted host can authenticate to the selected external system. It does not define the user, relationship, permission, resource, or capability.

Credential secrets remain outside canonical cognition and persisted provider/model context. Canonical state may retain a secret reference or binding identifier, never the secret itself.

Credential removal or rebinding must not change `CompanionPerson`, `CounterpartPerson`, `RelationshipState`, canonical Timeline identity, or previously established evidence identity.

## 2.6 Trusted Permission provenance

F5.A requires explicit standing read Permission for:

```text
holder = current CompanionPerson
capability = calendar.events.read
resource = selected PersonalResourceBinding
operation class = READ
```

A matching row is not sufficient. Permission is authoritative only when admitted through a trusted Permission boundary by a grantor authorized for the current counterpart/relationship/resource and operation class.

An admitted Permission retains immutable provenance sufficient to establish:

```text
holder CompanionPerson
capability / operation class
PersonalResourceBinding
relationship / counterpart
grantor_ref
trusted grant ceremony/source
grant-policy/version
granted_at
expires_at?
constraints
```

For the first F5 slice, the authorized grantor is the counterpart bound to the selected resource through the trusted first-party identity path. Credential ownership, provider account identity, model/tool claims, memory, historical conversation, or copied identifiers cannot grant authority.

Before every external read transport request, including every pagination request, validation requires:

```text
Permission present and readable
AND trusted Permission admission provenance valid
AND holder == current CompanionPerson
AND capability / operation class matches
AND resource matches selected PersonalResourceBinding
AND relationship/counterpart provenance matches
AND grantor_ref is currently policy-authorized
AND grant-policy/version is recognized
AND Permission is current / unexpired / unrevoked
AND constraints hold
```

Cross-relationship, cross-resource, forged, unreadable, revoked, or mismatched Permission fails closed.

The first slice does not require a separate per-interaction Approval for this bounded read. The active user request plus standing Permission is sufficient under this contract. That rule does not generalize to writes.

## 2.7 Read authority gate and provenance

Immediately before each external transport request, the host evaluates:

```text
calendar.events.read Capability is available and trusted
AND current AI Capability Policy permits the read
AND selected resource is inside current Resource Scope
AND trusted current Permission authorizes the read
AND usable CredentialBinding exists
AND provider technical scope is sufficient
AND exact requested interval satisfies all constraints
```

Provider technical scope is a ceiling, not Alsoul authority.

One successful semantic `Observation` retains immutable authority provenance sufficient to reconstruct why the read was authorized without consulting mutable current configuration. The durable authority provenance includes at least:

```text
Capability ref + contract/version
AI Capability Policy decision ref/version
Resource Scope decision ref/version
Permission ref + trusted grant provenance
PersonalResourceBinding
CredentialBinding ref
provider technical-scope snapshot/reference
source interaction
trusted timezone/rules/window
first and last authority-evaluation times
```

For multi-page acquisition, page requests remain children of the same Observation/acquisition identity while each transport dispatch records its own current authority evaluation or a mechanically linked evaluation record.

Authority provenance explains why access was allowed. It does not prove calendar content.

## 2.8 Canonical calendar membership

A normalized timed event occupies:

```text
event = [event_start, event_end)
```

A timed event belongs to the requested day exactly when:

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
- a midnight-spanning or multi-day event is included in every requested day whose exact interval it overlaps.

Zero-duration timed items are outside the first F5.A event contract.

### All-day events

An all-day event is normalized from provider calendar dates:

```text
all_day_start_date
all_day_end_date_exclusive
```

using the same trusted `calendar_timezone` and `timezone_rules_version` pinned to the selected resource. The normalized event interval is:

```text
[exact midnight(all_day_start_date),
 exact midnight(all_day_end_date_exclusive))
```

Both boundaries must resolve to unique valid instants. Ambiguous/nonexistent required boundaries fail closed for that acquisition rather than accepting provider/process defaults.

Provider-specific inclusive end dates, duration fields, or local-time representations must be converted to this exclusive-end form before membership evaluation.

## 2.9 Recurrence normalization

The first slice does not implement local recurrence-rule reasoning.

An eligible calendar capability must provide trusted, bounded provider/adapter expansion into concrete occurrences for the exact requested interval, including authoritative exceptions, replacements, and cancellations.

A normalized occurrence retains only the recurrence identity/provenance required to prevent omission or duplication, for example:

```text
series/master ref?
occurrence/instance ref
replacement/exception ref?
concrete start/end or all-day dates
occurrence status required for cancellation handling
```

The series master is never admitted directly as a day event merely because its template resembles an occurrence.

The first slice requires:

- cancelled occurrences to be excluded when cancellation status is authoritative;
- modified occurrences to use the concrete replacement occurrence;
- original replaced/cancelled occurrences not to survive as duplicates;
- occurrence identity to prevent master/instance/exception duplication;
- master-only or incomplete recurrence expansion to fail closed rather than return a knowingly partial schedule.

## 2.10 Complete, bounded, coherent, and time-anchored acquisition

Provider query behavior is not authoritative for Alsoul membership semantics.

For the first executable slice, an adapter is eligible only when its trusted capability contract proves that all concrete events/occurrences overlapping the exact requested interval can be enumerated without unbounded history access.

A `start-within-window`-only provider that cannot otherwise enumerate long-running overlapping events with a finite trusted bound is ineligible. The runtime must not compensate by fetching unbounded prior history.

One semantic read may require multiple bounded transport page requests. Pagination is part of one `Observation` and one logical acquisition, not multiple independent semantic observations.

### Pagination completeness

The capability contract must define trusted pagination/completeness semantics including at least:

```text
page request scope
page-token semantics
completion predicate / terminal token semantics
provider truncation/result-cap behavior
maximum bounded page/resource limits enforced by Alsoul
```

Every page request remains constrained to the same:

```text
PersonalResourceBinding
exact authorized interval
capability contract/version
field-selection/minimization contract
```

Current read authority is re-evaluated before every page transport dispatch. Revocation or unreadability during pagination aborts the acquisition; partial pages cannot be promoted into a complete `WorldResult`.

### Coherent-snapshot requirement

A terminal page token proves traversal completion only when the pages belong to one coherent logical view. The first slice therefore requires the capability contract to provide one of the following trusted mechanisms:

```text
snapshot-consistent cursor/session identity
OR provider revision/version fence that is stable across all pages
OR equivalent authoritative snapshot token
OR deterministic change detection that proves no membership-affecting mutation occurred across pagination
```

Pages from different provider revisions/snapshots must never be silently combined.

If the provider uses offset/page-number pagination without snapshot semantics, the adapter must detect any membership-affecting change that could skip, duplicate, add, remove, reorder, or replace an event while the logical acquisition is in progress. If coherent completeness cannot be proven, the acquisition fails closed.

A capability may permit a bounded restart of pagination only when all of the following hold:

```text
no WorldSourceCapture / WorldResult for the failed logical traversal has been admitted
current read authority is re-evaluated before the restarted transport
restart count is bounded by trusted capability policy
all prior partial page material is discarded rather than mixed into the new traversal
new traversal establishes one fresh coherent snapshot/revision lineage
```

The restart may remain under the same semantic Observation only as a failed internal traversal followed by a fresh bounded traversal for the same user interaction; it cannot make partial earlier pages canonical evidence.

### Snapshot as-of and freshness anchor

Coherent pagination is not enough to establish freshness age. A long traversal can finish much later than the snapshot it is enumerating.

Before the first page transport, the host durably records:

```text
acquisition_started_at
```

The capability contract also declares whether the coherent provider view exposes an authoritative:

```text
snapshot_as_of
```

or equivalent exact instant for the state represented by the snapshot/revision.

The canonical freshness anchor is:

```text
if authoritative snapshot_as_of exists and is trusted for this snapshot:
    freshness_anchor_at = snapshot_as_of
else:
    freshness_anchor_at = acquisition_started_at
```

`capture_committed_at`, terminal-page time, normalization-completion time, or model-invocation time must never be substituted as a newer freshness anchor merely because pagination took time.

If the provider exposes a stable revision but no trustworthy as-of instant, `acquisition_started_at` is the required conservative anchor. If the provider exposes a timestamp whose relationship to the coherent snapshot is ambiguous or untrusted, it is ignored for freshness and the conservative acquisition-start anchor applies.

A calendar mutation that occurs after a snapshot is pinned may correctly be absent from that coherent snapshot; freshness policy must age the result from the snapshot's actual as-of instant (or conservative acquisition start), not from traversal completion. A sufficiently long traversal can therefore yield a complete coherent result that is already stale and ineligible for current-state cognition by the time capture completes.

The `WorldSourceCapture` retains completeness/coherency/time provenance sufficient to establish:

```text
one Observation/acquisition identity
acquisition_started_at
snapshot/session/revision identity or equivalent coherency proof
authoritative snapshot_as_of when available
freshness_anchor_at and how it was derived
ordered page/cursor chain or equivalent page lineage
bounded request scope for every page
terminal completeness proof
provider count/cap signals needed to detect truncation
capture_committed_at
normalization schema version
```

If pagination terminates early, a cap is reached without authoritative completeness, a token is missing/inconsistent, provider truncation cannot be ruled out, snapshot/revision identity changes unexpectedly, or coherent traversal cannot otherwise be established, the acquisition fails closed. A partial or incoherent schedule cannot be narrated as a complete checked schedule.

## 2.11 Field-level minimization and non-canonical data handling

Resource/window minimization is necessary but not sufficient. The first F5.A slice uses an explicit normalized event allowlist.

Canonical event material admitted into `WorldSourceCapture` may contain only fields required for schedule truth, recurrence normalization, provenance, or deterministic recovery:

```text
selected PersonalResourceBinding / external resource ref
provider event/occurrence identity required for provenance/dedup
series/exception identity only when required for recurrence normalization
normalized summary/title
normalized start instant
normalized end instant
all_day flag and normalized all-day dates when applicable
occurrence status only when required to establish inclusion/cancellation
normalization/schema version
```

The first slice does not canonically capture or expose to the model fields such as:

```text
description/body
attendee identities or responses
organizer identity unless required by a later contract
conference/join metadata
attachments
reminders
private notes
extended/custom properties
location
provider-side unrelated metadata
```

If the provider necessarily returns disallowed fields, those fields may exist only ephemerally inside the trusted adapter boundary for the minimum time required to parse and normalize the response. They are discarded before canonical capture.

The same minimization boundary applies to **non-canonical persistence and telemetry**. Disallowed raw personal fields must not be written or emitted to:

```text
transport/debug logs
application logs
traces/spans
metrics labels or event payloads
retry caches or durable transport queues
response caches
crash dumps / diagnostic snapshots
analytics payloads
dead-letter stores
test fixtures captured from production responses
```

Operational telemetry may retain non-sensitive structural metadata such as request IDs, page counts, timing, redacted error classes, or normalized schema/version identifiers when that metadata does not reveal disallowed personal content.

If an adapter/runtime cannot prevent raw personal fields from being persisted or emitted outside the allowed canonical evidence path, that integration is ineligible for the first F5.A slice. Debug mode, exception serialization, and transport middleware do not create an exception to this rule.

The `ContextProjection` is stricter still. It exposes only the user-facing schedule fields needed to answer the bounded question, normally normalized title, time/all-day semantics, and source classification. Provider identifiers and recurrence mechanics remain outside model context unless a future contract explicitly requires them.

Field minimization is independently testable and is not satisfied merely because no MemoryClaim is created.

## 2.12 Evidence, result, and freshness

Calendar state is connected-world observation, not innate knowledge.

A successful logical acquisition creates an acquisition-specific `WorldSourceCapture` containing enough recoverable normalized material to establish:

```text
selected resource identity
requested date
trusted timezone/rules version
exact requested interval
acquisition_started_at
snapshot/revision/coherency identity
authoritative snapshot_as_of when available
freshness_anchor_at
capture_committed_at
normalized allowlisted event material
completeness/coherency provenance
normalization contract/version
```

Content support flows:

```text
Observation
↓
WorldSourceCapture
↓
EvidenceItem
↓
WorldResult
```

A calendar-derived `WorldResult` is classified equivalently to:

```text
CURRENT_PERSONAL_OBSERVATION
```

A current-state result carries historical freshness provenance such as:

```text
freshness_anchor_at
freshness_anchor_basis = PROVIDER_SNAPSHOT_AS_OF | ACQUISITION_STARTED_AT
freshness_policy_version_at_admission
fresh_until_at_admission?
```

Those values explain historical admission. They are not permanent eligibility tokens.

All current-policy freshness predicates in this checkpoint evaluate age from `freshness_anchor_at`, never from capture commit or page-traversal completion.

## 2.13 No silent memory admission

The read path creates no `MemoryClaim` or `PersonClaim` merely because an event mentions the counterpart, a preference, another person, a place, or a recurring pattern.

```text
personal data exposure
≠ memory proposal
≠ memory admission
```

Calendar content is retained only in the evidence/result lineage required for the authorized interaction and deterministic recovery. Any later personal-world memory admission requires a separate policy and contract.

## 2.14 Projection eligibility and current-policy recovery

Personal-world evidence is not a general-purpose context pool.

A calendar `WorldResult` is eligible only for the interaction that caused its authorized acquisition and deterministic recovery of that same interaction. Another interaction requires a new explicit selection/admission contract and, for a current-state question, normally a new acquisition.

Recovery resumes from the furthest trustworthy durable stage, but every pre-output stage that would create new cognition from historical personal-calendar material is gated by the trusted **current** freshness policy.

### Recovery from input only

```text
input admitted, no successful capture
    → re-evaluate current read authority and trusted time metadata
    → create a new Observation/acquisition
```

### Recovery from capture/result before projection

Before a recovered `WorldSourceCapture` or `WorldResult` can be used to admit/reuse a result for a new projection, eligibility requires:

```text
same originating interaction
AND same selected PersonalResourceBinding
AND same exact requested interval
AND current freshness policy is readable/trusted
AND current policy considers freshness_anchor_at eligible now
AND completeness/coherency/minimization/projection invariants remain valid
```

A historical `fresh_until_at_admission` remaining in the future is not sufficient after policy change.

If current freshness fails or is unreadable:

```text
retain old capture/result as immutable historical provenance
↓
re-evaluate current read authority
↓
perform a new Observation/acquisition
↓
admit a new WorldResult
↓
build a new ContextProjection
```

A stale recovered capture cannot be promoted into a newly admitted current-state result merely because its original acquisition was authorized.

### Recovery from projection before model generation

Before a new `ModelInvocation` from a previously committed personal-calendar `ContextProjection` with no durable `GeneratedOutput`, the runtime independently rechecks current freshness of the underlying observation/result from its `freshness_anchor_at`.

A policy change or elapsed time between projection construction and model invocation may invalidate that immutable projection. The stale projection remains historical provenance; new authorized acquisition/result/projection state is required for new current-state cognition.

## 2.15 First-presentation freshness, disclosure authority, and uncertain sink acceptance

A durable `GeneratedOutput` or unpresented `CompanionOutput` is immutable cognition, but it is not indefinitely eligible for **first presentation** of personal calendar material.

The F5 personal-data presentation contract extends the F4 first-party idempotent presentation boundary with explicit uncertain-acceptance reconciliation. The objective is to avoid both unauthorized redisclosure and false historical claims when the sink may already have accepted a payload before an acknowledgement was lost.

### 2.15.1 Before any payload-bearing presentation transport

Immediately before every transport that would send the personal-data payload to the first-party sink, the host evaluates two independent gates:

```text
A. current-state freshness eligibility
AND
B. current personal-data disclosure authority
```

Freshness is evaluated from the underlying `freshness_anchor_at` under the trusted current freshness policy.

Current disclosure authority includes at least:

```text
same trusted counterpart / RelationshipState remains valid for the output
AND selected PersonalResourceBinding remains associated with that counterpart/relationship
AND current AI Capability / personal-data disclosure policy permits presentation
AND current trusted read Permission remains present, unexpired, unrevoked, relationship/resource-matched, and disclosure-eligible for this interaction
AND no current policy or explicit revocation fence prohibits delivery of the captured personal data
```

Credential usability and provider technical scope are acquisition feasibility, not prerequisites for displaying already-captured data. They are rechecked only if a new acquisition is required.

If freshness fails while disclosure remains valid, the old generated/adopted output remains immutable historical provenance but is not sent with unqualified current-state language. The preferred first-slice path is new authorized acquisition/projection/generation. A future explicit versioned presentation policy may allow mechanically bounded `as of <freshness_anchor_at>` historical language.

If disclosure authority fails or is unreadable, no payload-bearing presentation transport occurs and no reacquisition is attempted until authority is restored.

### 2.15.2 Durable presentation attempt and dispatch uncertainty

Before a payload-bearing presentation transport can observe the payload, the host durably records a presentation attempt/fence conceptually equivalent to:

```text
PersonalPresentationAttempt {
    presentation_attempt_id
    companion_output_id
    presentation_key
    surface_binding_id
    channel_binding_id
    presentation_contract_version
    disclosure_authority_decision_ref/version
    freshness_decision_ref/version
    payload_digest
    dispatch_fenced_at
    sink_acceptance_state = UNKNOWN | ACCEPTED | NOT_ACCEPTED
}
```

The exact schema may differ, but recovery must distinguish:

```text
no presentation dispatch fence
    → sink could not have observed this payload through this attempt

presentation dispatch fenced, no validated acceptance receipt
    → UNKNOWN_PRESENTATION_ACCEPTANCE

validated sink acceptance
    → ACCEPTED

authoritative content-free sink status proves no acceptance
    → NOT_ACCEPTED
```

A transport timeout or lost acknowledgement after the presentation fence is not treated as definitely undisclosed and is not treated as presented.

### 2.15.3 Required content-free acceptance-status lookup

A first-party sink used for F5 personal-data presentation must preserve the F4 idempotent `presentation_key` contract **and** support an authoritative content-free acceptance-status lookup keyed only by the presentation identity.

Conceptually:

```text
lookup_presentation_status(presentation_key)
    → ACCEPTED + acceptance evidence
    | NOT_ACCEPTED + authoritative evidence
    | UNKNOWN
```

The lookup request must not resend, echo, hash-expand, or otherwise disclose the personal payload. The response may contain only structural acceptance metadata sufficient to establish presentation truth, such as the presentation key, acceptance state, sink receipt/reference, and acceptance timestamp.

A sink that can recover acceptance only by resending the payload is ineligible for F5 personal-data presentation because revocation after an uncertain dispatch would otherwise force either unauthorized redisclosure or permanent ambiguity.

### 2.15.4 Recovery of an uncertain presentation

When recovery finds `UNKNOWN_PRESENTATION_ACCEPTANCE`, it first performs the content-free status lookup. It does **not** resend the payload merely to recover a receipt.

If the status lookup establishes `ACCEPTED`:

```text
persist acceptance evidence
↓
commit/recover exactly one COMPANION_PRESENTED_OUTPUT Timeline event
```

This Timeline commit records a presentation that the sink already accepted before or during the earlier authorized payload dispatch. It does not constitute a new personal-data disclosure and therefore does not require current calendar read/disclosure Permission to be re-granted merely to record historical truth.

The Timeline event/presentation provenance must point to the original presentation attempt and sink acceptance evidence, including the sink's acceptance time when available. Revocation after that acceptance does not erase the historical event.

If the status lookup establishes `NOT_ACCEPTED`, no presentation event is committed. A later payload send is allowed only after fresh evaluation of current freshness and current disclosure authority. If either gate now fails, the output remains undisclosed and no payload retry occurs.

If the status lookup remains `UNKNOWN`, no Timeline presentation event is fabricated. The runtime retains the unknown presentation state. It may retry the **content-free lookup** under its bounded technical policy, but it may not resend the payload while disclosure authority is denied or freshness is ineligible. Even when authority/freshness are still valid, the first F5 slice prefers status reconciliation over payload replay after an uncertain dispatch; any payload replay must still use the exact semantic `presentation_key`, exact content, and both current gates.

### 2.15.5 Already-presented history

Once sink acceptance has been durably established and the canonical Timeline presentation event committed, deterministic replay/recovery does not retroactively rewrite or delete that historical event because Permission, resource bindings, relationship state, disclosure policy, or calendar contents later change.

## 2.16 User-facing truth and fail-closed behavior

User-facing language such as:

```text
"From your calendar, I can see..."
"I checked your calendar..."
```

is allowed only after authorized acquisition, coherent completeness validation, evidence-backed `WorldResult` admission, current freshness eligibility at cognition/payload-dispatch boundaries, current disclosure authority for each payload send, and validated presentation truth.

The model may summarize only the selected normalized calendar window. It cannot select another calendar, broaden the date range, reinterpret timezone, fetch another resource, infer missing pages, expose disallowed provider fields, or convert observed events into memory.

No read transport dispatch occurs when any required acquisition-authority layer is unavailable or invalid, including:

- unsupported personal-calendar grammar;
- zero or multiple active resources under the first-slice contract;
- missing/unreadable trusted timezone or rules version;
- ambiguous/nonexistent requested-day boundary;
- capability absent/unavailable/untrusted;
- access/effect classification missing/untrusted;
- AI policy denial;
- resource outside current scope;
- Permission absent/unreadable/expired/revoked/mismatched/untrusted;
- unauthorized Permission grantor or cross-relationship/resource provenance;
- CredentialBinding absent/unusable;
- provider technical scope insufficient;
- interval violates capability/Permission constraints.

No complete `WorldResult` is admitted when:

- recurrence expansion is incomplete;
- provider query cannot be overlap-complete within bounded access;
- pagination/truncation completeness cannot be established;
- pagination snapshot/coherency cannot be established;
- a trustworthy freshness anchor cannot be established;
- disallowed fields cannot be removed before canonical capture and prohibited from non-canonical persistence/telemetry;
- event/time normalization cannot be completed deterministically.

No new current-state cognition is allowed from stale personal-world evidence. No new payload disclosure is allowed when freshness or current disclosure authority fails. An uncertain prior presentation is reconciled content-free rather than guessed or forced through an unauthorized payload resend.

## 2.17 F5.A acceptance bar

F5.A is complete only when executable tests prove all of the following:

1. The same `CompanionPerson`, `CounterpartPerson`, and `RelationshipState` survive connector binding, credential rebinding, and complete runtime recomposition.
2. One bounded date question creates exactly one semantic authorized Observation/acquisition against exactly one selected calendar resource.
3. A logical acquisition may use multiple bounded page requests without creating multiple semantic Observations merely because transport pagination exists.
4. Every page request revalidates current read authority and remains scoped to the same resource/window/capability contract.
5. Missing, unreadable, revoked, expired, mismatched, forged, cross-relationship, or unauthorized-grantor Permission blocks dispatch.
6. Provider/account/credential identity cannot substitute for Permission grantor identity.
7. The date converts to an exact half-open interval using pinned trusted timezone rules, never process/account/adapter defaults.
8. Ambiguous or nonexistent local-midnight boundaries fail closed without connector dispatch.
9. Timed boundary-touching and midnight/multi-day overlap cases follow the canonical half-open predicate.
10. All-day events normalize through trusted timezone/rules metadata and ambiguous/nonexistent all-day boundaries fail closed.
11. Recurring masters are expanded into complete bounded concrete occurrences; moved exceptions, cancellations, and duplicate representations behave correctly.
12. A master-only or incomplete recurrence provider fails closed.
13. Provider query semantics are complete for canonical overlap while remaining bounded; unbounded-history compensation is prohibited.
14. Pagination completes only with authoritative terminal/completeness evidence; truncation, token inconsistency, cap exhaustion without completeness, or early termination fails closed.
15. Multi-page acquisition proves one coherent provider snapshot/revision (or equivalent change-fenced view); terminal pagination alone is insufficient.
16. A concurrent calendar mutation between page requests cannot cause skipped/duplicated/mixed-snapshot results to be admitted; the acquisition restarts from a fresh bounded traversal or fails closed.
17. Bounded pagination restart discards all prior partial page material and cannot mix snapshots.
18. Partial or incoherent pages cannot produce a settled checked schedule.
19. Acquisition records `acquisition_started_at`; an authoritative provider `snapshot_as_of` is retained when available and trusted.
20. Freshness age uses `snapshot_as_of` when authoritative, otherwise conservatively uses `acquisition_started_at`; terminal-page/capture-commit time cannot make an older snapshot appear fresh.
21. A mutation after snapshot pinning but before the terminal page does not change the snapshot's freshness anchor, and a long traversal can become stale before capture completion.
22. `WorldSourceCapture` retains acquisition/completeness/coherency/freshness-anchor provenance without retaining disallowed provider fields.
23. Provider descriptions, attendee identities, conference data, attachments, reminders, private notes, locations, and unrelated metadata are discarded before canonical capture under the first-slice schema.
24. Disallowed raw personal fields remain ephemeral inside the trusted adapter and never enter logs, traces, metrics payloads, caches, retry stores, crash diagnostics, analytics, or other non-canonical durable/telemetry paths.
25. An adapter that cannot enforce non-canonical minimization is rejected for the first slice.
26. Model context contains only the normalized schedule fields required for the answer and no credential secret.
27. The answer remains traceable through Investigation → Observation → WorldSourceCapture → EvidenceItem → WorldResult → ContextProjection.
28. Observation authority provenance durably records the exact capability/policy/resource/Permission/credential/time decisions used for the concrete acquisition.
29. Calendar content creates no MemoryClaim/PersonClaim automatically.
30. Another interaction cannot reuse the personal-world result as generic context.
31. Process loss after capture/result but before projection evaluates current freshness from `freshness_anchor_at` before new projection construction.
32. Tightening freshness policy invalidates recovered capture/result reuse even when historical admission metadata still says fresh.
33. Process loss after projection but before model generation independently rechecks current freshness from the same anchor before new ModelInvocation.
34. A policy change or elapsed time between projection and generation can invalidate the projection without mutating historical provenance.
35. A durable GeneratedOutput/CompanionOutput that becomes stale before any payload dispatch is not newly presented as an unqualified current answer; it is reacquired/regenerated only while current disclosure/read authority permits that path.
36. Permission revocation, resource unbinding, relationship mismatch, or disclosure-policy denial after generation but before any payload dispatch blocks delivery even when freshness remains valid.
37. Disclosure-authority failure does not delete historical generated/evidence state and does not trigger an unauthorized reacquisition.
38. Before a payload-bearing presentation transport, a durable presentation attempt/fence exists and records the current freshness/disclosure decision provenance.
39. A process loss after the sink accepts a payload but before the host receives/commits the acceptance receipt recovers as `UNKNOWN_PRESENTATION_ACCEPTANCE`, not definitely undisclosed and not presented.
40. The F5 first-party sink supports content-free authoritative status lookup by `presentation_key`; a sink requiring payload resend to recover acceptance is rejected.
41. If disclosure Permission is revoked after an uncertain presentation dispatch, recovery performs no payload resend; it may use only the content-free acceptance-status lookup.
42. If the lookup proves the sink had already accepted the original authorized presentation, recovery commits exactly one historical `COMPANION_PRESENTED_OUTPUT` linked to the original attempt/acceptance evidence without redisclosing the payload.
43. If the lookup proves `NOT_ACCEPTED` and current disclosure authority is revoked, no Timeline presentation is committed and no payload retry occurs.
44. If lookup remains `UNKNOWN`, the runtime preserves uncertainty and does not fabricate presentation or violate current disclosure authority.
45. Already-presented historical Timeline/evidence state is not deleted or rewritten when Permission, disclosure authority, or freshness later changes.
46. Strong observational language is impossible without authorized, coherent, complete, evidence-backed, current-eligible personal-world support and mechanically truthful presentation provenance.

Passing F5.A authorizes work on F5.B. It does not close F5.

# 3. F5.B — One bounded calendar mutation

## 3.1 Objective and grammar

After F5.A is stable, add one effectful capability:

```text
calendar.event.create
```

The first write grammar uses explicit offset-aware timestamps:

```text
"Add 'Dentist' to my calendar from 2026-09-10T15:00:00+03:00 to 2026-09-10T15:30:00+03:00."
```

The host normalizes semantic intent into one immutable `Action`. A connector call or model tool call is never direct execution authority.

The immutable Action pins at least:

```text
action_id
selected PersonalResourceBinding
summary/title
start timestamp with explicit offset
end timestamp with explicit offset
normalized start instant
normalized end instant
capability contract/version
source interaction/ref
action_digest
```

The explicit offsets are part of semantic intent. An adapter may translate representation for the provider but may not substitute process-local, account-default, or calendar-default time semantics.

Natural-language timezone inference, floating local times, recurrence, attendees, conferencing, reminders, edits, deletes, and free-form scheduling remain outside the first write slice.

## 3.2 Write Permission provenance

Write Permission is separate from read Permission.

A write Permission is authoritative only when admitted through the same trusted grant-boundary principles as F5.A, with provenance binding:

```text
holder CompanionPerson
calendar.event.create capability / WRITE operation class
selected PersonalResourceBinding
relationship / counterpart
authorized grantor
trusted grant ceremony/source
policy/version
expiry/constraints
```

A read Permission, provider scope, credential ownership, prior successful write, conversation history, or model assertion cannot authorize the create Action.

## 3.3 Approval is semantic consent, not an Action-ID token

F5.B requires operation-specific Approval for the exact immutable Action.

Approval validity requires both trusted approver authority and proof that the approver was presented a faithful semantic consent surface for that Action.

### Authorized approver

For the first F5.B slice, the authorized approver is the counterpart bound to the Action's relationship/resource through the trusted first-party identity path.

Broader delegation, shared-calendar approval, guardianship, organizational approval, and multi-party authorization remain outside the slice.

Credential ownership, provider account identity, model fields, historical conversation, memory, relationship familiarity, or possession of `action_id` cannot establish approver authority.

### Approval presentation provenance

Before approval can be admitted, the trusted first-party approval ceremony creates immutable presentation provenance conceptually equivalent to:

```text
ApprovalPresentation {
    approval_presentation_id
    action_id
    action_digest
    capability = calendar.event.create
    effect_class = WRITE / MUTATION
    selected PersonalResourceBinding
    target calendar display identity sufficient for human distinction
    title/summary
    start offset-aware timestamp
    end offset-aware timestamp
    normalized start/end instants
    canonical consent-rendering version
    canonical consent payload digest
    presented_to_counterpart_id
    presented_at
    presentation_acceptance_ref
}
```

The canonical consent payload must faithfully contain every effect-relevant Action field. A surface may add explanatory text, but it may not omit, substitute, truncate, reorder ambiguously, or misrepresent the semantic target/effect.

The Approval then binds:

```text
exact action_id / action_digest
exact approval_presentation_id / consent payload digest
authorized approver_ref
trusted approval ceremony/source
relationship/resource
policy/version
granted_at
expires_at?
```

Approval is invalid if the trusted presented semantic content does not mechanically equal the corresponding immutable Action semantics.

A materially changed resource, title, start/end representation or instant, capability/effect class, or other effect-relevant field creates a new Action and requires a new approval presentation and Approval.

A model-supplied confirmation token, client-supplied arbitrary Action ID, hidden tool argument, provider response, or UI button click without faithful semantic presentation is not sufficient Approval.

## 3.4 Dispatch-time authority and durable attempt provenance

For **every** concrete external mutation dispatch, including retry after restart, the host immediately re-evaluates:

```text
current Host Capability
AND current AI Capability Policy
AND current Resource Scope
AND current trusted write Permission
AND current Approval validity for exact Action
AND ApprovalPresentation semantic equivalence with exact Action
AND current authorized-approver eligibility
AND current Action constraints
AND usable CredentialBinding
AND sufficient provider technical scope
```

A prior successful authority decision is historical provenance, not a permanent dispatch token.

Each `ExecutionAttempt` durably records immutable authority-decision provenance sufficient to reconstruct why that exact attempt was allowed without consulting mutable current configuration.

Conceptually:

```text
ExecutionAttemptAuthority {
    execution_attempt_id
    action_id
    capability_ref + contract/version
    ai_policy_decision_ref/version
    resource_scope_decision_ref/version
    write_permission_ref + trusted grant provenance ref/version
    approval_ref
    approval_presentation_ref + consent payload digest
    authorized_approver decision ref/version
    credential_binding_id
    provider_scope_snapshot/reference
    action_constraint_evaluation ref/version
    authority_evaluated_at
}
```

The attempt retains these refs/snapshots even if current policy, Permission, Approval, credentials, provider scope, or relationship configuration later changes.

Historical attempt provenance explains why dispatch was allowed then. It does not authorize another dispatch now.

## 3.5 Action-specific external correlation

The first F5.B adapter must provide a recoverable capability-specific correlation mechanism tied to the exact `Action`.

Before crossing the external dispatch boundary, the host durably establishes:

```text
K(A1)
```

where `K(A1)` is unique to Action `A1` and is not derived solely from semantic payload equality.

Examples include a provider-supported idempotency/correlation key, client-chosen operation/event identifier, or another capability-specific marker that remains usable after process loss.

An adapter whose only unique identifier is learned ephemerally after a successful response and cannot be recovered from pre-dispatch correlation is ineligible for the first F5.B slice.

Retries of the same Action reuse the same external operation identity only when the trusted capability contract defines that behavior as safe.

Action correlation is not a substitute for the Alsoul-side dispatch serialization fence defined below.

## 3.6 Per-Action dispatch serialization and terminal guard

The first F5.B slice requires an atomic durable guard keyed by `action_id` that serializes dispatch eligibility across workers, retries, process restarts, and provider adapters.

The implementation may use a unique row, compare-and-swap revision, transactional ownership record, database lock protocol, or equivalent mechanism, but its semantics must enforce:

```text
at most one dispatch-eligible / may-have-dispatched attempt for an Action at a time
AND no new dispatch after CONFIRMED_EFFECT
AND no new dispatch while any prior attempt is UNKNOWN_EFFECT / DISPATCH_FENCED without conclusive resolution
```

A conceptual state machine is:

```text
NO_ACTIVE_ATTEMPT
    → atomically claim Action for PREPARED attempt

PREPARED, no dispatch fence
    → may be durably abandoned/released because transport could not have observed it
    → a later attempt still requires a new current authority gate

DISPATCH_FENCED / UNKNOWN_EFFECT
    → Action remains dispatch-locked
    → reconciliation only; no second mutation attempt

CONFIRMED_EFFECT
    → Action is terminal for mutation dispatch
    → all future dispatch attempts are rejected

CONFIRMED_NO_EFFECT
    → retry may become eligible only through an explicit atomic retry transition
    → new current authority/Approval validity/Action constraints are re-evaluated
    → still only one new active attempt may be claimed
```

A correlated semantic mismatch or other divergent external consequence remains unresolved/unknown for the intended Action and therefore keeps the Action dispatch-locked.

Creating a PREPARED `ExecutionAttempt` and claiming the per-Action dispatch slot must be atomic enough that two workers cannot both obtain dispatch eligibility. Committing `DISPATCH_FENCED` must preserve that exclusive Action ownership across crashes.

Provider idempotency support does not weaken this requirement. `K(A1)` may reduce duplicate external consequences, but Alsoul must not rely on optional provider idempotency to serialize its own concurrent workers.

## 3.7 ExecutionAttempt and durable dispatch-start fence

Each actual transport dispatch is represented by one distinct immutable `ExecutionAttempt` under the same Action.

Conceptually:

```text
Action A1
├── ExecutionAttempt X1 → K(A1)
└── ExecutionAttempt X2 → K(A1)   # only after X1 is conclusively no-effect and the Action guard permits retry
```

The trusted executor persists the attempt, Action correlation, and exclusive Action dispatch claim before dispatch.

Immediately before transport:

```text
ExecutionAttempt PREPARED with K(A1)
↓
exclusive per-Action dispatch claim is current
↓
revalidate complete current authority gate
↓
persist attempt-level authority provenance
↓
commit dispatch_started_at / DISPATCH_FENCED while preserving Action lock
↓
only then may provider transport observe the request
```

A transport adapter must never be called from an unfenced attempt or from an attempt that no longer owns the exclusive per-Action dispatch claim.

Recovery distinguishes:

```text
PREPARED, no dispatch fence
    → provider could not have observed this attempt
    → durable abandon/release is possible before a new attempt

DISPATCH_FENCED, no conclusive evidence
    → UNKNOWN_EFFECT; Action remains dispatch-locked
    → reconcile through K(A1); no blind retry
```

The fence is conservative: a crash after the fence but before actual transport still recovers as may-have-dispatched.

## 3.8 Effect confirmation requires correlation and semantic equivalence

`CONFIRMED_EFFECT` requires evidence that establishes **both**:

```text
1. unique Action correlation
AND
2. capability-specific semantic equivalence to the immutable Action
```

For the first calendar-create slice, evidence supporting `CONFIRMED_EFFECT` must establish at least:

```text
observed external event is uniquely correlated with K(A1)/Action A1
AND observed resource == Action.selected PersonalResourceBinding
AND normalized observed title/summary == Action title/summary
AND normalized observed start instant == Action normalized start instant
AND normalized observed end instant == Action normalized end instant
AND capability-specific create semantics otherwise match the intended Action
```

A correlated event with the wrong resource, wrong title, wrong start/end instant, or other material semantic mismatch is **not** `CONFIRMED_EFFECT` for the intended Action.

Because an unintended correlated external consequence may nevertheless exist, such a mismatch is also not automatically `CONFIRMED_NO_EFFECT`. Under the first slice it remains unresolved for the intended Action, is recorded with divergent evidence, remains effectively `UNKNOWN_EFFECT`, keeps the Action dispatch-locked, and blocks blind retry pending explicit reconciliation or a later compensation contract.

Visible field similarity without unique Action correlation is also insufficient, because an identical event may pre-exist or be independently created.

## 3.9 Durable Effect evidence ordering

After transport begins, provider response/reconciliation evidence becomes durable before Effect admission.

The first committed `CONFIRMED_EFFECT` or `CONFIRMED_NO_EFFECT` state must already have its required supporting evidence recoverably linked.

Conceptually:

```text
provider response / reconciliation observation
↓
durable evidence with Action correlation
↓
capability-specific semantic/negative proof validation
↓
Effect state + required SUPPORTS relation committed atomically enough
that no visible Effect state exists without its proof
```

The storage design may use one transaction, dependent insertion with integrity constraints, or another mechanism with equivalent crash semantics. It must not commit Effect state first and attach evidence later.

If sufficient evidence is durable but the process dies before Effect admission, recovery admits the corresponding Effect state from that evidence without redispatch.

A committed `CONFIRMED_EFFECT` atomically or transactionally advances the per-Action dispatch guard to terminal so no concurrent or later worker can dispatch the Action again.

A committed `CONFIRMED_NO_EFFECT` may release the Action for a later retry only through the explicit retry transition defined in §3.6; it is not an implicit redispatch signal.

## 3.10 UNKNOWN_EFFECT and reconciliation

A timeout or ambiguous transport after possible dispatch produces:

```text
UNKNOWN_EFFECT
```

not failure and not success.

`UNKNOWN_EFFECT` survives restart, retains the per-Action dispatch lock, and blocks blind mutation retry.

Reconciliation uses separately authorized read-side observation:

```text
UNKNOWN_EFFECT
↓
current authority for calendar.events.read
↓
Investigation / Observation / bounded coherent complete acquisition
↓
Action-correlated capability-specific evidence
↓
CONFIRMED_EFFECT
OR CONFIRMED_NO_EFFECT
OR still UNKNOWN_EFFECT
```

Reconciliation is observation, not a second create Action. If current read authority is unavailable, reconciliation remains blocked/unknown rather than bypassing authority.

## 3.11 Capability-sufficient `CONFIRMED_NO_EFFECT`

Absence from an ordinary calendar listing is not automatically proof that a create Action had no effect.

The trusted capability contract must explicitly define whether authoritative negative confirmation is supported and, if so, the exact predicate.

Negative-confirmation metadata includes at least:

```text
negative_confirmation_supported
Action-correlation lookup semantics using K(A1)
read-after-write consistency model
settling/visibility requirement or authoritative operation-status semantics
maximum authoritative observation horizon where applicable
predicate that proves the operation was not applied
```

`CONFIRMED_NO_EFFECT` is permitted only when capability-specific evidence establishes that the Action-correlated operation did not produce the intended external consequence **after** any required consistency/settling condition has been satisfied.

Examples of potentially sufficient proof, only when declared authoritative by the capability contract, include:

```text
provider operation-status lookup for K(A1) says terminal NOT_APPLIED
or
provider correlation lookup after guaranteed visibility horizon proves no correlated event/operation exists
```

The following are insufficient by themselves:

```text
first read immediately after timeout finds no event
ordinary event listing lacks a semantic match
absence before provider consistency/visibility is guaranteed
lack of a response
transport failure
```

If the provider offers only eventual visibility with no bounded authoritative no-effect predicate, then absence remains `UNKNOWN_EFFECT`; the first slice does not unlock retry by waiting an arbitrary guessed delay.

A delayed-visibility event that appears after an early empty read must never allow a premature `CONFIRMED_NO_EFFECT` or duplicate retry.

When `CONFIRMED_NO_EFFECT` is authoritative, a later retry still requires the per-Action atomic retry transition, a new current authority evaluation, current Approval validity, and a new `ExecutionAttempt`. Concurrent workers cannot both consume the same no-effect state to create separate retries.

## 3.12 Required crash and concurrency behavior

```text
crash while PREPARED, before dispatch fence
    → no external dispatch possible for this attempt
    → abandon/release PREPARED claim durably
    → later retry requires a new current authority gate

crash after dispatch fence, before transport invocation
    → UNKNOWN_EFFECT conservatively
    → Action remains dispatch-locked
    → reconcile using K(A1); no blind retry

crash after transport invocation, before conclusive evidence commit
    → UNKNOWN_EFFECT
    → Action remains dispatch-locked
    → reconcile using K(A1); no blind retry

crash after sufficient evidence commit, before Effect-state commit
    → recover evidence and admit the justified Effect state
    → do not redispatch

crash after CONFIRMED_EFFECT commit
    → Effect state and SUPPORTS evidence are recoverable
    → Action guard is terminal; no redispatch
```

Two workers racing to execute the same Action cannot both create dispatch-eligible attempts. A worker that loses the Action claim performs no transport call.

Presentation/model failure after a confirmed external Effect never causes the Action to execute again.

## 3.13 Strong completion language and fail-closed dispatch

```text
"I created the event."
```

is allowed only after `CONFIRMED_EFFECT` has durable evidence satisfying both Action correlation and semantic equivalence.

A timeout, ambiguous provider state, early empty reconciliation read, correlated semantic mismatch, incomplete evidence, or concurrent losing worker cannot justify strong completion language.

No mutation transport dispatch occurs when any required layer is absent, unreadable, denied, expired, revoked, unusable, mismatched, or not exclusively owned, including:

- semantic capability unavailable or effect contract untrusted;
- AI policy denial;
- target resource outside current scope;
- write Permission invalid or its grant provenance/authorized grantor invalid;
- required Approval invalid, expired, revoked, or for another Action/resource/relationship;
- ApprovalPresentation missing or semantically mismatched to the exact Action;
- approver unauthorized or approver eligibility unreadable;
- Action constraints violated;
- CredentialBinding unavailable/unusable;
- provider technical scope insufficient;
- durable Action correlation unavailable;
- attempt-level authority provenance cannot be committed;
- exclusive per-Action dispatch claim cannot be acquired or is already held by a may-have-dispatched attempt;
- Action already has `CONFIRMED_EFFECT`;
- Action has unresolved `UNKNOWN_EFFECT`/divergent-effect evidence;
- dispatch-start fence cannot be committed.

These conditions are re-evaluated before every retry.

## 3.14 F5.B acceptance bar

F5.B is complete only when executable tests prove all of the following:

1. Read authority cannot authorize write.
2. One immutable Action captures the exact calendar-create semantics, including selected resource, title, explicit-offset timestamps, normalized instants, source, and capability version.
3. Time semantics are immune to process/account/adapter defaults.
4. Any material Action change requires a new approval presentation and Approval.
5. Approval is invalid unless trusted immutable presentation provenance shows every effect-relevant Action field was faithfully presented to the authorized counterpart.
6. Omitted, tampered, stale, truncated, wrong-resource, wrong-title, wrong-time, or wrong-effect-class consent rendering cannot authorize dispatch even when `action_id` matches.
7. A forged/copied Action ID cannot substitute for trusted Approval provenance.
8. Approval from another relationship/resource or unauthorized approver cannot authorize this Action.
9. Credential/provider identity cannot substitute for approver identity.
10. Write Permission has trusted authorized-grantor provenance; cross-relationship/resource or forged grants fail closed.
11. Every dispatch/retry re-evaluates the complete current authority gate.
12. Revocation/expiry of Permission, Approval, approver eligibility, policy, resource scope, or provider feasibility between attempts blocks retry before transport.
13. Every ExecutionAttempt durably preserves exact Capability, AI policy, Resource Scope, Permission, Approval, ApprovalPresentation, approver decision, CredentialBinding, provider scope, Action constraints, source Action, and authority-evaluation provenance used for that attempt.
14. Historical attempt authority provenance can explain the prior dispatch without consulting mutable current configuration and does not authorize a later dispatch.
15. Action-specific external correlation is durably established before mutation dispatch.
16. An adapter relying only on a response-learned unrecoverable unique identifier is ineligible.
17. At most one worker can atomically claim dispatch eligibility for one Action at a time; a concurrent loser cannot create/fence/dispatch a second active attempt.
18. Provider idempotency does not substitute for the per-Action Alsoul dispatch guard.
19. Transport is impossible before a durable dispatch-start fence and without current ownership of the Action dispatch claim.
20. Crash before the fence is known not to have reached transport; crash after the fence is conservatively `UNKNOWN_EFFECT` and keeps the Action locked.
21. `UNKNOWN_EFFECT` survives restart and blocks all competing/retry dispatches until conclusive reconciliation.
22. `CONFIRMED_EFFECT` atomically makes the Action terminal for future mutation dispatch.
23. A later worker after `CONFIRMED_EFFECT` cannot create or dispatch a new attempt for that Action.
24. `CONFIRMED_NO_EFFECT` permits at most one later retry claim, only through an explicit atomic retry transition and new current authority validation.
25. Two workers cannot both consume one `CONFIRMED_NO_EFFECT` state to create duplicate retries.
26. An identical pre-existing event cannot be mistaken for this Action's Effect.
27. `CONFIRMED_EFFECT` requires unique Action correlation **and** semantic equality with the normalized intended resource/title/start/end/effect semantics.
28. A uniquely correlated event on the wrong resource, with wrong title, wrong start, or wrong end cannot produce `CONFIRMED_EFFECT` or strong completion language.
29. Correlated semantic mismatch remains unresolved for the intended Action, retains the dispatch lock, and cannot unlock blind retry.
30. Provider response/reconciliation evidence is durable before Effect-state admission.
31. The first visible confirmed Effect state already has its required SUPPORTS evidence.
32. Crash after evidence commit but before Effect-state commit recovers from evidence without redispatch.
33. `CONFIRMED_NO_EFFECT` is admitted only under an explicit capability-specific authoritative negative-evidence predicate.
34. Provider settling/read-after-write consistency requirements are mechanically enforced before negative confirmation.
35. An early empty read during delayed visibility remains `UNKNOWN_EFFECT` and cannot unlock retry.
36. If authoritative negative proof is unavailable, absence remains `UNKNOWN_EFFECT` rather than being guessed into no-effect.
37. Reconciliation requires current read authority and uses bounded coherent complete personal-calendar acquisition semantics from F5.A.
38. Presentation/model failure after confirmed Effect cannot execute the Action again.
39. Credential rotation may change execution binding without redefining Action or Person.
40. Strong completion language is mechanically blocked until the corresponding evidence-backed `CONFIRMED_EFFECT` exists.

# 4. F5 closure bar

F5 closes only when F5.A and F5.B are both green and executable evidence demonstrates:

- persistent Person/Relationship identity remains separate from account/resource/credential identity;
- personal-world read authority is explicit, current, provenance-backed, and fail-closed;
- trusted time semantics are explicit and deterministic;
- calendar membership is provider-independent and boundary-correct;
- recurrence expansion is concrete, bounded, and complete;
- pagination/truncation completeness is provable before settled schedule claims;
- multi-page reads prove one coherent snapshot/revision or fail closed on concurrent mutation;
- freshness age is anchored to the coherent snapshot's authoritative as-of instant or conservatively to acquisition start, never traversal completion;
- personal-world capture is field-minimized before canonical admission/model exposure;
- disallowed raw personal fields remain ephemeral and cannot leak into non-canonical logs, traces, caches, queues, diagnostics, or analytics;
- personal data does not silently broaden memory scope;
- freshness is revalidated across capture/result/projection/model boundaries that create new cognition;
- every payload-bearing first presentation attempt requires current freshness and current disclosure authority;
- revocation/resource-unbinding after generation blocks new disclosure without rewriting history;
- uncertain sink acceptance is represented durably and reconciled through content-free status lookup rather than forced payload resend;
- a prior accepted presentation may be recorded as historical truth after revocation without redisclosing its payload;
- read and write authority are independently scoped;
- Permission and Approval come from trusted authorized grant/approval paths;
- approval consent is bound to the exact semantic content actually presented to the counterpart;
- every effectful dispatch persists exact attempt-level authority provenance;
- authority is re-evaluated at every external dispatch;
- a durable per-Action guard serializes concurrent dispatch and blocks redispatch after possible/confirmed effect;
- attempted operation and established external Effect remain distinct;
- dispatch uncertainty survives restart and blocks blind replay;
- effect confirmation requires Action correlation and semantic equivalence;
- no-effect confirmation requires capability-sufficient authoritative negative proof;
- delayed provider visibility cannot prematurely unlock a mutation retry;
- effect evidence precedes and supports the first committed confirmed Effect state;
- credential removal/rebinding does not redefine Person identity;
- capability effect classification comes from trusted semantic metadata rather than provider/tool naming;
- access to an application/resource does not redefine Person or Relationship identity.

# 5. Explicit exclusions after this checkpoint

This checkpoint does not authorize:

- broad personal-world indexing;
- email sending;
- file mutation;
- contact editing;
- multiple-calendar natural-language routing;
- relative-date grammar without a trusted temporal-reference contract;
- autonomous background access;
- durable delegated work;
- recurring triggers;
- proactive contact;
- semantic history retrieval;
- general connector/plugin execution;
- compensation workflows for divergent external effects;
- shared-resource or delegated approval semantics;
- rich modality or embodiment.

Each later expansion must inherit the same identity, authority, provenance, minimization, freshness, disclosure, presentation-truth, approval, execution, effect, concurrency, and recovery boundaries rather than bypassing them.
