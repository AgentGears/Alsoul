# F5 Executable Checkpoint — Personal World + Trust

**Status:** Converged implementation contract; implementation pending  
**Publication:** GitHub-safe  
**Predecessor:** [F4 Exit Audit](F4_EXIT_AUDIT.md)  
**Architecture basis:** Decisions 06.A–06.C, 07.A–07.B, 08.A–08.B, 11.A, 14.A, and 15.A–15.B

F5 begins after the executable F4 foundation is closed. Its purpose is not to add a broad connector surface. Its purpose is to prove that Alsoul can enter the counterpart's personal digital world under explicit authority while preserving Person continuity, epistemic honesty, provenance, recovery, and fail-closed behavior.

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

Read authority does not imply write authority. Access to one personal resource does not imply access to another. Access to personal data does not make that data durable personal memory.

## Governing invariants

```text
CompanionPerson ≠ external account
CredentialBinding ≠ CounterpartPerson
Credential possession ≠ Permission
Capability availability ≠ Permission
Permission ≠ Approval
read / observe ≠ write / act
personal-world observation ≠ MemoryClaim
WorldSourceCapture ≠ general memory eligibility
Action ≠ ExecutionAttempt ≠ Effect
failed effect ≠ unknown effect
historical access ≠ current authority
provider/tool identity ≠ semantic capability
execution isolation ≠ capability authorization
process-local timezone ≠ trusted calendar time semantics
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

No lower layer may manufacture authority that is absent, unreadable, expired, revoked, or denied above it.

## F5 implementation strategy

F5 is split into two executable tranches:

```text
F5.A  personal-world observation
F5.B  bounded external action + effect reconciliation
```

F5.A is the immediate implementation target. F5.B starts only after the read-side authority/provenance boundary is executable. F5 is not closed until both tranches satisfy their acceptance bars.

This split prevents the first connector from collapsing observation and action semantics into one integration boundary.

# F5.A — Read-only personal calendar observation

## Objective

Answer one bounded current-state calendar question by actually reading one explicitly selected calendar resource under current authority.

The first executable grammar is intentionally narrow:

```text
"What's on my calendar on YYYY-MM-DD?"
"What do I have on my calendar on YYYY-MM-DD?"
```

The date denotes one local calendar day in the trusted timezone pinned to the selected calendar resource. It is not interpreted in process-local time, host locale, model locale, or an adapter default.

Relative-date expressions such as `tomorrow`, natural-language recurrence reasoning, free-form calendar search, email, contacts, files, and cross-resource aggregation remain outside the first slice. Relative dates require a separate trusted temporal-reference contract.

## Semantic path

```text
trusted COUNTERPART_INPUT
↓
bounded PERSONAL_CALENDAR_QUESTION classification
↓
resolve one selected personal calendar resource
↓
derive exact date window from its trusted timezone
↓
evaluate read authority
    calendar.events.read capability available
    AND AI policy permits read
    AND resource is inside declared scope
    AND current user Permission authorizes read
    AND usable CredentialBinding exists
↓
Investigation
↓
Observation
↓
personal-calendar connector read
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
first-party presentation
```

The connector performs acquisition only. It does not decide semantic routing, resource selection, permission, memory admission, time interpretation, or what the model may see.

## Capability contract

The first semantic capability is:

```text
calendar.events.read
```

This is a provider-independent operation family. Provider API method names, plugin names, transport endpoints, and credential types are adapter details and cannot define authority.

Trusted capability metadata declares at least:

```text
semantic operation
contract version
access/effect class = READ_ONLY
supported resource kind = CALENDAR
request constraints
response semantics
```

A missing or unreadable capability declaration blocks dispatch. The runtime must not infer read/write/effect class from a tool or function name.

## Personal resource identity and trusted time semantics

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
    display_label?
    status
}
```

`calendar_timezone` is trusted resource metadata established at binding/configuration time and validated before the resource becomes active. The first slice requires a non-empty recognized timezone contract. Missing or unreadable timezone state makes the calendar unavailable for date-window questions.

For an input date `D`, the host derives the exact half-open interval:

```text
[D 00:00, D+1 00:00)
```

