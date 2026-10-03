# Fast data contract

## Workflow

```text
parse -> prepare -> extract -> align -> build -> query
```

## Minimal extraction response

Per task, return only semantic delta. `review`, `reason`, `quote` and `evidence` are optional.

```json
{
  "fingerprint":"...",
  "tasks":[{
    "task_id":"unit_...",
    "mentions":[
      {"local_id":"p","type":"Product","name":"Example Product","aliases":["Example Pro"]},
      {"local_id":"t","type":"AITool","name":"Tool X"}
    ],
    "relations":[
      {"subject":"p","predicate":"depends_on","object":"t","qualifiers":{}}
    ],
    "assertions":[
      {"subject":"p","predicate":"revenue","value":18.5,"qualifiers":{"period":"2031-06"}}
    ]
  }]
}
```

The acceptor:

- automatically attaches the parser Unit locator as provenance when item evidence is omitted;
- resolves endpoints by local ID or unique name/alias;
- preserves unknown relation predicates instead of rejecting them;
- converts unknown literal predicates to `attribute` with the original predicate as the attribute name;
- accepts normal JSON numeric values;
- skips only an individual item whose endpoint cannot be resolved; it does not quarantine the entire task.

`unresolved` is optional and reserved for genuine semantic ambiguity, not formatting mistakes.

## Minimal alignment response

```json
{
  "fingerprint":"...",
  "round":1,
  "tasks":[
    {"task_id":"align_...","decision":"entity_..."},
    {"task_id":"align_...","decision":"NEW_ENTITY"}
  ]
}
```

`reason` is optional. `evidence_ids` are never required.

## Ontology

Preferred node types:

`Product, AITool, Actor, DataAsset, Version, Event, Observation`

Preferred relations:

`depends_on, uses, purchased, version_of, upgraded_to, replaced_by, merged_into, sister_product, affects, has_participant, has_observation, has_feedback, reported_cause, cites_data`

The preferred relation set guides extraction and retrieval; it is **not** a hard acceptance whitelist. Unknown relation predicates may remain as sparse graph edges.

## Evidence

Parser locator is authoritative provenance. Item-level quote is optional. No literal substring audit is required.

## Final graph integrity

Hard failures are limited to malformed top-level graph arrays, duplicate/missing IDs, dangling node/fact/edge references, and edge/fact ID mismatches. Everything else is warning-level metadata.
