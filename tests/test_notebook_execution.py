"""Exercise the actual notebook cells without network requests or production writes."""
import ast
import builtins
import contextlib
import io
import json
import os
import subprocess
import symtable
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd  # Import before mocking notebook subprocess calls on Windows.
import requests

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / 'evidence_kg_openrouter_debug.ipynb'


class NotebookExecutionTests(unittest.TestCase):
    def setUp(self):
        self.cells = json.loads(NOTEBOOK.read_text(encoding='utf-8'))['cells']
        self.old_cwd = Path.cwd()
        os.chdir(ROOT)
        self.addCleanup(os.chdir, self.old_cwd)
        self.temp = tempfile.TemporaryDirectory(prefix='notebook_check_')
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        self.output = io.StringIO()
        self.stdout = contextlib.redirect_stdout(self.output)
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)
        sys.path.insert(0, str(ROOT))
        self.native = ROOT / 'examples/prebuilt/work'
        self.before = {p.name: p.read_bytes() for p in self.native.iterdir() if p.is_file()}
        self.addCleanup(self.assert_graph_unchanged)
        self.display_patch = patch('IPython.display.display', lambda *args, **kwargs: None)
        self.display_patch.start()
        self.addCleanup(self.display_patch.stop)
        self.key_patch = patch('getpass.getpass', return_value='mock-only')
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.network_patch = patch('requests.post', side_effect=self.response)
        self.post = self.network_patch.start()
        self.addCleanup(self.network_patch.stop)

    def assert_graph_unchanged(self):
        self.assertEqual(self.before, {p.name: p.read_bytes() for p in self.native.iterdir() if p.is_file()})

    def code(self, number):
        marker = f'## Cell {number} '
        heading = next(i for i, c in enumerate(self.cells)
                       if c['cell_type'] == 'markdown' and ''.join(c['source']).startswith(marker))
        return ''.join(next(c for c in self.cells[heading + 1:] if c['cell_type'] == 'code')['source'])

    def execute(self, number, ns):
        exec(compile(self.code(number), f'{NOTEBOOK}:Cell{number}', 'exec'), ns)

    def response(self, *args, **kwargs):
        payload = kwargs['json']
        text = payload['messages'][1]['content']
        if isinstance(text, list):
            envelope = json.loads(text[0]['text'].split('\n', 1)[1])
            if envelope['stage'] == 'extract':
                tasks = [{'task_id': t['task_id'], 'mentions': [
                    {'local_id': 'p1', 'name': 'ExampleProduct', 'type': 'Product'}],
                    'relations': [], 'assertions': []} for t in envelope['tasks']]
            else:
                tasks = [{'task_id': t['task_id'], 'decision': 'NEW_ENTITY'} for t in envelope['tasks']]
            content = json.dumps({'tasks': tasks})
        else:
            content = 'Mock answer'
        response = Mock()
        response.json.return_value = {'choices': [{'message': {'content': content}}],
                                     'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}
        return response

    def overrides(self):
        return {'RUN_ROOT': self.run, 'WORK_DIR': self.run / 'work',
                'MODEL_OUTPUT_DIR': self.run / 'models', 'MANIFEST_PATH': self.run / 'inputs.json',
                'OPENROUTER_API_KEY': 'mock-only', 'RAG_SEARCH_ROOT': self.run,
                'RAG_FALLBACK_DIR': self.native, 'QA_MAX_TOKENS': 4096}

    def test_config_then_skill_setup_in_fresh_kernel(self):
        ns = {}
        self.execute(1, ns)
        ns.update(self.overrides())
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '', '')):
            self.execute(2, ns)
        self.assertEqual(ns['SKILL_DIR'], ROOT / 'skill/evidence-kg-builder')
        for name, value in {'EXTRACT_MAX_TOKENS': 10000, 'ALIGN_MAX_TOKENS': 3000,
                            'QA_MAX_TOKENS': 4096, 'RAW_PREVIEW_CHARS': 5000,
                            'CONTEXT_PREVIEW_CHARS': 8000, 'HTTP_TIMEOUT': 300,
                            'MAX_NETWORK_RETRIES': 2}.items():
            self.assertEqual(ns[name], value)
        self.assertEqual(ns['SKILL_SOURCE_KIND'], 'dir')
        self.assertEqual(ns['RAG_FALLBACK_DIR'], self.native)

    def test_query_runtime_selects_latest_graph_despite_stale_prebuilt_path(self):
        from interactive_kg import query_runtime
        import shutil
        newer = self.run / 'arbitrary-run-name' / 'graph'
        shutil.copytree(self.native, newer)
        (newer / 'state.json').write_text('{"config":{"parser_backend":"native"}}', encoding='utf-8')
        settings = self.overrides()
        settings['RAG_WORK_DIR'] = self.native
        runtime = query_runtime(NOTEBOOK, settings)
        self.assertEqual(runtime['RAG_WORK_DIR'], newer)

    def test_single_answer_rejects_context_from_a_different_graph(self):
        ns = self.overrides()
        self.execute(20, ns)
        import shutil
        newer = self.run / 'new-graph'
        shutil.copytree(self.native, newer)
        (newer / 'state.json').write_text('{"config":{"parser_backend":"native"}}', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'Cell 20'):
            self.execute(21, ns)
        self.post.assert_not_called()

    def test_no_global_references_missing_from_entire_notebook(self):
        known = set(dir(builtins))
        sources = [''.join(c['source']) for c in self.cells if c['cell_type'] == 'code']
        for source in sources:
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    known.add(node.id)
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    known.add(node.name)
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    known.update(a.asname or a.name.split('.')[0] for a in node.names)
        missing = []
        def scan(table):
            for symbol in table.get_symbols():
                if symbol.is_referenced() and symbol.is_global() and symbol.get_name() not in known:
                    missing.append(symbol.get_name())
            for child in table.get_children():
                scan(child)
        for source in sources:
            scan(symtable.symtable(source, str(NOTEBOOK), 'exec'))
        self.assertEqual(sorted(set(missing)), [])

    def test_retrieval_and_single_answer_without_build_cells(self):
        ns = self.overrides()
        self.execute(20, ns)
        self.assertEqual(ns['RAG_WORK_DIR'], self.native)
        self.assertEqual(len(ns['rag'].nodes), 273)
        self.assertTrue(ns['retrieval']['context'])
        self.post.assert_not_called()
        self.execute(21, ns)
        self.assertEqual(ns['answer'], 'Mock answer')
        self.assertEqual(len(ns['call_logs']), 1)
        self.assertEqual(self.post.call_args.kwargs['json']['max_tokens'], 4096)
        self.assertEqual(self.post.call_args.kwargs['timeout'], (30, 300))

    def test_concurrent_answers_then_metrics_in_fresh_kernel(self):
        ns = self.overrides()
        self.execute(22, ns)
        self.assertEqual(len(ns['multi_results']), len(ns['QUESTIONS']))
        self.assertTrue(all(r['answer'] == 'Mock answer' for r in ns['multi_results']))
        self.assertIn('mode=exhaustive structured=8 scope=8 augmentation=6', self.output.getvalue())
        self.execute(23, ns)
        metrics = json.loads((self.run / 'openrouter_metrics.json').read_text(encoding='utf-8'))
        self.assertEqual(len(metrics), len(ns['QUESTIONS']))
        self.assertEqual(ns['RAG_WORK_DIR'], self.native)

    def choice_response(self, content, finish_reason):
        response = Mock()
        response.json.return_value = {
            'choices': [{'message': {'content': content}, 'finish_reason': finish_reason}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 5, 'total_tokens': 10}}
        return response

    def qa_namespace(self):
        """Load Cell 21 without its Cell 20 prerequisite gate."""
        ns = dict(self.overrides())
        ns.update({'MODEL': 'test/model', 'QA_MAX_TOKENS': 4096, 'QA_REASONING': 'medium',
                   'MAX_NETWORK_RETRIES': 2, 'HTTP_TIMEOUT': 300,
                   'OPENROUTER_BASE_URL': 'https://example.invalid/api/v1',
                   'ANSWER_PROMPT': 'answer', 'call_logs': [], 'time': time,
                   'requests': requests, 'json': json})
        code = self.code(21)
        code = code.replace("if 'QUESTION' not in globals() or 'retrieval' not in globals():", 'if False:')
        code = code.replace("    raise RuntimeError('请先运行 Cell 20，得到同一问题的检索上下文，再运行 Cell 21。')", '    pass')
        ns['QUESTION'] = 'test'
        ns['retrieval'] = {'context': 'ctx', 'query_plan': {'intent': 'factual'}, 'stats': {}}
        exec(compile(code, 'cell21', 'exec'), ns)
        return ns

    def test_empty_model_answer_is_retried_and_then_reported(self):
        """A None content must not be handed downstream as a blank answer."""
        qa_ns = self.qa_namespace()
        responses = [self.choice_response(None, 'stop'), self.choice_response('重试后的答案', 'stop')]
        with patch('requests.post', side_effect=responses) as post:
            with patch('time.sleep'):
                answer, _usage, _elapsed = qa_ns['call_final_answer']('q', qa_ns['retrieval'])
        self.assertEqual(answer, '重试后的答案')
        self.assertEqual(post.call_count, 2)

    def test_exhausted_retries_raise_instead_of_returning_blank(self):
        qa_ns = self.qa_namespace()
        with patch('requests.post', return_value=self.choice_response('', 'length')):
            with patch('time.sleep'):
                with self.assertRaisesRegex(Exception, 'length|max_tokens'):
                    qa_ns['call_final_answer']('q', qa_ns['retrieval'])

    def test_concurrent_batch_reports_per_question_failure_without_aborting(self):
        ns = dict(self.overrides())
        original = self.post.side_effect

        def flaky(*args, **kwargs):
            text = kwargs['json']['messages'][1]['content']
            if isinstance(text, str) and text.startswith('QUESTION\nExcel'):
                return self.choice_response(None, 'stop')
            return original(*args, **kwargs)

        with patch('requests.post', side_effect=flaky):
            with patch('time.sleep'):
                exec(compile(self.code(22), 'cell22', 'exec'), ns)
        self.assertEqual(len(ns['multi_results']), len(ns['QUESTIONS']))
        failed = [r for r in ns['multi_results'] if r.get('error')]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]['index'], 5)

    def test_single_answer_without_retrieval_reports_prerequisite(self):
        with self.assertRaisesRegex(RuntimeError, 'Cell 20'):
            self.execute(21, self.overrides())
        self.post.assert_not_called()

    def test_gui_in_fresh_kernel_never_builds(self):
        ns = self.overrides()
        self.execute(24, ns)
        session = ns['KG_CHAT']
        self.assertEqual(session.graph_work_dir, self.native)
        session.runtime['run_cli'] = Mock(side_effect=AssertionError('Must not build'))
        result = session.ask('AI代码助手插件使用什么工具？')
        self.assertEqual(result['answer'], 'Mock answer')
        session.runtime['run_cli'].assert_not_called()

    def test_all_cells_in_order_with_simulated_pipeline_and_http(self):
        for backend in ('native', 'markitdown'):
            with self.subTest(backend=backend):
                self.simulate_all_cells(backend)

    def simulate_all_cells(self, backend):
        ns = {}
        task_counts = {'extract': 0, 'align': 0}
        work = self.run / backend / 'work'
        run = work.parent
        work.mkdir(parents=True)
        models = run / 'models'
        def write(path, data):
            Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        parsed = json.loads((self.native / '00_document_units.json').read_text(encoding='utf-8'))
        state = {'config': {'parser_backend': backend},
                 'extractions': {'u1': {'mentions': [{'name': 'ExampleProduct', 'type': 'Product'}]}},
                 'alignment': {'mapping': {'m1': 'e1'}, 'clusters': {'e1': ['m1']},
                               'cluster_status': {'e1': 'done'}, 'history': [], 'stopped': True, 'round': 1}}
        def command(cmd, **kwargs):
            if '-m' in cmd and 'pip' in cmd:
                return subprocess.CompletedProcess(cmd, 0, '', '')
            if 'parse_markitdown.py' in str(cmd[1]):
                stage = 'parse'
            else:
                stage = cmd[2]
            result = {}
            if stage == 'parse':
                write(work / '00_document_units.json', parsed)
                result = {'unit_count': len(parsed['units'])}
            elif stage == 'prepare':
                write(work / '00_extraction_plan.json', {'units': [
                    {'unit_id': 'u1', 'mode': 'semantic', 'priority': 1, 'reason': 'test'}]})
                write(work / 'state.json', state)
            elif stage == 'tasks':
                mode = cmd[cmd.index('--stage') + 1]
                task_counts[mode] += 1
                batches = [{'batch_index': 0, 'tasks': [{'task_id': 'u1', 'selection': {'mode': 'semantic'}}]}]
                export = {'fingerprint': parsed['fingerprint'], 'batches': batches if task_counts[mode] == 1 else [],
                          'pending_count': 1 if task_counts[mode] == 1 else 0, 'round': 1,
                          'stopped': mode == 'align' and task_counts[mode] > 1}
                write(cmd[cmd.index('--output') + 1], export)
            elif stage == 'accept':
                result = {'accepted': 1, 'pending_extraction': 0, 'reviewed_units': 1, 'round': 1}
            elif stage == 'build':
                (work / '04_knowledge_graph.json').write_bytes(self.before['04_knowledge_graph.json'])
            elif stage == 'validate':
                result = {'valid': True}
            else:
                raise AssertionError(f'Unexpected command: {stage}')
            return subprocess.CompletedProcess(cmd, 0, json.dumps(result), '')
        with patch('subprocess.run', side_effect=command):
            for cell in self.cells:
                if cell['cell_type'] != 'code':
                    continue
                source = ''.join(cell['source'])
                exec(compile(source, str(NOTEBOOK), 'exec'), ns)
                if 'SKILL_ZIP =' in source:
                    ns.update(self.overrides())
                    ns.update({'PARSER_BACKEND': backend, 'RUN_ROOT': run, 'WORK_DIR': work,
                               'MODEL_OUTPUT_DIR': models, 'MANIFEST_PATH': run / 'inputs.json'})
                    models.mkdir(exist_ok=True)
        self.assertTrue(ns['retrieval']['context'])
        self.assertEqual(ns['answer'], 'Mock answer')
        self.assertEqual(ns['RAG_WORK_DIR'], work)


if __name__ == '__main__':
    unittest.main()
