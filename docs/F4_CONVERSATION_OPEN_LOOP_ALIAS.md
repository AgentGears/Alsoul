# F4 Conversation Open Loop Alias

**Status:** Executable bounded Decision 13.C checkpoint  
**Publication:** GitHub-safe

This checkpoint adds explicit counterpart-authored aliases to the existing F4 `DECISION` `ConversationOpenLoop` without turning generated summaries, semantic similarity, or recency into conversational identity authority.

## Semantic boundary

```text
ConversationOpenLoop
≠ ConversationOpenLoopReference
≠ ConversationOpenLoopAlias
≠ current-input selector

open_loop_id
≠ open_loop_reference_id
≠ open_loop_alias_id
≠ canonical alias key
```

`open_loop_id` remains canonical loop identity. A source-derived reference mechanically describes one bounded opening. A `ConversationOpenLoopAlias` is a durable relationship-scoped name explicitly assigned by the counterpart. Neither address changes loop identity.

Aliases are routing state only:

```text
ConversationOpenLoopAlias
≠ MemoryClaim
≠ DelegatedTask
≠ Commitment
≠ Trigger
≠ Permission / Approval
≠ Action authority
```

## Counterpart-authored admission

F4 admits `USER_LABEL` aliases only from bounded counterpart input after trusted ingress. Example:

```text
I need to decide between A and B.
↓
ConversationOpenLoop OL1
+
ConversationOpenLoopReference LR1

Call the decision between A and B "work laptop".
↓
exact DECISION_OPTION_PAIR_V1 target resolution
↓
ConversationOpenLoopAlias LA1
    open_loop_id = OL1
    alias_kind = USER_LABEL
    alias_contract_version = USER_LABEL_V1
    display_label = "work laptop"
    canonical_alias_key = "work laptop"
```

The label command must resolve exactly one active loop before alias state changes. Missing or ambiguous targets fail closed. A model-generated title, summary, inferred topic, embedding result, or semantic search result cannot create a `USER_LABEL`.

## Mechanical alias contract

`USER_LABEL_V1` performs only:

1. Unicode NFC normalization;
2. outer-whitespace trimming;
3. internal-whitespace collapsing; and
4. Unicode case folding.

It does not perform synonym expansion, stemming, paraphrase matching, embeddings, topic inference, or model interpretation.

```text
"Work   Laptop" → "work laptop"

"work laptop" ≠ "office computer"
```

## Active namespace

Within one relationship and the current bounded `DECISION`/`USER_LABEL_V1` namespace, one canonical alias key may address at most one active loop.

```text
OL1 active + alias "work"

attempt alias "work" → OL2 active
↓
CONVERSATION_OPEN_LOOP_ALIAS_CONFLICT
```

Admission is protected by the relationship write fence and rechecks active alias ownership inside the write transaction. Concurrent attempts therefore cannot both establish the same active alias key for different loops.

The same loop may hold multiple aliases. Repeating the same canonical alias for the same active loop reuses the existing alias rather than creating another alias identity.

## Exact alias selectors

The bounded selector grammar can use aliases for resume, resolve, and cancel:

```text
Back to decision "work laptop".
Resolve decision "work laptop".
Cancel decision "work laptop".
```

Resolution is exact and cardinality-based:

```text
0 active matches → TARGET_NOT_FOUND
1 active match    → select it
>1 active matches → AMBIGUOUS / integrity failure
```

There is no candidate ranking phase. The model receives only the already-resolved loop.

A user alias can preserve addressability even when source-derived references later become ambiguous:

```text
OL1 → reference ["a","b"] + alias "work"
OL2 → reference ["a","b"]

Back to decision "work".
↓
OL1
```

Alias assignment does not retroactively solve an already ambiguous unlabeled target. The command that assigns a label must itself have a deterministic target.

## Append-oriented alias lifecycle

Alias lifecycle is separate from loop lifecycle.

```text
remove alias ≠ close loop
close loop ≠ erase alias history
rename ≠ mutate historical alias
```

Removal appends `ConversationOpenLoopAliasRetirement(kind=REMOVED)`.

Rename is:

```text
LA1 = "work laptop"
↓
retire LA1 as RENAMED
+
LA2 = "new laptop"
```

The original alias row remains immutable. A closed loop retains its aliases historically, but normal alias selection considers only active loops with non-retired aliases. A former alias key may therefore be explicitly reused by a later active loop after the old ownership no longer participates in the active namespace.

## ContextProjection and recovery

A successful alias resume is pinned before provider execution:

```text
ContextProjection
    selected_open_loop = OL1
    selected_alias = LA1
    selection_basis = EXPLICIT_USER_ALIAS
    selector_contract = USER_LABEL_V1
    selector_key = "work laptop"
```

Recovery does not search aliases again to decide what the original interaction meant. It recovers the immutable projection and validates whether that pinned selection remains eligible for another provider execution.

Alias-selected reuse requires:

```text
OL1 remains active
LA1 remains attached to OL1
LA1 remains unretired
exact active USER_LABEL_V1("work laptop") resolution remains {OL1}
```

An unrelated active loop or another different alias does not invalidate the selection. Alias retirement or closure of the selected loop does.

## Provider boundary

The provider receives the already-resolved open-loop context, not alias candidate state. Explicit alias selection records:

```text
selection_policy = EXPLICIT_USER_ALIAS
renderer_version = f4-renderer-v5
```

Existing provider contracts remain distinct:

```text
ordinary / prior-Timeline / unqualified open loop → f4-renderer-v3
explicit Decision 13.B source reference          → f4-renderer-v4
explicit Decision 13.C user alias                → f4-renderer-v5
```

Alias text is user-authored routing metadata. It is not privileged model instruction, policy, permission, or authority.

## Persistence and migration

Schema v4 adds:

```text
conversation_open_loop_alias
conversation_open_loop_alias_retirement
context_projection_open_loop_alias_selector
```

Migration `0004_open_loop_user_alias` deliberately performs no alias backfill. Earlier schema versions contain no canonical counterpart-authored alias-assignment contract from which a `USER_LABEL_V1` alias could be reconstructed without inventing state.

## F4 exclusions

This checkpoint does not implement semantic alias matching, model-generated loop titles, arbitrary history search, automatic alias creation, automatic rename, general open-loop kinds, background work, reminders, proactive contact, or authority derived from conversational labels.
