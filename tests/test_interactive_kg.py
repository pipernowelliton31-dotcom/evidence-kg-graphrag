import copy
import json
import sys
import tempfile
import unittest
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from interactive_kg import InteractiveKGSession, notebook_runtime


class InteractiveKGTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="interactive_kg_test_")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        materials = self.root / "materials"
        materials.mkdir()
        (materials / "business.txt").write_text(
            "# Example product\n\nExampleProduct 使用 ExampleTool。2026年第二季度收入为100万元，"
            "续费率为80%，价格为每月20元。4月上线了新版本，5月调整了定价。"
            "运营团队记录用户反馈，并通过销售记录核对收入变化。\n" * 5, encoding="utf-8")
        (materials / "分析问题集.txt").write_text("测试题不能构图", encoding="utf-8")
        (materials / "~$lock.docx").write_bytes(b"not a document")
        self.messages = []
        self.session = InteractiveKGSession(ROOT / "evidence_kg_openrouter_debug.ipynb", {
            "MATERIALS_ROOT": materials, "RUN_ROOT": self.root / "run", "WORK_DIR": self.root / "run/work",
            "MODEL_OUTPUT_DIR": self.root / "run/models", "MANIFEST_PATH": self.root / "run/inputs.json",
            "OPENROUTER_API_KEY": "test-key", "EXTRACT_CONCURRENCY": 2, "ALIGN_CONCURRENCY": 2,
        }, progress=self.messages.append)
        self.cli_calls = []
        actual_cli = self.session.runtime["run_cli"]

        def cli(*args, **kwargs):
            self.cli_calls.append(args[0])
            return actual_cli(*args, **kwargs)

        self.session.runtime["run_cli"] = cli
        self.batch_calls = []

        def batch(stage, batch, fingerprint, round_no=None):
            self.batch_calls.append(stage)
            if stage == "extract":
                tasks = [{"task_id": task["task_id"], "mentions": [
                    {"local_id": "p1", "name": "ExampleProduct", "type": "Product"},
                    {"local_id": "t1", "name": "ExampleTool", "type": "AITool"}],
                    "relations": [{"subject": "p1", "predicate": "uses", "object": "t1"}],
                    "assertions": [{"subject": "p1", "predicate": "attribute",
                                    "qualifiers": {"attribute": "price"}, "value": 20}],
                } for task in batch["tasks"]]
            else:
                tasks = [{"task_id": task["task_id"], "decision": "NEW_ENTITY"} for task in batch["tasks"]]
            return {"response": {"fingerprint": fingerprint, "round": round_no, "tasks": tasks},
                    "log": {"elapsed_s": 0.01, "total_tokens": 10}}

        self.session.runtime["call_openrouter_batch"] = batch

        def answer(question, retrieval):
            self.assertIn(question, retrieval["context"])
            return "测试答案：每月20元。", {"total_tokens": 5}, 0.01

        self.session.runtime["call_final_answer"] = answer

    def test_cold_start_builds_then_reuses_graph_for_next_question(self):
        result = self.session.ask("ExampleProduct 的价格是多少？")
        self.assertIn("20元", result["answer"])
        self.assertIn("extract", self.batch_calls)
        for stage in ("parse", "prepare", "build"):
            self.assertIn(stage, self.cli_calls)
        self.assertTrue(any("[Alignment" in message for message in self.messages))
        state = self.session._read_state()
        question_ids = {d["document_id"] for d in state["documents"] if d["role"] == "questions"}
        self.assertTrue(question_ids)
        self.assertFalse(any(u["document_id"] in question_ids for u in state["units"]))
        self.assertFalse(any(d["path"].startswith("~$") for d in state["documents"]))
        self.cli_calls.clear()
        self.batch_calls.clear()
        self.session.ask("ExampleProduct 使用什么工具？")
        self.assertEqual(self.cli_calls, ["validate"])
        self.assertEqual(self.batch_calls, [])
        self.assertEqual(len(self.session.history), 2)

    def test_missing_graph_resumes_completed_checkpoint_without_model_reextraction(self):
        self.session.ask("ExampleProduct 的价格是多少？")
        before = copy.deepcopy(self.session._read_state()["extractions"])
        (Path(self.session.runtime["WORK_DIR"]) / "04_knowledge_graph.json").unlink()
        self.cli_calls.clear()
        self.batch_calls.clear()
        self.session.ask("ExampleProduct 使用什么工具？")
        self.assertIn("parse", self.cli_calls)
        self.assertIn("build", self.cli_calls)
        self.assertNotIn("prepare", self.cli_calls)
        self.assertEqual(self.batch_calls, [])
        self.assertEqual(before, self.session._read_state()["extractions"])
        self.assertTrue(any("cached=True" in message for message in self.messages))

    def test_model_failure_keeps_checkpoint_and_does_not_build_partial_graph(self):
        def fail(*args):
            raise RuntimeError("test model failure")
        self.session.runtime["call_openrouter_batch"] = fail
        with self.assertRaisesRegex(RuntimeError, "成功结果已保存"):
            self.session.ask("ExampleProduct 的价格是多少？")
        work = Path(self.session.runtime["WORK_DIR"])
        self.assertTrue((work / "state.json").is_file())
        self.assertFalse((work / "04_knowledge_graph.json").exists())

    def test_empty_question_and_missing_key_do_not_start_build(self):
        with self.assertRaisesRegex(ValueError, "请先输入问题"):
            self.session.ask(" ")
        self.session.runtime["OPENROUTER_API_KEY"] = ""
        with self.assertRaisesRegex(ValueError, "API Key"):
            self.session.ask("价格是多少？")
        self.assertEqual(self.cli_calls, [])
        self.assertFalse(Path(self.session.runtime["WORK_DIR"]).exists())

    def test_model_helpers_work_with_missing_optional_config_limits(self):
        ns = self.session.runtime
        Path(ns['MODEL_OUTPUT_DIR']).mkdir(parents=True)
        response = Mock()
        response.json.return_value = {'choices': [{'message': {'content': '{"tasks":[{"task_id":"u1"}]}'}}],
                                      'usage': {'total_tokens': 1}}
        with patch.object(ns['requests'], 'post', return_value=response) as post:
            # Load the real helpers; setUp substitutes network-free stage functions.
            real = notebook_runtime(ROOT / 'evidence_kg_openrouter_debug.ipynb', ns)
            real['call_openrouter_batch']('extract', {'batch_index': 0, 'tasks': [{'task_id': 'u1'}]}, 'fp')
            self.assertEqual(post.call_args.kwargs['json']['max_tokens'], 10000)
            real['call_openrouter_batch']('align', {'batch_index': 0, 'tasks': [{'task_id': 'u1'}]}, 'fp', 1)
            self.assertEqual(post.call_args.kwargs['json']['max_tokens'], 3000)
            response.json.return_value = {'choices': [{'message': {'content': 'Answer'}}], 'usage': {}}
            real['call_final_answer']('question', {'context': 'Source context'})
            self.assertEqual(post.call_args.kwargs['json']['max_tokens'], 4096)
            self.assertEqual(post.call_args.kwargs['timeout'], (30, 300))

    def test_explicit_graph_reuses_snapshot_without_state_validation_or_build(self):
        work = self.root / 'existing'
        shutil.copytree(ROOT / 'examples/prebuilt/work', work)
        (work / 'state.json').write_text('{"engine_signature":"older_engine"}', encoding='utf-8')
        before = {p.name: p.read_bytes() for p in work.iterdir() if p.is_file()}
        session = InteractiveKGSession(ROOT / 'evidence_kg_openrouter_debug.ipynb',
                                       {'OPENROUTER_API_KEY': 'test-key'},
                                       progress=self.messages.append, graph_work_dir=work)
        session.runtime['run_cli'] = Mock(side_effect=AssertionError('Must not run pipeline'))
        session.runtime['call_final_answer'] = Mock(return_value=('Answer', {}, 0.01))
        result = session.ask('What is in the existing knowledge graph?')
        self.assertEqual(result['answer'], 'Answer')
        session.runtime['run_cli'].assert_not_called()
        self.assertEqual(before, {p.name: p.read_bytes() for p in work.iterdir() if p.is_file()})

    def test_explicit_missing_graph_never_starts_build(self):
        work = self.root / 'not-built'
        session = InteractiveKGSession(ROOT / 'evidence_kg_openrouter_debug.ipynb',
                                       {'OPENROUTER_API_KEY': 'test-key'}, graph_work_dir=work)
        session.runtime['run_cli'] = Mock(side_effect=AssertionError('Must not run pipeline'))
        session.runtime['call_final_answer'] = Mock(side_effect=AssertionError('Must not call model'))
        with self.assertRaisesRegex(FileNotFoundError, '04_knowledge_graph.json'):
            session.ask('ExampleProduct 的价格是多少？')
        self.assertFalse(work.exists())
        session.runtime['run_cli'].assert_not_called()
        session.runtime['call_final_answer'].assert_not_called()


if __name__ == "__main__":
    unittest.main()
