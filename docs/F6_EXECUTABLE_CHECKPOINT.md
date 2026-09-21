# F6 Executable Checkpoint — Continuous Presence + Embodiment

**Status:** Converged implementation contract; implementation pending  
**Publication:** GitHub-safe  
**Predecessor:** [F5 Exit Audit](F5_EXIT_AUDIT.md)  
**Architecture basis:** Decisions 05.B, 07.B, 11.A–11.B, 12.A, 14.A, and 15.A–15.B

F6 begins only after executable F5 closure. Its purpose is not broad multimodal coverage or avatar work. Its purpose is to prove that Alsoul remains one durable Person while presentation becomes interruption-sensitive, reception-aware, and capable of moving across multiple social presences without turning surfaces, channels, renderers, voices, devices, or provider sessions into identity owners.

This file is the single normative F6 executable checkpoint. No separate amendment or precedence chain is required.

# 1. Governing boundary

F6 preserves these distinctions:

```text
CompanionPerson ≠ SurfaceBinding
CompanionPerson ≠ ChannelBinding
CompanionPerson ≠ EmbodimentBinding
Relationship ≠ thread / conversation / call / device
surface ≠ channel
channel ≠ embodiment
presentation profile ≠ SelfModel
provider/model session ≠ CompanionPerson
background faculty ≠ second persona

GeneratedOutput
≠ CompanionOutput
≠ rendered presentation
≠ payload/frame dispatch
≠ sink acceptance
≠ presented extent
≠ reception/playback evidence
≠ understood meaning

presentation intent ≠ presentation attempt
presentation attempt ≠ presented extent
presented extent ≠ heard/read extent
interruption ≠ presentation failure
interruption ≠ permission to resume unpresented remainder
```

A **surface** names the social situation in which interaction occurs. A **channel** names the transport route. An **embodiment** names a replaceable presentation/body/voice renderer or asset binding. None may own Person identity, Relationship identity, canonical memory, authority, or historical truth.

Canonical shared history records what was actually presented, not what was merely generated, adopted, rendered, queued, or intended for delivery. Stronger reception evidence may prove a bounded playback/read receipt contract; it never proves human understanding.

All earlier Foundation authority remains in force. Progressive delivery, new surfaces, new channels, or a new embodiment cannot broaden what data may be disclosed or what external action may occur. For outputs containing personal-world material, every concrete payload-bearing transport remains subject to the applicable current F5 freshness/disclosure gate for that transport.

F6 is split into two executable tranches:

```text
F6.A  interruption-safe progressive presentation truth
F6.B  multi-presence continuity + replaceable embodiment binding
```

F6.A must close before F6.B depends on progressive presentation semantics. F7 durable assistance, generic background work, commitments, procedural learning, broad proactivity, and autonomous long-horizon scheduling remain outside F6.

# 2. F6.A — Interruption-safe progressive presentation truth

## 2.1 Objective

Prove one bounded first-party presentation session in which an adopted `CompanionOutput` may be presented progressively and may be interrupted by a canonical counterpart input without fabricating shared history or silently resuming material that was not presented.

The first executable slice is transport-neutral. It does not require a speech provider, microphone, avatar runtime, or third-party realtime protocol. A trusted first-party presentation adapter may use deterministic framed text to exercise the same state and interruption contract that later voice/audio presentation must satisfy.

The first slice proves the lifecycle, not product-grade media latency.

## 2.2 Semantic path

```text
CompanionOutput
↓
resolve current SurfaceBinding + ChannelBinding + optional EmbodimentBinding
↓
create durable presentation session / generation fence
↓
deterministically render immutable ordered presentation frames
↓
re-evaluate any inherited current payload-disclosure gate required for the exact frame transport
↓
transport one frame at a time under the exact generation fence
↓
trusted sink receipt records accepted/presented extent
↓
optional stronger reception/playback receipt records heard/read extent
↓
continue | interrupt | fail | become uncertain
↓
terminal settle/reconcile exact generation
↓
commit canonical Timeline history for exactly the presented extent
```

The same `CompanionOutput` may be fully presented, partially presented, or never presented. These are different historical outcomes.

## 2.3 Presentation session identity

One progressive presentation owns a durable semantic identity distinct from transport retries or frame receipts.

Conceptually:

