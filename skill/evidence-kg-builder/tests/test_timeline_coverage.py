import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lean_graphrag import LeanGraphRAG


class TimelineCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        nodes = [{'id': nid, 'name': name, 'type': typ, 'aliases': [name]}
                 for nid, name, typ in [
                     ('p', 'Atlas', 'Product'), ('other', 'Beta', 'Product'), ('actor', '负责人', 'Actor'),
                     ('price', '策略调整', 'Event'), ('bug', '兼容故障', 'Event'),
                     ('repair', '恢复发布', 'Event'), ('prior', '上季实验', 'Event'),
                     ('unrelated', 'Beta策略调整', 'Event')]]
        facts, edges = [], []
        def fact(subject, pred, value=None, obj=None, qualifiers=None):
            fid = 'f' + str(len(facts))
            f = {'fact_id': fid, 'subject': subject, 'predicate': pred,
                 'qualifiers': qualifiers or {}, 'evidence_ids': ['ev']}
            f.update({'object': obj} if obj else {'value': value})
            facts.append(f)
            if obj:
                edges.append({'id': fid, 'source': subject, 'target': obj,
                              'predicate': pred, 'fact_ids': [fid]})
        for eid, date in [('price', '2042-04-08'), ('bug', '2042-05-06'),
                          ('repair', '2042-05-20'), ('prior', '2042-03-15'), ('unrelated', '2042-04-01')]:
            fact(eid, 'event_time', date)
        fact('price', 'affects', obj='p')
        fact('price', 'attribute', '开放→付费', qualifiers={'attribute': '策略变化'})
        fact('bug', 'affects', obj='p')
        fact('repair', 'resolves', obj='bug')
        fact('prior', 'affects', obj='p')
        fact('price', 'has_participant', obj='actor')
        fact('unrelated', 'has_participant', obj='actor')
        fact('unrelated', 'affects', obj='other')
        parsed = {'documents': [{'document_id': 'd', 'path': 'ops.pptx', 'format': 'pptx'}],
                  'units': [{'unit_id': 'u', 'document_id': 'd', 'content_md': 'Atlas事件记录',
                             'locator': {'slide': 3}, 'structured': {}}]}
        graph = {'nodes': nodes, 'edges': edges, 'facts': facts, 'evidence': [
            {'evidence_id': 'ev', 'unit_id': 'u', 'document_id': 'd', 'source': 'ops.pptx',
             'locator': {'slide': 3}, 'quote': ''}]}
        for filename, data in [('00_document_units.json', parsed), ('04_knowledge_graph.json', graph)]:
            (self.work / filename).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        self.question = '2042年第二季度，按时间顺序列出Atlas收入下降相关的全部变更事件，说明因果关系。'

    def test_event_coverage_keeps_dates_and_changes_even_with_small_top_k(self):
        result = LeanGraphRAG(self.work, top_facts=1, top_paths=1, top_units=1).retrieve(self.question)
        self.assertEqual([hit['event']['name'] for hit in result.get('timeline_hits', [])],
                         ['策略调整', '兼容故障', '恢复发布'])
        self.assertIn('2042-04-08', result['context'])
        self.assertIn('开放→付费', result['context'])
        self.assertIn('ops.pptx', result['context'])
        self.assertIn('2042-05-20', result['context'])
        self.assertNotIn('Beta策略调整', result['context'])
        self.assertEqual(result['stats']['timeline_context_events_omitted'], 0)

    def test_tight_budget_reports_omissions_and_keeps_event_json_atomic(self):
        result = LeanGraphRAG(self.work, context_chars=1400).retrieve(self.question)
        self.assertLessEqual(len(result['context']), 1400)
        blocks = [json.loads(line.split(' ', 1)[1]) for line in result['context'].splitlines()
                  if line.startswith('TIMELINE_EVENT ')]
        self.assertEqual(result['stats']['timeline_context_events'], len(blocks))
        self.assertGreater(result['stats']['timeline_context_events_omitted'], 0)
        self.assertIn('TIMELINE_COVERAGE ', result['context'])


if __name__ == '__main__':
    unittest.main()
