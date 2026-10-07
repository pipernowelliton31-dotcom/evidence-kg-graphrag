#!/usr/bin/env python3
"""Lean multi-channel GraphRAG: structured + fact BM25 + entity/graph beam search + raw evidence."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

try:
    from kg_core import _xlsx_header_row_numbers, _xlsx_headers, read_json
except ImportError:  # pragma: no cover
    from .kg_core import _xlsx_header_row_numbers, _xlsx_headers, read_json

try:
    from model_io import model_text, write_model_text
except ImportError:  # pragma: no cover
    from .model_io import model_text, write_model_text

LITERAL_PREDICATES = {"attribute", "observed_value", "event_time", "recorded_time"}
STOPWORDS = {
    "为什么", "为何", "原因", "怎么", "如何", "什么", "哪些", "哪个", "是否", "请", "说明", "分析",
    "的", "了", "在", "是", "和", "与", "对", "从", "到", "有", "一个", "分别", "相关", "问题",
    "sheet", "工作表", "表格", "列", "字段", "页面", "页", "slide", "幻灯片",
}
RELATION_TERMS = {
    "reported_cause": ("原因", "因果", "归因", "导致", "cause"),
    "affects": ("影响", "冲击", "affect"),
    "has_participant": ("参与", "负责人"),
    "depends_on": ("依赖", "dependency"),
    "uses": ("使用工具", "采用工具", "调用工具", "工具"),
    "has_observation": ("指标", "收入", "续费", "转化", "评分"),
    "has_feedback": ("反馈", "投诉"),
    "version_of": ("版本",),
    "upgraded_to": ("升级",),
    "purchased": ("购买", "订单", "客户"),
    "replaced_by": ("替代", "停售"),
    "merged_into": ("合并", "并入"),
    "sister_product": ("关联产品", "姊妹", "姐妹"),
    "cites_data": ("数据", "来源"),
}
ANSWER_PROMPT = """你是企业异构数据知识图谱问答助手。根据提供的结构化记录、Canonical Facts、图路径和原始来源回答问题。
这些材料都是可用证据：Raw Source 并不低于 Canonical Fact；图用于连接事实，原文用于补漏和定位。
不要把问题前提当成事实，也不要使用材料之外的知识。
表格还原时，以 TABLE_SCHEMA 的有序表头和列数、TABLE_ROW 的完整行数组为依据，逐列对应；不得合并不同的表头。保留空单元格的位置，区分关联产品与备注等相邻字段。STRUCTURED_ROW 给出同一行各单元格，可用于确认工具名称和关联产品。若 TABLE_COVERAGE 显示遗漏行，不要声称已扫描全部记录。
时间线问题优先核对 TIMELINE_EVENT 的日期、变更和来源；sources 编号对应 TIMELINE_SOURCE 的文件及 locator。区分事件日期、记录日期与月份，不能用行序替代明确日期。多个事件记录可能描述同一业务变更，应结合证据合并叙述。若 TIMELINE_COVERAGE 显示遗漏，不要声称已列全；claims_omitted 表示只展示了该事件的部分事实。

回答必须严格只有下面三个 Markdown 段落，标题文字保持不变：
## 1. 结论
直接回答题目。优先给出最重要的结果、数量、对象、时间或原因；不要先写免责声明。

## 2. 推理路径
用多跳链条展示关键推理，每一跳写来源文件和 locator。优先使用实际图关系：
实体A →(关系类型)→ 实体B（来源：文件名，页码/章节/Sheet/行/单元格/Slide）→ ...
如果题目本质是 Sheet/列/表格扫描，可使用“原始记录 →(表明)→ 业务线索/结论”的证据链，但不要捏造不存在的业务关系。
只展示真正支撑结论的路径，不要堆无关路径。

## 3. 不确定项
仅写会改变主要结论、导致题目某个明确要求无法回答、或关键来源彼此冲突的不确定性。
没有这种重要不确定性时直接写“无重要不确定项”。不要把一般方法学提醒、不同指标不可直接比较、报告归因不等于实验因果等不影响本题结论的限定语反复写进正文。