```text
PresentationSession {
    presentation_session_id
    companion_output_id
    relationship_id
    surface_binding_id
    channel_binding_id
    embodiment_binding_id?
    presentation_contract_version
    frame_contract_version
    presentation_key
    opened_at
}
```

`presentation_key` is a stable semantic idempotency key for one intended presentation of one `CompanionOutput` to one resolved first-party target. A new transport generation for the same session must not create a second semantic presentation merely because recovery requires another bounded attempt.

Historical binding identity is pinned. Later replacement of a surface, channel, embodiment, device endpoint, or rendering asset cannot rewrite what target was used by an earlier session.

## 2.4 Deterministic rendered frames

The first slice renders the adopted `CompanionOutput` into an immutable ordered frame sequence before transport.

Each frame retains at least:

```text
presentation_session_id
frame_ordinal
rendering_contract_version
source_start
source_end
content_text
content_digest
```

The frame partition is deterministic for a pinned contract version. Frames are contiguous, non-overlapping, ordered, and together reconstruct exactly the canonical presented form of the `CompanionOutput` when the output is fully presented.

A renderer may change in a later contract version, but one active session cannot change rendering contract, frame boundaries, or frame digests mid-presentation.

For the first executable slice, a frame is the smallest atom the sink may claim as presented. A sink that can expose only an ambiguous partial frame cannot promote that partial material into authoritative presented extent.

## 2.5 Attempt generation and transport fence

Before the first payload/frame transport in one generation, the host durably records a presentation attempt/fence containing at least:

```text
presentation_attempt_id
presentation_session_id
attempt_generation
presentation_transport_fence_scope_id
surface_binding_id
channel_binding_id
embodiment_binding_id?
presentation_contract_version
frame_contract_version
opened_at
```

A transport call cannot exist before the fence exists.

The first slice sends frames serially. A later generation is permitted only after the previous generation is proven terminal against delayed presentation. Unknown prior delivery is reconciled before any payload replay.

## 2.6 Inherited authority and disclosure gate

F6 does not weaken F5 by turning one previously bounded presentation into an authority-amortizing stream.

Immediately before every payload-bearing frame transport that contains data governed by an earlier Foundation disclosure contract, the host must satisfy the applicable current gate for that exact transport. For F5 personal-calendar output this includes the current freshness/disclosure decision required by the F5 contract and the exact current surface/channel target eligibility.

A durable F6 presentation session or attempt fence records presentation lineage and idempotency. It is not a standing grant to continue disclosing after current authority changes.

If Permission is revoked, the Relationship or resource binding becomes invalid, freshness expires, disclosure policy denies the target, or the concrete surface/channel route becomes ineligible between two frames:

```text
already-authoritatively-presented frames remain historical truth
↓
next payload frame is blocked before transport
↓
any already in-flight frame is reconciled content-free
↓
no remaining payload is replayed merely to complete the original output
```

Changing surface, channel, embodiment, or presentation generation never broadens the underlying data authority. Recovery may record evidence that a prior authorized payload was already presented; it does not need current disclosure authority merely to preserve historical truth, but it may not send new payload under revoked authority.

## 2.7 Presented extent

Presented extent is append-oriented evidence over exact frames, not a mutable integer inferred from local intent.

A trusted presentation receipt binds at least:

```text
presentation_attempt_id
attempt_generation
frame_ordinal
presentation_key
sink_receipt_ref
presented_at
receipt_contract_version
```

The host may derive a contiguous presented prefix only when every frame from ordinal 1 through N has authoritative presented evidence under one valid lineage. A receipt for frame N does not authorize filling an unproved gap at frame N-1.

Duplicate receipts for the same frame/generation are idempotent. Conflicting receipts, cross-generation receipts, wrong presentation keys, wrong frame digests, or non-contiguous claims fail closed.

## 2.8 Reception / playback evidence

Reception evidence is stronger than presentation evidence and remains separately typed.

The first slice permits a trusted first-party sink to emit a bounded receipt such as:

```text
PLAYBACK_CONFIRMED_THROUGH_FRAME
```

or an equivalent read/display acknowledgement contract.

Reception evidence binds the exact presentation session/generation and exact contiguous frame extent. It cannot exceed presented extent. It cannot be inferred from elapsed wall-clock time, transport success, generation completion, or model intent.

