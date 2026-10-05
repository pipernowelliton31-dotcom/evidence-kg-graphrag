"""Interactive notebook entry point for the existing file-based KG Skill."""
from __future__ import annotations

import ast
import base64
import importlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

SUPPORTED = {".pdf", ".docx", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg", ".webp", ".md", ".txt"}
HELPERS = {"run_cli", "_extract_json_object", "_data_url", "_batch_content",
           "call_openrouter_batch", "call_final_answer"}
MODEL_DEFAULTS = {
    "EXTRACT_MAX_TOKENS": 10000, "ALIGN_MAX_TOKENS": 3000, "QA_MAX_TOKENS": 4096,
    "HTTP_TIMEOUT": 300, "MAX_NETWORK_RETRIES": 2,
    "RAW_PREVIEW_CHARS": 5000, "CONTEXT_PREVIEW_CHARS": 8000,
}


def notebook_runtime(notebook_path, overrides=None):
    """Load configuration, prompts and function definitions without running demo cells."""
    import requests

    notebook_path = Path(notebook_path).resolve()
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    code = ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]
    namespace = {**MODEL_DEFAULTS, "Path": Path, "json": json, "sys": sys, "os": os, "subprocess": subprocess,
                 "time": time, "requests": requests, "base64": base64, "mimetypes": mimetypes,
                 "re": re, "shlex": importlib.import_module("shlex")}
    config = ast.parse(next(c for c in code if "SKILL_ZIP =" in c))
    assignments = [n for n in config.body if isinstance(n, ast.Assign)]

    class AnchorPaths(ast.NodeTransformer):
        def visit_Call(self, node):
            self.generic_visit(node)
            if (isinstance(node.func, ast.Name) and node.func.id == "Path" and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
                    and not Path(node.args[0].value).is_absolute()):
                node.args[0] = ast.copy_location(
                    ast.Constant(str(notebook_path.parent / node.args[0].value)), node.args[0])
            return node

    anchored_config = AnchorPaths().visit(ast.Module(body=assignments, type_ignores=[]))
    exec(compile(ast.fix_missing_locations(anchored_config), str(notebook_path), "exec"), namespace)
    override_names = {t.id for n in assignments for t in n.targets if isinstance(t, ast.Name)}
    override_names |= MODEL_DEFAULTS.keys()
    override_names |= {"SKILL_DIR", "SCRIPTS_DIR", "OPENROUTER_API_KEY", "call_logs", "ROLE_OVERRIDES"}
    namespace.update({k: v for k, v in (overrides or {}).items() if k in override_names})
    namespace.setdefault("ROLE_OVERRIDES", {})
    namespace["ROLE_OVERRIDES"] = dict(namespace["ROLE_OVERRIDES"])
    namespace["ROLE_OVERRIDES"].setdefault("测试集A_分析问题集.docx", "questions")
    namespace.setdefault("call_logs", [])
    namespace["OPENROUTER_API_KEY"] = namespace.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")

    source = Path(namespace.get("SKILL_DIR", namespace["SKILL_SRC"]))
    if not source.exists() and Path(namespace["SKILL_ZIP"]).is_file():
        source = Path(namespace["SKILL_UNPACK_DIR"])
        source.mkdir(parents=True, exist_ok=True)
        shutil.unpack_archive(str(namespace["SKILL_ZIP"]), str(source))
    hits = [source] if (source / "SKILL.md").is_file() else [
        p for p in source.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()
    ] if source.is_dir() else []
    if len(hits) != 1:
        raise FileNotFoundError(f"找不到唯一的 Skill 目录，请检查 skill/ 或 skill.zip：{source}")
    namespace["SKILL_DIR"] = hits[0].resolve()
    namespace["SCRIPTS_DIR"] = namespace["SKILL_DIR"] / "scripts"
    namespace["PIPELINE"] = namespace["SCRIPTS_DIR"] / "kg_pipeline.py"

    definitions = []
    for source_code in code:
        for node in ast.parse(source_code).body:
            if isinstance(node, ast.FunctionDef) and node.name in HELPERS:
                definitions.append(node)
            elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in {"EXTRACTION_SYSTEM", "ALIGNMENT_SYSTEM"} for t in node.targets
            ):
                definitions.append(node)
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(notebook_path), "exec"), namespace)
    missing = HELPERS - namespace.keys()
    if missing:
        raise RuntimeError(f"Notebook 缺少必要函数：{sorted(missing)}")
    script_path = str(namespace["SCRIPTS_DIR"])
    if script_path not in sys.path:
        sys.path.insert(0, script_path)
    rag_module = importlib.reload(importlib.import_module("lean_graphrag"))
    namespace["ANSWER_PROMPT"] = rag_module.ANSWER_PROMPT
    namespace["LeanGraphRAG"] = rag_module.LeanGraphRAG
    return namespace