材料中若明确写“导致、归因、影响、贡献”等，可以按来源表述正常回答，不需要额外弱化成方法学免责声明。
如果 ENTITY_PROFILE 或来源表明确给出同一实体在不同系统/格式中的别名映射，直接逐项使用这些映射，不要求它们必须出现在图路径中。语言简洁、重点突出。"""


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def norm(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")).casefold())


def phrase_in(phrase, text):
    p, t = norm(phrase), norm(text)
    if not p:
        return False
    if re.fullmatch(r"[a-z0-9_.+\-/]+", p):
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", t))
    return p in t


def locator_text(locator):
    if not isinstance(locator, dict):
        return ""
    order = ["page", "section", "sheet", "row", "row_start", "row_end", "cell", "cells", "cell_range", "slide", "table", "shape_ids", "image"]
    parts = []
    for key in order:
        if key in locator and locator[key] not in (None, "", [], {}):
            value = locator[key]
            if isinstance(value, list):
                value = ",".join(map(str, value))
            parts.append(f"{key}={value}")
    return "; ".join(parts) or compact(locator)


class BM25Lite:
    """Small standard-library Okapi BM25 implementation."""
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.lengths = [len(d) for d in docs]
        self.avgdl = sum(self.lengths) / max(1, self.n)
        self.freqs = [Counter(d) for d in docs]
        df = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query_tokens):
        if not self.n or not query_tokens:
            return [0.0] * self.n
        result = []
        for freq, dl in zip(self.freqs, self.lengths):
            score = 0.0
            for term in query_tokens:
                f = freq.get(term, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / max(self.avgdl, 1e-9))
                score += self.idf.get(term, 0.0) * f * (self.k1 + 1) / denom
            result.append(score)
        return result


class LeanGraphRAG:
    def __init__(self, work_dir, *, max_hops=3, max_seeds=6, beam_width=20, branch_width=8,
                 top_paths=6, top_facts=14, top_structured=24, top_units=10, context_chars=18000):
        self.work = Path(work_dir).resolve()
        self.max_hops = max_hops
        self.max_seeds = max_seeds
        self.beam_width = beam_width
        self.branch_width = branch_width
        self.top_paths = top_paths
        self.top_facts = top_facts
        self.top_structured = top_structured
        self.top_units = top_units
        self.context_chars = context_chars
        graph = read_json(self.work / "04_knowledge_graph.json")
        facts_path = self.work / "03_canonical_facts.json"
        canonical = read_json(facts_path) if facts_path.exists() else graph
        parsed = read_json(self.work / "00_document_units.json")
        self.nodes = {n["id"]: n for n in graph.get("nodes", [])}
        self.facts = {f["fact_id"]: f for f in canonical.get("facts", [])}
        self.evidence = {e["evidence_id"]: e for e in canonical.get("evidence", [])}
        self.documents = {d["document_id"]: d for d in parsed.get("documents", graph.get("documents", []))}
        self.units = {u["unit_id"]: u for u in parsed.get("units", []) if u.get("content_md", "").strip()
                      and self.documents.get(u["document_id"], {}).get("role", "corpus") == "corpus"}
        self.labels = {}
        self.known_terms = set()
        for nid, node in self.nodes.items():
            labels = [node.get("name", ""), *node.get("aliases", [])]
            for claim in node.get("attribute_claims", []):
                for identifier in claim.get("identifiers", []):
                    labels.append(identifier.get("value", ""))
            labels = [x for x in labels if str(x).strip()]
            self.labels[nid] = sorted(set(labels), key=lambda x: (-len(norm(x)), x))
            self.known_terms.update(self.labels[nid])
        self.adjacency = defaultdict(list)
        for edge in graph.get("edges", []):
            if edge.get("source") not in self.nodes or edge.get("target") not in self.nodes:
                continue
            refs = [fid for fid in edge.get("fact_ids", []) if fid in self.facts]
            if not refs:
                continue
            item = {**edge, "fact_ids": refs}
            self.adjacency[item["source"]].append((item["target"], item, "outgoing"))
            self.adjacency[item["target"]].append((item["source"], item, "incoming"))
        self.subject_facts = defaultdict(list)
        self.unit_nodes = defaultdict(set)
        for f in self.facts.values():
            self.subject_facts[f.get("subject")].append(f["fact_id"])
            for eid in f.get("evidence_ids", []):
                ev = self.evidence.get(eid)
                if ev:
                    for nid in (f.get("subject"), f.get("object")):
                        if nid in self.nodes:
                            self.unit_nodes[ev.get("unit_id")].add(nid)
        self.structured_entries = self._build_structured_entries()
        self.fact_entries = self._build_fact_entries()
        self.raw_entries = [{"id": uid, "text": u.get("content_md", "")} for uid, u in sorted(self.units.items())]
        self._make_indexes()

    def _tokens(self, text):
        text = unicodedata.normalize("NFKC", str(text or "")).casefold()
        tokens = []
        tokens += re.findall(r"[a-z0-9]+(?:[_.+\-/][a-z0-9]+)*", text)
        for run in re.findall(r"[\u4e00-\u9fff]+", text):
            if len(run) <= 8:
                tokens.append(run)
            tokens += [run[i:i+2] for i in range(max(0, len(run)-1))]
            if len(run) <= 12:
                tokens += [run[i:i+3] for i in range(max(0, len(run)-2))]
        return [t for t in tokens if t and t not in STOPWORDS and len(t) > 1]

    def _make_indexes(self):
        self.fact_bm25 = BM25Lite([self._tokens(e["text"]) or ["__empty__"] for e in self.fact_entries])
        self.structured_bm25 = BM25Lite([self._tokens(e["text"]) or ["__empty__"] for e in self.structured_entries])
        self.raw_bm25 = BM25Lite([self._tokens(e["text"]) or ["__empty__"] for e in self.raw_entries])

    @staticmethod
    def _format_name(document):
        value = str(document.get("format") or Path(str(document.get("path", ""))).suffix.lstrip(".")).casefold()
        if value in {"doc", "docx", "word"}:
            return "word"
        if value in {"xls", "xlsx", "excel"}:
            return "excel"
        if value in {"ppt", "pptx", "powerpoint"}:
            return "ppt"
        if value in {"png", "jpg", "jpeg", "webp", "image", "图片"}:
            return "image"
        if value == "pdf":
            return "pdf"
        return value

    def _entity_profile(self, nid):
        node = self.nodes[nid]
        identifiers = []
        for claim in node.get("attribute_claims", []):
            identifiers.extend(claim.get("identifiers", []))
        return {"id": nid, "type": node.get("type"), "name": node.get("name"),
                "aliases": node.get("aliases", [])[:20],
                "alias_bindings": node.get("alias_bindings", [])[:20],
                "identifiers": [{"scope": x.get("scope"), "value": x.get("value")} for x in identifiers[:12]]}

    def _build_fact_entries(self):
        result = []
        for fid, fact in sorted(self.facts.items()):
            subject = self.nodes.get(fact.get("subject"), {})
            obj = self.nodes.get(fact.get("object"), {}) if fact.get("object") else {}
            parts = [subject.get("name", ""), *subject.get("aliases", []), fact.get("predicate", ""),
                     obj.get("name", ""), *obj.get("aliases", []), compact(fact.get("value", "")), compact(fact.get("qualifiers", {}))]
            result.append({"id": fid, "text": " ".join(str(x) for x in parts if x), "fact": fact})
        return result

    @staticmethod
    def _col(coord):
        m = re.match(r"([A-Z]+)", str(coord))
        return m.group(1) if m else ""

    def _build_structured_entries(self):
        entries = []
        for uid, unit in sorted(self.units.items()):
            structured = unit.get("structured", {}) or {}
            kind = structured.get("kind")
            source = self.documents.get(unit["document_id"], {}).get("path", "")
            if kind == "xlsx_cells":
                try:
                    headers, depth = _xlsx_headers(unit)
                    header_rows = _xlsx_header_row_numbers(unit, depth)
                except Exception:
                    headers, header_rows = {}, set()
                for record in structured.get("records", []):
                    row = record.get("row")
                    if row in header_rows:
                        continue
                    for cell in record.get("cells", []):
                        raw = str(cell.get("raw", "") or "").strip()
                        if not raw:
                            continue
                        col = self._col(cell.get("coordinate"))
                        header = headers.get(col, col)
                        locator = {**unit.get("locator", {}), "row": row, "cell": cell.get("coordinate")}
                        text = f"{source} {unit.get('locator', {}).get('sheet','')} {header} {raw}"
                        entries.append({"id": f"struct:{uid}:{cell.get('coordinate')}", "kind": "xlsx_cell", "unit_id": uid,
                                        "document_id": unit["document_id"], "source": source, "locator": locator,
                                        "sheet": unit.get("locator", {}).get("sheet", ""), "field": header, "value": raw, "text": text,
                                        "hidden": bool(record.get("hidden"))})
            elif kind == "pdf_table":
                header = structured.get("header", [])
                for idx, row in enumerate(structured.get("records", []), start=unit.get("locator", {}).get("row_start", 1)):
                    vals = list(row) if isinstance(row, (list, tuple)) else [row]
                    for ci, value in enumerate(vals):
                        raw = str(value or "").strip()
                        if not raw:
                            continue
                        field = str(header[ci] if ci < len(header) else f"col_{ci+1}")
                        locator = {**unit.get("locator", {}), "row": idx, "column": ci + 1}
                        entries.append({"id": f"struct:{uid}:{idx}:{ci}", "kind": "pdf_table_cell", "unit_id": uid,
                                        "document_id": unit["document_id"], "source": source, "locator": locator,
                                        "field": field, "value": raw, "text": f"{source} {field} {raw}"})
            elif kind == "pptx_shapes":
                for shape in structured.get("shapes", []):
                    text_value = str(shape.get("text", "") or "").strip()
                    if text_value:
                        locator = {**unit.get("locator", {}), "shape_ids": [shape.get("shape_id")]}
                        entries.append({"id": f"struct:{uid}:shape:{shape.get('shape_id')}", "kind": "ppt_shape", "unit_id": uid,
                                        "document_id": unit["document_id"], "source": source, "locator": locator,
                                        "field": shape.get("name", "shape"), "value": text_value,
                                        "text": f"{source} {shape.get('name','')} {text_value}"})
        return entries

    @staticmethod
    def _resolve_schema_hint(candidate, names):
        """Resolve a textual candidate to the most specific existing schema name."""
        value = norm(candidate).strip('“”"\'「」『』')
        exact = [name for name in names if norm(name) == value]
        if exact:
            return sorted(exact)[0]
        # Prefixes such as Excel"..." and Sheet的 belong to the question syntax.
        # Prefer the longest suffix so 处理备注 is not resolved to the shorter 备注.
        matches = [name for name in names if norm(name) and value.endswith(norm(name))]
        if not matches:
            return None
        longest = max(len(norm(name)) for name in matches)
        matches = [name for name in matches if len(norm(name)) == longest]
        return sorted(matches)[0] if len({norm(name) for name in matches}) == 1 else None

    def _structure_hints(self, question):
        sheet_candidates, column_candidates = [], []
        quoted = r'[“"\'「『]([^”"\'」』]{1,40})[”"\'」』]'
        for match in re.finditer(quoted, question):
            tail = question[match.end():]
            # Only adjacent structural cues describe the quoted name. A later column
            # reference must not turn the quoted sheet/product into a column hint.
            if re.match(r'\s*(?:的\s*)?(?:sheet|工作表)', tail, flags=re.I):
                sheet_candidates.append(match.group(1))
            elif re.match(r'\s*(?:的\s*)?(?:列(?!出)|字段)', tail):
                column_candidates.append(match.group(1))
        for pattern in (r'([^\s，。,:：]{1,40})\s*(?:sheet|工作表)',
                        r'(?:sheet|工作表)\s*[:：]\s*([^\s，。,:：]{1,40})'):
            sheet_candidates.extend(m.group(1) for m in re.finditer(pattern, question, flags=re.I))
        for match in re.finditer(r'([\u4e00-\u9fffA-Za-z0-9_\-]{1,40})列(?!出)', question):
            candidate = re.sub(r'(?:的|中|里|内)$', '', match.group(1)).strip()
            # 「列对应/列一致/列映射」描述表头关系，不是请求某个具体列。
            if candidate and not re.match(r'(?:对应|一致|映射|关系|名称|定义)', question[match.end():]):
                column_candidates.append(candidate)
        entries = self.structured_entries
        sheets = {e['sheet'] for e in entries if e.get('sheet')}
        sheet_hints = list(dict.fromkeys(h for value in sheet_candidates
                                       if (h := self._resolve_schema_hint(value, sheets))))
        scoped = [e for e in entries if not sheet_hints or any(
            norm(h) == norm(e.get('sheet', '')) for h in sheet_hints)]
        fields = {e['field'] for e in scoped if e.get('field') and
                  e.get('kind') in {'xlsx_cell', 'pdf_table_cell'}}
        column_hints = list(dict.fromkeys(h for value in column_candidates
                                        if (h := self._resolve_schema_hint(value, fields))))
        # Keep an unknown requested field from silently widening to the whole sheet.
        return sheet_hints, column_hints, bool(column_candidates)

    def _plan(self, question):
        q = question.strip()
        low = q.casefold()
        years = sorted(set(re.findall(r"(?<!\d)(20\d{2})(?!\d)", q)))
        months = sorted({int(x) for x in re.findall(r"(?<!\d)(1[0-2]|0?[1-9])月", q)})
        quarters_raw = re.findall(r"(?:[qQ]\s*([1-4])|第?([一二三四1-4])季度)", q)
        quarters = sorted({int(a or b.translate(str.maketrans("一二三四", "1234"))) for a, b in quarters_raw})
        causal = any(x in low for x in ("为什么", "为何", "原因", "导致", "因果", "归因", "影响", "cause", "why"))
        # Do not mistake verbs such as “列出/逐一列出” for a spreadsheet column request.
        structured = bool(re.search(r"(?:sheet|工作表|字段|单元格|表格|page|页面|第?\d+页|slide|幻灯片|[\w\u4e00-\u9fff-]{1,18}列(?!出))", q, flags=re.I))
        table_reconstruction = any(x in low for x in ("续表", "跨页", "表头", "列对应")) and any(
            x in low for x in ("还原", "对应", "合并", "缺失", "清空"))
        structured = structured or table_reconstruction
        list_all = any(x in low for x in ("找出", "列出", "全部", "所有", "哪些", "几条", "汇总"))
        comparison = any(x in low for x in ("比较", "对比", "分别", "变化", "差异"))
        rank = any(x in low for x in ("最大", "最小", "最高", "最低", "最多", "最少", "top"))
        timeline = any(x in low for x in ("时间线", "先后", "时间顺序", "历程"))
        event_timeline = timeline and causal
        expected = None
        m = re.search(r"(?:找出|列出|共有|包含|前)?\s*(\d{1,3})\s*(?:条|个|项|种)", q)
        if m:
            expected = int(m.group(1))
        format_patterns = {
            "pdf": ("pdf",), "word": ("word", "docx"), "excel": ("excel", "xlsx"),
            "ppt": ("ppt", "powerpoint"), "image": ("图片", "图像", "png", "jpg", "jpeg")
        }
        requested_formats = [fmt for fmt, cues in format_patterns.items() if any(c.casefold() in low for c in cues)]
        identity_words = ("名称", "称呼", "别名", "叫什么", "命名", "同一产品", "同一实体")
        # Alias mentions can qualify a causal question without being its requested task.
        cross_format_identity = (len(requested_formats) >= 2 and any(w in low for w in identity_words)
                                 and not event_timeline)
        sheet_hints, column_hints, column_requested = self._structure_hints(q)
        # A deterministic sheet/field enumeration is a scope scan, not a ranking problem.
        # Find the complete structural scope first; use GraphRAG only afterwards for explanation.
        retrieval_mode = "exhaustive" if (
            structured and list_all and bool(column_hints or (sheet_hints and not column_requested))
            and not (event_timeline and not sheet_hints)
        ) else "ranked"
        relation_weights = defaultdict(lambda: 0.4)
        if not cross_format_identity:
            for pred, words in RELATION_TERMS.items():
                if any(w.casefold() in low for w in words):
                    relation_weights[pred] = 2.0
        if causal:
            relation_weights.update({"reported_cause": 3.2, "affects": 2.5, "has_observation": 1.8,
                                     "depends_on": 1.3, "upgraded_to": 1.2, "replaced_by": 1.1})
        keywords = []
        for term in self.known_terms:
            if len(norm(term)) >= 2 and phrase_in(term, q):
                keywords.append(term)
        keywords += re.findall(r"[a-z0-9]+(?:[_.+\-/][a-z0-9]+)*", low)
        simplified = re.sub(r"为什么|为何|原因|导致|因果|归因|影响|找出|列出|逐一|全部|所有|哪些|几条|说明|分析|请|sheet|工作表|字段|单元格|表格|页面|幻灯片", " ", q, flags=re.I)
        simplified = re.sub(r"[的了在是和与对从到中里内及、，。；：:()（）\s]+", " ", simplified)
        keywords += [x for x in simplified.split() if len(x) > 1]
        keywords = [k for k in dict.fromkeys(keywords) if k.casefold() not in STOPWORDS and not str(k).isdigit()]
        if cross_format_identity:
            intent = "cross_format_identity"
        elif retrieval_mode == "exhaustive":
            intent = "structured_enumeration"
        elif event_timeline:
            intent = "causal"
        elif structured:
            intent = "structured_lookup"
        elif causal:
            intent = "causal"
        elif comparison:
            intent = "comparison"
        elif rank:
            intent = "rank"
        else:
            intent = "factual"
        return {"intent": intent, "structured": structured, "cross_format_identity": cross_format_identity,
                "table_reconstruction": table_reconstruction, "column_requested": column_requested,
                "retrieval_mode": retrieval_mode,
                "requested_formats": requested_formats, "list_all": list_all, "causal": causal,
                "comparison": comparison, "rank": rank, "timeline": timeline, "expected_count": expected,
                "sheet_hints": list(dict.fromkeys(sheet_hints)), "column_hints": list(dict.fromkeys(column_hints)),
                "years": years, "months": months, "quarters": quarters, "keywords": keywords,
                "relation_weights": dict(relation_weights)}

    def _time_score(self, text, plan):
        score = 0.0
        nt = norm(text)
        if plan["years"] and any(y in nt for y in plan["years"]):
            score += 1.0
        if plan["months"] and any(f"{m}月" in text or f"-{m:02d}" in text for m in plan["months"]):
            score += 0.8
        if plan["quarters"] and any(f"q{q}" in nt or f"{q}季度" in nt or "一二三四"[q-1] + "季度" in text for q in plan["quarters"]):
            score += 0.8
        return score

    def _overlap(self, text, plan):
        if not plan["keywords"]:
            return 0.0
        return sum(phrase_in(k, text) for k in plan["keywords"]) / max(1, len(plan["keywords"]))

    def _bm25_rank(self, bm25, entries, query, limit):
        scores = bm25.scores(self._tokens(query))
        ranked = sorted(range(len(entries)), key=lambda i: (-scores[i], entries[i]["id"]))
        return [(entries[i], scores[i]) for i in ranked[:limit] if scores[i] > 0]

    def _structured_retrieve(self, question, plan):
        if not self.structured_entries:
            return []
        if plan.get("retrieval_mode") == "exhaustive":
            # Exact structural scope wins over lexical relevance.  Never truncate matches here;
            # ranking/salience is only metadata for second-stage augmentation.
            pool = []
            for entry in self.structured_entries:
                if plan["sheet_hints"] and not any(norm(h) == norm(entry.get("sheet", "")) for h in plan["sheet_hints"]):
                    continue
                if plan["column_hints"] and not any(norm(h) == norm(entry.get("field", "")) for h in plan["column_hints"]):
                    continue
                if not str(entry.get("value", "")).strip():
                    continue
                pool.append(entry)
            value_freq = Counter(norm(e.get("value", "")) for e in pool if e.get("value"))
            hits = []
            for entry in pool:
                value = str(entry.get("value", ""))
                repeat_count = value_freq[norm(value)]
                salience = min(len(value) / 40.0, 1.5)
                if re.search(r"\d|→|变|增|降|影响|风险|原因|归因|升级|替代|合并|并入|投诉|异常|停售|发布|修复", value):
                    salience += 1.6
                salience -= 1.0 * max(0, repeat_count - 1)
                hits.append({**entry, "score": round(salience, 6), "salience": round(salience, 6),
                             "repeat_count": repeat_count, "retrieval_mode": "exhaustive"})
            hits.sort(key=lambda x: (x.get("locator", {}).get("row", 10**9),
                                     str(x.get("locator", {}).get("cell", "")), x["id"]))
            return hits
        base = self._bm25_rank(self.structured_bm25, self.structured_entries, question, max(self.top_structured * 2, 40))
        # A requested column that does not exist in the schema must not silently widen to the
        # whole sheet; returning unrelated rows would be worse than reporting no match.
        if plan.get("column_requested") and not plan["column_hints"]:
            return []
        pool = self.structured_entries if (plan["sheet_hints"] or plan["column_hints"]) else [x for x, _ in base]
        base_scores = {x["id"]: s for x, s in base}
        value_freq = Counter(norm(e.get("value", "")) for e in pool if e.get("value"))
        hits = []
        for e in pool:
            sheet_match = not plan["sheet_hints"] or any(norm(h) == norm(e.get("sheet", "")) for h in plan["sheet_hints"])
            col_match = not plan["column_hints"] or any(norm(h) == norm(e.get("field", "")) for h in plan["column_hints"])
            if (plan["sheet_hints"] and not sheet_match) or (plan["column_hints"] and not col_match):
                continue
            value = str(e.get("value", ""))
            info = min(len(value) / 40.0, 1.5) + (0.4 if re.search(r"\d|→|变|增|降|影响|风险|原因|归因|升级|替代|合并", value) else 0)
            repeat_count = value_freq[norm(value)]
            repeat_penalty = 1.0 * max(0, repeat_count - 1)
            score = base_scores.get(e["id"], 0.0) + (4.0 if sheet_match and plan["sheet_hints"] else 0) + (5.0 if col_match and plan["column_hints"] else 0) + info - repeat_penalty
            hits.append({**e, "score": round(score, 6), "repeat_count": repeat_count})
        hits.sort(key=lambda x: (-x["score"], str(x.get("locator", {})), x["id"]))
        limit = self.top_structured
        if plan.get("expected_count"):
            limit = max(limit, min(60, plan["expected_count"] * 3))
        return hits[:limit]

    def _table_retrieve(self, question, plan):
        """Retrieve a table with its inherited schema and all continuation chunks."""
        if not plan.get("table_reconstruction"):
            return []
        tables = {uid: u for uid, u in self.units.items()
                  if u.get("structured", {}).get("kind") == "pdf_table" and u['structured'].get('header')}
        roots = {}

        def root(uid, visiting=None):
            if uid in roots:
                return roots[uid]
            visiting = (visiting or set()) | {uid}
            unit = tables[uid]
            st, loc = unit['structured'], unit.get('locator', {})
            inherited = st.get('schema_inherited_from_page')
            candidates = [key for key, other in tables.items() if key not in visiting
                          and other['document_id'] == unit['document_id']
                          and other.get('locator', {}).get('page') == inherited
                          and [norm(x) for x in other['structured']['header']] == [norm(x) for x in st['header']]]
            bbox = loc.get('bbox')
            if bbox and candidates:
                candidates = [key for key in candidates if not tables[key].get('locator', {}).get('bbox') or
                              all(abs(float(tables[key]['locator']['bbox'][i]) - float(bbox[i])) <= 4 for i in (0, 2))]
            if inherited is not None and candidates:
                parent = max(candidates, key=lambda key: float(tables[key].get('locator', {}).get('bbox', [0, 0, 0, 0])[3]))
                value = root(parent, visiting)
            else:
                value = (unit['document_id'], loc.get('page'), loc.get('table'))
            roots[uid] = value
            return value

        groups = defaultdict(list)
        for uid, unit in tables.items():
            groups[root(uid)].append(unit)
        if not groups:
            return []
        # Rank the table request separately from a secondary entity-association question.
        primary = re.split(r'同时|此外|另外', question, maxsplit=1)[0]
        page_text = defaultdict(str)
        for unit in self.units.values():
            if unit.get('structured', {}).get('kind') == 'pdf_page':
                page_text[(unit['document_id'], unit.get('locator', {}).get('page'))] += unit.get('content_md', '')
        keys = sorted(groups, key=str)
        texts = []
        for key in keys:
            texts.append(' '.join(' '.join(map(str, u['structured']['header'])) * 3 + ' ' +
                                 u.get('content_md', '') + ' ' + page_text[(u['document_id'], u.get('locator', {}).get('page'))][:800]
                                 for u in groups[key]))
        scores = BM25Lite([self._tokens(t) for t in texts]).scores(self._tokens(primary))
        # A requested table name is stronger than generic words such as “对照”.
        # Captions may omit the final 表, so also match the complete name stem.
        names = []
        for match in re.finditer(r'([\w\u4e00-\u9fff-]{3,40}表)(?=[（(的中，。])', primary):
            name = re.split(r'中的|里的|中|的', match.group(1))[-1]
            name = re.sub(r'^(?:请|根据|PDF|文档)+', '', name, flags=re.I)
            stem = norm(name[:-1])
            if len(stem) >= 4:
                names.append(stem)
        for i, text in enumerate(texts):
            if any(name in norm(text) for name in names):
                scores[i] += 40.0
        best = max(range(len(keys)), key=lambda i: (scores[i], str(keys[i])))
        if scores[best] <= 0:
            return []
        result = []
        for unit in sorted(groups[keys[best]], key=lambda u: (u.get('locator', {}).get('page', 0),
                           u.get('locator', {}).get('table', 0), u.get('locator', {}).get('row_start', 0), u['unit_id'])):
            st = unit['structured']
            result.append({'unit_id': unit['unit_id'], 'source': self.documents.get(unit['document_id'], {}).get('path', ''),
                           'locator': unit.get('locator', {}), 'header': st['header'], 'records': st.get('records', []),
                           'column_count': len(st['header']), 'schema_inherited_from_page': st.get('schema_inherited_from_page')})
        return result

    def _structured_rows(self, hits):
        """Keep XLS row identifiers alongside matched attributes, across parsed chunks."""
        selected = {}
        for hit in hits:
            if hit.get('kind') != 'xlsx_cell':
                continue
            key = (hit['document_id'], hit.get('sheet'), hit.get('locator', {}).get('row'))
            selected[key] = max(selected.get(key, 0), hit.get('score', 0))
        rows = defaultdict(dict)
        for entry in self.structured_entries:
            key = (entry.get('document_id'), entry.get('sheet'), entry.get('locator', {}).get('row'))
            if entry.get('kind') == 'xlsx_cell' and key in selected:
                rows[key][entry['locator']['cell']] = entry
        result = []
        for key in sorted(selected, key=lambda k: (-selected[k], str(k)))[:24]:
            cells = sorted(rows[key].values(), key=lambda e: (len(self._col(e['locator']['cell'])), e['locator']['cell']))
            if not cells:
                continue
            result.append({'source': cells[0]['source'], 'locator': {'sheet': key[1], 'row': key[2]},
                           'entry_ids': [e['id'] for e in cells],
                           'cells': [{'cell': e['locator']['cell'], 'field': e['field'], 'value': e['value']} for e in cells]})
        return result

    def _fact_retrieve(self, question, plan):
        ranked = self._bm25_rank(self.fact_bm25, self.fact_entries, question, max(self.top_facts * 4, 50))
        hits = []
        family_counts = Counter()
        for entry, base in ranked:
            fact = entry["fact"]
            score = base + 2.0 * self._overlap(entry["text"], plan) + self._time_score(entry["text"], plan)
            if fact.get("predicate") in plan["relation_weights"]:
                score += plan["relation_weights"].get(fact.get("predicate"), 0)
            family = (fact.get("subject"), fact.get("predicate"), fact.get("object"),
                      fact.get("qualifiers", {}).get("attribute") if isinstance(fact.get("qualifiers"), dict) else None)
            cap = 3 if (plan.get("months") or plan.get("quarters") or plan.get("timeline")) else 2
            if family_counts[family] >= cap:
                continue
            family_counts[family] += 1
            hits.append({"fact_id": fact["fact_id"], "score": round(score, 6), "fact": fact, "text": entry["text"]})
            if len(hits) >= self.top_facts:
                break
        hits.sort(key=lambda x: (-x["score"], x["fact_id"]))
        return hits

    def _entity_candidates(self, question, fact_hits, raw_hits=None):
        candidates = defaultdict(lambda: {"score": 0.0, "methods": set(), "matched": set()})
        for nid, labels in self.labels.items():
            matched = [x for x in labels if len(norm(x)) >= 2 and phrase_in(x, question)]
            if matched:
                candidates[nid]["score"] += 12 + max(len(norm(x)) for x in matched)
                candidates[nid]["methods"].add("name_alias_identifier")
                candidates[nid]["matched"].update(matched)
        for rank, hit in enumerate(fact_hits[:12], 1):
            f = hit["fact"]
            for nid in (f.get("subject"), f.get("object")):
                if nid in self.nodes:
                    candidates[nid]["score"] += 2.0 / rank + 0.2 * hit["score"]
                    candidates[nid]["methods"].add("fact_bm25")
        if raw_hits:
            for rank, hit in enumerate(raw_hits[:8], 1):
                for nid in self.unit_nodes.get(hit["unit_id"], set()):
                    candidates[nid]["score"] += 1.0 / rank
                    candidates[nid]["methods"].add("raw_evidence_mapping")
        result = []
        for nid, item in candidates.items():
            result.append({"node_id": nid, "name": self.nodes[nid].get("name"), "type": self.nodes[nid].get("type"),
                           "score": round(item["score"], 6), "methods": sorted(item["methods"]), "matched_labels": sorted(item["matched"])})
        result.sort(key=lambda x: (-x["score"], x["node_id"]))
        return result[: max(self.max_seeds * 3, 12)]

    def _node_text(self, nid):
        n = self.nodes[nid]
        facts = [self.facts[fid] for fid in self.subject_facts.get(nid, [])[:20] if fid in self.facts]
        return " ".join([n.get("name", ""), *n.get("aliases", []), compact(facts)])

    def _timeline_retrieve(self, question, plan):
        """Collect event evidence by target identity, independent of lexical Top-K and beam rank."""
        if not (plan.get('timeline') and plan.get('causal')) or plan.get('retrieval_mode') == 'exhaustive':
            return []
        targets = {nid for nid, n in self.nodes.items() if n.get('type') in {'Product', 'AITool', 'DataAsset'}
                   and any(len(norm(label)) >= 2 and phrase_in(label, question) for label in self.labels[nid])}
        event_ids = {other for target in targets for other, _, _ in self.adjacency.get(target, [])
                     if self.nodes[other].get('type') == 'Event'}
        # Follow event-to-event causal/sequence links, never a shared tool/person or reused record ID.
        frontier = set(event_ids)
        for _ in range(2):
            more = {other for eid in frontier for other, edge, _ in self.adjacency.get(eid, [])
                    if self.nodes[other].get('type') == 'Event' and edge.get('predicate') not in
                    {'reuses_identifier_of', 'linked_to', 'has_participant', 'cites_data'}} - event_ids
            event_ids.update(more)
            frontier = more
        temporal = r'date|time|period|日期|时间|月份|季度'
        date_pattern = r'(?<!\d)(20\d{2})[-/年](0?[1-9]|1[0-2])(?!\d)(?:[-/月](0?[1-9]|[12]\d|3[01])(?!\d))?'
        hits = []
        for eid in sorted(event_ids):
            own = [self.facts[fid] for fid in self.subject_facts.get(eid, [])]
            dates, temporal_ids, date_fields = set(), set(), set()
            for f in own:
                qualifiers = f.get('qualifiers', {})
                values = [(k, v) for k, v in qualifiers.items() if re.search(temporal, str(k), re.I)]
                if f.get('predicate') in {'event_time', 'recorded_time'} or re.search(
                        temporal, str(qualifiers.get('attribute', '')), re.I):
                    value = f.get('value', '')
                    values.append((qualifiers.get('attribute') or f['predicate'],
                                   value.get('value', value.get('raw', '')) if isinstance(value, dict) else value))
                for field, value in values:
                    for year, month, day in re.findall(date_pattern, str(value)):
                        dates.add(f'{int(year):04d}-{int(month):02d}' + (f'-{int(day):02d}' if day else ''))
                        temporal_ids.add(f['fact_id'])
                        date_fields.add(str(field))
            if dates and not any(
                    (not plan['years'] or d[:4] in plan['years']) and
                    (not plan['months'] or int(d[5:7]) in plan['months']) and
                    (not plan['quarters'] or (int(d[5:7]) - 1) // 3 + 1 in plan['quarters']) for d in dates):
                continue
            linked = {fid for other, edge, _ in self.adjacency.get(eid, [])
                      if other in targets or other in event_ids for fid in edge.get('fact_ids', [])}
            relevant = {f['fact_id']: f for f in own}
            relevant.update({fid: self.facts[fid] for fid in linked if fid in self.facts})
            def priority(f):
                if f['fact_id'] in temporal_ids:
                    return 0
                if f.get('object') and (f.get('subject') in targets or f.get('object') in targets):
                    return 1
                if re.search(r'变|模式|原因|影响|内容|停更|reason|impact|change|transition',
                             compact(f.get('qualifiers', {})) + f.get('predicate', ''), re.I):
                    return 2
                return 3 if f.get('object') else 4
            selected = sorted(relevant.values(), key=lambda f: (priority(f), f['fact_id']))[:8]
            evidence_ids = sorted({ev for f in selected for ev in f.get('evidence_ids', [])})
            claims = []
            for f in selected:
                claim = {'fact_id': f['fact_id'], 'subject': self.nodes.get(f['subject'], {}).get('name'),
                         'predicate': f['predicate'], 'evidence_ids': f.get('evidence_ids', [])}
                claim.update({'object': self.nodes.get(f['object'], {}).get('name')} if f.get('object')
                             else {'value': f.get('value')})
                if f.get('qualifiers'):
                    claim['qualifiers'] = f['qualifiers']
                claims.append(claim)
            sources = [{'evidence_id': ev, 'source': self.evidence[ev].get('source') or
                        self.documents.get(self.evidence[ev].get('document_id'), {}).get('path', ''),
                        'locator': self.evidence[ev].get('locator', {})} for ev in evidence_ids if ev in self.evidence]
            hits.append({'event': {'id': eid, 'name': self.nodes[eid].get('name')}, 'dates': sorted(dates),
                         'date_fields': sorted(date_fields),
                         'date_status': 'documented' if dates else 'not_recorded', 'claims': claims,
                         'claims_omitted': len(relevant) - len(selected), 'sources': sources})
        hits.sort(key=lambda h: (h['dates'][0] if h['dates'] else '9999', h['event']['id']))
        return hits

    def _path_step_score(self, current, neighbor, edge, plan):
        relation = plan["relation_weights"].get(edge.get("predicate"), 0.4)
        node_overlap = self._overlap(self._node_text(neighbor), plan)
        time = self._time_score(self._node_text(neighbor), plan)
        fact_overlap = 0.0
        for fid in edge.get("fact_ids", [])[:4]:
            if fid in self.facts:
                fact_overlap = max(fact_overlap, self._overlap(compact(self.facts[fid]), plan))
        degree_penalty = 0.12 * math.log1p(len(self.adjacency.get(neighbor, [])))
        return 1.25 * relation + 2.8 * node_overlap + 0.8 * time + 1.2 * fact_overlap - degree_penalty

    def _beam_search(self, seeds, plan):
        if not seeds:
            return []
        beam = []
        for seed in seeds[:self.max_seeds]:
            beam.append({"node_ids": [seed["node_id"]], "steps": [], "score": seed["score"] * 0.15})
        completed = []
        for depth in range(self.max_hops):
            expanded = []
            for state in beam:
                current = state["node_ids"][-1]
                neigh = []
                for neighbor, edge, direction in self.adjacency.get(current, []):
                    if neighbor in state["node_ids"]:
                        continue
                    step_score = self._path_step_score(current, neighbor, edge, plan)
                    neigh.append((step_score, neighbor, edge, direction))
                neigh.sort(key=lambda x: (-x[0], x[2].get("id", ""), x[1]))
                for step_score, neighbor, edge, direction in neigh[:self.branch_width]:
                    step = {"edge_id": edge.get("id"), "source": edge.get("source"), "predicate": edge.get("predicate"),
                            "target": edge.get("target"), "fact_ids": edge.get("fact_ids", []), "traversal": direction}
                    nxt = {"node_ids": [*state["node_ids"], neighbor], "steps": [*state["steps"], step],
                           "score": state["score"] + step_score - 0.35}
                    expanded.append(nxt)
                    completed.append(nxt)
            if not expanded:
                break
            # Keep only the most promising partial paths, with endpoint diversity.
            expanded.sort(key=lambda x: (-x["score"], len(x["steps"]), x["node_ids"]))
            endpoint_count = Counter()
            next_beam = []
            for state in expanded:
                endpoint = state["node_ids"][-1]
                if endpoint_count[endpoint] >= 3:
                    continue
                endpoint_count[endpoint] += 1
                next_beam.append(state)
                if len(next_beam) >= self.beam_width:
                    break
            beam = next_beam
        for path in completed:
            path["path_id"] = "path:" + "/".join([path["node_ids"][0], *[s.get("edge_id", "") for s in path["steps"]]])
            path["nodes"] = [{"id": nid, "name": self.nodes[nid].get("name"), "type": self.nodes[nid].get("type")} for nid in path["node_ids"]]
        completed.sort(key=lambda x: (-x["score"], len(x["steps"]), x["path_id"]))
        unique, seen = [], set()
        for path in completed:
            key = tuple(s["edge_id"] for s in path["steps"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(path)
            if len(unique) >= self.top_paths:
                break
        return unique

    def _raw_retrieve(self, queries, limit=None, requested_formats=None):
        limit = limit or self.top_units
        scores = defaultdict(float)
        details = defaultdict(list)
        for qi, query in enumerate(queries):
            ranked = self._bm25_rank(self.raw_bm25, self.raw_entries, query, max(limit * 5, 30))
            weight = 2.2 if qi == 0 else 0.7
            for rank, (entry, bm25) in enumerate(ranked, 1):
                scores[entry["id"]] += weight / (60 + rank)
                details[entry["id"]].append({"query": query, "rank": rank, "bm25": round(bm25, 6), "weight": weight})
        ordered = sorted(scores, key=lambda x: (-scores[x], x))
        chosen = []
        requested_formats = list(dict.fromkeys(requested_formats or []))
        if requested_formats:
            # Explicit multi-source questions need coverage, not a global ranking dominated by one PDF.
            quota = max(1, limit // len(requested_formats))
            all_units = list(self.units)
            for fmt in requested_formats:
                candidates = [uid for uid in ordered if self._format_name(self.documents.get(self.units[uid]["document_id"], {})) == fmt]
                if len(candidates) < quota:
                    candidates += [uid for uid in all_units if uid not in candidates and
                                   self._format_name(self.documents.get(self.units[uid]["document_id"], {})) == fmt]
                picked, seen_locations = [], set()
                for uid in candidates:
                    loc = self.units[uid].get("locator", {})
                    coarse = (self.units[uid].get("document_id"), loc.get("page"), tuple(loc.get("section", []) if isinstance(loc.get("section"), list) else [loc.get("section")]),
                              loc.get("sheet"), loc.get("slide"), loc.get("image"))
                    if coarse in seen_locations and len(picked) < quota:
                        continue
                    seen_locations.add(coarse)
                    picked.append(uid)
                    if len(picked) >= quota:
                        break
                chosen.extend(picked)
        for uid in ordered:
            if uid not in chosen:
                chosen.append(uid)
            if len(chosen) >= limit:
                break
        result = []
        for uid in chosen[:limit]:
            unit = self.units[uid]
            doc = self.documents.get(unit["document_id"], {})
            result.append({"unit_id": uid, "document_id": unit["document_id"],
                           "source": doc.get("path", ""), "format": self._format_name(doc),
                           "locator": unit.get("locator", {}), "content_md": unit.get("content_md", ""),
                           "score": round(scores.get(uid, 0.0), 6), "hits": details.get(uid, [])})
        return result

    def _cross_format_raw(self, plan, entity_profiles, per_format=2):
        """Retrieve complementary name/unique-info evidence for every explicitly requested source format."""
        if not plan.get("cross_format_identity") or not plan.get("requested_formats"):
            return []
        entity_terms = []
        for profile in entity_profiles[:2]:
            entity_terms.extend([profile.get("name", ""), *profile.get("aliases", [])[:10]])
        entity_text = " ".join(dict.fromkeys(x for x in entity_terms if x))[:900]
        primary = str(entity_profiles[0].get("name", "") if entity_profiles else "")
        fmt_cues = {"pdf": "PDF", "word": "Word DOCX", "excel": "Excel XLSX", "ppt": "PPT PowerPoint", "image": "图片 图像"}
        chosen = []
        for fmt in plan.get("requested_formats", []):
            queries = [f"{entity_text} {fmt_cues.get(fmt, fmt)} 名称 称呼 别名 对照",
                       f"{primary} {fmt_cues.get(fmt, fmt)} 独有信息 独有信息 特有信息 各格式 仅在"]
            seen = set()
            for query in queries:
                picked = None
                for entry, score in self._bm25_rank(self.raw_bm25, self.raw_entries, query, 100):
                    unit = self.units[entry["id"]]
                    if self._format_name(self.documents.get(unit["document_id"], {})) != fmt or entry["id"] in seen:
                        continue
                    picked = (score, entry["id"], query)
                    break
                if picked is None:
                    continue
                score, uid, query_used = picked
                seen.add(uid)
                unit = self.units[uid]
                doc = self.documents.get(unit["document_id"], {})
                chosen.append({"unit_id": uid, "document_id": unit["document_id"],
                               "source": doc.get("path", ""), "format": self._format_name(doc),
                               "locator": unit.get("locator", {}), "content_md": unit.get("content_md", ""),
                               "score": round(score, 6), "hits": [{"query": query_used, "facet": "cross_format"}]})
                if len(seen) >= per_format:
                    break
            # Image units may have no text before multimodal extraction. Keep the locator anyway.
            if fmt == "image" and not any(x.get("format") == "image" for x in chosen):
                for uid, unit in self.units.items():
                    doc = self.documents.get(unit["document_id"], {})
                    if self._format_name(doc) == "image":
                        chosen.append({"unit_id": uid, "document_id": unit["document_id"], "source": doc.get("path", ""),
                                       "format": "image", "locator": unit.get("locator", {}),
                                       "content_md": unit.get("content_md", ""), "score": 0.0,
                                       "hits": [{"facet": "cross_format_locator"}]})
                        break
        return chosen

    def _rrf(self, structured_hits, fact_hits, paths, k=60):
        scores = defaultdict(float)
        sources = defaultdict(list)
        for channel, items, keyfn in [
            ("structured", structured_hits, lambda x: "structured:" + x["id"]),
            ("fact", fact_hits, lambda x: "fact:" + x["fact_id"]),
            ("graph", paths, lambda x: "path:" + x["path_id"]),
        ]:
            for rank, item in enumerate(items, 1):
                key = keyfn(item)
                scores[key] += 1 / (k + rank)
                sources[key].append({"channel": channel, "rank": rank})
                if channel == "graph":
                    for fid in {fid for step in item.get("steps", []) for fid in step.get("fact_ids", [])}:
                        fkey = "fact:" + fid
                        scores[fkey] += 0.6 / (k + rank)
                        sources[fkey].append({"channel": "graph_fact", "rank": rank})
        return [{"key": key, "rrf_score": round(score, 8), "sources": sources[key]}
                for key, score in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]

    def _expansion_queries(self, question, structured_hits, fact_hits, paths):
        queries = [question]
        concepts = []
        for hit in structured_hits[:8]:
            concepts += [hit.get("field", ""), str(hit.get("value", ""))[:80]]
        for hit in fact_hits[:8]:
            f = hit["fact"]
            for nid in (f.get("subject"), f.get("object")):
                if nid in self.nodes:
                    concepts.append(self.nodes[nid].get("name", ""))
            concepts.append(f.get("predicate", ""))
            concepts.append(compact(f.get("qualifiers", {})))
        for path in paths[:4]:
            concepts += [n.get("name", "") for n in path.get("nodes", [])]
            concepts += [s.get("predicate", "") for s in path.get("steps", [])]
        compact_concepts = [str(x).strip() for x in concepts if str(x).strip()]
        if compact_concepts:
            q = " ".join(dict.fromkeys(compact_concepts))
            if q:
                queries.append(q[:1200])
        return list(dict.fromkeys(queries))[:4]

    def retrieve(self, question):
        question = str(question or "").strip()
        if not question:
            raise ValueError("question 必须是非空字符串")
        plan = self._plan(question)
        structured_hits = self._structured_retrieve(question, plan)
        table_hits = self._table_retrieve(question, plan)
        structured_rows = self._structured_rows(structured_hits) if table_hits else []

        # For deterministic enumerations, first locate the complete sheet/field scope, then
        # let Fact/Graph retrieval explain the located records.  This prevents BM25/RRF
        # from pushing exact structural evidence out of the context.
        semantic_query = question
        augmentation_plan = plan
        augmentation_sources = []
        if plan.get("retrieval_mode") == "exhaustive" and structured_hits:
            by_salience = sorted(structured_hits, key=lambda x: (-x.get("salience", 0.0), x["id"]))
            expected = plan.get("expected_count") or 8
            take = max(1, min(24, expected))
            seen_values = set()
            for hit in by_salience:
                key = norm(hit.get("value", ""))
                if key in seen_values:
                    continue
                seen_values.add(key)
                augmentation_sources.append(hit)
                if len(augmentation_sources) >= take:
                    break
            located_values = [str(x.get("value", ""))[:180] for x in augmentation_sources]
            semantic_query = (question + " " + " ".join(located_values))[:4000]
            augmentation_plan = self._plan(semantic_query)

        fact_hits = self._fact_retrieve(semantic_query, augmentation_plan)
        raw_queries = list(dict.fromkeys([question, semantic_query]))
        preliminary_raw = self._raw_retrieve(raw_queries, limit=max(6, self.top_units // 2),
                                             requested_formats=plan.get("requested_formats"))
        entity_candidates = self._entity_candidates(semantic_query, fact_hits, preliminary_raw)
        entity_profiles = [self._entity_profile(x["node_id"]) for x in entity_candidates[:4]]
        timeline_hits = self._timeline_retrieve(question, plan)
        # Identity/source-comparison questions do not benefit from relation-path wandering.
        paths = [] if plan.get("cross_format_identity") else self._beam_search(entity_candidates[:self.max_seeds], augmentation_plan)
        fusion = self._rrf(structured_hits, fact_hits, paths)
        fusion_scores = {x["key"]: x["rrf_score"] for x in fusion}
        for hit in structured_hits:
            hit["rrf_score"] = fusion_scores.get("structured:" + hit["id"], 0.0)
        for hit in fact_hits:
            hit["rrf_score"] = fusion_scores.get("fact:" + hit["fact_id"], 0.0)
        for path in paths:
            path["rrf_score"] = fusion_scores.get("path:" + path["path_id"], 0.0)
        fact_hits.sort(key=lambda x: (-x.get("rrf_score", 0), -x["score"], x["fact_id"]))
        queries = self._expansion_queries(question, structured_hits, fact_hits, paths)
        # For cross-format identity, aliases themselves are excellent evidence-completion queries.
        if plan.get("cross_format_identity"):
            alias_terms = []
            for profile in entity_profiles[:2]:
                alias_terms.extend([profile.get("name", ""), *profile.get("aliases", [])[:10]])
            alias_terms = [x for x in alias_terms if x]
            if alias_terms:
                aliases = " ".join(dict.fromkeys(alias_terms))[:900]
                queries.append(aliases)
                queries.append((aliases + " 名称对照 别名 称呼 独有信息 各格式")[0:1200])
        raw_hits = self._raw_retrieve(list(dict.fromkeys(queries))[:5], requested_formats=plan.get("requested_formats"))
        if plan.get("cross_format_identity"):
            facet_hits = self._cross_format_raw(plan, entity_profiles)
            merged_raw = []
            seen_raw = set()
            for item in [*facet_hits, *raw_hits]:
                if item["unit_id"] in seen_raw:
                    continue
                seen_raw.add(item["unit_id"])
                merged_raw.append(item)
            raw_hits = merged_raw[: max(self.top_units, len(plan.get("requested_formats", [])) * 2)]
        result = {"question": question, "query_plan": plan, "structured_hits": structured_hits,
                  "table_hits": table_hits, "structured_rows": structured_rows, "timeline_hits": timeline_hits,
                  "fact_hits": fact_hits, "entity_candidates": entity_candidates, "entity_profiles": entity_profiles,
                  "paths": paths, "fusion": fusion, "raw_units": raw_hits,
                  "augmentation_sources": augmentation_sources,
                  "augmentation_query": semantic_query if semantic_query != question else None,
                  "stats": {"structured": len(structured_hits), "facts": len(fact_hits), "seeds": min(len(entity_candidates), self.max_seeds),
                            "profiles": len(entity_profiles), "paths": len(paths), "raw_units": len(raw_hits),
                            "timeline_events": len(timeline_hits),
                            "retrieval_mode": plan.get("retrieval_mode", "ranked"),
                            "table_units": len(table_hits), "table_rows": sum(len(t['records']) for t in table_hits),
                            "table_columns": max((t['column_count'] for t in table_hits), default=0),
                            "structured_rows": len(structured_rows),
                            "structured_scope_matches": len(structured_hits) if plan.get("retrieval_mode") == "exhaustive" else 0,
                            "structured_selected_for_augmentation": len(augmentation_sources)}}
        result["context"] = self.build_context(result)
        return result

    def _fact_with_sources(self, fact):
        evs = []
        for eid in fact.get("evidence_ids", []):
            ev = self.evidence.get(eid)
            if not ev:
                continue
            evs.append({"evidence_id": eid, "source": ev.get("source") or self.documents.get(ev.get("document_id"), {}).get("path", ""),
                        "locator": ev.get("locator", {}), "quote": ev.get("quote", "")})
        subject = self.nodes.get(fact.get("subject"), {})
        obj = self.nodes.get(fact.get("object"), {}) if fact.get("object") else None
        return {"fact_id": fact.get("fact_id"),
                "subject": {"id": fact.get("subject"), "name": subject.get("name", ""),
                            "aliases": subject.get("aliases", [])[:12], "alias_bindings": subject.get("alias_bindings", [])[:12]},
                "predicate": fact.get("predicate"),
                **({"object": {"id": fact.get("object"), "name": obj.get("name", ""), "aliases": obj.get("aliases", [])[:8]}} if obj else {"value": fact.get("value")}),
                "qualifiers": fact.get("qualifiers", {}), "evidence": evs}

    def build_context(self, result):
        parts = ["QUESTION\n" + result["question"],
                 "QUERY_PLAN\n" + compact({k: v for k, v in result["query_plan"].items() if k != "relation_weights"})]
        budget = self.context_chars

        def total_len():
            return sum(len(x) for x in parts) + 2 * len(parts)

        def append(block, cap=None):
            if cap is not None and len(block) > cap:
                block = block[:cap] + "\n[truncated]"
            if total_len() + len(block) > budget:
                return False
            parts.append(block)
            return True

        timeline_hits = result.get('timeline_hits', [])
        included_events = 0
        if timeline_hits:
            # Share locators across events and emit a compact inventory before optional detail.
            # Otherwise repeated source/claim JSON can consume the budget before later dates.
            budget -= 180
            source_ids, evidence_sources = {}, {}
            for event in timeline_hits:
                for source in event['sources']:
                    value = {k: source[k] for k in ('source', 'locator')}
                    key = compact(value)
                    if key not in source_ids:
                        sid = 't' + str(len(source_ids) + 1)
                        if append('TIMELINE_SOURCE ' + compact({'id': sid, **value})):
                            source_ids[key] = sid
                    if key in source_ids:
                        evidence_sources[source['evidence_id']] = source_ids[key]
            for event in timeline_hits:
                candidates = [c for c in event['claims'] if c['predicate'] not in {'event_time', 'recorded_time'}
                              and not re.search(r'date|time|日期|时间',
                                  str(c.get('qualifiers', {}).get('attribute', '')), re.I)]
                changes = [c for c in candidates if not c.get('object') and re.search(
                    r'变|模式|原因|影响|内容|停更|reason|impact|change|transition', compact(c.get('qualifiers', {})), re.I)]
                chosen = []
                for c in [*changes[:2], *[c for c in candidates if c.get('object')], *candidates]:
                    if c not in chosen:
                        chosen.append(c)
                    if len(chosen) == 2:
                        break
                claims = []
                for claim in chosen:
                    value = {k: v for k, v in claim.items() if k not in {'fact_id', 'evidence_ids', 'subject'}}
                    if claim.get('subject') != event['event']['name']:
                        value['subject'] = claim.get('subject')
                    value['sources'] = sorted({evidence_sources[ev] for ev in claim['evidence_ids']
                                               if ev in evidence_sources})
                    claims.append(value)
                event_sources = sorted({evidence_sources[s['evidence_id']] for s in event['sources']
                                        if s['evidence_id'] in evidence_sources})
                overview = {k: event[k] for k in ('event', 'dates', 'date_fields', 'date_status')}
                overview['event'] = event['event']['name']
                overview.update(claims=claims, sources=event_sources,
                                claims_omitted=event['claims_omitted'] + len(event['claims']) - len(chosen))
                if event_sources and append('TIMELINE_EVENT ' + compact(overview)):
                    included_events += 1
            budget += 180
            append('TIMELINE_COVERAGE ' + compact({'events_total': len(timeline_hits),
                'events_included': included_events, 'events_omitted': len(timeline_hits) - included_events}))
        result['stats']['timeline_context_events'] = included_events
        result['stats']['timeline_context_events_omitted'] = len(timeline_hits) - included_events

        # Schema and complete rows are atomic evidence; never slice a table row or JSON.
        included_table_units = set()
        included_rows = 0
        table_hits = result.get('table_hits', [])
        table_row_count = sum(len(t['records']) for t in table_hits)
        coverage_reserve = 160 if table_hits else 0
        budget -= coverage_reserve
        for table in table_hits:
            schema = {k: v for k, v in table.items() if k != 'records'}
            if append('TABLE_SCHEMA ' + compact(schema)):
                included_table_units.add(table['unit_id'])
        for table in table_hits:
            if table['unit_id'] not in included_table_units:
                continue
            for index, values in enumerate(table['records'], start=table['locator'].get('row_start', 1)):
                block = 'TABLE_ROW ' + compact({'unit_id': table['unit_id'],
                    'locator': {**{k: v for k, v in table['locator'].items() if k in ('page', 'table')}, 'row': index},
                    'values': values})
                if append(block):
                    included_rows += 1
        budget += coverage_reserve
        if table_hits:
            append('TABLE_COVERAGE ' + compact({'rows_total': table_row_count, 'rows_included': included_rows,
                                               'rows_omitted': table_row_count - included_rows,
                                               'schemas_omitted': len(table_hits) - len(included_table_units)}))
        included_entry_ids = set()
        for row in result.get('structured_rows', []):
            if append('STRUCTURED_ROW ' + compact({k: v for k, v in row.items() if k != 'entry_ids'})):
                included_entry_ids.update(row['entry_ids'])
        result['stats']['table_context_rows'] = included_rows
        result['stats']['table_context_rows_omitted'] = table_row_count - included_rows

        # Entity identity must not disappear between retrieval and generation.
        for profile in result.get("entity_profiles", [])[:3]:
            append("ENTITY_PROFILE " + compact(profile), cap=2600)

        # Exact structural enumerations are primary evidence: include them before any
        # BM25/Fact/Graph material can consume the context budget.
        if result["query_plan"].get("retrieval_mode") == "exhaustive":
            # An exhaustive enumeration must not be silently truncated by a fixed record cap;
            # the context budget is the only limit, and any omission is reported.
            structured_limit = len(result["structured_hits"])
            exhaustive = True
        else:
            exhaustive = False
            structured_limit = self.top_structured if result["query_plan"].get("structured") else min(8, self.top_structured)
        structured_included = 0
        structured_omitted = 0
        structured_candidates = result["structured_hits"][:structured_limit]
        for hit in structured_candidates:
            if hit['id'] in included_entry_ids or hit.get('unit_id') in included_table_units:
                continue
            block = "STRUCTURED_SOURCE " + compact({"source": hit.get("source"), "locator": hit.get("locator"),
                                                       "field": hit.get("field"), "value": hit.get("value"), "hidden": hit.get("hidden", False),
                                                       "retrieval_mode": hit.get("retrieval_mode"), "salience": hit.get("salience")})
            # Cell values are atomic evidence: include the whole record or omit it, never slice it.
            if not append(block, cap=None if exhaustive else 900):
                structured_omitted += 1
                continue
            structured_included += 1
        structured_total = sum(1 for hit in structured_candidates
                               if hit['id'] not in included_entry_ids
                               and hit.get('unit_id') not in included_table_units)
        if result["query_plan"].get("retrieval_mode") == "exhaustive":
            append("STRUCTURED_COVERAGE " + compact({"records_total": structured_total,
                                                      "records_included": structured_included,
                                                      "records_omitted": structured_total - structured_included}))
        result['stats']['structured_context_records'] = structured_included
        result['stats']['structured_context_records_omitted'] = structured_total - structured_included

        # Reserve raw-source coverage early; do not let repeated facts starve the actual documents.
        raw_first = result.get("raw_units", [])
        raw_cap = 1900 if result["query_plan"].get("cross_format_identity") else 1400
        for unit in raw_first[: min(len(raw_first), 6)]:
            prefix = "RAW_SOURCE " + compact({"source": unit.get("source"), "format": unit.get("format"),
                                                "locator": unit.get("locator"), "unit_id": unit.get("unit_id")}) + "\n"
            content = unit.get("content_md", "")
            if not append(prefix + content, cap=raw_cap):
                break

        for hit in result["fact_hits"][:self.top_facts]:
            if not append("CANONICAL_FACT " + compact(self._fact_with_sources(hit["fact"])), cap=1500):
                break

        for path in result["paths"][:self.top_paths]:
            steps = []
            for step in path.get("steps", []):
                step_facts = [self._fact_with_sources(self.facts[fid]) for fid in step.get("fact_ids", [])[:2] if fid in self.facts]
                steps.append({"source": self.nodes.get(step.get("source"), {}).get("name", step.get("source")),
                              "predicate": step.get("predicate"),
                              "target": self.nodes.get(step.get("target"), {}).get("name", step.get("target")),
                              "traversal": step.get("traversal"), "facts": step_facts})
            if not append("GRAPH_PATH " + compact({"score": round(path.get("score", 0), 4), "steps": steps}), cap=2400):
                break

        # If budget remains, add more raw units after the core evidence.
        already = {u.get("unit_id") for u in raw_first[: min(len(raw_first), 6)]}
        for unit in raw_first:
            if unit.get("unit_id") in already:
                continue
            prefix = "RAW_SOURCE " + compact({"source": unit.get("source"), "format": unit.get("format"),
                                                "locator": unit.get("locator"), "unit_id": unit.get("unit_id")}) + "\n"
            if not append(prefix + unit.get("content_md", ""), cap=1200):
                break
        return "\n\n".join(parts)

    def ask(self, question, *, model=None, env_file=None, timeout=240, reasoning_effort=None, debug_output=None):
        retrieval = self.retrieve(question)
        try:
            import requests
            from dotenv import dotenv_values
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("ask 需要 requests 与 python-dotenv；retrieve-only 不需要") from exc
        values = dict(os.environ)
        if env_file:
            values = {**dotenv_values(env_file), **values}
        key = str(values.get("OPENROUTER_API_KEY", "")).strip()
        if not key:
            raise RuntimeError("未配置 OPENROUTER_API_KEY")
        chosen = model or values.get("LLM_MODEL") or "openai/gpt-5.6"
        payload = {"model": chosen,
                   "messages": [{"role": "system", "content": ANSWER_PROMPT},
                                {"role": "user", "content": retrieval["context"]}],
                   "max_tokens": 4096, "stream": False}
        effort = reasoning_effort or values.get("LLM_REASONING_EFFORT")
        if effort:
            payload["reasoning"] = {"effort": effort}
        base = str(values.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        response = requests.post(base + "/chat/completions", json=payload,
                                 headers={"Authorization": "Bearer " + key}, timeout=(30, timeout))
        response.raise_for_status()
        body = response.json()
        choice = (body.get("choices") or [{}])[0]
        if debug_output:
            write_model_text(Path(debug_output).with_suffix(".response.json"),
                             json.dumps(body, ensure_ascii=False, indent=2))
        try:
            answer = model_text((choice.get("message") or {}).get("content"))
        except ValueError as exc:
            raise RuntimeError(f"模型未返回回答正文：{exc}; finish_reason={choice.get('finish_reason')!r}") from exc
        if choice.get("finish_reason") == "length":
            raise RuntimeError("模型回答被截断：finish_reason=length")
        if debug_output:
            write_model_text(debug_output, json.dumps({**retrieval, "answer": answer, "usage": body.get("usage")}, ensure_ascii=False, indent=2))
        return answer.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--retrieve-only", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--env-file")
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high"])
    parser.add_argument("--debug-output")
    parser.add_argument("--max-hops", type=int, default=3)
    parser.add_argument("--beam-width", type=int, default=20)
    parser.add_argument("--context-chars", type=int, default=18000)
    args = parser.parse_args()
    rag = LeanGraphRAG(args.work, max_hops=args.max_hops, beam_width=args.beam_width, context_chars=args.context_chars)
    if args.retrieve_only:
        result = rag.retrieve(args.question)
        print(json.dumps({k: v for k, v in result.items() if k != "context"}, ensure_ascii=False, indent=2))
    else:
        print(rag.ask(args.question, model=args.model, env_file=args.env_file,
                      reasoning_effort=args.reasoning_effort, debug_output=args.debug_output))


if __name__ == "__main__":
    main()