A playback/read receipt establishes only that the trusted first-party client completed the declared delivery contract for that frame extent. It does not establish attention, perception, comprehension, agreement, or understanding.

## 2.9 Canonical counterpart interruption

An interruption is authoritative only after a new trusted counterpart input has crossed normal ingress identity/routing validation and has been durably admitted to the canonical relationship Timeline.

A process-local microphone event, UI gesture, transport disconnect, speculative speech detector event, model guess, or untrusted callback cannot by itself become canonical social interruption.

For an admitted interruption, the host:

```text
records the interrupting input
↓
requests presentation cancellation/settling for the active session generation
↓
prevents authorization of new frames beyond the interrupt fence
↓
reconciles any already in-flight frame outcome
↓
settles exact presented/reception extent
↓
never automatically resumes the unpresented remainder
```

The interrupting input remains canonical even if the presentation sink subsequently fails.

## 2.10 Interruption race and settling proof

The first-party presentation contract must be able to order presentation relative to cancellation/settling strongly enough that the host never fabricates the terminal extent.

Terminal interruption evidence retains at least:

```text
presentation_attempt_id
attempt_generation
presentation_transport_fence_scope_id
settled_through_ref
last_authoritatively_presented_frame
last_authoritatively_received_frame?
settled_at
status_contract_version
```

The terminal proof must guarantee that frames beyond the reported presented extent cannot later become presented under the settled generation without a new explicitly authorized generation.

If the sink cannot prove this property, the session remains `UNKNOWN_PRESENTATION_EXTENT`. The host may perform content-free reconciliation but cannot guess the missing boundary or replay payload merely to force a deterministic answer.

## 2.11 Uncertain presentation outcome

A process loss or ambiguous transport after dispatch but before durable receipt creates uncertainty, not presentation truth.

Recovery for an uncertain generation uses content-free status reconciliation keyed by presentation/session/attempt identity. The lookup must not resend or echo presentation payload.

The authoritative outcomes are:

```text
PRESENTED extent known
NOT_PRESENTED / terminal extent known
UNKNOWN_PRESENTATION_EXTENT
```

A point-in-time absence is not terminal non-presentation unless the sink contract proves no queued/in-flight frame from that generation can later be presented.

Unknown state blocks unsafe payload replay. If the sink can later prove the exact accepted/presented extent, the host records historical truth without treating reconciliation as a new presentation.

## 2.12 Timeline truth for partial presentation

`COMPANION_PRESENTED_OUTPUT` history must represent exactly what was actually presented.

For a fully presented session, the event content equals the canonical complete presented rendering.

For a partially presented session, the event content equals only the canonical concatenation of the authoritative contiguous presented frames. It must not contain the unpresented remainder merely because that remainder existed in `CompanionOutput`.

A specialized presentation-lineage record links the Timeline event to:

```text
source companion_output_id
presentation_session_id
terminal presentation generation
exact first/last presented frame extent
rendering/frame contract version
presented content digest
terminal presentation evidence
```

If zero frames were authoritatively presented, no `COMPANION_PRESENTED_OUTPUT` event is fabricated.

Reception/playback evidence remains linked separately and may cover a shorter prefix than presented extent.

## 2.13 Recovery and idempotency

Complete process loss reconstructs the active/terminal presentation state from durable Alsoul-owned records and trusted content-free sink reconciliation where needed.

Recovery never restores Person identity from the sink/provider session. It resolves the same `CompanionPerson`, Relationship, `CompanionOutput`, bindings, session, attempt generation, frame contract, and known evidence from canonical state.

Repeated recovery cannot:

- create duplicate presentation sessions for the same presentation key;
- create duplicate Timeline presentation events;
- advance presented extent without new authoritative evidence;
- replay uncertain payload before terminal reconciliation;
- resume an interrupted remainder automatically;
- convert a presentation receipt into reception evidence.

## 2.14 F6.A non-scope

The first tranche does not require:

- speech recognition;
- speech synthesis;
- acoustic voice identity;
- camera/video input;
- avatar animation;
- speculative decoding;
- latency-optimized memory retrieval;
- background delegated work;
- autonomous wake words;
- generic media storage;
- human-attention or comprehension inference.

These may be added only behind the same truth boundary when a later executable requirement forces them.

