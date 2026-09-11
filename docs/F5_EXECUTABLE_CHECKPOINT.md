# F5 Executable Checkpoint — Personal World + Trust

**Status:** Converged implementation contract; implementation pending  
**Publication:** GitHub-safe  
**Predecessor:** [F4 Exit Audit](F4_EXIT_AUDIT.md)  
**Architecture basis:** Decisions 06.A–06.C, 07.A–07.B, 08.A–08.B, 11.A, 14.A, and 15.A–15.B

F5 begins after executable F4 closure. Its purpose is not broad connector coverage. Its purpose is to prove that Alsoul can enter the counterpart's personal digital world under explicit authority while preserving Person continuity, epistemic honesty, provenance, minimization, recovery, and fail-closed behavior.

This file is the single normative F5 executable checkpoint. No separate amendment or precedence chain is required.

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

Read authority does not imply write authority. Access to one personal resource does not imply access to another. Access to personal data does not make that data durable personal memory. Prior authority does not authorize later acquisition, model egress, presentation, mutation dispatch, or retry.

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
Permission validity ≠ current RelationshipState / resource-binding validity
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
projection freshness ≠ authority to disclose projection data to a model route
prior model route authority ≠ authority for a later model dispatch or changed route
model-generated schedule text ≠ adopted schedule truth
first generation ≠ indefinitely authorized first presentation
presentation payload dispatch ≠ sink acceptance
unknown presentation outcome ≠ presented
unknown presentation outcome ≠ definitely undisclosed
point-in-time negative sink lookup ≠ terminal non-acceptance
stable presentation_key ≠ presentation-attempt transport generation
Action correlation ≠ concurrency/idempotency fence
```

Authority is monotonic narrowing:

```text
Host Capability
∩ AI Capability Policy
∩ Resource Scope
∩ User Permission
∩ operation-specific Approval when required
= maximum authority for that operation
```

Personal-data disclosure is additionally narrowed at each egress boundary by the current policy and the concrete destination route. No lower layer may manufacture authority that is absent, unreadable, expired, revoked, mismatched, or denied above it.

F5 is split into two executable tranches:

```text
F5.A  personal-world observation
F5.B  bounded external action + effect reconciliation
```

F5.A is the immediate implementation target. F5.B starts only after the read-side authority, provenance, minimization, completeness, coherent-snapshot, model-egress, disclosure, presentation-reconciliation, and recovery boundaries are executable. F5 is not closed until both tranches satisfy their acceptance bars.

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
current freshness + current personal-data/model-egress authority for exact model route
↓
ModelInvocation / GeneratedOutput
↓
structured schedule-plan validation / deterministic schedule rendering
↓
CompanionOutput adoption
↓
current freshness + current first-party disclosure authority
↓
first-party presentation dispatch / acceptance reconciliation
↓
first accepted presentation
```

The connector performs acquisition only. It does not decide semantic routing, resource selection, Permission, memory admission, time interpretation, completeness policy, projection eligibility, model-egress authority, first-party disclosure authority, presentation truth, or what the model may see.

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

An adapter is ineligible for the first slice when it cannot provide a bounded complete and coherent view of the requested window, cannot provide a trustworthy freshness anchor, cannot enforce the field-minimization contract before persistence/telemetry, or cannot satisfy required authority/provenance semantics.

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

For input date `D`, the host resolves:

```text
D 00:00
(D + 1 day) 00:00
```

under the pinned timezone and rules version. F5.A accepts the date only when both boundaries resolve to exactly one valid instant. If either boundary is nonexistent or ambiguous, the request fails closed before connector dispatch. The first slice does not guess an offset, roll a boundary, or accept library-specific default behavior.

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

A `CredentialBinding` establishes how the trusted host can authenticate to the selected external system. It does not define the user, relationship, Permission, resource, or capability.

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
current RelationshipState remains active / valid for the counterpart
AND selected PersonalResourceBinding is ACTIVE and still associated with that relationship/counterpart
AND Permission present and readable
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

Cross-relationship, cross-resource, forged, unreadable, revoked, mismatched, ended-relationship, inactive-binding, or unbound-resource state fails closed.

The first slice does not require a separate per-interaction Approval for this bounded read. The active user request plus standing Permission is sufficient under this contract. That rule does not generalize to writes or to arbitrary personal-data egress.

## 2.7 Read authority gate and provenance

Immediately before each external read transport request, the host evaluates:

```text
same trusted counterpart / current RelationshipState remains valid for this interaction
AND selected PersonalResourceBinding remains ACTIVE and currently associated with that relationship/counterpart
AND calendar.events.read Capability is available and trusted
AND current AI Capability Policy permits the read
AND selected resource is inside current Resource Scope
AND trusted current Permission authorizes the read
AND usable CredentialBinding exists
AND provider technical scope is sufficient
AND exact requested interval satisfies all constraints
```

Provider technical scope is a ceiling, not Alsoul authority.

One successful semantic `Observation` retains immutable authority provenance sufficient to reconstruct why the read was authorized without consulting mutable current configuration. Durable authority provenance includes at least:

```text
Capability ref + contract/version
AI Capability Policy decision ref/version
Resource Scope decision ref/version
RelationshipState current-validity decision ref/version
PersonalResourceBinding active-association decision ref/version
Permission ref + trusted grant provenance
PersonalResourceBinding
CredentialBinding ref
provider technical-scope snapshot/reference
source interaction
trusted timezone/rules/window
first and last authority-evaluation times
```

For multi-page acquisition, page requests remain children of the same Observation/acquisition identity while each transport dispatch records its own current authority evaluation or a mechanically linked evaluation record. The page-specific authority record includes the current RelationshipState and active resource-binding decisions; a relationship end, resource deactivation, or unbinding between pages blocks the next transport before it can observe personal data.

Authority provenance explains why access was allowed. It does not prove calendar content and does not authorize later model egress or presentation.

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

A normalized occurrence retains only recurrence identity/provenance required to prevent omission or duplication, for example:

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

Current read authority is re-evaluated before every page transport dispatch, including current RelationshipState validity and active/current association of the selected PersonalResourceBinding. Revocation, relationship termination, resource deactivation/unbinding, or unreadability during pagination aborts the acquisition; partial pages cannot be promoted into a complete `WorldResult`.

### Coherent-snapshot requirement

A terminal page token proves traversal completion only when the pages belong to one coherent logical view. The first slice therefore requires the capability contract to provide one of:

```text
snapshot-consistent cursor/session identity
OR provider revision/version fence stable across all pages
OR equivalent authoritative snapshot token
OR deterministic change detection proving no membership-affecting mutation occurred across pagination
```

Pages from different provider revisions/snapshots must never be silently combined.

If the provider uses offset/page-number pagination without snapshot semantics, the adapter must detect any membership-affecting change that could skip, duplicate, add, remove, reorder, or replace an event while the logical acquisition is in progress. If coherent completeness cannot be proven, the acquisition fails closed.

A capability may permit a bounded restart only when:

