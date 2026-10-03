---
name: evidence-kg-builder
description: 将 PDF、Word、Excel、PPT 和图片企业材料快速解析为高覆盖 Canonical Facts、稀疏知识图谱，并用轻量多通道 GraphRAG 完成跨格式检索与多跳问答。适用于企业异构数据的实体抽取、别名对齐、事件/指标关联、变更影响分析和可解释问答。优先速度与召回：结构字段由 Python 处理，LLM 只做语义增量；模型输出采用最小 JSON，来源 locator 自动继承；只保留结构完整性和硬身份冲突检查，不做逐字 evidence 审计或冗余语义验收。
---

# Evidence KG Builder

构建 **高覆盖 Fact Store + 稀疏 KG + Lean GraphRAG**。第一目标是把可用知识留下并快速检索，不要为了“审计完美”牺牲召回率和墙钟时间。

按阶段读取：抽取前读 [selection.md](references/selection.md)，对齐前读 [alignment.md](references/alignment.md)，查询前读 [graphrag.md](references/graphrag.md)；输出契约见 [contracts.md](references/contracts.md)。只有解析异常时读 [parsing.md](references/parsing.md)。

## Core principles

1. **Speed and recall first**：相信宿主模型的语义抽取；格式小错自动修复或直接保留，不做逐字 quote、domain/range、raw literal、evidence hash 等语义审计。
2. **Only hard integrity gates**：只硬拦任务/文件指纹错误、最终 dangling ID、明显硬身份冲突和无法解析的结构；其它问题最多 warning。
3. **Rule first, semantic overlay**：订单、客户、产品、金额、日期等结构字段交给 Python；备注、原因、风险、影响、视觉关系和歧义才交给 LLM。
4. **Minimal model output**：LLM 只返回语义 delta；默认不返回重复 quote/evidence/reason。Unit locator 自动作为 provenance。
5. **Fact before Node**：普通数值、日期、价格、状态都留在 Fact；只有稳定身份、关键 Event 和需要 traversal 的对象建节点。
6. **Cluster alignment**：先 deterministic compaction，再对少量模糊 cluster 做 LLM Select；Alignment 只返回 `entity_id / NEW_ENTITY / UNCERTAIN`。
7. **Graph is one channel, not all knowledge**：Structured、Fact、Entity Profile、Graph、Raw Source 都是一等检索来源。
8. **Intent-aware retrieval**：跨格式名称/别名问题走 Entity Profile + source-aware retrieval，不跑无意义图扩展；结构扫描走 Structured；多跳问题才走 weighted beam。
9. **Direct Markdown answer**：最终模型直接输出三段答案，不先 JSON 再渲染。
10. **No benchmark leakage**：允许企业通用字段和 ontology；禁止评测集具体实体、别名、ID、数值、日期、Sheet 名和答案映射进入 production Skill。

## Environment

Python 3.11。不要安装 OCR、本地 embedding、向量数据库、Neo4j 或 GNN。

```bash
python -m pip install -r requirements.txt
```

## Input manifest

```json
{"root":"./materials","files":[
  {"path":"manual.docx","role":"corpus"},
  {"path":"questions.docx","role":"questions"},
  {"path":"task.pdf","role":"reference"}
]}
```

只有 `corpus` 进入知识抽取。题目本身不能作为事实来源。

# Build workflow

## 1. Parse

```bash
python scripts/kg_pipeline.py parse --manifest <inputs.json> --work <work> --fresh
```

输出 `00_document_units.json`。XLSX 用 openpyxl；PDF 优先文本层并懒渲染图片；DOCX/PPTX 直接解析原生结构；图片保留原图给宿主多模态能力。

### Optional MarkItDown entry

默认保持上述原生解析。只有用户选择 MarkItDown 阅读视图时，读取 [parsing-markitdown.md](references/parsing-markitdown.md)，安装可选依赖并改用独立入口：

```bash
python -m pip install -r requirements-markitdown.txt
python scripts/parse_markitdown.py --manifest <inputs.json> --work <separate-work> --fresh
```

它保留相同的 DocumentUnit、来源定位和原生结构契约。后续 `prepare / tasks / accept / build / validate` 和 GraphRAG 使用原有命令。不要混用两条路线的工作目录。

## 2. Prepare

```bash
python scripts/kg_pipeline.py prepare --work <work>
```

不调用模型。显式别名表、结构化业务字段、普通订单/指标先 deterministic；XLSX 自由文本只生成 `semantic overlay`，不把整行重复送给模型。