## 2.15 F6.A acceptance bar

F6.A is complete only when executable tests prove all of the following:

1. One presentation session binds exactly one adopted `CompanionOutput` and one resolved Relationship/Surface/Channel target.
2. Session identity, presentation key, and attempt-generation identity are distinct and mechanically enforced.
3. The frame renderer is deterministic under a pinned contract version and reconstructs the exact complete output when all frames are present.
4. Frame ordinals are contiguous, frame source ranges do not overlap, and frame digests bind exact rendered content.
5. No frame transport occurs before a durable presentation attempt/fence exists.
6. The first slice serializes frame transport so presented-order truth cannot depend on completion races between concurrently dispatched frames.
7. Sink presentation evidence is bound to the exact session, attempt generation, presentation key, frame ordinal, and frame content lineage.
8. A later-frame receipt cannot fill an unproved earlier-frame gap.
9. Duplicate exact receipts are idempotent and conflicting/cross-generation receipts fail closed.
10. Reception/playback evidence can never exceed authoritative presented extent.
11. Transport success, elapsed time, rendering completion, or local queueing cannot be promoted to reception/playback evidence.
12. A canonical counterpart input can interrupt an active presentation only after normal trusted ingress admission.
13. An interruption prevents authorization of new post-fence frames while allowing exact reconciliation of material that was already in flight.
14. Terminal interruption proof prevents any old-generation frame beyond the settled extent from later becoming presented without a new generation.
15. A sink unable to prove terminal presented extent leaves the session `UNKNOWN_PRESENTATION_EXTENT` rather than fabricating a prefix.
16. Process loss after payload dispatch but before receipt preserves uncertainty and does not mark the frame presented.
17. Recovery reconciles uncertain state content-free and does not resend payload merely to recover truth.
18. A point-in-time negative lookup cannot prove terminal non-presentation when delayed acceptance remains possible.
19. A partially presented output creates canonical shared history containing only the exact presented prefix.
20. An unpresented remainder never appears in `COMPANION_PRESENTED_OUTPUT` content merely because it existed in GeneratedOutput or CompanionOutput.
21. Zero presented frames create no companion-presented Timeline event.
22. Fully presented output remains backward-compatible with the existing complete-presentation history semantics.
23. Reception/playback evidence is retained separately from the Timeline presented event and may truthfully cover a shorter extent.
24. Complete process restart reconstructs the same Person, Relationship, output, session, attempts, frame lineage, and known presentation evidence before new presentation work.
25. Repeated recovery cannot duplicate presentation history or advance extent without evidence.
26. An interrupted session never automatically resumes its unpresented remainder; a later response/continuation requires a new semantic output/presentation decision.
27. Historical presented extent is not rewritten because a renderer, channel, surface, or embodiment binding is later replaced.
28. No new F7 durable task, commitment, procedure, or generic background-work authority is introduced by F6.A.
29. Every personal-data frame transport re-evaluates the inherited current freshness/disclosure gate required by F5 immediately before that payload transport.
30. Revocation, relationship/resource invalidation, freshness expiry, disclosure-policy denial, or target-route ineligibility between frames blocks the next payload frame before transport.
31. Already-presented personal-data frames remain historical truth after later revocation, while recovery of uncertain prior delivery uses only content-free reconciliation and never unauthorized payload resend.
32. Switching surface, channel, embodiment, session generation, or renderer cannot broaden Permission, disclosure scope, resource scope, or any other earlier Foundation authority.

Passing F6.A authorizes work on F6.B. It does not close F6.

# 3. F6.B — Multi-presence continuity + replaceable embodiment

## 3.1 Objective

Prove that the same durable companion and relationship can interact through more than one explicit social presence while surface, channel, and embodiment remain replaceable bindings beneath Person identity.

The first executable slice uses two distinct first-party social surfaces and at least two channel/binding compositions. It may use deterministic test adapters. Product-specific mobile/desktop/voice SDKs are not required to establish the semantic boundary.

## 3.2 Presence model

The first slice preserves:

```text
CompanionPerson
  ├── SurfaceBinding(s)
  ├── ChannelBinding(s)
  └── EmbodimentBinding(s)

Relationship
  └── canonical Timeline shared across eligible presences
```