def query_runtime(notebook_path, overrides=None):
    """Prepare a query cell without executing installation or graph-building cells."""
    settings = dict(overrides or {})
    settings.pop('RAG_WORK_DIR', None)  # A previous query's resolved path must not pin selection.
    settings.setdefault("call_logs", [])
    previous_chat = settings.get("KG_CHAT")
    if not settings.get("OPENROUTER_API_KEY") and previous_chat is not None:
        settings["OPENROUTER_API_KEY"] = previous_chat.runtime.get("OPENROUTER_API_KEY", "")
    namespace = notebook_runtime(notebook_path, settings)
    selected = select_query_graph(namespace['RAG_SEARCH_ROOT'], namespace['RAG_FALLBACK_DIR'],
                                  parser_backend=namespace.get('PARSER_BACKEND', 'native'))
    namespace['RAG_WORK_DIR'] = selected['work_dir']
    namespace['RAG_GRAPH_SELECTION'] = selected
    return namespace


def _validate_query_graph(work):
    """Validate query artifacts without executing or requiring a current build engine."""
    work = Path(work).resolve()
    for name in ('04_knowledge_graph.json', '00_document_units.json'):
        if not (work / name).is_file():
            raise FileNotFoundError(f'已有图谱缺少 {name}：{work}；本入口不会自动重建。')
    graph = json.loads((work / '04_knowledge_graph.json').read_text(encoding='utf-8-sig'))
    parsed = json.loads((work / '00_document_units.json').read_text(encoding='utf-8-sig'))
    fingerprint = graph.get('diagnostics', {}).get('fingerprint')
    if not graph.get('diagnostics', {}).get('workflow_complete'):
        raise RuntimeError('图谱未完成构建')
    if not fingerprint or parsed.get('fingerprint') != fingerprint:
        raise RuntimeError('图谱与解析单元的 fingerprint 不一致')
    facts_path = work / '03_canonical_facts.json'
    if facts_path.is_file():
        facts = json.loads(facts_path.read_text(encoding='utf-8-sig'))
        if facts.get('fingerprint') != fingerprint:
            raise RuntimeError('图谱与事实库的 fingerprint 不一致')
    excluded = {d['document_id'] for d in parsed['documents'] if d.get('role') != 'corpus'}
    if any(u['document_id'] in excluded for u in parsed['units']):
        raise RuntimeError('解析单元包含问题集或参考材料')
    try:
        from kg_core import validate_graph
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent / 'skill/evidence-kg-builder/scripts'))
        from kg_core import validate_graph
    report = validate_graph(graph)
    if not report['valid']:
        raise RuntimeError(f"已有图谱结构校验失败：{report['errors']}")
    state_path = work / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8-sig')) if state_path.is_file() else {}
    if state.get('fingerprint') and state['fingerprint'] != fingerprint:
        raise RuntimeError('图谱与构图 checkpoint 的 fingerprint 不一致')
    return {'backend': state.get('config', {}).get('parser_backend', 'native'),
            'fingerprint': fingerprint, 'nodes': len(graph.get('nodes', [])),
            'facts': len(graph.get('facts', []))}


def select_query_graph(search_root, fallback_dir, *, parser_backend='native'):
    """Choose the newest complete graph for the backend, then the original native snapshot."""
    search_root, fallback = Path(search_root).resolve(), Path(fallback_dir).resolve()
    excluded_dirs = {'archive', '.git', '.venv', 'venv', '__pycache__', 'node_modules'}
    candidates = []
    for directory, folders, files in os.walk(search_root, followlinks=False):
        folders[:] = [name for name in folders if name.casefold() not in excluded_dirs]
        work = Path(directory).resolve()
        if work == fallback:
            folders[:] = []
            continue
        if '04_knowledge_graph.json' in files:
            candidates.append(work)
    candidates.sort(key=lambda work: (-(work / '04_knowledge_graph.json').stat().st_mtime_ns, str(work)))
    skipped = []
    for work in candidates:
        try:
            metadata = _validate_query_graph(work)
            if metadata['backend'] != parser_backend:
                continue
            return {'work_dir': work, 'source': 'latest', **metadata, 'skipped': skipped}
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            skipped.append({'work_dir': str(work), 'reason': str(exc)})
    try:
        metadata = _validate_query_graph(fallback)
        if metadata['backend'] != 'native':
            raise RuntimeError('fallback 必须是之前的 native 图谱')
        return {'work_dir': fallback, 'source': 'fallback', **metadata, 'skipped': skipped}
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        raise FileNotFoundError(f'没有可用的完整图谱，native fallback 也不可用：{fallback}；{exc}') from exc


