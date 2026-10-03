# Fast selective extraction

## Goal

Maximize useful knowledge retained per model-second. Scan the full corpus, but never make the LLM restate deterministic structure.

## Routing

- `auto_no_facts`: structural/title-only;
- `deterministic_alias_table`: explicit canonical-name / alternate-name tables;
- `deterministic_xlsx`: explicit business rows without semantic free text;
- `xlsx_semantic_overlay`: Python keeps structured facts; LLM receives only remarks/reasons/risks/feedback plus compact row context;
- `llm_semantic / llm_visual`: genuinely semantic content.

## Minimal completion

Prefer the smallest response that preserves semantics:

- mention: `local_id/type/name`, plus aliases or IDs only when present;
- relation: endpoint IDs/names + predicate;
- assertion: subject + value + compact qualifiers;
- omit repeated evidence/quote; provenance is inherited from the Unit;
- omit review prose;
- do not echo deterministic rows or `known_mentions`;
- do not enumerate generic nouns;
- only create Event when it is useful for later traversal.

## Acceptance policy

Trust the model. The host should repair or preserve rather than audit:

- quote missing/mismatched -> inherit locator;
- ordinary JSON number -> keep;
- unknown relation predicate -> keep;
- unknown literal predicate -> store as generic attribute;
- endpoint written as unique entity name/alias -> resolve automatically;
- domain/range mismatch -> do not reject at extraction time;
- raw literal not verbatim in quote -> irrelevant;
- one malformed item -> skip that item only, no unresolved audit record unless the model itself declares genuine semantic ambiguity.

Only source/task identity and final reference integrity remain hard checks.

## Batch policy

Prefer **4–5 tasks / 12k–14k semantic characters per request**, then parallelize requests. With a provider that tolerates it, use 6–8 concurrent extraction calls. Large 20k–30k-token completions are worse than a few more concurrent compact requests.