A surface describes the social situation. Examples may include a conversational text surface and a realtime call surface, but public semantics remain provider-neutral.

A channel describes transport and endpoint identity. Replacing a channel endpoint or protocol does not replace the social surface or Person.

An embodiment binding selects replaceable presentation configuration/renderer identity for a presentation situation. It cannot author Self, Relationship, memory, authority, or canonical history.

## 3.3 Binding identity and history

Binding identity is immutable once used by canonical history. Replacement creates a new binding/state rather than rewriting historical references.

Every admitted inbound interaction and every presentation session retains the exact surface/channel binding identity used at that time. When an embodiment is involved, presentation lineage retains its exact binding identity as well.

A retired or replaced binding may become ineligible for new work without invalidating historical events that truthfully used it.

## 3.4 Trusted routing

Inbound routing resolves:

```text
trusted destination binding
→ CompanionPerson

trusted sender identity
→ CounterpartPerson

current relationship resolution
→ Relationship
```

before canonical input admission.

Thread IDs, call IDs, device IDs, channel endpoints, model sessions, renderer sessions, and body assets are routing/provenance data only. They cannot create a new `CompanionPerson`, `CounterpartPerson`, or Relationship by themselves.

Cross-binding spoofing, ambiguous destination resolution, untrusted sender identity, or binding-to-Person mismatch fails closed before Timeline admission.

## 3.5 Cross-surface continuity

A later eligible interaction on a different surface may project prior canonical relationship history and admissible memory under normal ContextProjection rules. It does not migrate identity by copying prompt text or provider state.

Surface change may influence derived presentation policy, but it cannot change factual memory, relationship identity, authority, epistemic classification, or prior presentation truth.

Conversation/thread-local context remains narrower than relationship history. A new thread on another surface is not a new Person and is not permission to import arbitrary unrelated context.

A surface/channel transition is never an authority upgrade. Every personal-data or effectful operation continues to satisfy the same current host capability, AI policy, resource scope, Permission, Approval where required, freshness, disclosure, and effect contracts that would apply without the transition.

## 3.6 Embodiment replacement

`EmbodimentBinding` is a replaceable rendering/presentation binding.

The first executable embodiment contract requires at least:

```text
embodiment_binding_id
companion_person_id
embodiment_kind
renderer_binding_ref
presentation_contract_version
bound_at
retired_at?
```

The concrete physical schema may preserve append-only lifecycle through separate state/revision rows rather than an in-place `retired_at`; the semantic requirement is that historical identity is immutable and current eligibility is independently represented.

Replacing an embodiment:

- keeps the same `CompanionPerson` and Relationship;
- does not rewrite historical presentation lineage;
- does not create or copy canonical memory;
- does not implicitly change PresentationProfile/SelfModel;
- requires new presentation sessions to pin the replacement binding explicitly;
- cannot cause an old active presentation session to silently switch renderer mid-generation.

Text-only operation remains valid when no embodiment is selected.

## 3.7 Presentation policy and foreground identity

F6 may derive a presentation policy from the current surface/channel/embodiment situation, but the policy is a bounded snapshot, not a second persona.

A background-origin or alternate-surface event cannot replace the foreground Person, mutate Self, or select a separate canonical memory/persona store merely because it uses another runtime faculty.

The first F6 implementation does not introduce generic durable background work. If a test uses a synthetic background-origin output to prove presentation-policy isolation, that output carries no independent task/commitment authority.

## 3.8 Recovery

After complete process death, runtime composition may change while semantic continuity remains:

```text
same CompanionPerson
same durable Self
same Relationship
same canonical Timeline
same admitted memory/evidence
new process/runtime
new provider/model binding if allowed
new surface/channel/embodiment composition if selected
```

Recovery resolves active presence bindings from canonical durable state. It does not recover Person identity from whichever device, channel, body asset, or provider happens to reconnect first.

An unresolved or ambiguous current binding blocks only the dependent presence/presentation operation when core Person/Relationship state remains otherwise healthy.

## 3.9 F6.B non-scope

F6.B does not require:

- product-grade avatar rendering;
- facial animation;
- full duplex audio/video;
- device sensor access;
- generic background task scheduling;
- cross-user rooms;
- multi-person group relationships;
- social-network discovery;
- durable Commitment semantics;
- learned reusable procedures;
- autonomous proactive outreach.

