#!/usr/bin/env python3
"""File-based host-Agent protocol. All stdout is JSON; no model API or credentials."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from kg_core import (ContractError, accept_alignment, accept_extractions, alignment_tasks,
                     build_graph, extraction_plan, extraction_tasks, load_state, prepare_selective_extraction,
                     read_json, require, save_state, validate_graph, write_json)


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def protect_output(path, state, work):
    resolved = Path(path).resolve()
    for document in state["documents"]:
        require(resolved != (Path(state["source_root"]) / document["path"]).resolve(), "Cannot overwrite input source")
    reserved = {"state.json", "00_document_units.json", "00_extraction_plan.json", "01_mentions.json", "02_entity_map.json", "03_canonical_facts.json"}
    require(resolved not in {(Path(work) / name).resolve() for name in reserved}, "Cannot overwrite checkpoint with exported data")


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    parse = subs.add_parser("parse", help="Parse explicit input manifest")
    parse.add_argument("--manifest", required=True)
    parse.add_argument("--work", required=True)
    parse.add_argument("--fresh", action="store_true", help="Archive checkpoint and reparse")
    parse.add_argument("--max-chars", type=int, default=12000)
    parse.add_argument("--max-rows", type=int, default=80)
    prepare = subs.add_parser("prepare", help="Run cheap selective-extraction planning and deterministic prepass")
    prepare.add_argument("--work", required=True)
    prepare.add_argument("--output")
    tasks = subs.add_parser("tasks", help="Export host extraction/alignment tasks")
    tasks.add_argument("--work", required=True)
    tasks.add_argument("--stage", choices=["extract", "align"], required=True)
    tasks.add_argument("--limit", type=int, default=5, help="Tasks per model request")
    tasks.add_argument("--char-budget", type=int, default=14000, help="Approximate semantic-text character budget per extraction request")
    tasks.add_argument("--batch-count", type=int, default=1, help="Return multiple disjoint batches for concurrent model calls")
    tasks.add_argument("--output")
    accept = subs.add_parser("accept", help="Validate and atomically accept host response")
    accept.add_argument("--work", required=True)
    accept.add_argument("--stage", choices=["extract", "align"], required=True)
    accept.add_argument("--response", required=True)
    build = subs.add_parser("build", help="Build self-contained KG JSON")
    build.add_argument("--work", required=True)
    build.add_argument("--output")
    build.add_argument("--allow-partial", action="store_true")
    validate = subs.add_parser("validate", help="Validate standalone graph or work checkpoint")
    choice = validate.add_mutually_exclusive_group(required=True)
    choice.add_argument("--graph")
    choice.add_argument("--work")
    validate.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    if args.command == "parse":
        from parse_documents import parse_manifest
        state, cached = parse_manifest(args.manifest, args.work,
            {"max_chars": args.max_chars, "max_rows": args.max_rows}, args.fresh)
        failures = [d for d in state["documents"] if d["parse_status"] == "failed"]
        emit({"ok": not failures, "fingerprint": state["fingerprint"], "cached": cached,
              "documents": [{"path": d["path"], "role": d["role"], "status": d["parse_status"],
                             "error": d.get("parse_error")} for d in state["documents"]],
              "unit_count": len(state["units"]), "parser_versions": state["parser_versions"],
              "next": "prepare", "work": str(Path(args.work).resolve())})
        return 2 if failures else 0
    if args.command == "validate" and args.graph:
        report = validate_graph(read_json(args.graph))
        if args.require_complete:
            graph = read_json(args.graph)
            if not graph["diagnostics"].get("workflow_complete"):
                report["errors"].append("Workflow incomplete")
                report["valid"] = False
        emit(report)
        return 0 if report["valid"] else 2
    state = load_state(args.work)
    if args.command == "prepare":
        state, plan = prepare_selective_extraction(state)
        save_state(args.work, state)
        target = Path(args.output) if args.output else Path(args.work) / "00_extraction_plan.json"
        protect_output(target, state, args.work) if args.output else None
        write_json(target, plan)
        pending = len(state["units"]) - len(state["extractions"])
        modes = {}
        for item in plan["units"]:
            modes[item["mode"]] = modes.get(item["mode"], 0) + 1
        emit({"ok": True, "output": str(Path(target).resolve()), "reviewed_without_llm": len(state["extractions"]),
              "pending_llm_units": pending, "mixed_semantic_units": state.get("selection", {}).get("mixed_semantic_units", 0),
              "modes": modes, "next": "tasks --stage extract"})
        return 0
    if args.command == "tasks":
        require(args.limit > 0 and args.batch_count > 0, "Task limit/batch-count must be positive")
        if args.batch_count == 1:
            result = extraction_tasks(state, args.limit, args.char_budget) if args.stage == "extract" else alignment_tasks(state, args.limit)
        elif args.stage == "extract":
            temp = copy.deepcopy(state)
            batches = []
            pending_count = len(state["units"]) - len(state["extractions"])
            for idx in range(args.batch_count):
                part = extraction_tasks(temp, args.limit, args.char_budget)
                if not part["tasks"]:
                    break
                batches.append({"batch_index": idx, "batch_chars": part.get("batch_chars", 0), "tasks": part["tasks"]})
                for task in part["tasks"]:
                    temp["extractions"][task["task_id"]] = {}
            result = {"schema_version": state["schema_version"], "fingerprint": state["fingerprint"], "stage": "extract",
                      "pending_count": pending_count, "concurrent_batches": True, "batches": batches}
        else:
            all_result = alignment_tasks(state, 10**9)
            tasks_all = all_result.get("tasks", [])
            batches = [{"batch_index": i, "round": all_result.get("round"), "tasks": tasks_all[i*args.limit:(i+1)*args.limit]}
                       for i in range(args.batch_count) if tasks_all[i*args.limit:(i+1)*args.limit]]
            result = {k: v for k, v in all_result.items() if k != "tasks"}
            result.update({"concurrent_batches": True, "batches": batches})
        if args.stage == "align":
            save_state(args.work, state)
        if args.output:
            protect_output(args.output, state, args.work)
            require(Path(args.output).resolve() != (Path(args.work) / "04_knowledge_graph.json").resolve(), "Cannot overwrite graph with tasks")
            write_json(args.output, result)
            task_count = sum(len(b["tasks"]) for b in result.get("batches", [])) if result.get("concurrent_batches") else len(result.get("tasks", []))
            emit({"ok": True, "output": args.output, "pending_count": result["pending_count"], "task_count": task_count,
                  "batch_count": len(result.get("batches", [])) if result.get("concurrent_batches") else 1})
        else:
            emit(result)
    elif args.command == "accept":
        response = read_json(args.response)
        state = accept_extractions(state, response) if args.stage == "extract" else accept_alignment(state, response)
        save_state(args.work, state)
        # Any prior graph is obsolete after newly accepted work.
        for name in ("03_canonical_facts.json", "04_knowledge_graph.json"):
            (Path(args.work) / name).unlink(missing_ok=True)
        emit({"ok": True, "stage": args.stage, "accepted": len(response["tasks"]),
              "reviewed_units": len(state["extractions"]), "pending_extraction": len(state["units"]) - len(state["extractions"]),
              "round": state["alignment"]["round"]})
    elif args.command == "build":
        graph = build_graph(state, args.allow_partial)
        output = Path(args.output) if args.output else Path(args.work) / "04_knowledge_graph.json"
        output = output.resolve()
        protect_output(output, state, args.work)
        write_json(Path(args.work) / "03_canonical_facts.json", {"fingerprint": state["fingerprint"], "facts": graph["facts"], "evidence": graph["evidence"]})
        write_json(Path(args.work) / "04_knowledge_graph.json", graph)
        if output != (Path(args.work) / "04_knowledge_graph.json").resolve():
            write_json(output, graph)
        save_state(args.work, state)
        emit({"ok": True, "output": str(output), **validate_graph(graph)})
    elif args.command == "validate":
        errors = []
        pending = len(state["units"]) - len(state["extractions"])
        failures = [d["path"] for d in state["documents"] if d["parse_status"] == "failed"]
        graph_path = Path(args.work) / "04_knowledge_graph.json"
        report = {"valid": True, "errors": errors, "warnings": [], "pending_extraction": pending,
                  "parse_failures": failures, "alignment_stopped": state["alignment"]["stopped"]}
        if graph_path.exists():
            graph = read_json(graph_path)
            report.update(validate_graph(graph))
            if graph["diagnostics"].get("fingerprint") != state["fingerprint"]:
                report["errors"].append("Stale graph fingerprint")
        else:
            report["warnings"].append("Graph has not been built")
        if args.require_complete and (pending or failures or not state["alignment"]["stopped"] or not graph_path.exists()):
            report["errors"].append("Workflow incomplete")
        report["valid"] = not report["errors"]
        emit(report)
        return 0 if report["valid"] else 2
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.exit(cli())
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        emit({"ok": False, "error": str(exc), "error_type": type(exc).__name__})
        sys.exit(2)