```text
no WorldSourceCapture / WorldResult for the failed traversal has been admitted
current read authority is re-evaluated before restarted transport
restart count is bounded by trusted capability policy
all prior partial page material is discarded
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

If the provider exposes a stable revision but no trustworthy as-of instant, `acquisition_started_at` is the required conservative anchor. If a provider timestamp has an ambiguous or untrusted relationship to the coherent snapshot, it is ignored for freshness and acquisition start applies.

A calendar mutation after snapshot pinning may correctly be absent from that coherent snapshot; freshness policy ages the result from the snapshot's actual as-of instant or conservative acquisition start. A sufficiently long traversal can therefore yield a complete coherent result that is already stale by capture completion.

`WorldSourceCapture` retains completeness/coherency/time provenance sufficient to establish:

```text
one Observation/acquisition identity
acquisition_started_at
snapshot/session/revision identity or equivalent coherency proof
authoritative snapshot_as_of when available
freshness_anchor_at and derivation basis
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
organizer identity
conference/join metadata
attachments
reminders
private notes
extended/custom properties
location
provider-side unrelated metadata
```

If the provider necessarily returns disallowed fields, those fields may exist only ephemerally inside the trusted adapter boundary for the minimum time required to parse and normalize the response. They are discarded before canonical capture.

The same minimization boundary applies to non-canonical persistence and telemetry. Disallowed raw personal fields must not be written or emitted to:

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

If an adapter/runtime cannot enforce this rule, that integration is ineligible. Debug mode, exception serialization, and transport middleware do not create an exception.

`ContextProjection` is stricter still. It exposes only user-facing schedule fields needed for the bounded answer, normally normalized title, time/all-day semantics, and source classification. Provider identifiers and recurrence mechanics remain outside model context unless a later contract explicitly requires them.

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

Recovery resumes from the furthest trustworthy durable stage, but every pre-output stage that would create new cognition from historical personal-calendar material is gated by the trusted current freshness policy.

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

Before a new `ModelInvocation` from a previously committed personal-calendar `ContextProjection` with no durable `GeneratedOutput`, the runtime independently rechecks current freshness of the underlying observation/result from `freshness_anchor_at`.

A policy change or elapsed time between projection construction and model invocation may invalidate that immutable projection. The stale projection remains historical provenance; new authorized acquisition/result/projection state is required for new current-state cognition.

Freshness alone does not authorize model disclosure. The separate model-egress gate below applies to every new model transport.

## 2.15 Current personal-data/model-egress authority

A `ContextProjection` containing personal calendar data is not automatically eligible to leave the trusted host boundary merely because acquisition was authorized or the projection is fresh.

Immediately before every model transport that would expose any personal-calendar projection material, including a retry after process loss or transport failure, the host evaluates a distinct current egress gate:

```text
same trusted counterpart / RelationshipState remains valid for the interaction
AND selected PersonalResourceBinding remains associated with that counterpart/relationship
AND current personal-data/model-egress policy permits this processing purpose
AND current trusted read Permission remains present, unexpired, unrevoked, relationship/resource-matched, and model-egress-eligible
AND the exact configured model route/provider is currently trusted and inside the allowed personal-data processing scope
AND the route's current data-handling/retention/residency constraints, when policy-relevant, satisfy the governing policy
AND current freshness eligibility still holds for the projection being sent
AND no explicit revocation or egress fence prohibits disclosure
```

The egress decision is route-specific. A prior decision for route `R1` does not authorize route `R2`, and a prior route that was once allowed does not remain allowed after policy, relationship, resource, or route eligibility changes.

A model tool name, model self-report, provider credential, prior successful invocation, or acquisition Permission alone cannot establish model-egress authority.

Every `ModelInvocation` that receives personal-calendar material retains immutable provenance sufficient to reconstruct why that exact egress was allowed, including at least:

```text
model_invocation_id
source ContextProjection / WorldResult lineage
counterpart / relationship ref
PersonalResourceBinding ref
freshness decision ref/version
current read Permission ref + trusted grant provenance
personal-data/model-egress policy decision ref/version
concrete model route/provider binding ref + route contract/version
route eligibility decision ref/version
dispatched_at
```

Credential secrets are never part of this provenance or model context.

If the model-egress gate fails or is unreadable:

```text
retain historical evidence/result/projection state
↓
do not dispatch personal data to the model
↓
do not create a GeneratedOutput that claims new cognition occurred
```

Model-egress denial by itself does not authorize or require reacquisition. A new acquisition occurs only when independently required by freshness/current-state recovery and current read authority permits it.

A lost model response does not make a retry inherit the old egress decision. Every retry that would transmit personal data is a new disclosure decision and re-evaluates the full current model-egress gate for the exact route.

## 2.16 Mechanically constrained schedule cognition and adoption

Personal-calendar truth is not entrusted to unconstrained generated prose.

The first F5.A slice retains the `ModelInvocation` boundary, but the model may produce only a bounded structured schedule plan. Schedule facts become adoptable only after mechanical validation against the exact `ContextProjection`.

Conceptually:

```text
CalendarAnswerPlanV1 {
    source_context_projection_id
    source_world_result_id
    requested_date
    ordered_occurrence_refs[]
    rendering_contract_version = DAY_SCHEDULE_V1
    framing_mode?              # optional bounded trusted enum; no factual payload
}
```

The structured plan does **not** carry authoritative title, time, resource, or event-detail overrides. Those facts are resolved only from the selected normalized projection after validation.

Before any `GeneratedOutput` can be adopted as `CompanionOutput`, the host mechanically verifies:

```text
source_context_projection_id == selected eligible ContextProjection
AND source_world_result_id matches that projection lineage
AND requested_date == canonical requested date
AND every ordered_occurrence_ref resolves to one selected normalized occurrence in that projection
AND every selected normalized occurrence is represented exactly once
AND no unknown / duplicate / out-of-window occurrence ref exists
AND rendering_contract_version is trusted/current for this slice
AND no model-supplied field can override normalized title/time/all-day/resource semantics
```

For a complete empty schedule, `ordered_occurrence_refs` is empty only when the coherent complete current `WorldResult` contains zero selected normalized occurrences.

The host then deterministically renders schedule facts from projection data. A model-selected `framing_mode`, when supported, is a bounded non-factual rendering option and cannot introduce or modify event propositions.

Instruction-like calendar titles are inert data. They are represented to the model and renderer as data fields, never as system/developer/user/tool instructions; the deterministic renderer escapes/quotes them according to its contract and does not execute or reinterpret their contents. A title such as an imperative remains only the title of an observed event.

If the structured plan is malformed, omits or invents an occurrence, references another window/resource, duplicates an occurrence, attempts a title/time override, or otherwise fails semantic equality, the generated result remains unadopted. The runtime does not fall back to raw model prose, does not create a truthful-looking `CompanionOutput`, and does not present unsupported schedule claims.

Source phrases such as “I checked your calendar” are admitted/rendered from validated acquisition/provenance state, not from model assertion.

## 2.17 First-presentation freshness, disclosure authority, and uncertain sink acceptance

A durable `GeneratedOutput` or unpresented `CompanionOutput` is immutable cognition, but it is not indefinitely eligible for first presentation of personal calendar material.

The F5 personal-data presentation contract extends the F4 first-party idempotent presentation boundary with explicit uncertain-acceptance reconciliation. The objective is to avoid unauthorized redisclosure and false historical claims when the sink may already have accepted a payload before an acknowledgement was lost.

### 2.17.1 Before any payload-bearing presentation transport

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

If disclosure authority fails or is unreadable, no payload-bearing presentation transport occurs and no reacquisition is attempted solely to bypass that denial.

### 2.17.2 Durable presentation attempt, transport generation, and dispatch uncertainty

Before a payload-bearing presentation transport can observe the payload, the host durably records a presentation attempt/fence conceptually equivalent to:

```text
PersonalPresentationAttempt {
    presentation_attempt_id
    presentation_attempt_generation
    presentation_transport_fence_scope_id
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

`presentation_key` remains the restart-stable semantic identity of the same `CompanionOutput`. `presentation_attempt_generation` / `presentation_transport_fence_scope_id` identifies the exact bounded transport epoch. Every payload-bearing transport request must carry both the stable semantic key and the exact attempt/fence generation identity.

Conceptually:

```text
send_personal_presentation(
    presentation_key,
    presentation_attempt_generation,
    presentation_transport_fence_scope_id,
    payload
)
```

The exact wire representation may differ, but the sink must be able to bind acceptance, terminal-negative status, cancellation/settling, and content-free lookup to the exact transport generation. A payload request from attempt `P1` cannot later be interpreted as transport from attempt `P2` merely because both share the same stable semantic `presentation_key`.

The exact schema may differ, but recovery must distinguish:

```text
no presentation dispatch fence
    → sink could not have observed this payload through this attempt generation

presentation dispatch fenced, no validated acceptance receipt
    → UNKNOWN_PRESENTATION_ACCEPTANCE

validated sink acceptance for exact attempt generation/fence scope
    → ACCEPTED

authoritative terminal content-free sink status proves prior attempt generation cannot be accepted
    → NOT_ACCEPTED
```

A transport timeout or lost acknowledgement after the presentation fence is not treated as definitely undisclosed and is not treated as presented.

### 2.17.3 Required content-free acceptance-status lookup

A first-party sink used for F5 personal-data presentation must preserve the F4 restart-stable semantic `presentation_key` contract and support an authoritative content-free acceptance-status lookup keyed by the exact presentation transport generation/fence scope.

Conceptually:

```text
lookup_presentation_status(
    presentation_key,
    presentation_attempt_generation,
    presentation_transport_fence_scope_id
)
    → ACCEPTED + acceptance evidence
    | NOT_ACCEPTED + terminal-negative evidence
    | UNKNOWN
```

The lookup request must not resend, echo, hash-expand, or otherwise disclose the personal payload. The response may contain only structural acceptance metadata sufficient to establish presentation truth, such as the presentation key, attempt generation/fence scope, acceptance state, sink receipt/reference, settling/cancellation reference, and relevant timestamps.

A validated acceptance receipt must bind the exact `presentation_key` and attempt generation/fence scope. An acceptance record for another generation cannot satisfy the current attempt merely because the payload digest or semantic key matches.

A sink that can recover acceptance only by resending the payload, or that cannot distinguish transport generations under one semantic `presentation_key`, is ineligible for F5 personal-data presentation.

### 2.17.4 `NOT_ACCEPTED` must be terminal against delayed acceptance

A point-in-time absence, eventually consistent negative index result, or observation that the sink has not accepted **yet** is not `NOT_ACCEPTED`.

`NOT_ACCEPTED` is authoritative only when the sink contract proves, for the covered uncertain presentation attempt generation/fence scope, that every payload transport already dispatched, queued, or in flight under that generation can no longer later become accepted without a new explicitly authorized payload transport under a new generation.

The first slice permits either:

```text
linearizable terminal per-key/per-attempt-generation negative status
OR
an authoritative cancellation + settling fence that proves all earlier transports in that generation are drained/cancelled and cannot later accept
```

Terminal-negative evidence retains at least:

```text
presentation_key
presentation_attempt_id
presentation_attempt_generation
presentation_transport_fence_scope_id
terminal-negative proof kind
settled/cancelled-through reference
status/consistency contract version
proved_at
```

If the sink cannot prove this terminality, recovery remains `UNKNOWN_PRESENTATION_ACCEPTANCE` even if a current lookup returns no acceptance.

An eligible sink must therefore make the following impossible:

```text
host records authoritative NOT_ACCEPTED for attempt generation P1/G1
↓
no new authorized payload transport for G1 occurs
↓
an old queued/in-flight transport from P1/G1 later becomes ACCEPTED
```

If the sink's consistency model permits that sequence, the sink is ineligible for the first F5 personal-data presentation slice.

A later explicitly authorized payload delivery, when allowed, is a new bounded presentation attempt generation after the terminal-negative fence. It reuses the same stable semantic `presentation_key` for the same `CompanionOutput` but receives a new attempt/generation/fence identity. Acceptance or terminality for the old generation cannot be reopened, transferred, or reclassified as truth for the new generation. The new attempt re-evaluates current freshness and current disclosure authority before any payload is sent.

### 2.17.5 Recovery of an uncertain presentation

When recovery finds `UNKNOWN_PRESENTATION_ACCEPTANCE`, it first performs the content-free status lookup for the exact attempt generation/fence scope. It does not resend the payload merely to recover a receipt.

If the lookup establishes `ACCEPTED`:

```text
persist exact-generation acceptance evidence
↓
commit/recover exactly one COMPANION_PRESENTED_OUTPUT Timeline event
```

This Timeline commit records a presentation the sink already accepted before or during the earlier authorized payload dispatch. It does not constitute a new personal-data disclosure and therefore does not require current calendar read/disclosure Permission merely to record historical truth.

The Timeline event/presentation provenance points to the original presentation attempt generation and sink acceptance evidence, including acceptance time when available. Revocation after that acceptance does not erase the historical event.

If the lookup establishes authoritative terminal `NOT_ACCEPTED`, no presentation event is committed. Any later payload send is a new bounded presentation attempt generation and requires fresh evaluation of current freshness and current disclosure authority. If either gate fails, no payload retry occurs.

If lookup remains `UNKNOWN`, no Timeline presentation event is fabricated. The runtime retains the unknown presentation state. It may retry the content-free lookup under bounded technical policy, but it may not resend the payload merely to resolve uncertainty.

Across multiple attempt generations for the same semantic `presentation_key`, the host commits at most one canonical presentation event for the `CompanionOutput`. A new generation is allowed only after the immediately prior generation has authoritative terminal `NOT_ACCEPTED`; therefore a delayed old-generation acceptance cannot race with or satisfy a later generation under an eligible sink contract.

### 2.17.6 Already-presented history

Once sink acceptance has been durably established and the canonical Timeline presentation event committed, deterministic replay/recovery does not retroactively rewrite or delete that historical event because Permission, resource bindings, relationship state, disclosure policy, or calendar contents later change.

## 2.18 User-facing truth and fail-closed behavior

User-facing language such as:

```text
"From your calendar, I can see..."
"I checked your calendar..."
```

is allowed only after authorized acquisition, coherent completeness validation, evidence-backed `WorldResult` admission, current freshness eligibility at cognition/egress/payload-dispatch boundaries, current model-egress authority for every model transport carrying personal data, mechanically validated schedule-plan adoption with deterministic schedule rendering, current first-party disclosure authority for every payload send, and validated presentation truth.

The model may operate only on the selected normalized calendar window and may not directly author authoritative schedule facts outside the structured plan contract. It cannot select another calendar, broaden the date range, reinterpret timezone, fetch another resource, infer missing pages, expose disallowed provider fields, convert observed events into memory, add events, change titles/times, or treat event titles as instructions.

No read transport dispatch occurs when any required acquisition-authority layer is unavailable or invalid, including:

- unsupported personal-calendar grammar;
- zero or multiple active resources under the first-slice contract;
- current RelationshipState invalid/ended for the counterpart;
- selected PersonalResourceBinding inactive, unbound, or no longer associated with that relationship/counterpart;
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

No `CompanionOutput` carrying schedule claims is adopted when the structured plan cannot be mechanically proven equivalent to the selected normalized projection. No new personal-data model transport occurs when model-egress authority, exact route eligibility, current read/disclosure Permission, or freshness is unavailable or invalid. No new payload presentation occurs when freshness or first-party disclosure authority fails. An uncertain prior presentation is reconciled content-free rather than guessed or forced through an unauthorized payload resend.

## 2.19 F5.A acceptance bar

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
15. Multi-page acquisition proves one coherent provider snapshot/revision or equivalent change-fenced view; terminal pagination alone is insufficient.
16. A concurrent calendar mutation between page requests cannot cause skipped/duplicated/mixed-snapshot results to be admitted; the acquisition restarts from a fresh bounded traversal or fails closed.
17. Bounded pagination restart discards all prior partial page material and cannot mix snapshots.
18. Partial or incoherent pages cannot produce a settled checked schedule.
19. Acquisition records `acquisition_started_at`; an authoritative provider `snapshot_as_of` is retained when available and trusted.
20. Freshness age uses `snapshot_as_of` when authoritative, otherwise conservatively uses `acquisition_started_at`; terminal-page/capture-commit time cannot make an older snapshot appear fresh.
21. A mutation after snapshot pinning but before the terminal page does not change the snapshot freshness anchor, and a long traversal can become stale before capture completion.
22. `WorldSourceCapture` retains acquisition/completeness/coherency/freshness-anchor provenance without retaining disallowed provider fields.
23. Provider descriptions, attendee identities, conference data, attachments, reminders, private notes, locations, and unrelated metadata are discarded before canonical capture under the first-slice schema.
24. Disallowed raw personal fields remain ephemeral inside the trusted adapter and never enter logs, traces, metrics payloads, caches, retry stores, crash diagnostics, analytics, or other non-canonical durable/telemetry paths.
25. An adapter that cannot enforce non-canonical minimization is rejected for the first slice.
26. Model context contains only normalized schedule fields required for the answer and no credential secret.
27. The answer remains traceable through Investigation → Observation → WorldSourceCapture → EvidenceItem → WorldResult → ContextProjection.
28. Observation authority provenance durably records the exact capability/policy/resource/Permission/credential/time decisions used for the concrete acquisition.
29. Calendar content creates no MemoryClaim/PersonClaim automatically.
30. Another interaction cannot reuse the personal-world result as generic context.
31. Process loss after capture/result but before projection evaluates current freshness from `freshness_anchor_at` before new projection construction.
32. Tightening freshness policy invalidates recovered capture/result reuse even when historical admission metadata still says fresh.
33. Process loss after projection but before model generation independently rechecks current freshness from the same anchor before new ModelInvocation.
34. A policy change or elapsed time between projection and generation can invalidate the projection without mutating historical provenance.
35. Immediately before every personal-data model dispatch/retry, current model-egress authority and eligibility of the exact configured model route are re-evaluated.
36. Revoked read/disclosure Permission, relationship/resource mismatch, egress-policy denial, or route ineligibility between projection and model dispatch blocks personal-data model transport even when the projection remains fresh.
37. Changing the configured model route requires a new current route-specific egress decision; an earlier route's authority cannot be reused.
38. Every personal-data `ModelInvocation` durably records the exact projection lineage, freshness decision, Permission provenance, personal-data/model-egress policy decision, concrete route/provider binding, route eligibility decision, and dispatch time used for that invocation.
39. A lost model response does not authorize retry from historical egress provenance; every retry carrying personal data re-evaluates the current gate.
40. Model-egress denial preserves historical projection/evidence state and does not trigger reacquisition solely to bypass the denial.
41. A durable GeneratedOutput/CompanionOutput that becomes stale before any payload dispatch is not newly presented as an unqualified current answer; it is reacquired/regenerated only while current authority permits that path.
42. Permission revocation, resource unbinding, relationship mismatch, or disclosure-policy denial after generation but before any payload dispatch blocks delivery even when freshness remains valid.
43. Disclosure-authority failure does not delete historical generated/evidence state and does not trigger an unauthorized reacquisition.
44. Before a payload-bearing presentation transport, a durable presentation attempt/fence exists and records current freshness/disclosure decision provenance.
45. Process loss after the sink accepts a payload but before host receipt commit recovers as `UNKNOWN_PRESENTATION_ACCEPTANCE`, not definitely undisclosed and not presented.
46. The F5 first-party sink supports authoritative content-free status lookup by presentation identity; a sink requiring payload resend to recover acceptance is rejected.
47. A point-in-time or eventually consistent negative lookup cannot produce `NOT_ACCEPTED`; it remains `UNKNOWN_PRESENTATION_ACCEPTANCE` unless terminality is proven.
48. Authoritative `NOT_ACCEPTED` proves that every prior dispatched/queued/in-flight transport covered by that presentation attempt can no longer later become accepted without a new explicitly authorized payload transport.
49. Linearizable terminal status or equivalent cancellation/settling proof is required for `NOT_ACCEPTED`; a sink unable to provide it is ineligible for the first slice.
50. A delayed acceptance from an old uncertain transport after authoritative `NOT_ACCEPTED` is impossible under the eligible sink contract; a test sink that permits it must fail qualification rather than corrupt canonical presentation truth.
51. If disclosure Permission is revoked after an uncertain presentation dispatch, recovery performs no payload resend; it may use only content-free status reconciliation.
52. If lookup proves the sink had already accepted the original authorized presentation, recovery commits exactly one historical `COMPANION_PRESENTED_OUTPUT` linked to the original attempt/acceptance evidence without redisclosing the payload.
53. If lookup proves terminal `NOT_ACCEPTED` and current disclosure authority is revoked, no Timeline presentation is committed and no payload retry occurs.
54. If lookup remains `UNKNOWN`, runtime preserves uncertainty and does not fabricate presentation or violate current disclosure authority.
55. Any later payload delivery after terminal `NOT_ACCEPTED` is a new bounded presentation attempt with fresh current freshness/disclosure checks and cannot be confused with delayed acceptance from the old attempt.
56. Already-presented historical Timeline/evidence state is not deleted or rewritten when Permission, disclosure authority, or freshness later changes.
57. Strong observational language is impossible without authorized, coherent, complete, evidence-backed, current-eligible personal-world support and mechanically truthful cognition/egress/presentation provenance.
58. Immediately before every external calendar page transport, the current `RelationshipState` remains valid and the selected `PersonalResourceBinding` remains ACTIVE and currently associated with the same counterpart/relationship.
59. Relationship termination, resource deactivation, or unbinding between pagination requests blocks the next page before transport and prevents partial prior pages from becoming a settled `WorldResult`.
60. Each page-specific authority record durably preserves the current RelationshipState-validity and resource-binding-association decisions used for that concrete transport.
61. Every calendar `GeneratedOutput` eligible for adoption conforms to the bounded structured `CalendarAnswerPlanV1` contract and references the exact selected projection/result lineage.
62. Adoption rejects unknown, duplicate, missing, cross-window, or cross-resource occurrence references and rejects any model attempt to override normalized title/time/all-day/resource semantics.
63. Instruction-like event titles remain inert data through model context and deterministic rendering and cannot alter routing, authority, tool use, schedule claims, or control flow.
64. A zero-item schedule plan is valid only when the coherent complete selected `WorldResult` contains zero normalized occurrences.
65. Raw free-form model schedule prose cannot bypass structured validation or deterministic rendering to become `CompanionOutput`.
66. Every payload-bearing personal-data presentation transport carries both the stable semantic `presentation_key` and the exact presentation attempt generation/fence scope.
67. Sink acceptance, content-free status lookup, cancellation/settling evidence, and terminal-negative evidence are all bound to the exact attempt generation/fence scope; another generation cannot satisfy them.
68. After terminal `NOT_ACCEPTED` for generation G1, any later authorized delivery uses a new generation G2; a delayed G1 transport cannot be accepted, reopened, or reclassified as G2.
69. The stable semantic `presentation_key` remains unchanged across bounded retry generations for the same `CompanionOutput`, while the host still commits at most one canonical presentation event.

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

Approval validity requires trusted approver authority and proof that the approver was presented a faithful semantic consent surface for that Action.

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

For every concrete external mutation dispatch, including retry after restart, the host immediately re-evaluates:

```text
same trusted counterpart / current RelationshipState remains valid for the Action
AND selected PersonalResourceBinding remains ACTIVE and currently associated with that relationship/counterpart
AND current Host Capability
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
    relationship_state_decision_ref/version
    personal_resource_binding_state_decision_ref/version
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

The attempt retains these refs/snapshots even if current policy, Permission, Approval, credentials, provider scope, relationship state, or resource-binding configuration later changes.

Historical attempt provenance explains why dispatch was allowed then. It does not authorize another dispatch now.

## 3.5 Action-specific external correlation

The first F5.B adapter must provide a recoverable capability-specific correlation mechanism tied to the exact Action.

Before crossing the external dispatch boundary, the host durably establishes:

```text
K(A1)
```

where `K(A1)` is unique to Action `A1` and is not derived solely from semantic payload equality.

Examples include a provider-supported idempotency/correlation key, client-chosen operation/event identifier, or another capability-specific marker that remains usable after process loss.

An adapter whose only unique identifier is learned ephemerally after a successful response and cannot be recovered from pre-dispatch correlation is ineligible for the first F5.B slice.

Retries of the same Action reuse the same external operation identity only when the trusted capability contract defines that behavior as safe.

Action correlation is not a substitute for the Alsoul-side dispatch serialization fence below.

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
    → later attempt still requires a new current authority gate

DISPATCH_FENCED / UNKNOWN_EFFECT
    → Action remains dispatch-locked
    → reconciliation only; no second mutation attempt

CONFIRMED_EFFECT
    → Action terminal for mutation dispatch
    → all future dispatch attempts rejected

CONFIRMED_NO_EFFECT
    → retry may become eligible only through explicit atomic retry transition
    → new current authority/Approval validity/Action constraints re-evaluated
    → still only one new active attempt may be claimed
```

A correlated semantic mismatch or other divergent external consequence remains unresolved/unknown for the intended Action and keeps the Action dispatch-locked.

Creating a PREPARED `ExecutionAttempt` and claiming the per-Action dispatch slot must be atomic enough that two workers cannot both obtain dispatch eligibility. Committing `DISPATCH_FENCED` must preserve exclusive Action ownership across crashes.

Provider idempotency support does not weaken this requirement. `K(A1)` may reduce duplicate external consequences, but Alsoul does not rely on optional provider idempotency to serialize its own workers.

## 3.7 ExecutionAttempt and durable dispatch-start fence

Each actual transport dispatch is represented by one distinct immutable `ExecutionAttempt` under the same Action.

Conceptually:

```text
Action A1
├── ExecutionAttempt X1 → K(A1)
└── ExecutionAttempt X2 → K(A1)   # only after X1 is conclusively no-effect and Action guard permits retry
```

The trusted executor persists the attempt, Action correlation, and exclusive Action dispatch claim before dispatch.

Immediately before transport:

```text
ExecutionAttempt PREPARED with K(A1)
↓
exclusive per-Action dispatch claim is current
↓
revalidate complete current authority gate, including current RelationshipState and active resource binding
↓
select and validate the exact trusted adapter / executor / correlation / negative-confirmation contracts for this attempt
↓
commit attempt-level authority provenance + exact execution-semantic pins + dispatch_started_at / DISPATCH_FENCED atomically while preserving Action lock
↓
only then may the exactly pinned provider transport observe the request
```

The execution-semantic pins committed with `DISPATCH_FENCED` include the Action-pinned capability contract/version, concrete adapter binding/ref and adapter contract/version, trusted executor contract/version, external correlation contract/version when distinct, and negative-confirmation contract/version when applicable. Each selected pin must be trusted, current, and compatible with the immutable Action at the fence linearization point.

A transport adapter must never be called from an unfenced attempt, from an attempt that no longer owns the exclusive per-Action dispatch claim, or through an adapter/executor/correlation contract different from the exact versions durably pinned by that fence. A hot swap after fencing cannot rewrite or substitute the attempt's execution semantics.

Recovery distinguishes:

```text
PREPARED, no dispatch fence
    → provider could not have observed this attempt
    → durable abandon/release possible before a new attempt

DISPATCH_FENCED, no conclusive evidence
    → exact execution-semantic pins are already durable
    → UNKNOWN_EFFECT; Action remains dispatch-locked
    → reconcile through K(A1) under the pinned semantics; no blind retry
```

The fence is conservative: a crash after the fence but before actual transport still recovers as may-have-dispatched. If a pinned adapter/executor becomes unavailable or mismatched after the fence but before transport, another implementation/version cannot be substituted for that attempt; transport fails closed and recovery preserves the fenced uncertainty semantics.

## 3.8 Effect confirmation requires correlation and semantic equivalence

`CONFIRMED_EFFECT` requires evidence establishing both:

```text
1. unique Action correlation
AND
2. capability-specific semantic equivalence to the immutable Action
```

For the first calendar-create slice, evidence supporting `CONFIRMED_EFFECT` must establish at least:

```text
observed external event uniquely correlated with K(A1)/Action A1
AND observed resource == Action.selected PersonalResourceBinding
AND normalized observed title/summary == Action title/summary
AND normalized observed start instant == Action normalized start instant
AND normalized observed end instant == Action normalized end instant
AND capability-specific create semantics otherwise match intended Action
```

A correlated event with wrong resource, title, start/end instant, or other material semantic mismatch is not `CONFIRMED_EFFECT` for the intended Action.

Because an unintended correlated external consequence may nevertheless exist, such a mismatch is also not automatically `CONFIRMED_NO_EFFECT`. Under the first slice it remains unresolved for the intended Action, is recorded with divergent evidence, remains effectively `UNKNOWN_EFFECT`, keeps the Action dispatch-locked, and blocks blind retry pending explicit reconciliation or a later compensation contract.

Visible field similarity without unique Action correlation is insufficient because an identical event may pre-exist or be independently created.

## 3.9 F5.B mutation-evidence minimization

Provider mutation responses are not permission to durably retain the provider's full response.

The first F5.B slice uses an explicit mutation-evidence allowlist. Raw create-response material may exist only ephemerally inside the trusted adapter for the minimum time required to normalize sufficient proof.

Durable positive-effect evidence may retain only fields necessary to prove Action correlation, semantic equivalence, provenance, or deterministic recovery, for example:

```text
action_id / execution_attempt_id
K(A1) or equivalent correlation identity
provider operation/event identity required for correlation
selected PersonalResourceBinding / normalized target resource proof
normalized title/summary proof
normalized start instant proof
normalized end instant proof
provider operation/result status required for effect truth
provider receipt/reference and timestamps required for proof/recovery
evidence-normalization schema/version
```

Durable negative-effect evidence may retain only fields necessary to prove the capability-specific authoritative no-effect predicate, for example:

```text
action_id / execution_attempt_id
K(A1)
authoritative operation/correlation status
terminal non-application proof for every transport covered by the attempt
settling/cancellation/drain proof refs and timestamps
consistency/status contract version
negative-evidence schema/version
```

The first slice does not canonically retain or expose as mutation evidence unrelated provider response fields such as:

```text
organizer/account identities
attendee identities or responses
conference/join metadata
description/body
location
attachments
reminders
extended/custom properties
provider defaults unrelated to Action semantics
unrelated calendar/account metadata
raw HTTP headers
credential material / authorization headers
```

If any such fields are necessarily returned, they remain ephemeral inside the trusted adapter and are discarded before durable evidence admission.

The same prohibition applies to non-canonical handling. Disallowed mutation-response fields must not enter:

```text
transport/debug/application logs
traces/spans
metrics payloads
response/retry caches
durable transport queues
crash dumps / diagnostic snapshots
analytics payloads
dead-letter stores
production-derived test fixtures
```

Only non-sensitive structural telemetry may survive when it does not reveal disallowed personal content.

If the adapter cannot establish sufficient correlation/semantic/negative proof without persisting disallowed raw response data, it is ineligible for the first F5.B slice.

A crash after external transport but before normalized allowlisted evidence becomes durable recovers as `UNKNOWN_EFFECT`; raw provider response material is not retained merely to avoid uncertainty. Reconciliation proceeds through durable `K(A1)` and separately authorized observation.

## 3.10 Durable Effect evidence ordering

After transport begins, normalized provider response/reconciliation evidence becomes durable before Effect admission.

The first committed `CONFIRMED_EFFECT` or `CONFIRMED_NO_EFFECT` state must already have its required supporting evidence recoverably linked.

Conceptually:

```text
provider response / reconciliation observation
↓
trusted adapter minimizes to allowlisted Action-correlated evidence
↓
durable minimized evidence
↓
capability-specific semantic/negative proof validation
↓
Effect state + required SUPPORTS relation committed atomically enough
that no visible Effect state exists without its proof
```

The storage design may use one transaction, dependent insertion with integrity constraints, or another mechanism with equivalent crash semantics. It must not commit Effect state first and attach evidence later.

If sufficient minimized evidence is durable but the process dies before Effect admission, recovery admits the corresponding Effect state from that evidence without redispatch.

A committed `CONFIRMED_EFFECT` atomically or transactionally advances the per-Action dispatch guard to terminal so no concurrent or later worker can dispatch the Action again.

A committed `CONFIRMED_NO_EFFECT` may release the Action for a later retry only through the explicit retry transition in §3.6 and only when the linked negative evidence includes the terminal non-application proof required by §3.12. It is not an implicit redispatch signal.

## 3.11 UNKNOWN_EFFECT and reconciliation

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
Action-correlated capability-specific minimized evidence
↓
CONFIRMED_EFFECT
OR CONFIRMED_NO_EFFECT
OR still UNKNOWN_EFFECT
```

Reconciliation is observation, not a second create Action. If current read authority is unavailable, reconciliation remains blocked/unknown rather than bypassing authority.

Read-side reconciliation inherits F5.A field minimization and non-canonical telemetry rules. F5.B does not create an exception to them.

## 3.12 Capability-sufficient and terminal `CONFIRMED_NO_EFFECT`

Absence from an ordinary calendar listing is not automatically proof that a create Action had no effect. Neither is absence after a visibility horizon when an earlier mutation transport may still be queued or in flight.

The trusted capability contract explicitly defines whether authoritative negative confirmation is supported and, if so, the exact terminal predicate.

Negative-confirmation metadata includes at least:

```text
negative_confirmation_supported
Action-correlation lookup semantics using K(A1)
read-after-write consistency model
visibility semantics
authoritative terminal operation-status semantics and/or cancellation + settling/drain semantics
transport-generation / ExecutionAttempt scope covered by terminal proof
predicate proving the intended consequence is absent
predicate proving every transport covered by the fenced attempt can no longer apply the Action
```

`CONFIRMED_NO_EFFECT` is permitted only when capability-specific minimized evidence establishes both:

```text
1. the Action-correlated intended external consequence does not exist
AND
2. every dispatched, queued, or in-flight transport covered by the exact fenced ExecutionAttempt is terminal and can no longer later apply the Action
```

Visibility, read-after-write consistency, or an elapsed observation horizon can help establish the first predicate. They do not establish the second predicate by themselves.

Potentially sufficient terminal proof, only when declared authoritative by the pinned negative-confirmation contract, includes:

```text
provider operation-status bound to K(A1) / the exact attempt says terminal NOT_APPLIED
AND the status contract guarantees no transport for that attempt can later apply
```

or:

```text
authoritative cancellation + settling/drain fence covers every dispatched/queued/in-flight transport for the exact attempt
AND proves those transports cannot later apply
AND a capability-sufficient correlation observation proves no intended Effect exists
```

The following are insufficient by themselves:

```text
first read immediately after timeout finds no event
ordinary event listing lacks a semantic match
absence before provider consistency/visibility is guaranteed
absence after a guaranteed visibility horizon while an older request may still be queued or in flight
lack of a response
transport failure
```

If terminal non-application cannot be proven for every transport covered by the fenced attempt, state remains `UNKNOWN_EFFECT`, the per-Action dispatch guard remains locked, and retry is prohibited even when current observation shows no event.

An eligible first-slice negative-confirmation contract must make this sequence impossible:

```text
ExecutionAttempt X1 becomes CONFIRMED_NO_EFFECT
↓
the Action guard permits retry X2
↓
an old queued/in-flight transport from X1 later applies the Action
```

If the provider/executor semantics permit that sequence, the integration cannot support `CONFIRMED_NO_EFFECT` for the first F5.B slice; uncertainty remains until terminality can be established.

When `CONFIRMED_NO_EFFECT` is authoritative, its durable minimized SUPPORTS evidence includes the exact terminal proof before the Action guard can enter the retry-eligible transition. A later retry still requires the per-Action atomic retry transition, a new current authority evaluation, current Approval validity, and a new `ExecutionAttempt`. Concurrent workers cannot both consume the same no-effect state to create separate retries.

## 3.13 Required crash and concurrency behavior

```text
crash while PREPARED, before dispatch fence
    → no external dispatch possible for this attempt
    → abandon/release PREPARED claim durably
    → later retry requires new current authority gate

crash after dispatch fence, before transport invocation
    → exact execution-semantic pins remain recoverable
    → UNKNOWN_EFFECT conservatively
    → Action remains dispatch-locked
    → reconcile using K(A1) under pinned semantics; no blind retry

crash after transport invocation, before minimized conclusive evidence commit
    → UNKNOWN_EFFECT
    → raw response is not durably retained
    → Action remains dispatch-locked
    → reconcile using K(A1); no blind retry

crash after sufficient minimized evidence commit, before Effect-state commit
    → recover evidence and admit justified Effect state
    → do not redispatch

crash after CONFIRMED_EFFECT commit
    → Effect state and SUPPORTS evidence recoverable
    → Action guard terminal; no redispatch
```

Two workers racing to execute the same Action cannot both create dispatch-eligible attempts. A worker that loses the Action claim performs no transport call.

Presentation/model failure after a confirmed external Effect never causes the Action to execute again.

## 3.14 Mechanically constrained mutation completion and fail-closed dispatch

A confirmed external Effect is necessary for a success response, but the existence of some Effect does not by itself authorize arbitrary mutation-completion prose.

Model-assisted mutation completion has a stricter input boundary than canonical Action/Effect state. Before any mutation-completion model transport, the host constructs a completion-local projection containing only opaque non-authority identity and bounded non-factual controls.

Conceptually:

```text
CalendarMutationCompletionProjectionV1 {
    mutation_completion_ref
    result_kind = CREATED
    rendering_contract_version = CALENDAR_CREATE_RESULT_V1
    allowed_framing_modes[]?   # optional bounded trusted enums; no factual payload
}
```

The host retains a private mapping:

```text
mutation_completion_ref
    → exact immutable Action
    → exact evidence-backed CONFIRMED_EFFECT for that Action
```

`mutation_completion_ref` is Alsoul-owned, opaque to the model, scoped to exactly one mutation-completion context, carries no execution/Resource Scope/Permission/Approval authority, is not a provider or resource identity, and is invalid outside that exact Action/Effect completion context.

The model-visible mutation-completion input is an explicit allowlist. The first slice exposes no effect-relevant factual payload and no host-side proof/authority identifiers beyond the opaque completion-local reference and bounded rendering controls. In particular, model context excludes:

```text
action_id / action_digest
effect_id / raw or durable Effect evidence
ExecutionAttempt identifiers or dispatch-fence state
K(A1) / external correlation identifiers
provider event / operation identifiers
provider receipts / proof references
PersonalResourceBinding identifiers / external resource identifiers
CredentialBinding / provider-scope material
Permission / Approval / authority-decision provenance
adapter / executor / reconciliation contract pins
```

Those values remain host-side even when they are required for validation, recovery, or deterministic rendering. A later contract may explicitly allow additional completion-facing fields; the first slice does not infer such eligibility from their presence in canonical Action or Effect state.

For the first F5.B slice, any model-assisted mutation completion uses a bounded structured result plan conceptually equivalent to:

```text
CalendarMutationResultPlanV1 {
    mutation_completion_ref
    result_kind = CREATED
    rendering_contract_version = CALENDAR_CREATE_RESULT_V1
    framing_mode?              # optional bounded trusted enum; no factual payload
}
```

The plan carries no authoritative resource, title, time, effect-class, receipt, Action identifier, Effect identifier, or other effect-relevant override. Those facts are resolved only through the host-side `mutation_completion_ref` mapping to the exact immutable Action and its evidence-backed `CONFIRMED_EFFECT` lineage.

Before any mutation `GeneratedOutput` can be adopted as `CompanionOutput`, the host mechanically verifies:

```text
mutation_completion_ref resolves in the exact current completion context
AND the resolved Action is the exact immutable Action being completed
AND the resolved Effect is the exact CONFIRMED_EFFECT admitted for that Action
AND the Effect already has durable SUPPORTS evidence
AND that evidence uniquely correlates the Effect to the Action / K(A1)
AND the Effect evidence is semantically equivalent to Action.selected PersonalResourceBinding
AND normalized Effect title/summary proof == Action title/summary
AND normalized Effect start instant proof == Action normalized start instant
AND normalized Effect end instant proof == Action normalized end instant
AND result_kind == CREATED
AND rendering_contract_version is trusted/current for this slice
AND no model-supplied field can add or override an effect-relevant proposition
```

The host then deterministically renders all factual mutation-completion claims from the immutable Action plus the validated evidence-backed Effect. A bounded `framing_mode`, when supported, may affect only non-factual connective language and cannot add another effect, target, title, time, resource, status, or receipt claim.

An unknown, forged, stale, or cross-Action/cross-Effect `mutation_completion_ref`, a malformed plan, an unconfirmed or unsupported Effect, a wrong resource/title/time, an unsupported additional effect, or any attempted factual override remains unadopted. The runtime does not fall back to free-form model prose and does not present a truthful-looking success response from unvalidated generated text.

Strong completion language such as:

```text
"I created the event."
```

is allowed only after this exact completion-reference and Action/Effect validation has succeeded and the resulting mutation completion has been adopted. A timeout, ambiguous provider state, early empty reconciliation read, correlated semantic mismatch, incomplete evidence, cross-Action Effect substitution, invalid mutation plan, or concurrent losing worker cannot justify strong completion language.

No mutation transport dispatch occurs when any required layer is absent, unreadable, denied, expired, revoked, unusable, mismatched, inactive, unbound, or not exclusively owned, including:

- current RelationshipState ended/invalid or counterpart association no longer valid;
- selected PersonalResourceBinding inactive, unbound, or no longer associated with that relationship/counterpart;
- semantic capability unavailable or effect contract untrusted;
- AI policy denial;
- target resource outside current scope;
- write Permission invalid or grant provenance/authorized grantor invalid;
- required Approval invalid, expired, revoked, or for another Action/resource/relationship;
- ApprovalPresentation missing or semantically mismatched to exact Action;
- approver unauthorized or approver eligibility unreadable;
- Action constraints violated;
- CredentialBinding unavailable/unusable;
- provider technical scope insufficient;
- durable Action correlation unavailable;
- attempt-level authority provenance cannot be committed;
- exact adapter/executor/correlation/negative-confirmation execution-semantic pins cannot be selected, validated, or durably fenced;
- exclusive per-Action dispatch claim cannot be acquired or is already held by a may-have-dispatched attempt;
- Action already has `CONFIRMED_EFFECT`;
- Action has unresolved `UNKNOWN_EFFECT`/divergent-effect evidence;
- dispatch-start fence cannot be committed.

An adapter is also ineligible when it cannot enforce F5.B mutation-response minimization before canonical/non-canonical persistence.

These conditions, including current RelationshipState and active resource-binding association, are re-evaluated before every retry.

## 3.15 F5.B acceptance bar

F5.B is complete only when executable tests prove all of the following:

1. Read authority cannot authorize write.
2. One immutable Action captures exact calendar-create semantics, including selected resource, title, explicit-offset timestamps, normalized instants, source, and capability version.
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
20. Crash before fence is known not to have reached transport; crash after fence is conservatively `UNKNOWN_EFFECT` and keeps Action locked.
21. `UNKNOWN_EFFECT` survives restart and blocks all competing/retry dispatches until conclusive reconciliation.
22. `CONFIRMED_EFFECT` atomically makes the Action terminal for future mutation dispatch.
23. A later worker after `CONFIRMED_EFFECT` cannot create or dispatch a new attempt for that Action.
24. `CONFIRMED_NO_EFFECT` permits at most one later retry claim, only through an explicit atomic retry transition and new current authority validation.
25. Two workers cannot both consume one `CONFIRMED_NO_EFFECT` state to create duplicate retries.
26. An identical pre-existing event cannot be mistaken for this Action's Effect.
27. `CONFIRMED_EFFECT` requires unique Action correlation and semantic equality with normalized intended resource/title/start/end/effect semantics.
28. A uniquely correlated event on wrong resource, wrong title, wrong start, or wrong end cannot produce `CONFIRMED_EFFECT` or strong completion language.
29. Correlated semantic mismatch remains unresolved for intended Action, retains dispatch lock, and cannot unlock blind retry.
30. Raw provider create responses are minimized inside trusted adapter before any durable evidence admission.
31. Durable mutation evidence contains only explicit correlation/semantic/negative-proof allowlisted fields; organizer/account identities, attendee data, conference data, descriptions, locations, reminders, custom properties, unrelated provider defaults, raw headers, and credential material are excluded.
32. Disallowed mutation-response fields remain ephemeral and never enter logs, traces, caches, queues, diagnostics, analytics, dead-letter stores, or production-derived fixtures.
33. An adapter unable to enforce mutation-evidence minimization is rejected for F5.B.
34. Crash after transport but before minimized evidence commit recovers as `UNKNOWN_EFFECT`; raw response persistence is not used as a shortcut.
35. Provider response/reconciliation evidence is durable before Effect-state admission.
36. First visible confirmed Effect state already has required SUPPORTS evidence.
37. Crash after minimized evidence commit but before Effect-state commit recovers from evidence without redispatch.
38. `CONFIRMED_NO_EFFECT` is admitted only under an explicit capability-specific authoritative terminal negative-evidence predicate.
39. Read-after-write visibility/consistency may contribute to negative proof but cannot establish terminal non-application of queued/in-flight mutation transports by itself.
40. An early or post-horizon empty read remains `UNKNOWN_EFFECT` whenever an older mutation transport may still apply, and therefore cannot unlock retry.
41. If terminal non-application proof is unavailable for every transport covered by the fenced attempt, state remains `UNKNOWN_EFFECT` and the Action remains dispatch-locked.
42. Reconciliation requires current read authority and uses bounded coherent complete minimized personal-calendar acquisition semantics from F5.A.
43. Presentation/model failure after confirmed Effect cannot execute the Action again.
44. Credential rotation may change execution binding without redefining Action or Person.
45. Strong completion language is mechanically blocked until corresponding evidence-backed `CONFIRMED_EFFECT` exists and the exact Action/Effect completion plan validates.
46. Immediately before every mutation dispatch/retry, the current `RelationshipState` remains valid and the selected `PersonalResourceBinding` remains ACTIVE and currently associated with the same counterpart/relationship.
47. Relationship termination, resource deactivation, or unbinding after Action/Approval creation but before a dispatch or retry blocks transport even when Permission, Approval, Resource Scope, and credentials otherwise remain valid.
48. Every `ExecutionAttempt` authority record durably preserves the current RelationshipState-validity and PersonalResourceBinding active-association decisions used for that concrete dispatch.
49. The exact concrete adapter binding/version, executor contract/version, external correlation contract/version when distinct, and negative-confirmation contract/version when applicable are selected and validated before `DISPATCH_FENCED` and become durable in the same fence commit.
50. Crash immediately after `DISPATCH_FENCED` but before provider invocation recovers all exact execution-semantic pins; a hot-swapped or mismatched implementation cannot substitute for the fenced attempt or reinterpret its recovery semantics.
51. `CONFIRMED_NO_EFFECT` includes durable terminal non-application evidence proving every transport covered by the exact fenced `ExecutionAttempt` can no longer apply the Action before the per-Action guard becomes retry-eligible.
52. A guaranteed visibility horizon or currently empty correlation lookup cannot release the Action guard while any older transport may still be queued or in flight.
53. After `CONFIRMED_NO_EFFECT` unlocks retry X2, a transport from the earlier attempt X1 cannot later apply; an integration whose semantics permit that sequence is ineligible for authoritative no-effect confirmation in the first slice.
54. Every mutation `GeneratedOutput` eligible for adoption conforms to `CalendarMutationResultPlanV1` and carries a host-issued `mutation_completion_ref` that resolves only in the exact current completion context to the exact immutable Action and its exact evidence-backed `CONFIRMED_EFFECT`.
55. Mutation-output adoption rejects an unknown, forged, stale, cross-Action, or cross-Effect `mutation_completion_ref`, an unconfirmed/unsupported Effect, wrong resource/title/start/end semantics, unsupported additional effects, or any model attempt to override effect-relevant facts.
56. Deterministic mutation rendering derives all factual success claims from the host-side exact Action and validated Effect evidence; raw free-form mutation prose cannot bypass the structured validator to become `CompanionOutput`.
57. Cross-Action Effect substitution or wrong-title/wrong-time/wrong-resource completion text cannot become adopted output or justify strong completion language.
58. Mutation-completion model context is explicitly allowlisted to the opaque completion-local reference, fixed result/rendering semantics, and bounded non-factual framing controls required by the first slice.
59. `action_id`, `effect_id`, `K(A1)`, provider operation/event identifiers, receipts/proof references, raw/durable Effect evidence, internal resource identifiers, credentials/provider scopes, execution/fence/correlation state, and authority provenance remain host-side and are absent from mutation-completion model context.
60. A `mutation_completion_ref` is opaque and scoped to exactly one Action/Effect completion context; using it against another Action, Effect, resource, or completion context fails adoption and conveys no authority.
61. Unknown, forged, stale, or cross-context completion references fail closed with no free-form fallback or factual success presentation.

# 4. F5 closure bar

F5 closes only when F5.A and F5.B are both green and executable evidence demonstrates:

- persistent Person/Relationship identity remains separate from account/resource/credential identity;
- personal-world read authority is explicit, current, provenance-backed, and fail-closed;
- current RelationshipState validity and active PersonalResourceBinding association are re-evaluated before every personal-calendar page transport and every mutation dispatch/retry;
- page/attempt authority provenance preserves the relationship/resource-binding decisions that authorized each concrete transport;
- trusted time semantics are explicit and deterministic;
- calendar membership is provider-independent and boundary-correct;
- recurrence expansion is concrete, bounded, and complete;
- pagination/truncation completeness is provable before settled schedule claims;
- multi-page reads prove one coherent snapshot/revision or fail closed on concurrent mutation;
- freshness age is anchored to coherent snapshot authoritative as-of instant or conservatively to acquisition start, never traversal completion;
- personal-world capture is field-minimized before canonical admission/model exposure;
- disallowed raw read-side personal fields remain ephemeral and cannot leak into non-canonical logs, traces, caches, queues, diagnostics, or analytics;
- personal data does not silently broaden memory scope;
- freshness is revalidated across capture/result/projection/model boundaries that create new cognition;
- current personal-data/model-egress authority and exact model route eligibility are re-evaluated before every personal-data model dispatch/retry;
- historical model-route authority cannot authorize a changed route or later retry;
- every personal-data ModelInvocation retains immutable egress decision and concrete route provenance;
- personal-calendar schedule claims are mechanically constrained to the exact normalized projection before CompanionOutput adoption;
- instruction-like calendar titles remain inert data and cannot become control instructions or unsupported schedule claims;
- every payload-bearing first presentation attempt requires current freshness and current first-party disclosure authority;
- every personal-data payload transport carries a stable semantic `presentation_key` plus an exact attempt-generation/fence identity;
- sink acceptance, terminal-negative status, cancellation/settling, and content-free reconciliation are scoped to the exact presentation attempt generation;
- a terminal old presentation generation cannot later accept or be conflated with a newly authorized generation under the same semantic key;
- revocation/resource-unbinding after generation blocks new disclosure without rewriting history;
- uncertain sink acceptance is represented durably and reconciled through content-free status lookup rather than forced payload resend;
- `NOT_ACCEPTED` is admitted only as a terminal negative against delayed acceptance from all earlier transports covered by that attempt generation;
- eventually consistent or point-in-time negative presentation status remains unknown unless linearizable terminality or equivalent cancellation/settling proof exists;
- prior accepted presentation may be recorded as historical truth after revocation without redisclosing its payload;
- read and write authority are independently scoped;
- Permission and Approval come from trusted authorized grant/approval paths;
- approval consent is bound to exact semantic content actually presented to counterpart;
- every effectful dispatch persists exact attempt-level authority provenance;
- authority is re-evaluated at every external mutation dispatch;
- durable per-Action guard serializes concurrent dispatch and blocks redispatch after possible/confirmed effect;
- attempted operation and established external Effect remain distinct;
- dispatch uncertainty survives restart and blocks blind replay;
- exact adapter/executor/correlation/negative-confirmation execution semantics are selected, trusted, and durably pinned with the mutation dispatch fence before transport can observe the request;
- a fenced mutation attempt cannot silently switch execution semantics after a hot swap or process restart;
- effect confirmation requires Action correlation and semantic equivalence;
- no-effect confirmation requires capability-sufficient evidence plus terminal proof that every transport covered by the fenced attempt can no longer apply;
- visibility or current absence cannot unlock mutation retry while an earlier transport may still apply;
- model-assisted mutation completion exposes only an allowlisted completion-local context; canonical Action/Effect identifiers, correlation/evidence/provider/resource-authority details, credentials, and execution proof remain host-side;
- `mutation_completion_ref` is opaque, completion-context-scoped, carries no authority, and cannot transfer Action/Effect truth across contexts;
- mutation completion claims are mechanically constrained to the exact immutable Action and its evidence-backed confirmed Effect before `CompanionOutput` adoption;
- cross-Action, wrong-resource, wrong-title, wrong-time, or unsupported additional mutation effects cannot become completion truth;
- mutation responses are minimized to explicit evidence allowlists before durable admission;
- disallowed mutation-response fields remain ephemeral and cannot leak into canonical evidence or non-canonical telemetry/persistence;
- effect evidence precedes and supports first committed confirmed Effect state;
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

Each later expansion must inherit the same identity, authority, provenance, minimization, freshness, model-egress, disclosure, presentation-truth, approval, execution, effect, concurrency, and recovery boundaries rather than bypassing them.

# 6. Cross-cutting execution invariants for F5 closure

The following requirements are part of this same normative checkpoint and are required by the F5.A and F5.B acceptance bars above. They close transport-race, resource-identity, model-reference, reconciliation-authority, and execution-contract drift cases without creating a separate amendment or precedence document.

## 6.1 Authority linearization at every external transport boundary

A current-authority check that merely happens before transport is insufficient. Every external transport that can acquire, disclose, present, or mutate personal-world state has one durable authority linearization point immediately before the external boundary.

This applies independently to:

```text
calendar read page transport
personal-data model transport
personal-data first-party presentation transport
calendar mutation transport / retry
external reconciliation probe
```

For each transport attempt, the trusted host records or references the exact current authority state used by that attempt, including every mutable authority head, revision, epoch, or policy decision whose change could make the transport invalid. At minimum, as applicable:

```text
RelationshipState head/revision
PersonalResourceBinding lifecycle head/revision
Capability contract/version and availability epoch
AI policy decision/version
Resource Scope decision/version
Permission state/revision and grant provenance
Approval state/revision and approver eligibility for mutation
CredentialBinding state/revision and provider-scope snapshot
freshness decision for current-state personal data
model-route eligibility for model egress
first-party disclosure decision for presentation
```

The durable dispatch fence, `ModelInvocation` dispatch admission, `PersonalPresentationAttempt` fence, read-page dispatch record, or reconciliation-probe dispatch record must be committed through a transaction/CAS/serialization mechanism that validates those exact current heads or epochs at the same logical linearization point. Revocation, relationship termination, resource unbinding/deactivation, policy changes, Approval revocation, and credential/scope invalidation that participate in those authority states must update through the same ordering discipline.

The required race semantics are:

```text
revocation / invalidation linearizes first
    → stale authority CAS/fence fails
    → external transport cannot start

dispatch authority fence linearizes first
    → that exact attempt is the already-authorized may-have-dispatched unit
    → later revocation does not rewrite its historical authorization
    → later revocation blocks every later transport attempt/retry
```

The fence is not a durable bearer token for arbitrary delayed reuse. If process loss occurs before a definitely unstarted transport can be resumed, a new transport attempt requires a new current authority linearization. If the old fenced transport may have crossed the boundary, recovery preserves the appropriate uncertainty state and does not redispatch merely because the historical fence exists.

For F5.A pagination, an authority race on any page aborts that page and prevents partial prior pages from being promoted into a complete result. For model egress, a stale authority snapshot cannot create a new personal-data `ModelInvocation`. For presentation, the existing attempt-generation/fence identity carries the linearized disclosure decision and uncertain-acceptance semantics. For F5.B, the authority linearization composes with the exclusive per-Action dispatch guard and `DISPATCH_FENCED`; neither substitutes for the other.

## 6.2 PersonalResourceBinding target identity is immutable within one binding identity

For the first F5 slice, `personal_resource_binding_id` identifies one immutable semantic target. The following target-defining fields cannot be changed in place under the same binding identity:

```text
counterpart_id
relationship_id
resource_kind
external_system_ref
external_resource_ref
calendar_timezone
timezone_rules_version
```

Lifecycle state such as ACTIVE/inactive/revoked may advance through append-oriented or revisioned state, and a non-authoritative display label may change, but those lifecycle/display changes do not retarget the binding.

Changing any target-defining field creates a new `PersonalResourceBinding` identity. The new binding does not inherit standing Permission, Approval, Action target identity, acquisition authority, evidence eligibility, or presentation authority from the old binding merely because the provider account, credential, display label, or relationship is the same.

Every Permission, Observation/acquisition, `ContextProjection`, Action, ApprovalPresentation/Approval, ExecutionAttempt, Effect proof, model-egress decision, and presentation-disclosure decision that depends on a personal resource pins the exact immutable binding identity. A provider-side alias or mutable account default cannot redirect that identity silently.

An implementation that models resource bindings with immutable complete revisions instead may do so only when every dependent authority/evidence object pins the exact target revision and retargeting creates a new non-inheriting semantic target revision. The first executable slice SHOULD prefer immutable binding identity plus separate lifecycle state because it makes stale-authority rejection simpler.

## 6.3 Projection-local schedule item references

`CalendarAnswerPlanV1.ordered_occurrence_refs[]` is fulfilled by Alsoul-owned projection-local handles, not by provider identifiers and not by matching generated title/time text back to events.

When constructing a personal-calendar `ContextProjection`, the host creates exactly one opaque `schedule_item_ref` for each selected normalized occurrence and retains a host-side mapping:

```text
ContextProjection
    schedule_item_ref
        → exactly one normalized selected occurrence
```

The model-visible schedule item contains only:

```text
schedule_item_ref
normalized title/summary
normalized time or all-day semantics
source classification required by the answer contract
```

Provider event IDs, provider occurrence IDs, recurrence master IDs, resource credentials, and other provider-side authority/correlation identifiers remain outside model context.

A `schedule_item_ref`:

```text
is scoped to exactly one ContextProjection
is opaque to the model
carries no Resource Scope, Permission, or execution authority
is not a provider identity
is invalid when presented against another projection
cannot be resolved by title/time similarity
```

The host may derive the handle from projection identity plus a collision-free local ordinal/nonce under a versioned renderer contract, but the external/model-visible form must not leak the provider identifier. Deterministic schedule rendering resolves plan entries only through the exact host-side projection mapping. Unknown, forged, duplicate, stale, or cross-projection handles fail adoption.

## 6.4 Every external reconciliation probe has explicit semantic read authority

Reconciliation does not gain authority from its usefulness to an existing write Action. Every external probe used to resolve `UNKNOWN_EFFECT`, `CONFIRMED_NO_EFFECT`, or divergent-effect evidence must be represented by a trusted READ_ONLY semantic capability and must pass its own current authority linearization before transport.

A provider operation-status or K(A1)-correlation lookup may execute under `calendar.events.read` only when the exact trusted `calendar.events.read` contract version explicitly declares that probe semantics, request/resource scope, minimization, completeness/consistency behavior, and Permission coverage.

Otherwise the probe is a separate semantic read capability with separate current:

```text
Capability availability / contract version
AI policy decision
Resource Scope
Permission and trusted grant provenance
RelationshipState / PersonalResourceBinding validity
CredentialBinding / provider technical scope
transport authority fence
```

The `Observation` and Effect-evidence provenance record the exact reconciliation capability/contract/version and concrete probe lineage. A provider status endpoint, correlation API, or transport method name is never self-authorizing. If the required semantic read capability is absent or not currently authorized, reconciliation remains blocked and Effect state remains unresolved.

## 6.5 Action-pinned capability and concrete executor semantics cannot drift silently

The immutable F5.B Action pins the exact `calendar.event.create` capability contract version whose semantics were normalized and approved. In the first executable slice, mutation dispatch requires exact version equality:

```text
Action.capability_contract_version
== current trusted executable calendar.event.create contract version
```

If the Action-pinned version is no longer trusted, available, or executable, the Action cannot dispatch or retry. A newer capability version does not inherit authority merely because its semantic operation name is unchanged.

Any effect-relevant contract change—including target semantics, parameter normalization, idempotency/correlation behavior, provider dispatch semantics, positive-effect proof, negative-effect proof, terminal non-application semantics, consistency guarantees, or minimization obligations—requires a new immutable Action and a new faithful approval presentation/Approval. A later architecture decision may define explicit compatibility proofs; the first F5.B slice does not.

Every `ExecutionAttempt` additionally retains:

```text
Action-pinned capability contract/version
concrete adapter binding/ref
adapter contract/version
trusted executor contract/version
external correlation contract/version when distinct
negative-confirmation contract/version when applicable
```

These values are not eventual audit fields. Before `DISPATCH_FENCED` can commit, the trusted executor must select the exact concrete values, validate that each required binding/contract is trusted, current, and compatible with the Action-pinned capability semantics, and include them durably in the same transaction/CAS/serialization step that linearizes current authority, preserves the exclusive Action lock, and commits the dispatch fence.

When authoritative no-effect confirmation is supported, the pinned negative-confirmation semantics include the exact terminal operation-status or cancellation/settling/drain proof required to show that every mutation transport covered by the fenced attempt can no longer apply. A later implementation or configuration cannot weaken that terminality predicate for an already-fenced attempt.

Only the adapter/executor/correlation semantics pinned by that fenced `ExecutionAttempt` may perform its provider transport or interpret its post-dispatch response. A runtime hot swap, configuration reload, adapter replacement, or contract-version change after fencing cannot rewrite the attempt or substitute a different execution stack. If the exact pinned execution stack is unavailable or mismatched before transport, that attempt fails closed; because the fence already establishes may-have-dispatched status, recovery retains `UNKNOWN_EFFECT` semantics and uses only the durable pins to determine valid reconciliation behavior.

A crash immediately after the fence but before provider invocation must recover the complete exact execution-semantic pins together with `K(A1)` and the Action guard. Recovery must never need to consult whichever adapter/executor happens to be current merely to determine what the fenced attempt meant.

The attempt may use a different credential binding after rotation only when the immutable resource target and Action semantics are unchanged and the complete current authority gate passes. Adapter/executor replacement never changes the Action meaning silently.

## 6.6 Additional mandatory acceptance cases

The F5.A acceptance bar additionally requires executable tests proving:

1. A Permission revocation, RelationshipState termination, or resource unbinding racing a calendar page authority fence has deterministic linearized behavior: if invalidation wins, no page transport occurs; if the fence wins, that exact attempt is historical/may-have-dispatched and no later page/retry inherits its authority.
2. A model-egress policy/Permission/route change racing `ModelInvocation` dispatch admission cannot allow personal data to leave under a stale authority snapshot.
3. A first-party disclosure revocation racing a personal-presentation fence cannot allow a new payload transport when revocation linearizes first; an already-fenced uncertain attempt follows content-free reconciliation and never becomes a bearer authorization for a later resend.
4. Retargeting an external calendar, timezone/rules target, or relationship association cannot occur under the same immutable PersonalResourceBinding identity; a replacement binding cannot reuse the old binding's Permission or current-state evidence eligibility.
5. Model context contains an Alsoul-owned projection-local `schedule_item_ref` for each schedule item while provider event/occurrence identifiers remain absent.
6. Forged, stale, duplicate, or cross-projection `schedule_item_ref` values fail mechanical adoption, and deterministic rendering resolves only through the exact projection-local mapping.

The F5.B acceptance bar additionally requires executable tests proving:

1. Permission/Approval/resource/policy/credential invalidation racing mutation dispatch has deterministic linearized behavior; invalidation winning first prevents `DISPATCH_FENCED`, while a fence winning first yields exactly one may-have-dispatched attempt and later invalidation blocks later retry.
2. Same-ID PersonalResourceBinding retargeting is impossible; creating a replacement binding for another external calendar cannot authorize an Action or Approval that pinned the old binding.
3. A provider operation-status or correlation endpoint cannot be called for reconciliation unless the exact authorized semantic read capability contract includes that probe or a separate trusted read capability is currently authorized.
4. Reconciliation Observation/evidence provenance records the exact semantic probe capability and version actually used.
5. A `calendar.event.create` capability-version change after Action approval blocks dispatch under the old Action in the first slice, even when the operation name and provider account remain unchanged.
6. Every ExecutionAttempt records the Action-pinned capability version plus concrete adapter and executor contract versions used at dispatch.
7. The exact adapter binding/version, executor contract/version, external correlation contract/version when distinct, and negative-confirmation contract/version when applicable are selected, validated trusted/current, and durably committed in the same `DISPATCH_FENCED` linearization before provider transport can observe the request.
8. A crash immediately after `DISPATCH_FENCED` but before provider invocation recovers those exact execution-semantic pins; a hot swap or version mismatch after fencing cannot substitute a new adapter/executor/correlation/negative-confirmation contract for the fenced attempt, and any such mismatch fails closed without transport under different semantics.
9. `CONFIRMED_NO_EFFECT` cannot be admitted from an empty or post-horizon observation unless durable evidence also proves every transport covered by the exact fenced attempt is terminal and cannot later apply.
10. A test provider that allows an old X1 transport to apply after X1 is declared `CONFIRMED_NO_EFFECT` and retry X2 becomes eligible fails first-slice qualification; the Action remains `UNKNOWN_EFFECT`/locked unless terminality is provable.
11. Mutation-completion model input contains only an Alsoul-owned opaque `mutation_completion_ref`, fixed result/rendering semantics, and bounded non-factual framing controls; canonical Action/Effect identifiers, `K(A1)`, provider IDs/receipts, Effect evidence, internal resource identifiers, credentials/scopes, execution/fence/correlation state, and authority provenance remain host-side.
12. `mutation_completion_ref` resolves only within one exact Action/Effect completion context, conveys no authority, and forged, stale, unknown, cross-Action, or cross-Effect references fail mechanical adoption.
13. `CalendarMutationResultPlanV1` can be adopted only when its completion-local reference resolves to the exact immutable Action and that Action's evidence-backed `CONFIRMED_EFFECT`; unconfirmed, unsupported, or semantically mismatched resolutions fail adoption.
14. Deterministic mutation rendering takes factual resource/title/start/end/effect claims only from the validated host-side Action/Effect lineage, and generated free-form factual overrides or unsupported additional-effect claims cannot become `CompanionOutput`.

These requirements are part of the existing F5 closure bar: authority must be current **and linearized**, resource identity must be non-retargetable under existing authority, model references must remain Alsoul-owned and projection-local or completion-local, reconciliation must be explicitly authorized, approved Action semantics must not drift between consent and execution, no-effect must be terminal against delayed application before retry eligibility, mutation-completion model input must remain minimized to opaque non-authority context, and mutation completion truth must remain mechanically bound to the exact Action and evidence-backed Effect.