in the pinned calendar timezone before dispatch. The normalized request records both the trusted timezone and the resulting exact instants/offsets so adapter defaults cannot change the requested window.

The exact physical representation may differ, but these boundaries must be enforceable:

```text
PersonalResourceBinding ≠ CounterpartPerson
PersonalResourceBinding ≠ CredentialBinding
external principal ≠ CounterpartPerson identity
calendar timezone ≠ process-local timezone
```

The first slice requires exactly one configured active calendar resource for the relationship. Zero resources fail unavailable. More than one active resource fails ambiguous until an explicit resource-selector contract exists.

## Credential binding

A `CredentialBinding` establishes how the trusted host can authenticate to the selected external system. It does not define the user, relationship, permission, resource, or capability.

Credential secrets remain outside canonical cognition and persisted provider context. Canonical state may retain a secret reference or binding identifier, never the secret itself.

Credential removal or rebinding must not change `CompanionPerson`, `CounterpartPerson`, `RelationshipState`, canonical Timeline identity, or previously established evidence identity.

## Permission contract

F5.A requires explicit standing read Permission for:

```text
holder = current CompanionPerson
capability = calendar.events.read
resource = selected PersonalResourceBinding
operation class = READ
```

The grant must be current, unrevoked, and inside any declared expiry/constraint window before connector dispatch.

The first slice does not require a separate per-interaction Approval for this read: the user is actively asking the bounded read question and standing Permission is constrained to one selected resource. This does not generalize to writes. A future policy may require read approval without weakening any higher authority layer.

Missing, malformed, unreadable, expired, revoked, or mismatched Permission fails closed before acquisition.

## Authority provenance for reads

A successful personal-world Observation retains immutable provenance sufficient to answer:

```text
which semantic capability authorized the read?
which personal resource was read?
which trusted timezone/window was requested?
which Permission was current?
which CredentialBinding was used?
which user interaction caused the read?
```

The implementation may persist this as an Observation authority relation/snapshot rather than a new general-purpose aggregate. It must not reconstruct historical authority from mutable current configuration.

Authority provenance explains why access was allowed. It does not itself prove calendar content. Content support still flows through Observation → WorldSourceCapture → EvidenceItem.

## Acquisition, freshness, and minimization

Calendar state is connected-world observation, not innate knowledge.

A successful read creates an acquisition-specific `WorldSourceCapture` containing enough recoverable material to establish:

```text
selected external resource identity
requested date
trusted calendar timezone
exact requested interval
captured_at
provider-resolved resource/window metadata where available
exact acquired material or deterministic normalized capture
```

A current calendar answer requires a fresh acquisition for the current user interaction unless the runtime is recovering the same already-completed interaction from a durable capture/result that still satisfies the same request contract.

A failed/unknown read retry creates a new Observation. Because the capability is read-only, uncertainty concerns what was observed; no external `Effect` is created for the read.

The connector may request only the selected calendar and exact requested interval. It must not ingest full calendar history, unrelated calendars, contacts, messages, files, or application state merely because provider credentials technically allow it.

Provider technical scope is a ceiling, not Alsoul authority.

## Personal-world result semantics

The admitted result remains distinct from memory and public-world search.

The projection must carry a source classification equivalent to:

```text
CURRENT_PERSONAL_OBSERVATION
```

User-facing language may use forms such as:

```text
"From your calendar, I can see..."
"I checked your calendar..."
```

only after an authorized acquisition and evidence-backed result exist.

The model may summarize the already-selected calendar window. It cannot select another calendar, broaden the date range, reinterpret timezone, fetch another resource, or convert observed events into memory.

## No silent memory admission

The read path creates no `MemoryClaim` or `PersonClaim` merely because an event mentions the counterpart, a preference, a location, another person, or a recurring pattern.

```text
personal data exposure
≠ memory proposal
≠ memory admission
```

Calendar content is retained only in the evidence/result lineage required for the authorized interaction and deterministic recovery. Any later personal-world memory admission requires a separate policy and contract.

## Projection eligibility

Personal-world evidence must not become a general-purpose context pool.

