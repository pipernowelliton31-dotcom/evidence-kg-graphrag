# Fast cluster alignment

## Goal

Resolve durable identities with minimal model work. Do not turn alignment into an evidence-audit task.

## Pipeline

1. repair obvious identity metadata;
2. deterministic merge by scoped ID, explicit alias declaration, stable record key and stable exact name when no hard conflict exists;
3. indexed candidate blocking;
4. cluster-level LLM Select only for ambiguous cross-name cases;
5. rerun a collective round only if a merge changed context.

Global Event alignment is disabled by default; Event IDs can intentionally repeat across distinct events and one-off Events rarely need expensive cross-document ER.

## Compact task

Profiles contain only a few names/aliases, IDs, stable attributes, up to four relation-neighbor signals and one short evidence example. Do not resend all members or full source text.

The model returns only:

```json
{"task_id":"align_...","decision":"entity_..."}
```

or `NEW_ENTITY / UNCERTAIN`. `reason` is optional; `evidence_ids` are never required because the host already owns the task evidence.

## Hard conflicts kept

Only identity-breaking conflicts remain hard:

- incompatible entity type;
- incompatible scoped IDs;
- explicit distinct versions/variants/parent IDs;
- person-vs-organization conflict where explicit;
- endpoints of explicit distinct relations such as replacement/version transitions when merging them would collapse the relation.

Do not add soft “maybe different context” checks. Same stable entity should merge aggressively when strong name/alias/ID evidence exists.

## Concurrency

All tasks in one alignment round use the same frozen snapshot. They may be split into disjoint batches and called concurrently. Apply responses against that round, then start the next round only after all relevant decisions are accepted.

Recommended provider concurrency: 8 initially; benchmark 8–12 if rate limits permit.
