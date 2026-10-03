# Lean multi-channel GraphRAG

## Channels

```text
Question
  -> cheap Query Planner
     -> Structured Retrieval
     -> Fact BM25 + diversity cap
     -> Entity Profile / alias bindings
     -> Entity Linking -> Weighted Beam Graph Search (when useful)
  -> source-aware Raw BM25
  -> compact mixed evidence context
  -> final LLM answer
```

No embedding model, vector DB, Neo4j, GNN, community summaries or global graph preprocessing.

## Planner

Recognize at least:

- `structured_lookup`: explicit Sheet/field/row/cell/page/slide/table;
- `cross_format_identity`: two or more named source formats plus name/alias/call-it wording;
- `causal`, `comparison`, `rank`, `timeline`, `list_all`;
- explicit expected counts and year/quarter/month;
- requested source formats.

Important lexical guards:

- `列出 / 逐一列出` is a verb, not a spreadsheet column;
- `使用了什么名称` is naming language, not business relation `uses`.

## Cross-format identity/source comparison

For questions asking how one entity is named across PDF/Word/Excel/PPT/image or other systems:

1. link the entity;
2. send `ENTITY_PROFILE` with aliases and `alias_bindings`;
3. reserve source coverage for every explicitly requested format;
4. retrieve separate “name/alias” and “unique information” raw evidence per format;
5. skip graph beam unless the question also asks for a real relation path.

Alias-table column roles are preserved from the source itself. The code never hardcodes a benchmark-specific mapping.

## Fact retrieval

BM25 indexes names/aliases, predicate, value/object and qualifiers. Cap near-duplicate families so repeated monthly `A uses B` facts do not consume the full Top-K.

## Graph retrieval

Only use graph traversal when the question needs relations/multi-hop reasoning. Weighted beam defaults:

- max hops 3;
- beam width 20;
- branch width 8;
- relation/query/time/fact relevance bonuses;
- degree and path-length penalties.

Never restore wide BFS enumeration.

## Raw evidence and context budget

Raw Source is first-class evidence. Put Entity Profile and several source-diverse Raw Source blocks into context **before** facts and graph paths so raw evidence cannot be starved by repeated facts.

For explicit multi-format questions, reserve at least one source unit per requested format when available; prefer complementary source locations rather than duplicate page/table views.

## Final answer

The final model directly writes:

```text
## 1. 结论
...
## 2. 推理路径
...
## 3. 不确定项
...
```

Only important uncertainty belongs in section 3. Do not add generic methodological disclaimers that do not change the answer.
