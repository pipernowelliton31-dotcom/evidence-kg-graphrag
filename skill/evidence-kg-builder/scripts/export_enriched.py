#!/usr/bin/env python3
"""Export existing document units as readable provenance-enriched Markdown.

Standard library only. Does not parse inputs, modify checkpoints, or call an LLM.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote


def json_block(value):
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def relative_link(path, target_directory):
    import os
    return quote(Path(os.path.relpath(path, target_directory)).as_posix(), safe="/._-")


def location_label(unit):
    loc = unit["locator"]
    parts = []
    if "page" in loc:
        parts.append(f"PDF 第 {loc['page']} 页")
    if "sheet" in loc:
        parts.append("Sheet：" + loc["sheet"])
    if "slide" in loc:
        parts.append(f"Slide {loc['slide']}")
    if loc.get("section"):
        section = loc["section"]
        parts.append(" / ".join(section) if isinstance(section, list) else str(section))
    if "table" in loc:
        parts.append(f"表格 {loc['table']}")
    if "row_start" in loc:
        parts.append(f"行 {loc['row_start']}–{loc['row_end']}")
    if "cell_range" in loc:
        parts.append(loc["cell_range"])
    if "paragraph_start" in loc:
        parts.append(f"段落 {loc['paragraph_start']}–{loc['paragraph_end']}")
    if "paragraph" in loc:
        parts.append(f"段落 {loc['paragraph']}")
    if "image" in loc:
        parts.append("图片：" + loc["image"])
    if "media_part" in loc:
        parts.append(loc["media_part"])
    if "part" in loc:
        parts.append(f"分段 {loc['part']}")
    return " · ".join(parts) or "文档单元"


def display_structured(unit, checkpoint_link):
    structured = unit.get("structured")
    if structured is None:
        return "本单元没有额外结构台账。正文和定位字段仍完整保留。"
    if structured.get("kind") == "pdf_page":
        # Keep the readable export small; the original word boxes remain in JSON.
        value = {key: val for key, val in structured.items() if key != "words"}
        value.update(word_count=len(structured.get("words", [])),
                     words_preview=structured.get("words", [])[:3])
        return ("本页文字框台账只展示前三项，全文未截断；完整 words 数组见 "
                f"[结构化检查点]({checkpoint_link}) 中同一 unit_id。\n\n" + json_block(value))
    return json_block(structured)


def render_document(document, units, work, directory, checkpoint_link):
    lines = ["# " + Path(document["path"]).name + " · enriched", "",
             "以下内容由已有文档单元直接导出；未重新解析、未进行 LLM 实体或关系抽取。", "",
             "- Source：`" + document["path"] + "`",
             "- Format：`" + document["format"] + "`",
             "- Document ID：`" + document["document_id"] + "`",
             "- File SHA256：`" + document["sha256"] + "`",
             f"- Unit count：{len(units)}", "",
             "PDF 页码为文件实际页序号；table 编号为本页解析器检测的表格序号，"
             "不保证等于文档印刷表号。PDF / DOCX 表格行号来自解析器结构；Excel 行号是原始工作表行号。", ""]
    if document.get("parse_status") == "failed":
        lines += ["**解析失败：** " + document.get("parse_error", "unknown"), ""]
    seen_assets = set()
    for number, unit in enumerate(units, 1):
        lines += ["---", "", f"<a id=\"{unit['unit_id']}\"></a>", "",
                  f"## 单元 {number} · {location_label(unit)}", "",
                  "### Provenance", "",
                  json_block({"unit_id": unit["unit_id"], "document_id": unit["document_id"],
                              "source": document["path"], "format": unit["format"], "locator": unit["locator"]}), ""]
        if unit.get("parse_warnings"):
            lines += ["**解析提醒：**", "", *["- " + warning for warning in unit["parse_warnings"]], ""]
        lines += ["### 内容 · content_md", "", unit["content_md"], ""]
        for ref in unit.get("asset_refs", []):
            asset = (work / ref).resolve()
            if not asset.is_relative_to(work) or not asset.is_file():
                lines += [f"**图像资产不可用：** `{ref}`", ""]
                continue
            link = relative_link(asset, directory)
            if ref not in seen_assets:
                lines += [f"![原始图像 / PDF 页图]({link})", ""]
                seen_assets.add(ref)
            else:
                lines += [f"[查看同页图像]({link})", ""]
        lines += ["<details>", "<summary>展开 structured：原始结构台账</summary>", "",
                  display_structured(unit, checkpoint_link), "", "</details>", ""]
    return "\n".join(lines)


def export(work):
    work = Path(work).resolve()
    source = work / "00_document_units.json"
    snapshot = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(snapshot.get("documents"), list) or not isinstance(snapshot.get("units"), list):
        raise ValueError("Invalid document-unit checkpoint")
    destination = work / "enriched"
    destination.mkdir(parents=True, exist_ok=True)
    grouped = {}
    seen_units = set()
    for unit in snapshot["units"]:
        if unit["unit_id"] in seen_units:
            raise ValueError("Duplicate unit_id")
        seen_units.add(unit["unit_id"])
        grouped.setdefault(unit["document_id"], []).append(unit)
    combined = ["# 文档解析结果 · Provenance-enriched Markdown", "",
                "本文件是已有解析结果的阅读导出，不表示语义抽取或实体对齐已完成。", "",
                "- Fingerprint：`" + snapshot["fingerprint"] + "`",
                f"- Total units：{len(snapshot['units'])}", "",
                "## 文档索引", ""]
    outputs, bodies = [], []
    corpus = [d for d in snapshot["documents"] if d["role"] == "corpus"]
    for ordinal, document in enumerate(corpus, 1):
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(document["path"]).stem).strip(". ")[:80] or "document"
        target = destination / f"{ordinal:02d}_{stem}.enriched.md"
        units = grouped.get(document["document_id"], [])
        rendered = render_document(document, units, work, destination, relative_link(source, destination))
        target.write_text(rendered, encoding="utf-8")
        combined += [f"- [{Path(document['path']).name}]({relative_link(target, work)})：{len(units)} 个单元"]
        bodies.append(render_document(document, units, work, work, relative_link(source, work)))
        outputs.append({"source": document["path"], "path": str(target), "unit_count": len(units)})
    excluded = [d["path"] for d in snapshot["documents"] if d["role"] != "corpus"]
    if excluded:
        combined += ["", "参考／问题文件未进入正文：" + "、".join(excluded)]
    main = work / "enriched.md"
    main.write_text("\n".join(combined + ["", "---", "", "\n\n---\n\n".join(bodies), ""]), encoding="utf-8")
    return {"ok": True, "combined": str(main), "documents": outputs,
            "unit_count": len(snapshot["units"]), "fingerprint": snapshot["fingerprint"]}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(export(args.work), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)