For F5.A, a calendar-derived WorldResult is eligible only for the interaction that caused its authorized acquisition and deterministic recovery of that same interaction. Reuse in another interaction requires a new explicit selection/admission contract and, for current-state questions, normally a new acquisition.

Permission revocation does not delete historical evidence or already-presented Timeline content. It blocks new personal-world acquisitions and unrelated future projections that would require current access authority.

## Recovery behavior

F5.A preserves the F4 rule: resume from the furthest trustworthy durable stage.

```text
input admitted, no successful capture
    → re-evaluate current read authority and resource timezone, then create a new Observation

capture/result committed, projection not yet committed
    → recover the same interaction from durable authorized evidence if request/freshness invariants still hold

projection/generated/adopted/presented committed
    → reuse the canonical downstream stage; do not re-read merely because the process restarted
```

A restart never assumes that an old Permission, credential, resource binding, or process timezone is valid for a new acquisition.

## F5.A fail-closed cases

The connector is not dispatched when any of the following holds:

- unsupported personal-calendar grammar;
- zero or multiple active calendar resources under the first-slice contract;
- missing/unreadable trusted calendar timezone;
- capability absent or unavailable;
- capability access/effect class missing or untrusted;
- AI policy denies the read;
- selected resource outside declared scope;
- Permission absent, unreadable, expired, revoked, or mismatched;
- CredentialBinding absent or unusable;
- credential/provider technical scope insufficient;
- requested date/window violates capability or Permission constraints.

Failure occurs before model execution when no evidence-backed calendar result can be admitted.

## F5.A acceptance bar

F5.A is complete only when executable tests prove:

1. The same `CompanionPerson`, `CounterpartPerson`, and `RelationshipState` survive connector binding, credential rebinding, and complete runtime recomposition.
2. A bounded date question dispatches exactly one authorized read against exactly one selected calendar resource.
3. The date is converted to an exact interval using the resource's trusted timezone, never process/adapter defaults.
4. No connector call occurs without current Capability, AI policy, resource scope, Permission, usable CredentialBinding, and valid trusted timezone state.
5. Missing/unreadable authority or timezone state fails closed.
6. Provider/tool naming cannot change trusted READ_ONLY classification.
7. The answer is traceable through Investigation → Observation → WorldSourceCapture → EvidenceItem → WorldResult → ContextProjection.
8. The Observation retains immutable authority/time provenance for capability, resource, permission, credential binding, source interaction, timezone, and exact interval.
9. The model receives no credential secret and no authority to widen or reinterpret the read.
10. Calendar event content creates no MemoryClaim/PersonClaim automatically.
11. A second unrelated interaction cannot reuse the personal-world result as generic context.
12. Process loss after durable capture/result can recover without unnecessary duplicate acquisition when same-interaction freshness remains valid.
13. Process loss before successful capture re-evaluates current authority before a new read.
14. Strong observational language is impossible without admitted personal-world evidence.
15. Permission revocation blocks new reads without deleting historical Timeline/evidence state.

Passing F5.A authorizes work on F5.B. It does not close F5.

# F5.B — One bounded calendar mutation

## Objective

After F5.A is stable, add one effectful capability sufficient to prove Decisions 08.A–08.B:

```text
calendar.event.create
```

The user specifies one exact event target. The host normalizes that intent into an immutable `Action`; a connector or model tool call is never direct execution authority.

The first write grammar uses explicit offset-aware timestamps so the intended instants are mechanically bounded without relying on account, process, host, or adapter timezone defaults:

```text
"Add 'Dentist' to my calendar from 2026-09-10T15:00:00+03:00 to 2026-09-10T15:30:00+03:00."
```

The immutable Action pins at least:

```text
selected PersonalResourceBinding
summary/title
start timestamp with explicit offset
end timestamp with explicit offset
normalized start instant
normalized end instant
capability contract/version
```

The explicit offsets are part of semantic intent and approval. An adapter may translate representation for the provider, but it may not substitute process-local, account-default, or calendar-default time semantics.

Natural-language timezone inference, floating local times, recurrence, attendees, conferencing, reminders, edits, deletes, and free-form scheduling remain outside the first write slice.