class InteractiveKGSession:
    def __init__(self, notebook_path, overrides=None, progress=None, *, graph_work_dir=None):
        self.runtime = notebook_runtime(notebook_path, overrides)
        self.graph_work_dir = Path(graph_work_dir).resolve() if graph_work_dir is not None else None
        if self.graph_work_dir is not None:
            self.runtime["WORK_DIR"] = self.graph_work_dir
        self.progress = progress or (lambda message: print(message, flush=True))
        self.history = []
        self.last_result = None

    def _cli(self, *args, **kwargs):
        return self.runtime["run_cli"](*args, **kwargs)

    def _read_state(self):
        return json.loads((Path(self.runtime["WORK_DIR"]) / "state.json").read_text(encoding="utf-8"))

    def _manifest(self):
        root = Path(self.runtime["MATERIALS_ROOT"]).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"材料目录不存在：{root}")
        entries = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name.startswith("~$") or path.suffix.lower() not in SUPPORTED:
                continue
            relative = path.relative_to(root).as_posix()
            default_role = "questions" if "问题集" in path.stem else "corpus"
            role = self.runtime["ROLE_OVERRIDES"].get(relative, default_role)
            if role not in {"corpus", "questions", "reference"}:
                raise ValueError(f"非法材料角色：{relative}: {role}")
            if "问题集" in path.stem and role == "corpus":
                raise ValueError(f"问题集不能标为 corpus：{relative}")
            entries.append({"path": relative, "role": role})
        if not any(e["role"] == "corpus" for e in entries):
            raise ValueError("没有可用于构图的 corpus 材料")
        manifest = {"root": str(root), "files": entries}
        target = Path(self.runtime["MANIFEST_PATH"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        self.progress(f"[输入] 业务语料={sum(e['role'] == 'corpus' for e in entries)}，"
                      f"排除的问题集/参考资料={sum(e['role'] != 'corpus' for e in entries)}")

    def _graph_ready(self):
        work = Path(self.runtime["WORK_DIR"])
        if not all((work / name).is_file() for name in (
            "state.json", "04_knowledge_graph.json", "00_document_units.json"
        )):
            return False
        state = self._read_state()
        for document in state["documents"]:
            path = document["path"]
            expected = self.runtime["ROLE_OVERRIDES"].get(path)
            if (expected is not None and document["role"] != expected) or (
                "问题集" in Path(path).stem and document["role"] == "corpus"
            ):
                self.progress(f"[检查] 材料角色已变化，需要重建：{path}")
                return False
        parsed = json.loads((work / "00_document_units.json").read_text(encoding="utf-8"))
        if parsed.get("fingerprint") != state["fingerprint"]:
            return False
        report = self._cli("validate", "--work", work, "--require-complete", check=False)
        return report.get("valid") is True

    def _run_stage(self, stage):
        ns = self.runtime
        work, run_root, model_root = map(Path, (ns["WORK_DIR"], ns["RUN_ROOT"], ns["MODEL_OUTPUT_DIR"]))
        label = "Extraction" if stage == "extract" else "Alignment"
        concurrency = ns["EXTRACT_CONCURRENCY"] if stage == "extract" else ns["ALIGN_CONCURRENCY"]
        limit = ns["EXTRACT_BATCH_SIZE"] if stage == "extract" else ns["ALIGN_BATCH_SIZE"]
        run_id = uuid.uuid4().hex[:12]
        previous_position = None
        for wave in range(1, 1001):
            task_file = run_root / f"interactive_{run_id}_{stage}_wave{wave:03d}.json"
            args = ["tasks", "--stage", stage, "--work", work, "--limit", limit,
                    "--batch-count", concurrency, "--output", task_file]
            if stage == "extract":
                args.extend(["--char-budget", ns["EXTRACT_CHAR_BUDGET"]])
            self._cli(*args)
            export = json.loads(task_file.read_text(encoding="utf-8"))
            batches = [b for b in export.get("batches", []) if b.get("tasks")]
            pending, round_no = export.get("pending_count", 0), export.get("round")
            position = (round_no, pending)
            self.progress(f"[{label} wave {wave}] round={round_no if round_no is not None else '-'} "
                          f"pending={pending} batches={len(batches)} tasks={sum(len(b['tasks']) for b in batches)}")
            if not batches:
                if (stage == "extract" and pending == 0) or (stage == "align" and export.get("stopped")):
                    self.progress(f"[{label}] 已完成。")
                    return
                raise RuntimeError(f"{label} 没有可执行任务但尚未完成，请检查 checkpoint")
            if position == previous_position:
                raise RuntimeError(f"{label} 未推进，已保留 checkpoint；请检查模型的 task_id/decision")
            previous_position = position
            failures = []
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=min(concurrency, len(batches))) as pool:
                futures = {pool.submit(ns["call_openrouter_batch"], stage, batch,
                                       export["fingerprint"], round_no): batch for batch in batches}
                remaining = set(futures)
                while remaining:
                    done, remaining = wait(remaining, timeout=10, return_when=FIRST_COMPLETED)
                    if not done:
                        self.progress(f"[{label}] 等待模型，已耗时 {time.perf_counter() - started:.0f}s，"
                                      f"剩余 {len(remaining)} 个批次…")
                    for future in done:
                        batch = futures[future]
                        index = batch["batch_index"]
                        try:
                            result = future.result()
                            log = result["log"]
                            self.progress(f"[{stage}] batch={index} tasks={len(batch['tasks'])} "
                                          f"time={log['elapsed_s']:.1f}s tokens={log.get('total_tokens')}")
                            target = model_root / f"interactive_{run_id}_{stage}_wave{wave:03d}_batch{index:02d}.json"
                            target.write_text(json.dumps(result["response"], ensure_ascii=False, indent=2), encoding="utf-8")
                            report = self._cli("accept", "--stage", stage, "--work", work, "--response", target)
                            detail = (f"pending={report.get('pending_extraction')}" if stage == "extract"
                                      else f"round_now={report.get('round')}")
                            self.progress(f"  accept batch={index} {detail}")
                        except Exception as exc:
                            failures.append(f"batch={index}: {exc}")
                            self.progress(f"[{label}] batch={index} 失败：{exc}")
            if failures:
                raise RuntimeError("部分批次失败，成功结果已保存；可再次提问继续。\n" + "\n".join(failures))
        raise RuntimeError(f"{label} 超过轮次上限，checkpoint 已保留")

    def ensure_graph(self):
        ns = self.runtime
        self.progress("[检查] 检查已有知识图谱是否完整、可用…")
        if self.graph_work_dir is not None:
            self._check_existing_graph()
            self.progress(f"[检查] 使用已有图谱：{self.graph_work_dir}；跳过全部构图阶段。")
            return
        if self._graph_ready():
            self.progress("[检查] 已有完整知识图谱，跳过 Parse / Extraction / Alignment / Build。")
            return
        work = Path(ns["WORK_DIR"])
        self.progress("[构图] 未发现可用的完整图谱，开始构图；匹配的 checkpoint 会继续复用。")
        for name in ("RUN_ROOT", "WORK_DIR", "MODEL_OUTPUT_DIR"):
            Path(ns[name]).mkdir(parents=True, exist_ok=True)
        self._manifest()
        self.progress("[Parse] 正在本地解析材料…")
        parsed = self._cli("parse", "--manifest", ns["MANIFEST_PATH"], "--work", work)
        for document in parsed.get("documents", []):
            self.progress(f"  {document['status']}: {document['path']}")
        self.progress(f"[Parse] unit_count={parsed.get('unit_count')} cached={parsed.get('cached')}")
        if not parsed.get("ok"):
            raise RuntimeError("部分材料解析失败，请检查上方解析结果")
        if not self._read_state().get("selection"):
            self.progress("[Prepare] 进行本地结构化预提取，筛选需要模型处理的内容…")
            prepared = self._cli("prepare", "--work", work)
            self.progress(f"[Prepare] 自动处理={prepared.get('reviewed_without_llm')}，"
                          f"待模型抽取={prepared.get('pending_llm_units')}")
        else:
            self.progress("[Prepare] 已有抽取计划，继续复用。")
        self._run_stage("extract")
        self._run_stage("align")
        self.progress("[Build] 生成最终知识图谱…")
        built = self._cli("build", "--work", work)
        self.progress(f"[Build] {built.get('counts', {})}")
        report = self._cli("validate", "--work", work, "--require-complete")
        if report.get("valid") is not True:
            raise RuntimeError(f"图谱未通过完整性检查：{report.get('errors')}")
        self.progress("[构图] 已完成并通过完整性检查。")

    def _check_existing_graph(self):
        """Validate query artifacts without requiring a current build checkpoint."""
        _validate_query_graph(self.graph_work_dir)

    def ask(self, question, api_key=None):
        question = str(question or "").strip()
        if not question:
            raise ValueError("请先输入问题")
        if api_key is not None and api_key.strip():
            self.runtime["OPENROUTER_API_KEY"] = api_key.strip()
        if not self.runtime.get("OPENROUTER_API_KEY"):
            raise ValueError("请在密码框输入 OpenRouter API Key，或先设置 OPENROUTER_API_KEY")
        started = time.perf_counter()
        self.ensure_graph()
        self.progress("[GraphRAG] 正在召回实体、结构化记录、事实、图路径和原文证据…")
        rag = self.runtime["LeanGraphRAG"](self.runtime["WORK_DIR"], max_hops=3,
                                           beam_width=20, context_chars=18_000)
        retrieved = rag.retrieve(question)
        stats = retrieved['stats']
        self.progress(f"[GraphRAG] mode={stats.get('retrieval_mode', 'ranked')} "
                      f"structured={stats.get('structured', 0)} "
                      f"scope={stats.get('structured_scope_matches', 0)} "
                      f"augmentation={stats.get('structured_selected_for_augmentation', 0)} "
                      f"table_units={stats.get('table_units', 0)} table_columns={stats.get('table_columns', 0)} "
                      f"table_rows={stats.get('table_context_rows', 0)}/{stats.get('table_rows', 0)} "
                      f"facts={len(retrieved.get('fact_hits', []))} "
                      f"paths={len(retrieved.get('paths', []))} raw_units={len(retrieved.get('raw_units', []))} "
                      f"context_chars={len(retrieved['context'])}")
        self.progress(f"[回答] 正在调用 {self.runtime['MODEL']}，依据召回证据生成答案…")
        answer_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.runtime["call_final_answer"], question, retrieved)
            while not wait([future], timeout=10).done:
                self.progress(f"[回答] 模型正在生成答案，已等待 {time.perf_counter() - answer_started:.0f}s…")
            answer, usage, elapsed = future.result()
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("模型返回了空答案，请再次提问")
        self.progress(f"[回答] 完成，模型耗时={elapsed:.1f}s tokens={usage.get('total_tokens')} "
                      f"总耗时={time.perf_counter() - started:.1f}s")
        result = {"question": question, "answer": answer, "usage": usage, "retrieval": retrieved}
        self.last_result = result
        self.history.append(result)
        return result


