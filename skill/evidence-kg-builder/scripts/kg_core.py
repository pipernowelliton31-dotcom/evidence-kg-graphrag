"""Evidence-first KG mechanics. Standard library only; no model client."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCHEMA_VERSION = "1.3"
ENGINE_VERSION = "4.0.0"
TYPES = {"Product", "AITool", "Actor", "DataAsset", "Version", "Event", "Observation"}
BUSINESS = TYPES - {"Event", "Observation"}
RELATIONS = {
    "depends_on": ({"Product"}, {"Product", "AITool", "DataAsset"}),
    "uses": ({"Actor", "Product"}, {"AITool", "DataAsset"}),
    "purchased": ({"Actor"}, {"Product"}),
    "version_of": ({"Version"}, {"Product", "AITool"}),
    "upgraded_to": ({"Product", "AITool", "Version"}, {"Version"}),
    "replaced_by": ({"Product"}, {"Product"}),
    "merged_into": ({"Product"}, {"Product"}),
    "sister_product": ({"Product"}, {"Product"}),
    "affects": ({"Event"}, TYPES - {"Event"}),
    "has_participant": ({"Event"}, BUSINESS),
    "has_observation": (BUSINESS | {"Event"}, {"Observation"}),
    "has_feedback": ({"Product", "AITool", "DataAsset"}, {"Observation"}),
    "reported_cause": ({"Event"}, {"Event", "Observation"}),
    "cites_data": ({"Event", "Observation"}, {"DataAsset"}),
}
LITERAL_PREDICATES = {"observed_value", "event_time", "recorded_time", "attribute"}
CONFIG = {"max_chars": 12000, "max_rows": 80, "weak_candidates": 5, "max_rounds": 3,
          "extract_batch_chars": 14000, "extract_batch_units": 5,
          "alignment_evidence_examples": 1, "alignment_relation_examples": 4,
          "alignment_quote_chars": 96}

ALIGNABLE_TYPES = {"Product", "AITool", "Actor", "DataAsset", "Version"}
STABLE_EXACT_TYPES = {"Product", "AITool", "DataAsset"}
GENERIC_IDENTITY_NAMES = {"产品", "工具", "插件", "用户", "客户", "未知", "unknown", "none"}
LITERAL_KINDS = {"number", "range", "date", "period", "identifier", "text", "boolean"}

RELATION_CUES = ("依赖", "使用", "购买", "替代", "合并", "升级", "影响", "导致", "原因", "归因",
                 "depends", "uses", "purchased", "replace", "merge", "upgrade", "affect", "cause")
METRIC_CUES = ("收入", "续费", "转化", "评分", "价格", "费用", "成本", "金额", "用户数", "调用", "ltv", "arpu", "%")
EVENT_CUES = ("变更", "调整", "升级", "停售", "上线", "发布", "修复", "故障", "实验", "评审", "风险", "回退")
ALIAS_CUES = ("又称", "别名", "简称", "称呼", "同一", "alias")
FREE_TEXT_HEADERS = ("备注", "原因", "说明", "内容", "影响", "结论", "风险", "反馈")


class ContractError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ContractError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def ident(prefix, value):
    return prefix + "_" + hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()[:20]


def engine_signature():
    base = Path(__file__).resolve().parent
    return ident("engine", {name: hashlib.sha256((base / name).read_bytes()).hexdigest()
        for name in ("kg_core.py", "kg_pipeline.py", "parse_documents.py")})


def norm(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value))).casefold()


def _looks_like_version_label(value):
    return bool(re.fullmatch(r"v\d+(?:[._-]\d+)*", str(value).strip(), flags=re.I))


def _supported_inline_business_codes(labels, evidence_text):
    """Extract generic evidence-backed business codes without assuming benchmark prefixes.

    A code must belong to the mention's own name/aliases, not merely occur somewhere in its
    evidence unit. Document, review and change-record codes are not IDs of every entity on a page.
    Explicit identifier fields supplied by the extractor are handled separately.
    """
    labels = [unicodedata.normalize("NFKC", str(x)) for x in labels if str(x).strip()]
    evidence = unicodedata.normalize("NFKC", str(evidence_text))
    candidates = set()
    token_re = r"[A-Za-z][A-Za-z0-9._/-]{1,31}"
    for label in labels:
        for m in re.finditer(r"[（(]\s*(" + token_re + r")\s*[)）]", label):
            candidates.add(m.group(1))
    cue_re = r"(?:编号|编码|代码|标识|ID|identifier|code)\s*[:：=#]?\s*(" + token_re + r")"
    for m in re.finditer(cue_re, evidence, flags=re.I):
        code = m.group(1)
        boundary = r"(?<![A-Za-z0-9._/-])" + re.escape(code) + r"(?![A-Za-z0-9._/-])"
        if any(re.search(boundary, label, flags=re.I) for label in labels):
            candidates.add(code)
    result = set()
    for code in candidates:
        if _looks_like_version_label(code):
            continue
        if not (re.search(r"[A-Za-z]", code) and re.search(r"\d", code)):
            continue
        boundary = r"(?<![A-Za-z0-9._/-])" + re.escape(code) + r"(?![A-Za-z0-9._/-])"
        if re.search(boundary, evidence, flags=re.I):
            result.add(code)
    return result


def clean(value):
    # Preserve newlines, tabs and Markdown indentation.
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value)).replace("\r\n", "\n")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_state(work):
    state = read_json(Path(work) / "state.json")
    require(state.get("schema_version") == SCHEMA_VERSION, "Unsupported state schema")
    require(state.get("engine_version") == ENGINE_VERSION, "Reparse after engine version changes")
    require(state.get("engine_signature") == engine_signature(), "Scripts changed; run parse to invalidate downstream checkpoints")
    return state


def save_state(work, state):
    work = Path(work)
    write_json(work / "state.json", state)
    write_json(work / "01_mentions.json", {"fingerprint": state["fingerprint"],
               "extractions": state["extractions"]})
    write_json(work / "02_entity_map.json", {"fingerprint": state["fingerprint"],
               **state["alignment"]})


def _count_cues(text, cues):
    low = text.casefold()
    return sum(low.count(c.casefold()) for c in cues)


def _id_like_count(text):
    patterns = [r"\b[A-Z]{1,6}\d{1,8}\b", r"\b[A-Z]{2,12}[-_][A-Z0-9][A-Z0-9_-]{1,24}\b"]
    return sum(len(re.findall(p, text)) for p in patterns)


def _date_count(text):
    return len(re.findall(r"\b20\d{2}(?:[-/.年]\d{1,2})?(?:[-/.月]\d{1,2})?", text))


def unit_signal(unit):
    """Cheap deterministic routing only. It never asserts semantic KG facts."""
    text = unit.get("content_md", "") or ""
    structured = unit.get("structured", {}) or {}
    kind = structured.get("kind", "")
    nonempty = [line.strip() for line in text.splitlines() if line.strip()]
    non_heading = [line for line in nonempty if not line.lstrip().startswith("#")]
    table_like = kind in {"xlsx_cells", "pdf_table", "pptx_shapes"} and ("|" in text or kind == "xlsx_cells")
    visual = bool(unit.get("asset_refs")) and unit.get("format") in {"png", "jpg", "jpeg", "webp"}
    relation_hits = _count_cues(text, RELATION_CUES)
    metric_hits = _count_cues(text, METRIC_CUES)
    event_hits = _count_cues(text, EVENT_CUES)
    alias_hits = _count_cues(text, ALIAS_CUES)
    ids = _id_like_count(text)
    dates = _date_count(text)
    hidden = False
    if kind == "xlsx_cells":
        hidden = any(r.get("hidden") for r in structured.get("records", [])) or bool(structured.get("hidden_columns"))
    structural_only = (len(text.strip()) < 90 and not table_like and not visual and relation_hits == 0 and
                       metric_hits == 0 and event_hits == 0 and alias_hits == 0 and ids == 0 and
                       len(non_heading) <= 2)
    score = (3 if visual else 0) + (2 if table_like else 0) + min(relation_hits, 3) + min(metric_hits, 2) + \
            min(event_hits, 2) + min(alias_hits * 2, 4) + min(ids, 2) + min(dates, 1) + (2 if hidden else 0)
    if structural_only:
        mode, priority = "auto_no_facts", 0
    elif visual:
        mode, priority = "llm_visual", 100 + score
    elif kind == "xlsx_cells":
        mode, priority = "xlsx_rule_or_fallback", 80 + score
    elif table_like:
        mode, priority = "llm_structured", 70 + score
    elif score >= 5:
        mode, priority = "llm_semantic", 60 + score
    else:
        mode, priority = "llm_batch", 20 + score
    return {"unit_id": unit["unit_id"], "mode": mode, "priority": priority, "score": score,
            "chars": len(text), "format": unit.get("format"), "structured_kind": kind,
            "signals": {"relation": relation_hits, "metric": metric_hits, "event": event_hits,
                        "alias": alias_hits, "id_like": ids, "date": dates, "hidden": hidden,
                        "table_like": table_like, "visual": visual}}


def extraction_plan(state):
    return {"schema_version": SCHEMA_VERSION, "fingerprint": state["fingerprint"],
            "policy": "full_coverage_sparse_extraction", "units": [unit_signal(u) for u in state["units"]]}


def _col(coord):
    m = re.match(r"([A-Z]+)", str(coord))
    return m.group(1) if m else ""


def _row_quote(unit, row_number):
    needle = f"| {row_number} |"
    for line in unit.get("content_md", "").splitlines():
        if line.startswith(needle):
            return line
    # Fallback to a source-preserving compact line assembled from the structured ledger.
    for record in unit.get("structured", {}).get("records", []):
        if record.get("row") == row_number:
            pieces = [f"{c['coordinate']}={c.get('raw','')}" for c in record.get("cells", []) if str(c.get("raw", "")).strip()]
            candidate = "; ".join(pieces)
            if candidate and candidate in unit.get("content_md", ""):
                return candidate
    return ""


def _xlsx_headers(unit):
    rows = unit.get("structured", {}).get("header_candidates", [])
    if not rows:
        return {}, 0
    def looks_header(row):
        vals = [str(c.get("raw", "")).strip() for c in row if str(c.get("raw", "")).strip()]
        if not vals:
            return False
        numeric_or_date = sum(bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?%?", v)) or bool(re.match(r"20\d{2}[-/.年]", v)) for v in vals)
        return numeric_or_date <= max(1, len(vals) // 3)
    header_rows = [rows[0]]
    if len(rows) > 1 and looks_header(rows[1]):
        first = {_col(c["coordinate"]): str(c.get("raw", "")).strip() for c in rows[0]}
        second = {_col(c["coordinate"]): str(c.get("raw", "")).strip() for c in rows[1]}
        if any((not first.get(k)) and v for k, v in second.items()) or any(v for v in second.values() if any(x in v for x in ("单价", "数量", "金额", "率", "日期"))):
            header_rows.append(rows[1])
    headers = defaultdict(list)
    for row in header_rows:
        for c in row:
            raw = str(c.get("raw", "")).strip()
            if raw:
                headers[_col(c["coordinate"])].append(raw)
    return {k: "/".join(dict.fromkeys(v)) for k, v in headers.items()}, len(header_rows)


def _header_find(headers, terms, exclude=()):
    for col, h in headers.items():
        nh = norm(h)
        if any(norm(t) in nh for t in terms) and not any(norm(x) in nh for x in exclude):
            return col
    return None


def _cell_map(record):
    return {_col(c["coordinate"]): c for c in record.get("cells", [])}


def _typed_number(raw, header=""):
    text = str(raw).strip()
    cleaned = text.replace(",", "").replace("，", "")
    cleaned = re.sub(r"^(约|≈|~)", "", cleaned)
    m = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if not m:
        return None
    number = m.group(0)
    unit = ""
    combined = f"{header} {text}"
    if "%" in combined or "百分" in combined:
        unit = "%"
    elif "万元" in combined or "(万)" in combined or "（万）" in combined:
        unit = "万元"
    elif "千元" in combined:
        unit = "千元"
    elif "元" in combined:
        unit = "元"
    elif "万次" in combined:
        unit = "万次"
    elif "次" in combined:
        unit = "次"
    return {"raw": text, "number": number, "unit": unit}


def _xlsx_header_row_numbers(unit, header_depth):
    rows = unit.get("structured", {}).get("header_candidates", [])[:header_depth]
    result = set()
    for row in rows:
        for cell in row:
            match = re.search(r"(\d+)$", str(cell.get("coordinate", "")))
            if match:
                result.add(int(match.group(1)))
    return result


def xlsx_semantic_overlay(unit, headers=None, header_depth=None):
    """Return only free-text cells that need semantic interpretation plus compact row context.

    Structured columns stay deterministic. This prevents a single remarks cell from forcing the
    whole row/table through the LLM, while guaranteeing that remarks/reasons/risks are never skipped.
    """
    if unit.get("structured", {}).get("kind") != "xlsx_cells":
        return []
    if headers is None or header_depth is None:
        headers, header_depth = _xlsx_headers(unit)
    free_cols = [c for c, h in headers.items() if any(norm(x) in norm(h) for x in FREE_TEXT_HEADERS)]
    if not free_cols:
        return []
    header_rows = _xlsx_header_row_numbers(unit, header_depth)
    rows = []
    for record in unit.get("structured", {}).get("records", []):
        row_no = record.get("row")
        if row_no in header_rows:
            continue
        cells = _cell_map(record)
        semantic = []
        for col in free_cols:
            raw = str(cells.get(col, {}).get("raw", "")).strip()
            if raw:
                semantic.append({"coordinate": cells[col]["coordinate"], "header": headers.get(col, col), "raw": raw})
        if not semantic:
            continue
        context = []
        for col, cell in cells.items():
            raw = str(cell.get("raw", "")).strip()
            if not raw or col in free_cols:
                continue
            context.append({"coordinate": cell["coordinate"], "header": headers.get(col, col), "raw": raw})
        rows.append({"row": row_no, "context": context[:10], "semantic_cells": semantic})
    return rows


def _semantic_overlay_markdown(unit, rows):
    sheet = unit.get("locator", {}).get("sheet", "")
    parts = [f"# Sheet: {sheet}", "", "Only interpret the free-text cells below; structured fields are already handled deterministically."]
    for row in rows:
        parts.extend(["", f"## Row {row['row']}"])
        if row.get("context"):
            parts.append("Context: " + "; ".join(f"{c['coordinate']} {c['header']}={c['raw']}" for c in row["context"]))
        for cell in row.get("semantic_cells", []):
            parts.append(f"{cell['coordinate']} {cell['header']}: {cell['raw']}")
    return "\n".join(parts)


def _has_semantic_fallback(unit, headers, header_depth):
    return bool(xlsx_semantic_overlay(unit, headers, header_depth))


def deterministic_xlsx_task(unit, *, allow_semantic=False):
    """Extract explicit spreadsheet structure; semantic free text can be handled as a small overlay."""
    if unit.get("structured", {}).get("kind") != "xlsx_cells":
        return None
    headers, depth = _xlsx_headers(unit)
    semantic_rows = xlsx_semantic_overlay(unit, headers, depth)
    if not headers or (semantic_rows and not allow_semantic):
        return None
    product_col = _header_find(headers, ("产品名称", "商品名称", "产品"), ("关联", "类型"))
    tool_col = _header_find(headers, ("工具名称", "ai工具", "工具"), ("关联", "类型", "用途"))
    actor_col = _header_find(headers, ("客户名称", "客户", "用户名称"), ("类型", "数"))
    responsible_col = _header_find(headers, ("负责人",))
    related_product_col = _header_find(headers, ("关联产品",))
    id_col = _header_find(headers, ("订单编号", "变更编号", "事件编号", "实验编号", "评审编号", "记录编号", "编号"))
    date_col = _header_find(headers, ("订单日期", "变更日期", "统计月份", "日期", "时间", "月份"))
    event_type_col = _header_find(headers, ("变更类型", "事件类型"))
    if not any((product_col, tool_col, actor_col)):
        return None
    records = unit.get("structured", {}).get("records", [])
    header_rows = _xlsx_header_row_numbers(unit, depth)
    mentions, relations, assertions = [], [], []
    used = set()
    free_cols = {c for c, h in headers.items() if any(norm(x) in norm(h) for x in FREE_TEXT_HEADERS)}

    def add_entity(lid, typ, name, quote, cells, attrs=None, identifier=None, actor_kind=None):
        if lid in used or not str(name).strip():
            return
        used.add(lid)
        attributes = dict(attrs or {})
        if actor_kind:
            attributes.update(actor_kind=actor_kind, roles=["customer"] if actor_col else [])
        attributes["_record_key_scope"] = f"{unit['document_id']}:{unit['locator'].get('sheet','')}:{typ}"
        item = {"local_id": lid, "type": typ, "name": str(name).strip(), "attributes": attributes,
                "evidence": [{"quote": quote, "cells": cells}]}
        if identifier:
            item["identifiers"] = [{"value": identifier[0], "scope": identifier[1],
                                    "evidence": [{"quote": quote, "cells": cells}]}]
        mentions.append(item)

    for record in records:
        row = record.get("row")
        if row in header_rows:
            continue
        cells = _cell_map(record)
        quote = _row_quote(unit, row)
        if not quote:
            continue
        row_cells = [c["coordinate"] for c in record.get("cells", []) if str(c.get("raw", "")).strip()]
        def val(col): return str(cells.get(col, {}).get("raw", "")).strip() if col else ""
        p_name, t_name, a_name = val(product_col), val(tool_col), val(actor_col)
        rid, when, event_type = val(id_col), val(date_col), val(event_type_col)
        if p_name:
            add_entity(f"p_{row}", "Product", p_name, quote, row_cells)
        if t_name:
            add_entity(f"t_{row}", "AITool", t_name, quote, row_cells)
        if a_name:
            add_entity(f"a_{row}", "Actor", a_name, quote, row_cells, actor_kind="unknown")
        if responsible_col and val(responsible_col):
            add_entity(f"r_{row}", "Actor", val(responsible_col), quote, row_cells, actor_kind="person")
        order_like = bool(p_name and a_name and id_col and any("订单" in h for h in headers.values()))
        if order_like:
            q = {"record_id": rid} if rid else {}
            if when: q["time"] = when
            for col, header in headers.items():
                if col in {product_col, actor_col, id_col, date_col} or col in free_cols or not val(col):
                    continue
                number = _typed_number(val(col), header)
                if number is not None:
                    q.setdefault("record_values", {})[header] = number
                elif any(x in header for x in ("支付", "渠道", "类型")):
                    q.setdefault("record_values", {})[header] = val(col)
            relations.append({"subject": f"a_{row}", "predicate": "purchased", "object": f"p_{row}",
                              "qualifiers": q, "evidence": [{"quote": quote, "cells": row_cells}]})
        if t_name and related_product_col and val(related_product_col):
            for i, name in enumerate([x.strip() for x in re.split(r"[;；,，/、]", val(related_product_col)) if x.strip()]):
                lid = f"rp_{row}_{i}"
                add_entity(lid, "Product", name, quote, row_cells)
                relations.append({"subject": lid, "predicate": "uses", "object": f"t_{row}", "qualifiers": {"period": when} if when else {},
                                  "evidence": [{"quote": quote, "cells": row_cells}]})
        if p_name and (event_type or (id_col and any("变更" in h or "事件" in h for h in headers.values()))):
            ename = event_type or "记录事件"
            attrs = {"event_type": ename, "subject_scope": p_name}
            if when: attrs["event_time"] = when
            identifier = (rid, next((h for h in headers.values() if "编号" in h), "业务事件编号")) if rid else None
            add_entity(f"e_{row}", "Event", f"{p_name}:{ename}", quote, row_cells, attrs=attrs, identifier=identifier)
            relations.append({"subject": f"e_{row}", "predicate": "affects", "object": f"p_{row}", "qualifiers": {},
                              "evidence": [{"quote": quote, "cells": row_cells}]})
            if responsible_col and val(responsible_col):
                relations.append({"subject": f"e_{row}", "predicate": "has_participant", "object": f"r_{row}", "qualifiers": {},
                                  "evidence": [{"quote": quote, "cells": row_cells}]})
            if when:
                assertions.append({"subject": f"e_{row}", "predicate": "event_time", "value": when, "qualifiers": {},
                                   "evidence": [{"quote": quote, "cells": row_cells}]})
        subject = f"p_{row}" if p_name else (f"t_{row}" if t_name else (f"a_{row}" if a_name else None))
        if subject and not order_like:
            skip_cols = {c for c in (product_col, tool_col, actor_col, responsible_col, related_product_col, id_col, date_col, event_type_col) if c} | free_cols
            for col, header in headers.items():
                if col in skip_cols:
                    continue
                raw = val(col)
                if not raw:
                    continue
                number = _typed_number(raw, header)
                if number is None:
                    continue
                qualifiers = {"attribute": header}
                if when: qualifiers["period"] = when
                assertions.append({"subject": subject, "predicate": "attribute", "value": number, "qualifiers": qualifiers,
                                   "evidence": [{"quote": quote, "cells": [cells[col]["coordinate"]]}]})
    if not mentions:
        return None
    return {"task_id": unit["unit_id"], "review": {"status": "facts", "reason": "deterministic structured-table extraction"},
            "mentions": mentions, "relations": relations, "assertions": assertions, "unresolved": []}

def _md_table_rows(text):
    rows = []
    for line in str(text).splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [re.sub(r"<br\s*/?>", " ", c, flags=re.I).strip() for c in stripped.strip("|").split("|")]
        if cells and not all(re.fullmatch(r"[:\-\s]+", c or "-") for c in cells):
            rows.append((stripped, cells))
    return rows


def _alias_header_role(header):
    """Classify alias-table headers by semantic role, independent of source format names."""
    raw = unicodedata.normalize("NFKC", str(header)).strip()
    low = raw.casefold()
    canonical_cues = ("标准名称", "规范名称", "统一名称", "主名称", "canonical", "standard name", "primary name")
    if any(c in low for c in canonical_cues):
        return "canonical"
    explicit_alias = ("别名", "别称", "曾用名", "简称", "称呼", "显示名", "alias", "aka", "alternate name", "alternative name", "display name")
    if any(c in low for c in explicit_alias):
        return "alias"
    # Generic source-specific name columns such as "移动端名称" or "客服系统名称".
    # Do not enumerate benchmark formats; only the semantic role "name/label" matters.
    metadata_cues = ("类型", "类别", "编号", "id", "代码", "code", "日期", "时间", "状态", "备注", "说明", "负责人")
    if ("名称" in raw or "name" in low or "label" in low) and not any(c in low for c in metadata_cues):
        return "name_like"
    if any(c in low for c in ("实体类型", "对象类型", "entity type", "object type")):
        return "type"
    return "other"


def _business_type_from_text(value):
    """Map generic enterprise ontology words to a KG type; return None if ambiguous."""
    raw = unicodedata.normalize("NFKC", str(value)).strip()
    low = raw.casefold()
    rules = [
        ("Version", ("版本", "version", "release")),
        ("DataAsset", ("数据资产", "数据集", "数据源", "报表", "文档", "dataset", "data asset", "report", "document")),
        ("Actor", ("客户", "用户", "人员", "成员", "组织", "团队", "customer", "user", "person", "organization", "team")),
        ("AITool", ("ai工具", "智能工具", "模型工具", "ai tool", "model tool")),
        ("Product", ("产品", "商品", "服务", "应用", "插件", "product", "service", "application", "app", "plugin")),
    ]
    hits = [typ for typ, cues in rules if any(c in low for c in cues)]
    return hits[0] if len(set(hits)) == 1 else None


def deterministic_alias_table_task(unit):
    """Parse explicit identity-equivalence tables without knowing any benchmark entity values.

    The rule recognizes semantic column roles (canonical name / alias / entity type), not PDF/Word/
    Excel/PPT/image-specific columns. If the entity type is not unambiguous, fall back to the LLM.
    """
    rows = _md_table_rows(unit.get("content_md", ""))
    if len(rows) < 2:
        return None
    _, headers = rows[0]
    roles = [_alias_header_role(h) for h in headers]
    canonical_cols = [i for i, role in enumerate(roles) if role == "canonical"]
    if len(canonical_cols) != 1:
        return None
    canonical_col = canonical_cols[0]
    alias_cols = [i for i, role in enumerate(roles) if role in {"alias", "name_like"} and i != canonical_col]
    # Require explicit identity structure: at least one true alias column, or multiple alternate-name columns.
    explicit_alias_cols = [i for i, role in enumerate(roles) if role == "alias"]
    if not explicit_alias_cols and len(alias_cols) < 2:
        return None
    type_cols = [i for i, role in enumerate(roles) if role == "type"]
    context = " ".join(str(x) for x in unit.get("locator", {}).get("section", [])) + " " + " ".join(headers)
    table_type = _business_type_from_text(context)
    mentions_out = []
    for row_idx, (quote, cells) in enumerate(rows[1:], start=1):
        if len(cells) != len(headers):
            continue
        name = cells[canonical_col].strip()
        if not name:
            continue
        row_type = None
        if len(type_cols) == 1 and cells[type_cols[0]].strip():
            row_type = _business_type_from_text(cells[type_cols[0]])
        entity_type = row_type or table_type
        if entity_type not in ALIGNABLE_TYPES:
            # Identity is explicit, but ontology type is not safe to infer deterministically.
            return None
        aliases = []
        alias_bindings = []
        seen = {norm(name)}
        for i in alias_cols:
            value = cells[i].strip()
            if not value or norm(value) in seen:
                continue
            aliases.append(value)
            alias_bindings.append({"alias": value, "role": headers[i]})
            seen.add(norm(value))
        if not aliases:
            continue
        mentions_out.append({"local_id": f"alias_{row_idx}", "type": entity_type, "name": name,
                             "aliases": aliases, "alias_declared": True,
                             "attributes": {"alias_bindings": alias_bindings},
                             "evidence": [{"quote": quote}]})
    if not mentions_out:
        return None
    return {"task_id": unit["unit_id"], "review": {"status": "facts", "reason": "deterministic explicit alias table"},
            "mentions": mentions_out, "relations": [], "assertions": [], "unresolved": []}


def prepare_selective_extraction(state):
    """Apply deterministic facts first; send only semantic deltas to the host LLM."""
    revised = copy.deepcopy(state)
    plan = extraction_plan(revised)
    plan_by_id = {x["unit_id"]: x for x in plan["units"]}
    auto_tasks = []
    prefills = {}
    overlays = {}
    deterministic = alias_tables = trivial = mixed = 0
    for unit in revised["units"]:
        if unit["unit_id"] in revised["extractions"]:
            continue
        info = plan_by_id[unit["unit_id"]]
        alias_task = deterministic_alias_table_task(unit)
        if alias_task is not None:
            auto_tasks.append(alias_task)
            deterministic += 1
            alias_tables += 1
            info["mode"] = "deterministic_alias_table"
        elif info["mode"] == "auto_no_facts":
            auto_tasks.append({"task_id": unit["unit_id"], "review": {"status": "no_facts", "reason": "deterministic structural-only unit"},
                               "mentions": [], "relations": [], "assertions": [], "unresolved": []})
            trivial += 1
        elif info["mode"] == "xlsx_rule_or_fallback":
            headers, depth = _xlsx_headers(unit)
            overlay = xlsx_semantic_overlay(unit, headers, depth)
            base = deterministic_xlsx_task(unit, allow_semantic=True)
            if overlay:
                if base is not None:
                    prefills[unit["unit_id"]] = base
                overlays[unit["unit_id"]] = overlay
                info["mode"] = "xlsx_semantic_overlay"
                info["semantic_rows"] = len(overlay)
                mixed += 1
            elif base is not None:
                auto_tasks.append(base)
                deterministic += 1
                info["mode"] = "deterministic_xlsx"
    if auto_tasks:
        revised = accept_extractions(revised, {"fingerprint": revised["fingerprint"], "tasks": auto_tasks})
    revised.setdefault("selection", {})
    revised["selection"].update({"plan": plan_by_id, "prepared": True,
                                  "auto_no_facts": trivial, "deterministic_units": deterministic,
                                  "deterministic_alias_tables": alias_tables, "mixed_semantic_units": mixed,
                                  "prefill": prefills, "semantic_overlays": overlays})
    revised["audit"].append({"action": "prepare_selective", "auto_no_facts": trivial,
                              "deterministic_units": deterministic, "deterministic_alias_tables": alias_tables,
                              "mixed_semantic_units": mixed})
    return revised, {"schema_version": SCHEMA_VERSION, "fingerprint": revised["fingerprint"],
                     "policy": "full_coverage_sparse_extraction_with_semantic_overlay",
                     "units": [plan_by_id[u["unit_id"]] for u in revised["units"]]}

def check_json(value, context="value"):
    # Keep only JSON-serializability checks. Model outputs may use ordinary JSON numbers.
    require(isinstance(value, (dict, list, str, int, float, bool, type(None))),
            f"{context}: unsupported JSON value")
    if isinstance(value, dict):
        for k, v in value.items():
            require(isinstance(k, str), f"{context}: object keys must be strings")
            check_json(v, context + "." + k)
    elif isinstance(value, list):
        for v in value:
            check_json(v, context)


def decimal_string(value):
    if isinstance(value, bool) or value is None:
        raise ContractError(f"Invalid decimal: {value}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ContractError(f"Invalid decimal: {value}") from exc
    require(number.is_finite(), "Nonfinite decimal")
    return format(number.normalize(), "f") if number else "0"


def _infer_literal_kind(raw):
    text = str(raw or "").strip()
    if not text:
        return "text"
    if re.fullmatch(r"20\d{2}(?:[-/.年]\d{1,2})?(?:[-/.月]\d{1,2})?日?", text):
        return "date" if re.search(r"(?:日|[-/.]\d{1,2}$)", text) else "period"
    if re.fullmatch(r"[A-Za-z]{1,12}[-_][A-Za-z0-9][A-Za-z0-9_-]{1,40}", text):
        return "identifier"
    if re.search(r"(?:→|~|～|至|到)", text) and re.search(r"\d", text):
        return "range"
    if text.casefold() in {"true", "false", "是", "否", "有", "无"}:
        return "boolean"
    return "text"


def normalize_value(value):
    """Normalize only deterministic numeric scales; salvage nonnumeric typed values."""
    if not isinstance(value, dict):
        return value
    out = copy.deepcopy(value)
    number = out.get("number")
    # Older/model outputs often send {raw, number:null}. Treat them as typed literals,
    # not as invalid decimals.
    if number is None or number == "":
        raw = out.get("raw", out.get("value", ""))
        kind = out.get("kind") or _infer_literal_kind(raw)
        return {"raw": str(raw), "kind": kind, "value": out.get("value", str(raw)),
                **({"unit": out["unit"]} if isinstance(out.get("unit"), str) and out.get("unit") else {})}
    if "normalized" in out:
        return out
    known = {"万次": ("次", "10000"), "万元": ("元", "10000"), "千元": ("元", "1000"), "%": ("比例", "0.01")}
    if out.get("unit") not in known:
        return out
    try:
        number = Decimal(decimal_string(out["number"]))
    except ContractError:
        return out
    target, scale = known[out["unit"]]
    out["normalized"] = {"number": decimal_string(str(number * Decimal(scale))), "unit": target,
                         "rule": "unit_scale", "scale": scale}
    return out


def validate_value(value):
    """Lightweight literal check: preserve source semantics instead of auditing formatting."""
    check_json(value)
    return True


def value_key(value):
    if isinstance(value, dict) and value.get("number") not in {None, ""}:
        nv = value.get("normalized", value)
        return {"number": decimal_string(nv["number"]), "unit": nv["unit"],
                "currency": value.get("currency")}
    return value


def _evidence_norm(text):
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = re.sub(r"<br\s*/?>", "", text, flags=re.I)
    # Ignore layout-only Markdown/PDF artifacts, while retaining lexical content.
    return re.sub(r"[\s|`*_]+", "", text).casefold()


def evidence_contains(source, quote):
    if quote in source:
        return True
    q = _evidence_norm(quote)
    return bool(q) and q in _evidence_norm(source)


def _default_evidence(unit, quote=""):
    item = {"unit_id": unit["unit_id"], "document_id": unit["document_id"], "kind": "text",
            "locator": copy.deepcopy(unit.get("locator", {})), "quote": str(quote or ""),
            "match_mode": "locator_only"}
    item["evidence_id"] = ident("ev", item)
    return item


def evidence_item(raw, unit):
    """Attach provenance with almost no rejection. Unit boundaries are authoritative."""
    if not isinstance(raw, dict):
        return _default_evidence(unit, raw if isinstance(raw, str) else "")
    kind = raw.get("kind", "text")
    locator = copy.deepcopy(unit.get("locator", {}))
    requested = raw.get("locator")
    if isinstance(requested, dict):
        # Accept only refinements that agree with the parser; silently ignore invented locator fields.
        for k, v in requested.items():
            if k in locator and locator[k] == v:
                locator[k] = v
    quote = str(raw.get("quote", "") or "")
    item = {"unit_id": unit["unit_id"], "document_id": unit["document_id"],
            "kind": "text" if kind not in {"text", "visual"} else kind,
            "locator": locator, "quote": quote}
    if "cells" in raw and unit.get("structured", {}).get("kind") == "xlsx_cells":
        structured = unit["structured"]
        source_cells = {c["coordinate"]: c for row in structured.get("header_candidates", []) for c in row}
        source_cells.update({c["coordinate"]: c for r in structured.get("records", []) for c in r.get("cells", [])})
        requested_cells = [c for c in raw.get("cells", []) if isinstance(c, str) and c in source_cells]
        if requested_cells:
            item["locator"]["cells"] = sorted(set(requested_cells))
            item["cell_values"] = {c: {"raw": source_cells[c].get("raw", ""),
                                       "value": source_cells[c].get("value", source_cells[c].get("raw", ""))}
                                   for c in sorted(set(requested_cells))}
    if "shape_ids" in raw:
        available = {s.get("shape_id") for s in unit.get("structured", {}).get("shapes", [])}
        requested_shapes = [s for s in raw.get("shape_ids", []) if s in available]
        if requested_shapes:
            item["locator"]["shape_ids"] = sorted(set(requested_shapes))
    if item["kind"] == "visual":
        asset = raw.get("asset_ref")
        if asset in unit.get("asset_refs", []):
            item.update(asset_ref=asset, region=str(raw.get("region", "") or ""),
                        description=str(raw.get("description", "") or ""),
                        verification="host_visual_observation")
        else:
            item["kind"] = "text"
    if item["kind"] == "text":
        if quote and quote in unit.get("content_md", ""):
            item["match_mode"] = "exact"
        elif quote and evidence_contains(unit.get("content_md", ""), quote):
            item["match_mode"] = "normalized"
        else:
            item["match_mode"] = "locator_only"
    item["evidence_id"] = ident("ev", item)
    return item


def evidence_list(raw, unit, owner=None):
    # Evidence is optional in model output. Reuse the parser locator automatically.
    if raw is None and isinstance(owner, dict) and isinstance(owner.get("quote"), str):
        raw = [{"quote": owner.get("quote", "")}]
    elif isinstance(raw, (str, dict)):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        return [_default_evidence(unit)]
    items = [evidence_item(x, unit) for x in raw[:3]]
    return items or [_default_evidence(unit)]


def _best_effort_evidence(raw, unit):
    return evidence_list(raw.get("evidence") if isinstance(raw, dict) else None,
                         unit, raw if isinstance(raw, dict) else None)


def _merge_prefill_task(prefill, task):
    if not prefill:
        return task
    merged = copy.deepcopy(task)
    known = {m.get("local_id") for m in prefill.get("mentions", [])}
    additions = [m for m in merged.get("mentions", []) if m.get("local_id") not in known]
    merged["mentions"] = [*copy.deepcopy(prefill.get("mentions", [])), *additions]
    merged["relations"] = [*copy.deepcopy(prefill.get("relations", [])), *merged.get("relations", [])]
    merged["assertions"] = [*copy.deepcopy(prefill.get("assertions", [])), *merged.get("assertions", [])]
    merged["unresolved"] = [*copy.deepcopy(prefill.get("unresolved", [])), *merged.get("unresolved", [])]
    merged["review"] = {"status": "facts", "reason": "deterministic structure + semantic overlay"}
    return merged


def _normalize_relation_predicate(value):
    raw = str(value or "").strip()
    if not raw:
        return "related_to"
    key = raw.casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "cause": "reported_cause", "causes": "reported_cause", "caused_by": "reported_cause",
        "contributes_to": "affects", "influences": "affects", "impacts": "affects",
        "depends": "depends_on", "depends_on": "depends_on", "replaces": "replaced_by",
        "merged_to": "merged_into", "upgrade_to": "upgraded_to", "used_by": "uses",
        "purchase": "purchased", "buys": "purchased",
    }
    return aliases.get(key, key)


def _resolve_endpoint(value, local, output):
    # Entity endpoints are scalar references, never JSON arrays or objects.
    # Let the caller record an unresolved-endpoint warning instead of crashing
    # an entire batch on an unhashable model value.
    if not isinstance(value, str) or not value.strip():
        return None
    if value in local:
        return local[value]
    target = norm(value)
    matches = []
    for m in output["mentions"]:
        labels = [m.get("local_id", ""), m.get("name", ""), *m.get("aliases", [])]
        if target and any(norm(x) == target for x in labels if str(x).strip()):
            matches.append(m["mention_id"])
    return matches[0] if len(set(matches)) == 1 else None


def accept_extractions(state, response):
    """Fast-path acceptance: trust semantic extraction and only protect task identity/reference integrity."""
    require(response.get("fingerprint") == state["fingerprint"], "Stale response fingerprint")
    tasks = response.get("tasks")
    require(isinstance(tasks, list) and bool(tasks), "Response needs tasks")
    units = {u["unit_id"]: u for u in state["units"]}
    revised = copy.deepcopy(state)
    seen = set()
    prefills = revised.get("selection", {}).get("prefill", {})
    for supplied in tasks:
        uid = supplied.get("task_id")
        if uid not in units or uid in seen or uid in state["extractions"]:
            continue
        seen.add(uid)
        unit = units[uid]
        task = _merge_prefill_task(prefills.get(uid), supplied)
        review = task.get("review") if isinstance(task.get("review"), dict) else {}
        review = {"status": "no_facts" if review.get("status") == "no_facts" else "facts",
                  "reason": str(review.get("reason") or "fast semantic extraction")}
        entities = task.get("mentions", []) if isinstance(task.get("mentions"), list) else []
        relations = task.get("relations", []) if isinstance(task.get("relations"), list) else []
        assertions = task.get("assertions", []) if isinstance(task.get("assertions"), list) else []
        if review["status"] == "no_facts" and (entities or relations or assertions):
            review["status"] = "facts"
        output = {"task_id": uid, "review": review, "mentions": [], "relations": [], "assertions": [],
                  "unresolved": [], "warnings": []}
        local = {}
        # Mentions: invalid individual items are skipped, never quarantine the unit.
        for idx, raw in enumerate(entities):
            if not isinstance(raw, dict):
                continue
            typ = raw.get("type")
            name = str(raw.get("name", "") or "").strip()
            if typ not in TYPES or not name:
                output["warnings"].append("skipped_invalid_mention")
                continue
            lid = str(raw.get("local_id") or f"m{idx+1}")
            if lid in local:
                lid = f"{lid}_{idx+1}"
            ev = evidence_list(raw.get("evidence"), unit, raw)
            aliases = [str(a).strip() for a in raw.get("aliases", []) if str(a).strip()] if isinstance(raw.get("aliases", []), list) else []
            attrs = raw.get("attributes") if isinstance(raw.get("attributes"), dict) else {}
            ids = raw.get("identifiers", []) if isinstance(raw.get("identifiers"), list) else []
            identifiers = []
            for item in ids:
                if not isinstance(item, dict) or not str(item.get("value", "")).strip():
                    continue
                identifiers.append({"value": str(item["value"]), "scope": str(item.get("scope") or "identifier"),
                                    "evidence": evidence_list(item.get("evidence"), unit, item)})
            inline_scope = f"inline_{typ.casefold()}_code"
            existing = {(norm(i["scope"]), norm(i["value"])) for i in identifiers}
            evidence_text = "\n".join(e.get("quote", "") for e in ev) or unit.get("content_md", "")
            for code in sorted(_supported_inline_business_codes([name, *aliases], evidence_text)):
                if (norm(inline_scope), norm(code)) not in existing:
                    identifiers.append({"value": code, "scope": inline_scope, "evidence": ev})
            mid = ident("m", [uid, lid])
            local[lid] = mid
            output["mentions"].append({"mention_id": mid, "local_id": lid, "unit_id": uid, "type": typ,
                "name": name, "aliases": aliases, "alias_declared": bool(raw.get("alias_declared", False)),
                "identifiers": identifiers, "attributes": attrs, "evidence": ev})

        # Relationships: resolve local IDs or unique names/aliases. Keep unknown predicates instead of rejecting them.
        for raw in relations:
            if not isinstance(raw, dict):
                continue
            subject = _resolve_endpoint(raw.get("subject"), local, output)
            obj = _resolve_endpoint(raw.get("object"), local, output)
            if not subject or not obj or subject == obj:
                output["warnings"].append("skipped_unresolved_relation_endpoint")
                continue
            predicate = _normalize_relation_predicate(raw.get("predicate"))
            qualifiers = raw.get("qualifiers") if isinstance(raw.get("qualifiers"), dict) else {}
            output["relations"].append({"subject": subject, "predicate": predicate, "object": obj,
                "qualifiers": qualifiers, "evidence": evidence_list(raw.get("evidence"), unit, raw), "origin": "asserted"})

        # Literal facts: unknown predicate names become generic attributes instead of being rejected.
        for raw in assertions:
            if not isinstance(raw, dict):
                continue
            subject = _resolve_endpoint(raw.get("subject"), local, output)
            if not subject or "value" not in raw:
                output["warnings"].append("skipped_unresolved_assertion")
                continue
            raw_pred = str(raw.get("predicate") or "attribute").strip()
            predicate = raw_pred if raw_pred in LITERAL_PREDICATES else "attribute"
            qualifiers = raw.get("qualifiers") if isinstance(raw.get("qualifiers"), dict) else {}
            if predicate == "attribute" and not qualifiers.get("attribute"):
                qualifiers["attribute"] = str(raw.get("attribute") or (raw_pred if raw_pred != "attribute" else "value"))
            value = normalize_value(raw.get("value"))
            output["assertions"].append({"subject": subject, "predicate": predicate, "value": value,
                "qualifiers": qualifiers, "evidence": evidence_list(raw.get("evidence"), unit, raw), "origin": "asserted"})

        # Keep only genuine model-declared uncertainty; never manufacture unresolved items from formatting defects.
        for raw in task.get("unresolved", []) if isinstance(task.get("unresolved"), list) else []:
            if isinstance(raw, dict) and str(raw.get("reason", "")).strip():
                output["unresolved"].append({"reason": str(raw.get("reason")), "details": str(raw.get("details", "")),
                                             "evidence": evidence_list(raw.get("evidence"), unit, raw)})
        if output["mentions"] or output["relations"] or output["assertions"]:
            output["review"]["status"] = "facts"
        revised["extractions"][uid] = output
    require(not state["alignment"]["history"], "Finish extraction before accepting alignment decisions")
    revised["alignment"] = empty_alignment()
    revised["audit"].append({"action": "accept_extract", "tasks": sorted(seen), "mode": "fast_trust_model"})
    return revised


def scoped_ids(m):
    return {(norm(i["scope"]), norm(i["value"])) for i in m["identifiers"]}


def hard_conflict(a, b, forbidden):
    if frozenset([a["mention_id"], b["mention_id"]]) in forbidden:
        return "explicit_distinct_relation"
    if a["type"] != b["type"]:
        return "different_type"
    at, bt = a["attributes"], b["attributes"]
    if a["type"] in {"Product", "Version"}:
        for key in ("version", "variant", "parent_id"):
            if at.get(key) and bt.get(key) and norm(at[key]) != norm(bt[key]):
                return "different_" + key
    if a["type"] == "Actor" and at.get("actor_kind") in {"person", "organization"} and bt.get("actor_kind") in {"person", "organization"} and at["actor_kind"] != bt["actor_kind"]:
        return "different_actor_kind"
    ai, bi = scoped_ids(a), scoped_ids(b)
    if a["type"] in BUSINESS:
        for scope in {x[0] for x in ai} & {x[0] for x in bi}:
            av, bv = {x[1] for x in ai if x[0] == scope}, {x[1] for x in bi if x[0] == scope}
            if av.isdisjoint(bv):
                return "different_scoped_id"
    if a["type"] == "Event":
        for key in ("event_type", "subject_scope"):
            if at.get(key) and bt.get(key) and norm(at[key]) != norm(bt[key]):
                return "different_event_" + key
        if at.get("event_time") and bt.get("event_time") and at["event_time"] != bt["event_time"]:
            return "event_date_needs_review"
    return None


def forbidden_pairs(state):
    return {frozenset([r["subject"], r["object"]]) for r in all_relations(state)
            if r["predicate"] in {"replaced_by", "merged_into", "version_of", "upgraded_to"}}


def names(m):
    return {norm(x) for x in [m["name"], *m["aliases"]] if str(x).strip()}


def tokens(m):
    value = norm(" ".join([m["name"], *m["aliases"]]))
    result = {x for x in re.findall(r"[a-z0-9]+", value) if len(x) >= 2}
    chinese = re.findall(r"[\u4e00-\u9fff]+", value)
    for part in chinese:
        result.update(part[i:i + 2] for i in range(max(0, len(part) - 1)))
    return result


def _qualified_version_name(name):
    text = unicodedata.normalize("NFKC", str(name)).strip()
    m = re.fullmatch(r"(.+?)[\s_-]*[vV](\d+(?:\.\d+)*)", text)
    if not m:
        return None
    base = m.group(1).strip(" _-")
    return (base, "v" + m.group(2)) if base else None


def _distinctive_exact_name(m):
    key = norm(m["name"])
    if not key or key in GENERIC_IDENTITY_NAMES:
        return False
    if m["type"] in STABLE_EXACT_TYPES:
        return True
    if m["type"] == "Actor":
        kind = m["attributes"].get("actor_kind")
        return kind == "organization" or len(key) >= 4
    if m["type"] == "Version":
        return bool(_qualified_version_name(m["name"]))
    return False


def _alias_signature(m):
    return frozenset(x for x in names(m) if x not in GENERIC_IDENTITY_NAMES)


def anchor(a, b):
    """High-precision deterministic identity evidence. Hard conflicts are checked separately."""
    if a["type"] in BUSINESS and scoped_ids(a) & scoped_ids(b):
        return "same_scoped_id"
    if (a["type"] == b["type"] and a["type"] in ALIGNABLE_TYPES and
        a["attributes"].get("_record_key_scope") and
        a["attributes"].get("_record_key_scope") == b["attributes"].get("_record_key_scope") and
        norm(a["name"]) == norm(b["name"])):
        return "same_structured_record_key"
    if a["type"] == b["type"] and _distinctive_exact_name(a) and norm(a["name"]) == norm(b["name"]):
        return "same_stable_name"
    if a["type"] not in {"Event", "Observation"} and a["type"] == b["type"]:
        for owner, other in [(a, b), (b, a)]:
            if owner["alias_declared"] and norm(other["name"]) in names(owner):
                return "explicit_alias_declaration"
        overlap = _alias_signature(a) & _alias_signature(b)
        if len(overlap) >= 2:
            return "corroborated_alias_set"
    return None


def empty_alignment():
    return {"mapping": {}, "clusters": {}, "status": {}, "cluster_status": {}, "round": 1,
            "batches": {}, "history": [], "stopped": False}


def mentions(state):
    return {m["mention_id"]: m for ex in state["extractions"].values() for m in ex["mentions"]}


def all_relations(state):
    return [r for ex in state["extractions"].values() for r in ex["relations"]]


def _repair_identity_metadata(state):
    """Backfill deterministic alias declarations and inline business IDs from accepted evidence."""
    changed = []
    units = {u["unit_id"]: u for u in state.get("units", [])}
    inline_scopes = {norm(f"inline_{typ.casefold()}_code") for typ in TYPES}
    for m in mentions(state).values():
        evidence_text = "\n".join(e.get("quote", "") for e in m.get("evidence", []))
        if m.get("aliases") and not m.get("alias_declared") and all(norm(x) in norm(evidence_text) for x in [m["name"], *m["aliases"]]):
            m["alias_declared"] = True
            changed.append({"mention_id": m["mention_id"], "field": "alias_declared"})
        scope = f"inline_{m['type'].casefold()}_code"
        labels = [m["name"], *m.get("aliases", [])]
        code_evidence = evidence_text or units.get(m.get("unit_id"), {}).get("content_md", "")
        codes = _supported_inline_business_codes(labels, code_evidence)
        supported = {norm(code) for code in codes}
        retained = []
        for item in m.get("identifiers", []):
            if norm(item["scope"]) in inline_scopes and norm(item["value"]) not in supported:
                changed.append({"mention_id": m["mention_id"], "field": "identifier",
                                "action": "remove_unowned_inline_code", "value": item["value"]})
            else:
                retained.append(item)
        m["identifiers"] = retained
        existing = {(norm(i["scope"]), norm(i["value"])) for i in retained}
        for code in sorted(codes):
            if (norm(scope), norm(code)) in existing:
                continue
            m.setdefault("identifiers", []).append({"value": code, "scope": scope, "evidence": copy.deepcopy(m["evidence"])})
            changed.append({"mention_id": m["mention_id"], "field": "identifier", "value": code})
    if changed:
        state["audit"].append({"action": "repair_identity_metadata", "changes": changed})
    return changed


def _incident_type_ok(mid, new_type, state):
    for r in all_relations(state):
        if mid not in (r["subject"], r["object"]):
            continue
        constraints = RELATIONS.get(r["predicate"])
        if constraints is None:
            # Preserve custom predicates; without their endpoint constraints,
            # there is insufficient evidence to automatically change a type.
            return False
        domain, range_ = constraints
        if r["subject"] == mid and new_type not in domain:
            return False
        if r["object"] == mid and new_type not in range_:
            return False
    return True


def _repair_version_types(state):
    """Conservatively repair Tool/Product mentions that are clearly versions of a known AI tool."""
    ms = mentions(state)
    tool_names = {norm(m["name"]): m["name"] for m in ms.values() if m["type"] == "AITool" and not _qualified_version_name(m["name"])}
    changed = []
    for m in ms.values():
        if m["type"] not in {"AITool", "Product"}:
            continue
        parsed = _qualified_version_name(m["name"])
        if not parsed or norm(parsed[0]) not in tool_names or not _incident_type_ok(m["mention_id"], "Version", state):
            continue
        old = m["type"]
        m["type"] = "Version"
        m["attributes"].setdefault("version", parsed[1])
        m["attributes"].setdefault("parent_name", tool_names[norm(parsed[0])])
        changed.append({"mention_id": m["mention_id"], "from": old, "to": "Version", "basis": "qualified_known_tool_version"})
    if changed:
        state["audit"].append({"action": "repair_version_types", "changes": changed})
    return changed


def cluster_conflict(mid, members, ms, forbidden):
    return next((reason for other in members if other != mid and
                 (reason := hard_conflict(ms[mid], ms[other], forbidden))), None)


def clusters_conflict(a_eid, b_eid, alignment, ms, forbidden):
    for a in alignment["clusters"].get(a_eid, []):
        for b in alignment["clusters"].get(b_eid, []):
            reason = hard_conflict(ms[a], ms[b], forbidden)
            if reason:
                return reason
    return None


def _cluster_to_member_status(value):
    return {"record": "record", "active": "pending", "resolved": "confirmed", "uncertain": "uncertain"}.get(value, "pending")


def _sync_cluster_status(alignment, eid):
    value = _cluster_to_member_status(alignment["cluster_status"].get(eid, "active"))
    for mid in alignment["clusters"].get(eid, []):
        alignment["status"][mid] = value


def add_cluster(alignment, mid, status):
    eid = ident("entity", mid)
    alignment["clusters"][eid] = [mid]
    alignment["mapping"][mid] = eid
    alignment["cluster_status"][eid] = "record" if status == "record" else "active"
    alignment["status"][mid] = status
    return eid


def join_cluster(alignment, source, target, reopen=True):
    if source == target:
        return target
    source_members = alignment["clusters"].pop(source)
    alignment["clusters"][target].extend(source_members)
    alignment["clusters"][target] = sorted(set(alignment["clusters"][target]))
    for mid in source_members:
        alignment["mapping"][mid] = target
    source_status = alignment["cluster_status"].pop(source, "active")
    target_status = alignment["cluster_status"].get(target, "active")
    if reopen and "record" not in {source_status, target_status}:
        alignment["cluster_status"][target] = "active"
    elif target_status == "record":
        alignment["cluster_status"][target] = "record"
    elif source_status == "uncertain" or target_status == "uncertain":
        alignment["cluster_status"][target] = "uncertain"
    else:
        alignment["cluster_status"][target] = target_status
    _sync_cluster_status(alignment, target)
    return target


def _merge_group(state, mids, basis):
    alignment = state["alignment"]
    ms = mentions(state)
    forbidden = forbidden_pairs(state)
    eids = []
    for mid in mids:
        eid = alignment["mapping"].get(mid)
        if eid and eid not in eids:
            eids.append(eid)
    if len(eids) < 2:
        return 0
    target = eids[0]
    merged = 0
    for source in eids[1:]:
        source = alignment["mapping"][alignment["clusters"][source][0]] if source in alignment["clusters"] else source
        target = alignment["mapping"][alignment["clusters"][target][0]] if target in alignment["clusters"] else target
        if source == target or source not in alignment["clusters"] or target not in alignment["clusters"]:
            continue
        if clusters_conflict(source, target, alignment, ms, forbidden):
            continue
        source_members = list(alignment["clusters"][source])
        target = join_cluster(alignment, source, target, reopen=True)
        merged += 1
        alignment["history"].append({"round": 0, "decision": "deterministic_merge", "basis": basis,
            "source_members": source_members, "entity_id": target})
    return merged


def _deterministic_alignment_closure(state):
    """Collapse cheap identity duplicates before any LLM task. Uses indexed buckets, not all-pairs scans."""
    alignment = state["alignment"]
    ms = mentions(state)
    buckets = defaultdict(list)
    for mid, m in ms.items():
        if alignment["cluster_status"].get(alignment["mapping"][mid]) == "record":
            continue
        for scope, value in scoped_ids(m):
            buckets[("same_scoped_id", m["type"], scope, value)].append(mid)
        rscope = m["attributes"].get("_record_key_scope")
        if rscope:
            buckets[("same_structured_record_key", m["type"], str(rscope), norm(m["name"]))].append(mid)
        if _distinctive_exact_name(m):
            buckets[("same_stable_name", m["type"], norm(m["name"]))].append(mid)
        if m["alias_declared"]:
            for alias_name in names(m):
                buckets[("explicit_alias_declaration", m["type"], alias_name)].append(mid)
        sig = _alias_signature(m)
        if len(sig) >= 2:
            buckets[("corroborated_alias_set", m["type"], tuple(sorted(sig)))].append(mid)
    merged = 0
    for key, mids in sorted(buckets.items(), key=lambda kv: str(kv[0])):
        # Explicit alias buckets also need same-type mentions whose primary name equals the alias.
        if key[0] == "explicit_alias_declaration":
            alias_name = key[-1]
            mids = list(mids) + [mid for mid, m in ms.items() if m["type"] == key[1] and norm(m["name"]) == alias_name]
        merged += _merge_group(state, sorted(set(mids)), key[0])
    return merged


def initialize_alignment(state):
    require(len(state["extractions"]) == len(state["units"]), "Finish all extraction tasks before alignment")
    if state["alignment"]["mapping"]:
        return
    _repair_identity_metadata(state)
    _repair_version_types(state)
    alignment = state["alignment"]
    ms = mentions(state)
    for mid in sorted(ms):
        alignable = ms[mid]["type"] in ALIGNABLE_TYPES
        add_cluster(alignment, mid, "pending" if alignable else "record")
    merged = _deterministic_alignment_closure(state)
    alignment["history"].append({"round": 0, "decision": "prealign_summary", "merged_clusters": merged,
                                  "remaining_clusters": len(alignment["clusters"])})


def _short_quote(text, limit):
    value = re.sub(r"\s+", " ", str(text)).strip()
    return value if len(value) <= limit else value[: max(0, limit - 1)] + "…"


def _cluster_names(eid, clusters, ms):
    return sorted({m["name"] for m in (ms[x] for x in clusters[eid])} |
                  {a for x in clusters[eid] for a in ms[x]["aliases"]})


def _cluster_identifiers(eid, clusters, ms):
    items = {(i["scope"], i["value"]) for x in clusters[eid] for i in ms[x]["identifiers"]}
    return [{"scope": s, "value": v} for s, v in sorted(items)]


def _cluster_attributes(eid, clusters, ms):
    result = {}
    for key in ("platform", "category", "version", "variant", "parent_id", "parent_name", "actor_kind", "roles"):
        values = []
        for x in clusters[eid]:
            value = ms[x]["attributes"].get(key)
            if value is None:
                continue
            if isinstance(value, list):
                values.extend(value)
            else:
                values.append(value)
        unique = []
        for value in values:
            if canonical(value) not in {canonical(x) for x in unique}:
                unique.append(value)
        if unique:
            result[key] = unique[:6]
    return result


def _cluster_evidence(eid, clusters, ms, state, limit=None):
    limit = limit or state["config"].get("alignment_evidence_examples", 3)
    seen, out = set(), []
    quote_chars = state["config"].get("alignment_quote_chars", 220)
    for mid in clusters[eid]:
        for ev in ms[mid]["evidence"]:
            if ev["evidence_id"] in seen:
                continue
            seen.add(ev["evidence_id"])
            out.append({"evidence_id": ev["evidence_id"], "quote": _short_quote(ev.get("quote", ""), quote_chars),
                        "locator": ev.get("locator", {})})
            if len(out) >= limit:
                return out
    return out


def _cluster_relation_context(eid, state, snapshot):
    mapping, clusters = snapshot["mapping"], snapshot["clusters"]
    ms = mentions(state)
    members = set(clusters[eid])
    result, seen = [], set()
    max_items = state["config"].get("alignment_relation_examples", 12)
    for r in all_relations(state):
        if r["subject"] not in members and r["object"] not in members:
            continue
        outgoing = r["subject"] in members
        other = r["object"] if outgoing else r["subject"]
        neighbor = mapping.get(other)
        if not neighbor or neighbor == eid or neighbor not in clusters:
            continue
        key = ("out" if outgoing else "in", r["predicate"], neighbor)
        if key in seen:
            continue
        seen.add(key)
        neighbor_members = clusters[neighbor]
        result.append({"direction": key[0], "predicate": r["predicate"], "neighbor_entity_id": neighbor,
                       "neighbor_type": ms[neighbor_members[0]]["type"],
                       "neighbor_names": _cluster_names(neighbor, clusters, ms)[:4],
                       "evidence_ids": [e["evidence_id"] for e in r["evidence"][:2]]})
        if len(result) >= max_items:
            break
    return result


def cluster_profile(eid, state, snapshot, *, signals=None):
    clusters = snapshot["clusters"]
    ms = mentions(state)
    members = clusters[eid]
    primary_names = [ms[x]["name"] for x in members]
    counts = Counter(primary_names)
    display = sorted(counts, key=lambda x: (-counts[x], len(x), x))[0]
    return {"entity_id": eid, "representative_member_id": members[0], "type": ms[members[0]]["type"],
            "name": display, "names": _cluster_names(eid, clusters, ms)[:8], "member_count": len(members),
            "identifiers": _cluster_identifiers(eid, clusters, ms), "attributes": _cluster_attributes(eid, clusters, ms),
            "signals": signals or [], "relation_context": _cluster_relation_context(eid, state, snapshot),
            "evidence_examples": _cluster_evidence(eid, clusters, ms, state)}


def _profile_name_norms(profile):
    return {norm(x) for x in profile["names"] if str(x).strip()}


def _profile_tokens(profile):
    pseudo = {"name": profile["name"], "aliases": profile["names"]}
    return tokens(pseudo)


def _candidate_indices(state, snapshot):
    ms = mentions(state)
    indexes = {"names": defaultdict(set), "tokens": defaultdict(set), "attrs": defaultdict(set), "relations": defaultdict(set)}
    profiles = {}
    for eid, members in snapshot["clusters"].items():
        if snapshot["cluster_status"].get(eid) == "record" or ms[members[0]]["type"] not in ALIGNABLE_TYPES:
            continue
        p = cluster_profile(eid, state, snapshot)
        profiles[eid] = p
        for name in _profile_name_norms(p):
            indexes["names"][(p["type"], name)].add(eid)
        for token in _profile_tokens(p):
            indexes["tokens"][(p["type"], token)].add(eid)
        for key, values in p["attributes"].items():
            if key not in {"platform", "category", "version", "variant", "parent_id", "parent_name", "actor_kind"}:
                continue
            for value in values:
                indexes["attrs"][(p["type"], key, norm(value))].add(eid)
        for rel in p["relation_context"]:
            signature = (p["type"], rel["direction"], rel["predicate"], rel["neighbor_entity_id"])
            indexes["relations"][signature].add(eid)
    return profiles, indexes


def cluster_candidates(eid, state, snapshot=None):
    alignment = state["alignment"]
    snapshot = snapshot or {"mapping": dict(alignment["mapping"]), "clusters": copy.deepcopy(alignment["clusters"]),
                            "cluster_status": dict(alignment["cluster_status"])}
    profiles, indexes = _candidate_indices(state, snapshot)
    source = profiles[eid]
    ids = set()
    source_names = _profile_name_norms(source)
    for name in source_names:
        ids.update(indexes["names"].get((source["type"], name), set()))
    for token in _profile_tokens(source):
        ids.update(indexes["tokens"].get((source["type"], token), set()))
    for key, values in source["attributes"].items():
        if key in {"platform", "category", "version", "variant", "parent_id", "parent_name", "actor_kind"}:
            for value in values:
                ids.update(indexes["attrs"].get((source["type"], key, norm(value)), set()))
    for rel in source["relation_context"]:
        ids.update(indexes["relations"].get((source["type"], rel["direction"], rel["predicate"], rel["neighbor_entity_id"]), set()))
    ids.discard(eid)
    ms = mentions(state)
    forbidden = forbidden_pairs(state)
    rejected, candidates = [], []
    source_tokens = _profile_tokens(source)
    source_rel = {(r["direction"], r["predicate"], r["neighbor_entity_id"]) for r in source["relation_context"]}
    for target in sorted(ids):
        if target not in profiles or profiles[target]["type"] != source["type"]:
            continue
        conflict = clusters_conflict(eid, target, alignment, ms, forbidden)
        if conflict:
            rejected.append({"entity_id": target, "reason": conflict})
            continue
        p = profiles[target]
        signals = []
        target_names = _profile_name_norms(p)
        overlap = source_names & target_names
        if overlap:
            signals.append("name_or_alias")
        if len(overlap) >= 2:
            signals.append("alias_set_overlap")
        if any(min(len(a), len(b)) >= 4 and (a in b or b in a) for a in source_names for b in target_names):
            signals.append("name_containment")
        token_overlap = source_tokens & _profile_tokens(p)
        # One generic token/bigram is too weak and creates noisy O(N) candidate lists.
        # Require at least two lexical overlaps unless stronger structural evidence exists.
        if len(token_overlap) >= 2:
            signals.append("name_tokens")
        for key in {"platform", "category", "version", "variant", "parent_id", "parent_name", "actor_kind"}:
            left = {norm(x) for x in source["attributes"].get(key, [])}
            right = {norm(x) for x in p["attributes"].get(key, [])}
            if left & right:
                signals.append("attribute:" + key)
        target_rel = {(r["direction"], r["predicate"], r["neighbor_entity_id"]) for r in p["relation_context"]}
        if source_rel & target_rel:
            signals.append("confirmed_neighbor")
        if not signals or signals == ["name_tokens"]:
            continue
        candidates.append(cluster_profile(target, state, snapshot, signals=signals))
    candidates.sort(key=lambda x: ("name_or_alias" not in x["signals"],
                                   "name_containment" not in x["signals"],
                                   "confirmed_neighbor" not in x["signals"],
                                   "alias_set_overlap" not in x["signals"],
                                   not any(s.startswith("attribute:") for s in x["signals"]),
                                   "name_tokens" not in x["signals"],
                                   -x["member_count"], x["entity_id"]))
    limit = state["config"]["weak_candidates"]
    return candidates[:limit], rejected, len(candidates) > limit, source


def _snapshot_alignment(alignment):
    return {"mapping": dict(alignment["mapping"]), "clusters": copy.deepcopy(alignment["clusters"]),
            "cluster_status": dict(alignment["cluster_status"])}


def extraction_tasks(state, limit, char_budget=None):
    if not state.get("selection", {}).get("prepared"):
        plan_by_id = {x["unit_id"]: x for x in extraction_plan(state)["units"]}
    else:
        plan_by_id = state["selection"]["plan"]
    pending = [u for u in state["units"] if u["unit_id"] not in state["extractions"]]
    pending.sort(key=lambda u: (-plan_by_id[u["unit_id"]]["priority"], u["document_id"], str(u["locator"]), u["unit_id"]))
    char_budget = char_budget or state["config"].get("extract_batch_chars", 18000)
    max_units = min(limit, state["config"].get("extract_batch_units", limit))
    task_units, used_chars = [], 0
    first_doc = pending[0]["document_id"] if pending else None
    if pending and plan_by_id[pending[0]["unit_id"]]["mode"] == "llm_visual":
        max_units = 1
    ordered = [u for u in pending if u["document_id"] == first_doc] + [u for u in pending if u["document_id"] != first_doc]
    prefills = state.get("selection", {}).get("prefill", {})
    overlays = state.get("selection", {}).get("semantic_overlays", {})
    for unit in ordered:
        if len(task_units) >= max_units:
            break
        info = plan_by_id[unit["unit_id"]]
        task_unit = copy.deepcopy(unit)
        if info.get("mode") == "xlsx_semantic_overlay":
            rows = overlays.get(unit["unit_id"], [])
            task_unit["content_md"] = _semantic_overlay_markdown(unit, rows)
            task_unit["structured"] = {"kind": "xlsx_semantic_overlay", "rows": rows}
            pre = prefills.get(unit["unit_id"], {})
            relevant_rows = {str(r.get("row")) for r in rows}
            def relevant_mention(m):
                lid = str(m.get("local_id", ""))
                match = re.search(r"_(\d+)(?:_|$)", lid)
                return not match or match.group(1) in relevant_rows
            task_unit["known_mentions"] = [{k: m.get(k) for k in ("local_id", "type", "name", "aliases") if m.get(k) not in (None, [], "")}
                                           for m in pre.get("mentions", []) if relevant_mention(m)]
            task_unit["known_fact_counts"] = {"relations": len(pre.get("relations", [])), "assertions": len(pre.get("assertions", []))}
        elif task_unit.get("structured", {}).get("kind") == "pdf_page":
            words = task_unit["structured"].pop("words", [])
            task_unit["structured"]["word_count"] = len(words)
        size = len(task_unit.get("content_md", ""))
        if task_units and used_chars + size > char_budget:
            continue
        task_units.append({"task_id": unit["unit_id"], "selection": info,
            "extraction_policy": {"coverage": "full", "representation": "sparse",
                "node_rule": "identity/event only; prefer literal fact over new node",
                "observation_rule": "use Observation only when it participates in a relation/path",
                "llm_role": "semantic delta only; never restate deterministic table facts",
                "output_rule": "minimal JSON only; omit evidence/quote/review reason unless essential; unit locator is inherited automatically",
                "known_mentions_rule": "known_mentions already exist; relations/assertions may reference those local_ids without repeating the mention"}, **task_unit})
        used_chars += size
    return {"schema_version": SCHEMA_VERSION, "fingerprint": state["fingerprint"],
            "stage": "extract", "pending_count": len(pending), "batch_chars": used_chars,
            "batch_policy": "one-model-call-per-batch; host may request multiple disjoint batches and run them concurrently",
            "host_guidance": "Return minimal semantic delta only. Omit repetitive quote/evidence/review text; the acceptor inherits the parser locator. For xlsx_semantic_overlay, reference known_mentions local_ids and do not repeat deterministic row facts. Put only genuine ambiguity in unresolved.",
            "tasks": task_units}

def alignment_tasks(state, limit):
    initialize_alignment(state)
    alignment = state["alignment"]
    if alignment["stopped"]:
        return {"fingerprint": state["fingerprint"], "stage": "align", "pending_count": 0,
                "tasks": [], "stopped": True}
    round_key = str(alignment["round"])
    if round_key not in alignment["batches"]:
        snapshot = _snapshot_alignment(alignment)
        generated, deferred = [], []
        for eid in sorted(snapshot["clusters"]):
            if snapshot["cluster_status"].get(eid) not in {"active", "uncertain"}:
                continue
            choices, rejected, truncated, source = cluster_candidates(eid, state, snapshot)
            if not choices:
                deferred.append(eid)
                continue
            task = {"task_id": ident("align", [state["fingerprint"], alignment["round"], eid, [c["entity_id"] for c in choices]]),
                    "source_cluster": source, "current_entity_id": eid, "candidates": choices,
                    "candidates_truncated": truncated,
                    "decision_policy": "Return only candidate entity_id, NEW_ENTITY or UNCERTAIN. Do not write explanations unless genuinely uncertain."}
            generated.append(task)
        alignment["batches"][round_key] = {"tasks": generated, "accepted": [], "merged": False,
                                             "deferred": deferred, "snapshot": snapshot}
        if not generated:
            # Nothing ambiguous remains. No model call is useful; unresolved zero-candidate clusters are new identities.
            for eid in deferred:
                current = alignment["mapping"].get(snapshot["clusters"][eid][0])
                if current in alignment["cluster_status"] and alignment["cluster_status"][current] == "active":
                    alignment["cluster_status"][current] = "resolved"
                    _sync_cluster_status(alignment, current)
            alignment["stopped"] = True
    batch = alignment["batches"][round_key]
    pending = [t for t in batch["tasks"] if t["task_id"] not in batch["accepted"]]
    return {"schema_version": SCHEMA_VERSION, "fingerprint": state["fingerprint"],
            "stage": "align", "round": alignment["round"], "pending_count": len(pending),
            "alignment_mode": "cluster_select", "tasks": pending[:limit], "stopped": alignment["stopped"]}


def _resolve_task_cluster(profile, alignment):
    mid = profile["representative_member_id"]
    require(mid in alignment["mapping"], "Alignment task references unknown member")
    return alignment["mapping"][mid]


def _task_evidence_ids(task):
    known = set()
    for profile in [task["source_cluster"], *task["candidates"]]:
        known.update(e["evidence_id"] for e in profile.get("evidence_examples", []))
        for rel in profile.get("relation_context", []):
            known.update(rel.get("evidence_ids", []))
    return known


def accept_alignment(state, response):
    require(response.get("fingerprint") == state["fingerprint"], "Stale response fingerprint")
    require(response.get("round") == state["alignment"]["round"], "Stale alignment round")
    revised = copy.deepcopy(state)
    alignment = revised["alignment"]
    require(not alignment["stopped"], "Alignment already stopped")
    batch = alignment["batches"].get(str(alignment["round"]))
    require(batch is not None, "Request tasks before accepting alignment")
    task_map = {x["task_id"]: x for x in batch["tasks"]}
    answers = response.get("tasks")
    require(isinstance(answers, list) and bool(answers), "Response needs decisions")
    ms = mentions(revised)
    forbidden = forbidden_pairs(revised)
    accepted = set(batch["accepted"])
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        tid = answer.get("task_id")
        if tid not in task_map or tid in accepted:
            continue
        task = task_map[tid]
        source = _resolve_task_cluster(task["source_cluster"], alignment)
        choice = answer.get("decision")
        candidate = next((c for c in task["candidates"] if c["entity_id"] == choice), None)
        if choice not in {"NEW_ENTITY", "UNCERTAIN"} and candidate is None:
            choice = "UNCERTAIN"
        reason = str(answer.get("reason") or "")
        if choice in {"NEW_ENTITY", "UNCERTAIN"}:
            if source in alignment["cluster_status"]:
                alignment["cluster_status"][source] = "resolved" if choice == "NEW_ENTITY" else "uncertain"
                _sync_cluster_status(alignment, source)
            alignment["history"].append({"round": alignment["round"], "decision": choice,
                                           "entity_id": source, **({"reason": reason} if reason else {})})
        else:
            target = _resolve_task_cluster(candidate, alignment)
            if source != target and not clusters_conflict(source, target, alignment, ms, forbidden):
                source_members = list(alignment["clusters"][source])
                target_members = list(alignment["clusters"][target])
                merged = join_cluster(alignment, source, target, reopen=True)
                batch["merged"] = True
                alignment["history"].append({"round": alignment["round"], "decision": "cluster_merge",
                    "source_entity_id": source, "target_entity_id": target, "entity_id": merged,
                    "source_members": source_members, "target_members": target_members,
                    **({"reason": reason} if reason else {})})
            else:
                alignment["cluster_status"][source] = "resolved"
                _sync_cluster_status(alignment, source)
        accepted.add(tid)
    batch["accepted"] = sorted(accepted)
    if len(accepted) == len(batch["tasks"]):
        if batch["merged"] and alignment["round"] < state["config"]["max_rounds"]:
            alignment["round"] += 1
        else:
            snapshot = batch.get("snapshot", {})
            for old_eid in batch.get("deferred", []):
                members = snapshot.get("clusters", {}).get(old_eid, [])
                if not members:
                    continue
                current = alignment["mapping"].get(members[0])
                if current in alignment["cluster_status"] and alignment["cluster_status"][current] == "active":
                    alignment["cluster_status"][current] = "resolved"
                    _sync_cluster_status(alignment, current)
            alignment["stopped"] = True
    revised["audit"].append({"action": "accept_align", "tasks": sorted(a.get("task_id") for a in answers if isinstance(a, dict) and a.get("task_id")),
                              "mode": "fast_cluster_select"})
    return revised


def scope_complete(qualifiers):
    def known(value):
        return (isinstance(value, str) and bool(value.strip()) and norm(value) not in {"unknown", "未知"}) or (isinstance(value, dict) and bool(value))
    return all(known(qualifiers.get(k)) for k in ("period", "sample_scope", "metric_definition"))


def coalesce_observations(state, mapping):
    ms = mentions(state)
    assertions = [a for ex in state["extractions"].values() for a in ex["assertions"]]
    parents = defaultdict(set)
    for r in all_relations(state):
        if r["predicate"] in {"has_observation", "has_feedback"}:
            parents[r["object"]].add(mapping[r["subject"]])
    index = {}
    for mid in sorted(ms):
        m = ms[mid]
        if m["type"] != "Observation" or not parents[mid] or not m["attributes"].get("metric"):
            continue
        own = [a for a in assertions if a["subject"] == mid and a["predicate"] == "observed_value"]
        if len(own) != 1 or not scope_complete(own[0]["qualifiers"]):
            continue
        # Same observation context may have competing values; retain both as facts.
        value = own[0]["value"]
        nv = value_key(value)
        unit = nv.get("unit") if isinstance(nv, dict) else None
        currency = nv.get("currency") if isinstance(nv, dict) else None
        key = canonical([sorted(parents[mid]), norm(m["attributes"]["metric"]), own[0]["qualifiers"], unit, currency])
        if key in index:
            previous = mapping[mid]
            target = index[key]
            for candidate in mapping:
                if mapping[candidate] == previous:
                    mapping[candidate] = target
        else:
            index[key] = mapping[mid]
    return mapping


def build_graph(state, allow_partial=False):
    complete_extraction = len(state["extractions"]) == len(state["units"])
    parse_complete = all(d.get("parse_status") != "failed" for d in state["documents"])
    if complete_extraction:
        initialize_alignment(state)
    alignment = state["alignment"]
    # No-semantic-task graphs (only observations or no facts) can complete directly.
    if complete_extraction and not any(s in {"pending", "uncertain"} for s in alignment["status"].values()):
        alignment["stopped"] = True
    require(allow_partial or (parse_complete and complete_extraction and alignment["stopped"]), "Incomplete workflow; finish tasks or use --allow-partial")
    mapping = dict(alignment["mapping"])
    ms = mentions(state)
    for mid in ms:
        mapping.setdefault(mid, ident("entity", mid))
    mapping = coalesce_observations(state, mapping)
    evidence = {}
    for ex in state["extractions"].values():
        for item in [*ex["mentions"], *ex["relations"], *ex["assertions"], *ex["unresolved"]]:
            for ev in item["evidence"]:
                evidence[ev["evidence_id"]] = copy.deepcopy(ev)
            for identifier in item.get("identifiers", []):
                for ev in identifier["evidence"]:
                    evidence[ev["evidence_id"]] = copy.deepcopy(ev)
    documents = {d["document_id"]: d for d in state["documents"]}
    for ev in evidence.values():
        d = documents[ev["document_id"]]
        ev.update(source=d["path"], file_sha256=d["sha256"])
    grouped = defaultdict(list)
    for mid, m in ms.items():
        grouped[mapping[mid]].append(m)
    nodes = []
    for eid, members in sorted(grouped.items()):
        labels = sorted({m["name"] for m in members})
        counts = Counter(m["name"] for m in members)
        def label_score(name):
            linked = [m for m in members if m["name"] == name]
            return (-counts[name],
                    -int(any(m["identifiers"] for m in linked)),
                    -int(any(m["alias_declared"] for m in linked)),
                    len(name), name)
        display_name = sorted(labels, key=label_score)[0]
        alias_bindings = []
        seen_bindings = set()
        for m in members:
            for binding in m.get("attributes", {}).get("alias_bindings", []) if isinstance(m.get("attributes", {}).get("alias_bindings", []), list) else []:
                if not isinstance(binding, dict) or not str(binding.get("alias", "")).strip():
                    continue
                key = (norm(binding.get("alias")), str(binding.get("role", "")))
                if key in seen_bindings:
                    continue
                seen_bindings.add(key)
                alias_bindings.append({"alias": str(binding.get("alias")), "role": str(binding.get("role", ""))})
        nodes.append({"id": eid, "type": members[0]["type"], "name": display_name,
            "aliases": sorted(set(labels) | {a for m in members for a in m["aliases"]}),
            "alias_bindings": alias_bindings,
            "mention_ids": sorted(m["mention_id"] for m in members),
            "attribute_claims": [{"attributes": {k: v for k, v in m["attributes"].items() if not k.startswith("_")}, "identifiers": m["identifiers"],
                "evidence_ids": sorted(e["evidence_id"] for e in m["evidence"])} for m in members],
            "review_status": "unresolved" if any(alignment["status"].get(m["mention_id"], "pending") in {"pending", "uncertain"} for m in members) else "supported"})
    facts_by_key = {}
    for ex in state["extractions"].values():
        for raw in [*ex["relations"], *ex["assertions"]]:
            fact = {"subject": mapping[raw["subject"]], "predicate": raw["predicate"],
                    "qualifiers": raw["qualifiers"], "origin": "asserted", "review_status": "supported"}
            if "object" in raw:
                fact["object"] = mapping[raw["object"]]
                if fact["subject"] == fact["object"]:
                    continue
                object_key = fact["object"]
            else:
                fact["value"] = raw["value"]
                object_key = value_key(raw["value"])
            key_parts = [fact["subject"], fact["predicate"], object_key, fact["qualifiers"], fact["origin"]]
            # Unknown metric scope cannot deduplicate across distinct source records.
            if fact["predicate"] == "observed_value" and not scope_complete(fact["qualifiers"]):
                key_parts.append(ex["task_id"])
                fact["review_status"] = "scope_unknown"
            key = canonical(key_parts)
            if key not in facts_by_key:
                facts_by_key[key] = {"fact_id": ident("fact", key_parts), **fact,
                    "evidence_ids": [], "value_claims": []}
            stored = facts_by_key[key]
            stored["evidence_ids"] = sorted(set(stored["evidence_ids"]) | {e["evidence_id"] for e in raw["evidence"]})
            if "value" in raw and raw["value"] not in stored["value_claims"]:
                stored["value_claims"].append(raw["value"])
    facts = sorted(facts_by_key.values(), key=lambda f: f["fact_id"])
    diagnostics = {"fingerprint": state["fingerprint"], "engine_version": ENGINE_VERSION,
                   "parsed_units": len(state["units"]), "reviewed_units": len(state["extractions"]),
                   "alignment_round": alignment["round"], "workflow_complete": parse_complete and complete_extraction and alignment["stopped"],
                   "parse_warnings": [{"unit_id": u["unit_id"], "warnings": u["parse_warnings"]}
                                      for u in state["units"] if u["parse_warnings"]],
                   "metric_comparisons": []}
    groups = defaultdict(list)
    for f in facts:
        if f["predicate"] == "observed_value":
            groups[canonical([f["subject"], f["qualifiers"]])].append(f)
    for members in groups.values():
        if len({canonical(value_key(f["value"])) for f in members}) > 1:
            status = "conflict" if scope_complete(members[0]["qualifiers"]) else "scope_unknown"
            for f in members:
                f["review_status"] = status
            diagnostics["metric_comparisons"].append({"status": status, "fact_ids": [f["fact_id"] for f in members]})
    # Report differing/unknown scopes across observations of the same subject/metric.
    observation_meta = {}
    for eid, members in grouped.items():
        if members[0]["type"] == "Observation":
            observation_meta[eid] = {norm(m["attributes"].get("metric", "")) for m in members}
    comparable = defaultdict(list)
    for raw in all_relations(state):
        if raw["predicate"] in {"has_observation", "has_feedback"}:
            obs = mapping[raw["object"]]
            for metric in observation_meta.get(obs, set()):
                if metric:
                    comparable[(mapping[raw["subject"]], metric)].extend(f for f in facts if f["subject"] == obs and f["predicate"] == "observed_value")
    for members in comparable.values():
        unique = {f["fact_id"]: f for f in members}
        if len(unique) > 1 and len({canonical(f["qualifiers"]) for f in unique.values()}) > 1:
            diagnostics["metric_comparisons"].append({"status": "different_scope" if all(scope_complete(f["qualifiers"]) for f in unique.values()) else "scope_unknown",
                "fact_ids": sorted(unique)})
    edge_groups = defaultdict(list)
    for f in facts:
        if "object" in f:
            edge_groups[(f["subject"], f["predicate"], f["object"])].append(f)
    edges = []
    for (source, predicate, target), members in sorted(edge_groups.items()):
        qualifier_keys = {canonical(f["qualifiers"]) for f in members}
        edge = {"id": ident("edge", [source, predicate, target]), "source": source, "target": target,
                "predicate": predicate, "fact_ids": sorted(f["fact_id"] for f in members)}
        if len(qualifier_keys) == 1:
            edge["qualifiers"] = members[0]["qualifiers"]
        else:
            edge["qualifiers"] = {}
            edge["qualifier_mode"] = "fact_level"
        edges.append(edge)
    unresolved = []
    for mid, m in ms.items():
        if alignment["status"].get(mid, "pending") in {"pending", "uncertain"}:
            unresolved.append({"kind": "entity_alignment", "mention_id": mid, "entity_id": mapping[mid],
                "name": m["name"], "evidence_ids": [e["evidence_id"] for e in m["evidence"]]})
    for ex in state["extractions"].values():
        for item in ex["unresolved"]:
            unresolved.append({"kind": "extraction", "reason": item["reason"], "details": item["details"],
                               "evidence_ids": [e["evidence_id"] for e in item["evidence"]]})
    for unit in state["units"]:
        if unit["unit_id"] not in state["extractions"]:
            unresolved.append({"kind": "unreviewed_unit", "unit_id": unit["unit_id"], "locator": unit["locator"]})
    for document in state["documents"]:
        if document.get("parse_status") == "failed":
            unresolved.append({"kind": "parse_failure", "document_id": document["document_id"], "error": document["parse_error"]})
    graph = {"schema_version": SCHEMA_VERSION, "documents": state["documents"], "nodes": nodes,
             "edges": edges, "facts": facts, "evidence": sorted(evidence.values(), key=lambda e: e["evidence_id"]),
             "unresolved": unresolved, "diagnostics": diagnostics}
    graph["diagnostics"]["integrity"] = validate_graph(graph)
    return graph


def validate_graph(graph):
    """Minimal runtime integrity check. Quality/audit issues are warnings, never build blockers."""
    errors, warnings = [], []
    if not isinstance(graph, dict):
        return {"valid": False, "errors": ["Graph must be an object"], "warnings": []}
    for key in ("documents", "nodes", "edges", "facts", "evidence", "unresolved"):
        if not isinstance(graph.get(key), list):
            errors.append(f"{key} must be array")
    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings}
    indexes = {}
    for key, field in [("nodes", "id"), ("edges", "id"), ("facts", "fact_id"), ("evidence", "evidence_id"), ("documents", "document_id")]:
        values = [x.get(field) for x in graph[key] if isinstance(x, dict)]
        if len(values) != len(graph[key]) or None in values or len(set(values)) != len(values):
            errors.append(f"Duplicate or missing {key} IDs")
        indexes[key] = {x.get(field): x for x in graph[key] if isinstance(x, dict) and x.get(field) is not None}
    nodes, facts, evs = indexes["nodes"], indexes["facts"], indexes["evidence"]
    for fact in facts.values():
        if fact.get("subject") not in nodes:
            errors.append("Dangling fact subject")
        if "object" in fact and fact.get("object") not in nodes:
            errors.append("Dangling fact object")
        missing_evidence = [x for x in fact.get("evidence_ids", []) if x not in evs]
        if missing_evidence:
            warnings.append("Fact references missing evidence")
    projected = set()
    for edge in indexes["edges"].values():
        if edge.get("source") not in nodes or edge.get("target") not in nodes:
            errors.append("Dangling edge")
        refs = edge.get("fact_ids", []) if isinstance(edge.get("fact_ids"), list) else []
        if not refs:
            warnings.append("Edge without fact_ids")
        for fid in refs:
            if fid not in facts:
                errors.append("Edge references missing fact")
                continue
            projected.add(fid)
            f = facts[fid]
            if (edge.get("source"), edge.get("predicate"), edge.get("target")) != (f.get("subject"), f.get("predicate"), f.get("object")):
                errors.append("Edge/fact mismatch")
    relation_facts = {f["fact_id"] for f in facts.values() if "object" in f}
    if relation_facts - projected:
        warnings.append(f"{len(relation_facts - projected)} relation facts are not projected as edges")
    if graph.get("unresolved"):
        warnings.append(f"{len(graph['unresolved'])} unresolved items retained")
    if not graph.get("diagnostics", {}).get("workflow_complete"):
        warnings.append("Workflow incomplete")
    return {"valid": not errors, "errors": list(dict.fromkeys(errors)), "warnings": list(dict.fromkeys(warnings)),
            "counts": {k: len(graph.get(k, [])) for k in ("nodes", "edges", "facts", "evidence", "unresolved")}}