## 3.10 F6.B acceptance bar

F6.B is complete only when executable tests prove all of the following:

1. The same `CompanionPerson`, Counterpart, Relationship, Self revision, and canonical Timeline survive interaction through two distinct first-party surfaces.
2. `SurfaceBinding`, `ChannelBinding`, and `EmbodimentBinding` identities remain distinct from Person and Relationship identity.
3. A thread/call/device/provider/renderer identifier cannot create a new Person or Relationship merely by changing value.
4. Trusted destination and sender resolution occurs before inbound Timeline admission on every supported surface.
5. Ambiguous, spoofed, mismatched, or untrusted binding resolution fails closed before canonical input admission.
6. Historical InteractionEvents retain the exact surface/channel bindings used when they were admitted.
7. Presentation sessions retain the exact surface/channel/embodiment bindings used for rendering/delivery.
8. Replacing a channel endpoint does not replace the Person, Relationship, Self, memory, evidence, or Timeline.
9. Replacing an embodiment does not replace the Person, Relationship, Self, memory, evidence, or Timeline.
10. Replacing an embodiment creates new current binding lineage rather than rewriting historical binding references.
11. An active progressive presentation cannot silently switch embodiment or rendering contract mid-generation.
12. Text-only presentation remains valid without an embodiment binding.
13. A new interaction on another surface can derive eligible relationship continuity from canonical state without restoring a provider/model session.
14. Cross-surface ContextProjection remains subject to the same memory/evidence/currentness rules and does not import arbitrary thread-local state as relationship truth.
15. Surface-specific presentation policy may change style/shape while leaving epistemic claims, authority, and historical truth unchanged.
16. A background-origin or alternate-surface faculty cannot become a second canonical persona or memory owner.
17. Complete process restart reconstructs the same semantic Person before new model invocation or presentation, regardless of which eligible surface reconnects first.
18. Missing/retired/ambiguous embodiment or channel state blocks only the dependent presentation path and cannot broaden authority or fabricate a replacement binding.
19. Previously presented history remains truthful and unchanged after surface/channel/embodiment replacement.
20. Interruption truth from F6.A remains valid across the alternate realtime-style surface.
21. Generated, adopted, rendered, presented, and reception/playback states remain distinct across all supported surfaces.
22. F6 introduces no generic Commitment, Procedure, durable DelegatedTask, or autonomous long-horizon work semantics.
23. Switching surface, channel, embodiment, device endpoint, renderer, or provider session cannot broaden any earlier Foundation capability, policy, resource, Permission, Approval, freshness, disclosure, or effect authority.

# 4. F6 closure bar

F6 is closed only when all of the following are independently established on the exact reviewed implementation head:

1. F6.A acceptance bar passes in executable tests.
2. F6.B acceptance bar passes in executable tests.
3. Compilation succeeds for source and tests.
4. The complete repository acceptance suite passes; F6 does not replace earlier Foundation acceptance coverage with a narrow F6-only suite.
5. Database migration upgrade/downgrade round trip succeeds for every new F6 schema revision.
6. Exact-head manual review finds no unresolved correctness, recovery, authority, identity, presentation-truth, migration, or scope blocker.
7. Pull-request review discussion contains no unresolved blocking finding.
8. The exact reviewed head is squash-merged without semantic change.
9. The resulting `main` commit passes the same complete post-merge Foundation gate.

The F6 exit audit, when created, records independently established evidence. It must not self-certify closure or use a volatile hard-coded repository test count as normative evidence.

# 5. Implementation order

The required implementation order is:

```text
F6.A contract tests
↓
minimal durable presentation-session/frame/receipt state
↓
interruption + uncertain-outcome reconciliation
↓
partial-presentation Timeline truth
↓
F6.A recovery tests
↓
F6.A acceptance pass
↓
F6.B binding/lifecycle tests
↓
minimal EmbodimentBinding + multi-surface routing continuity
↓
cross-surface recovery and replacement tests
↓
F6.B acceptance pass
↓
full F6 closure audit
```

Implementation must prefer the smallest additive schema/service changes that satisfy the checkpoint. Existing F4/F5 truth and authority contracts remain in force. No F7 subsystem may be pulled forward merely because a future presentation or background mechanism could use it.