## 3. Semantic extraction

单批建议 4–5 个 task / 12k–14k 字符。若宿主支持并发，直接一次申请多个不重叠 batch：

```bash
python scripts/kg_pipeline.py tasks --stage extract --work <work> \
  --limit 5 --char-budget 14000 --batch-count 8 --output extract_batches.json
```

`batches[]` 可并发调用模型。推荐 host concurrency **6–8**；不要靠把单请求塞到 12–20 个 Unit 来提速。

模型只返回最小语义 delta：

- mention：`local_id, type, name, aliases/identifiers`；
- relation：`subject, predicate, object, qualifiers`；
- assertion：`subject, predicate/value, qualifiers`；
- evidence/quote/review reason 默认省略；
- `unresolved` 只写真正影响语义的歧义；
- `known_mentions` 可直接作为 relation/assertion 端点，不要重复声明；
- `xlsx_semantic_overlay` 不重述 Python 已抽出的订单/金额/日期等事实。

每个并发结果分别：

```bash
python scripts/kg_pipeline.py accept --stage extract --work <work> --response <response.json>
```

Acceptor 会自动继承 Unit locator、按唯一 name/alias 修复端点、保留未知 relation predicate，并把未知 literal predicate 降为普通 attribute；不会因为 quote 不匹配、类型 domain/range、raw literal 格式等把正确事实隔离。

## 4. Alignment

```bash
python scripts/kg_pipeline.py tasks --stage align --work <work> \
  --limit 8 --batch-count 8 --output align_batches.json
```

同一 round 的 `batches[]` 基于冻结 snapshot，可并发调用。推荐 alignment concurrency **8–12**，视 provider 限流调整。

LLM 每题只返回：

```json
{"task_id":"align_...","decision":"entity_..."}
```

或 `NEW_ENTITY / UNCERTAIN`。不要强制 reason 或 evidence_ids。

```bash
python scripts/kg_pipeline.py accept --stage align --work <work> --response <response.json>
```

只保留真正必要的 hard identity conflict；Event 不做昂贵的全局对齐。

## 5. Build

```bash
python scripts/kg_pipeline.py build --work <work>
```

Build 不再被语义审计阻塞。`validate` 仅做最小引用完整性检查：

```bash
python scripts/kg_pipeline.py validate --work <work> --require-complete
```

它不会因为 quote、raw literal、attribute claim、domain/range 或 unresolved 数量拒绝图。

# Lean GraphRAG

```bash
python scripts/lean_graphrag.py --work <work> --question "<问题>" --retrieve-only
```

查询分流：

```text
Query Planner
  ├─ Structured Retrieval
  ├─ Fact BM25 (with diversity cap)
  ├─ Entity Profile / alias bindings
  └─ Entity Linking -> Weighted Beam Graph Search (only when useful)
        ↓
  Raw BM25 / source-aware coverage
        ↓
  compact context
        ↓
  final LLM answer
```

关键策略：

- `列出/逐一列出` 不能误判为 Excel “某一列”；
- “使用了什么名称”不能触发业务 `uses` 关系；
- 若问题明确要求 PDF/Word/Excel/PPT/图片等多个来源，Planner 标记 `cross_format_identity`，按来源保留覆盖，并优先传 `ENTITY_PROFILE.aliases/alias_bindings`；
- 这类身份/来源对照题默认 **不跑 graph beam**；
- Fact 检索对相同 `subject+predicate+object` 做 diversity cap，避免月份重复事实霸榜；
- Raw Source 在 context 早期预留空间，不能被 Fact/Path 吃光；
- 多跳问题用 weighted beam，默认 3 hop、beam 20、branch 8，不恢复宽 BFS。

## Final answer

```bash
python scripts/lean_graphrag.py --work <work> --question "<问题>" --env-file .env
```

模型直接输出：

```text
## 1. 结论
...

## 2. 推理路径
实体A →(关系)→ 实体B（来源：文件，locator）→ ...

## 3. 不确定项
无重要不确定项 / 只列会改变结论的关键缺失或冲突
```

不要把 debug telemetry、轻微口径提醒、一般方法学免责声明塞进正文。Raw Source 与 Canonical Fact 都可以直接支持答案。

# Delivery checks

交付前只确认：

- corpus 都已 parse 或明确记录 parse failure；
- extraction pending=0；
- alignment stopped；
- graph 无 dangling node/fact/edge ID；
- production Skill 无评测集具体内容；
- Structured / Fact / Entity Profile / Graph / Raw 通道可用；
- 最终回答严格三段。