def display_chat(session):
    """Display widgets, or a terminal-style input loop if widgets are unavailable."""
    from IPython.display import Markdown, display
    try:
        import ipywidgets as widgets
    except ImportError:
        from getpass import getpass
        print("当前环境没有 ipywidgets，使用输入式问答；输入 /exit 结束。", flush=True)
        if not session.runtime.get("OPENROUTER_API_KEY"):
            session.runtime["OPENROUTER_API_KEY"] = getpass("OpenRouter API Key: ").strip()
        while True:
            question = input("请输入问题（/exit 结束）：").strip()
            if question.casefold() in {"/exit", "exit", "quit", "退出"}:
                break
            if question:
                try:
                    display(Markdown(session.ask(question)["answer"]))
                except Exception as exc:
                    print(f"执行失败：{exc}", flush=True)
        return None

    placeholder = ("在这里输入问题；直接查询已有图谱，不会重新构图。" if session.graph_work_dir is not None
                   else "在这里输入问题；首次提问会按需构图。")
    question = widgets.Textarea(placeholder=placeholder,
                                layout=widgets.Layout(width="100%", height="120px"))
    key = widgets.Password(description="API Key", placeholder="已有内核 Key 时可留空",
                           layout=widgets.Layout(width="100%"))
    button = widgets.Button(description="提问", button_style="primary", icon="comment")
    output = widgets.Output()

    def submit(_):
        if not question.value.strip():
            with output:
                print("请先输入问题。")
            return
        button.disabled = question.disabled = key.disabled = True
        try:
            with output:
                print("\n问题：" + question.value.strip(), flush=True)
                try:
                    result = session.ask(question.value, key.value)
                    display(Markdown(result["answer"]))
                except Exception as exc:
                    print(f"执行失败：{exc}", flush=True)
        finally:
            key.value = ""
            button.disabled = question.disabled = key.disabled = False

    button.on_click(submit)
    ui = widgets.VBox([widgets.HTML("<b>输入问题后点击“提问”，进度和答案会显示在下方。</b>"),
                       question, key, button, output])
    display(ui)
    return ui