## Action path

```text
trusted COUNTERPART_INPUT
↓
bounded calendar-create intent with exact time semantics
↓
resolve selected calendar resource
↓
normalize immutable Action
↓
evaluate current authority
    capability available
    AND AI policy permits write
    AND resource scope permits target
    AND Permission permits calendar.event.create
    AND current operation-specific Approval binds exact Action
    AND usable CredentialBinding/provider scope exists
↓
ExecutionAttempt persisted before dispatch
↓
external dispatch
↓
CONFIRMED_EFFECT
    OR CONFIRMED_NO_EFFECT
    OR UNKNOWN_EFFECT
```

Read Permission does not satisfy write Permission. A prior read request does not approve a later mutation.

## Approval contract

Approval binds the immutable semantic Action, including selected resource and all effect-relevant parameters.

Material change to any of the following creates a new Action and requires new Approval where policy requires it:

```text
resource
title/summary
start instant or offset-aware representation
end instant or offset-aware representation
other effect-relevant bounded parameters
```

A model-supplied confirmation token, tool argument, UI implementation detail, or provider response is not human Approval.

## Effect truth

Strong completion language is downstream of evidence-backed Effect state.

```text
"I created the event."
```

requires `CONFIRMED_EFFECT` for the intended Action.

A transport timeout after possible dispatch produces `UNKNOWN_EFFECT`, not failure and not success. While `UNKNOWN_EFFECT` remains unresolved, blind mutation retry is prohibited.

## Reconciliation

Unknown calendar-create effects are reconciled through the read side:

```text
UNKNOWN_EFFECT
↓
authorized calendar.events.read
↓
Investigation / Observation / Capture
↓
capability-specific match against exact resource + time + event semantics
↓
CONFIRMED_EFFECT
OR CONFIRMED_NO_EFFECT
OR still UNKNOWN_EFFECT
```

Reconciliation is observation, not a second create Action.

## F5.B acceptance bar

F5.B is complete only when tests prove:

1. Read authority cannot authorize write.
2. One immutable Action captures the exact semantic calendar-create intent.
3. Start/end time semantics are offset-aware, normalized to exact instants, and immune to process/account/adapter timezone defaults.
4. Changed effect-relevant parameters, including time offsets/instants, require a new Action/Approval.
5. Each concrete dispatch is a distinct ExecutionAttempt under the same Action.
6. External idempotency identity, when supported, is stable per Action rather than derived solely from payload equality.
7. Effect is admitted only from capability-sufficient evidence.
8. Timeout/ambiguous dispatch persists `UNKNOWN_EFFECT` across restart.
9. `UNKNOWN_EFFECT` blocks blind retry.
10. Reconciliation uses read-side observation and can resolve success, no-effect, or continued uncertainty.
11. Presentation/model failure after confirmed Effect cannot cause the Action to execute again.
12. Credential rotation can change execution binding without redefining the semantic Action or Person.
13. Strong completion language is mechanically blocked until the corresponding Effect is confirmed.

# F5 closure bar

F5 closes only when F5.A and F5.B are both green and executable evidence demonstrates:

- personal-world provenance and freshness survive connector use;
- trusted time semantics are explicit for both calendar reads and writes;
- personal data does not silently broaden memory scope;
- authority state fails closed and remains monotonic narrowing;
- read and write authority are independently scoped;
- one bounded mutation uses explicit semantic Approval;
- attempted operation and established external Effect remain distinct;
- ambiguous effects survive restart and are reconciled instead of blindly replayed;
- credential removal/rebinding does not redefine Person identity;
- access/effect classification comes from trusted capability semantics rather than provider/tool naming;
- access to an application/resource does not redefine Person or Relationship identity.

## Explicit exclusions after this contract

This checkpoint does not authorize broad personal-world indexing, email sending, file mutation, contact editing, multiple-calendar natural-language routing, autonomous background access, durable delegated work, recurring triggers, proactive contact, semantic history retrieval, rich modality, or general connector/plugin execution.

Each later expansion must inherit the same authority, provenance, time, memory, effect, and recovery boundaries rather than bypassing them.
