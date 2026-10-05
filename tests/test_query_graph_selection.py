import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import interactive_kg


class QueryGraphSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='graph_selection_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fallback = self.root / 'original-native'
        shutil.copytree(ROOT / 'examples/prebuilt/work', self.fallback)

    def graph(self, name, stamp, backend='native'):
        work = self.root / name
        shutil.copytree(self.fallback, work)
        (work / 'state.json').write_text(json.dumps({'config': {'parser_backend': backend}}), encoding='utf-8')
        os.utime(work / '04_knowledge_graph.json', (stamp, stamp))
        return work

    def select(self, backend='native'):
        return interactive_kg.select_query_graph(self.root, self.fallback, parser_backend=backend)

    def test_latest_complete_matching_backend_wins_over_other_backend(self):
        self.graph('older/weird/workdir', 100)
        latest = self.graph('any-name/output', 200)
        self.graph('newer-markitdown/output', 300, 'markitdown')
        selected = self.select()
        self.assertEqual(selected['work_dir'], latest)
        self.assertEqual(selected['source'], 'latest')

    def test_incomplete_and_archived_newer_graphs_do_not_replace_valid_graph(self):
        valid = self.graph('complete', 100)
        broken = self.graph('partial', 200)
        (broken / '00_document_units.json').unlink()
        self.graph('run/archive/checkpoint', 300)
        self.assertEqual(self.select()['work_dir'], valid)

    def test_mismatched_fingerprints_are_skipped(self):
        bad = self.graph('bad', 200)
        parsed_path = bad / '00_document_units.json'
        parsed = json.loads(parsed_path.read_text(encoding='utf-8-sig'))
        parsed['fingerprint'] = 'different-run'
        parsed_path.write_text(json.dumps(parsed), encoding='utf-8')
        self.assertEqual(self.select()['work_dir'], self.fallback)

    def test_no_new_graph_uses_original_native_fallback(self):
        selected = self.select('markitdown')
        self.assertEqual(selected['work_dir'], self.fallback)
        self.assertEqual(selected['source'], 'fallback')
        self.assertEqual(selected['backend'], 'native')

    def test_missing_fallback_does_not_create_work_or_start_build(self):
        shutil.rmtree(self.fallback)
        with self.assertRaisesRegex(FileNotFoundError, '图谱'):
            self.select()
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
