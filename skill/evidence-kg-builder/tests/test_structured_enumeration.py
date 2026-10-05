import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lean_graphrag import BM25Lite, LeanGraphRAG


class StructuredEnumerationTests(unittest.TestCase):
    @staticmethod
    def rag(entries):
        rag = LeanGraphRAG.__new__(LeanGraphRAG)
        rag.known_terms = set()
        rag.structured_entries = entries
        rag.top_structured = 24
        rag.structured_bm25 = BM25Lite([rag._tokens(e["text"]) or ["__empty__"] for e in entries])
        return rag

    def test_exhaustive_scope_is_not_truncated_by_bm25(self):
        values = [
            "例行月度结算", "客户投诉量从45增至128", "版本A→B升级后出现兼容性异常",
            "例行月度结算", "旧版本停售，由新版本替代", "风险预警发布",
            "归因分析：策略-17%，兼容性-12%", "新增用户首次突破50人",
        ]
        entries = [
            {"id": f"e{i}", "kind": "xlsx_cell", "sheet": "事件清单", "field": "备注",
             "value": value, "source": "ops.xlsx",
             "locator": {"sheet": "事件清单", "row": i, "cell": f"J{i}"},
             "text": f"ops.xlsx 事件清单 备注 {value}"}
            for i, value in enumerate(values, 1)
        ]
        rag = self.rag(entries)
        question = 'Excel"事件清单"Sheet的备注列中隐藏了6条关键线索，请找出全部6条。'
        plan = rag._plan(question)
        self.assertEqual(plan["intent"], "structured_enumeration")
        self.assertEqual(plan["retrieval_mode"], "exhaustive")
        self.assertEqual(plan["expected_count"], 6)
        self.assertEqual(plan["sheet_hints"], ["事件清单"])
        self.assertEqual(plan["column_hints"], ["备注"])
        hits = rag._structured_retrieve(question, plan)
        self.assertEqual(len(hits), 8)
        self.assertEqual([h["locator"]["row"] for h in hits], list(range(1, 9)))
        ranked = sorted(hits, key=lambda h: -h["salience"])
        self.assertTrue(all(h["value"] != "例行月度结算" for h in ranked[:6]))

    def test_schema_resolution_uses_longest_field_and_exact_sheet_scope(self):
        entries = [
            {"id": str(i), "kind": "xlsx_cell", "sheet": sheet, "field": field,
             "value": "产品升级", "locator": {"row": i, "cell": f"J{i}"},
             "text": f"{sheet} {field} 产品升级"}
            for i, (sheet, field) in enumerate([
                ("维护记录", "备注"), ("维护记录", "处理备注"), ("旧维护记录", "处理备注")], 1)
        ]
        rag = self.rag(entries)
        question = 'Excel"维护记录"Sheet的处理备注列，请列出全部记录。'
        plan = rag._plan(question)
        self.assertEqual(plan['sheet_hints'], ['维护记录'])
        self.assertEqual(plan['column_hints'], ['处理备注'])
        self.assertEqual([h['id'] for h in rag._structured_retrieve(question, plan)], ['2'])

    def test_unknown_column_does_not_trigger_whole_sheet_exhaustive_scan(self):
        rag = self.rag([{'id': 'e1', 'kind': 'xlsx_cell', 'sheet': '维护记录', 'field': '备注',
                         'value': '升级', 'text': '维护记录 备注 升级', 'locator': {'row': 1}}])
        question = 'Excel"维护记录"Sheet的"不存在"列，请找出所有记录。'
        plan = rag._plan(question)
        self.assertEqual(plan['column_hints'], [])
        self.assertEqual(plan['retrieval_mode'], 'ranked')
        self.assertEqual(rag._structured_retrieve(question, plan), [])

    def enumeration_context(self, values, budget):
        entries = [{'id': str(i), 'kind': 'xlsx_cell', 'sheet': '维护记录', 'field': '备注',
                    'source': 'ops.xlsx', 'value': value, 'text': '维护记录 备注 ' + value,
                    'locator': {'row': i, 'cell': f'J{i}'}}
                   for i, value in enumerate(values, 1)]
        rag = self.rag(entries)
        rag.context_chars, rag.top_facts, rag.top_paths = budget, 14, 6
        question = 'Excel"维护记录"Sheet的备注列，请列出全部记录。'
        plan = rag._plan(question)
        result = {'question': question, 'query_plan': plan,
                  'structured_hits': rag._structured_retrieve(question, plan),
                  'fact_hits': [], 'paths': [], 'entity_candidates': [], 'raw_units': [], 'stats': {}}
        result['context'] = rag.build_context(result)
        return result

    def test_exhaustive_context_has_no_arbitrary_eighty_record_cap(self):
        result = self.enumeration_context([f'变更{i}' for i in range(100)], 40000)
        sources = [line for line in result['context'].splitlines() if line.startswith('STRUCTURED_SOURCE ')]
        self.assertEqual(len(sources), 100)
        self.assertEqual(result['stats']['structured_context_records'], 100)
        self.assertEqual(result['stats']['structured_context_records_omitted'], 0)

    def test_long_values_are_atomic_and_omissions_are_reported(self):
        long_value = '完整变更记录' * 400
        result = self.enumeration_context(['开始', long_value, '结束'], 2200)
        blocks = [json.loads(line.split(' ', 1)[1]) for line in result['context'].splitlines()
                  if line.startswith('STRUCTURED_SOURCE ')]
        self.assertEqual([b['value'] for b in blocks], ['开始', '结束'])
        coverage = next(json.loads(line.split(' ', 1)[1]) for line in result['context'].splitlines()
                        if line.startswith('STRUCTURED_COVERAGE '))
        self.assertEqual(coverage['records_included'], 2)
        self.assertEqual(coverage['records_omitted'], 1)
        self.assertLessEqual(len(result['context']), 2200)
        result = self.enumeration_context([long_value], 10000)
        block = next(json.loads(line.split(' ', 1)[1]) for line in result['context'].splitlines()
                     if line.startswith('STRUCTURED_SOURCE '))
        self.assertEqual(block['value'], long_value)

    def test_quoted_sheet_is_not_column_even_when_column_cue_is_nearby(self):
        rag = self.rag([{'id': 'e1', 'kind': 'xlsx_cell', 'sheet': '备注', 'field': '时间',
                         'value': '2026-01-01', 'text': '备注 时间', 'locator': {'row': 1}}])
        plan = rag._plan('Excel"备注"Sheet的所有记录，请逐一列出。')
        self.assertEqual(plan['sheet_hints'], ['备注'])
        self.assertEqual(plan['column_hints'], [])
        self.assertEqual(plan['retrieval_mode'], 'exhaustive')

    def test_causal_timeline_does_not_become_alias_lookup_or_global_note_scan(self):
        rag = self.rag([{'id': 'e1', 'kind': 'xlsx_cell', 'sheet': '维护记录', 'field': '备注',
                         'value': '升级', 'text': '维护记录 备注 升级', 'locator': {'row': 1}}])
        plan = rag._plan('请按时间顺序列出产品Atlas收入下降相关的全部变更事件，说明因果关系。'
                         '线索分散在Excel（含隐藏的备注列）、Word、PDF、PPT中，产品使用不同名称。')
        self.assertEqual(plan['intent'], 'causal')
        self.assertFalse(plan['cross_format_identity'])
        self.assertEqual(plan['retrieval_mode'], 'ranked')

    def test_primary_cross_format_name_question_remains_identity_lookup(self):
        rag = self.rag([])
        plan = rag._plan('Atlas在PDF、Word、Excel、PPT中分别使用什么名称？请列出各格式独有信息。')
        self.assertEqual(plan['intent'], 'cross_format_identity')


class NativeSnapshotPlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rag = LeanGraphRAG(Path(__file__).resolve().parents[3] / 'examples/prebuilt/work')

    def test_original_q5_scans_eight_notes_and_augments_six_key_events(self):
        question = 'Excel"订单明细"Sheet的备注列中隐藏了6条关键线索（分布在不同的行中）。请找出全部6条隐藏线索，并按时间顺序串联成一条完整的事件链，说明这些事件之间的因果关系。'
        result = self.rag.retrieve(question)
        plan = result['query_plan']
        self.assertEqual(plan['intent'], 'structured_enumeration')
        self.assertEqual(plan['sheet_hints'], ['订单明细'])
        self.assertEqual(plan['column_hints'], ['备注'])
        cells = ['J8', 'J18', 'J33', 'J48', 'J63', 'J78', 'J93', 'J108']
        self.assertEqual([h['locator']['cell'] for h in result['structured_hits']], cells)
        self.assertEqual(result['stats']['structured_scope_matches'], 8)
        self.assertEqual(result['stats']['structured_selected_for_augmentation'], 6)
        selected = result['augmentation_sources']
        self.assertEqual({h['locator']['cell'] for h in selected},
                         {'J8', 'J33', 'J63', 'J78', 'J93', 'J108'})
        self.assertNotIn('例行月度结算', result['augmentation_query'])
        structured_context = [line for line in result['context'].splitlines()
                              if line.startswith('STRUCTURED_SOURCE ')]
        self.assertEqual(len(structured_context), 8)

    def test_original_q10_does_not_treat_column_alignment_phrase_as_a_field(self):
        question = 'PDF文档中的AI工具使用对照表（T2）的续表清空。请根据首页表头和续表数据，还原正确的列对应关系，并说明判断依据。同时，该表中哪些AI工具与"AI代码助手插件"存在直接或间接的关联？'
        result = self.rag.retrieve(question)
        self.assertEqual(result['query_plan']['column_hints'], [])
        self.assertEqual(result['query_plan']['intent'], 'structured_lookup')
        self.assertEqual(result['query_plan']['retrieval_mode'], 'ranked')
        self.assertGreater(len(result['structured_hits']), 0)

    def test_original_q1_keeps_pricing_transition_and_date_in_model_context(self):
        from docx import Document
        root = Path(__file__).resolve().parents[3]
        paragraphs = [p.text for p in Document(next((root / 'materials').glob('*问题*docx'))).paragraphs]
        question = paragraphs[next(i for i, p in enumerate(paragraphs) if p.startswith('Q1 ')) + 1]
        result = self.rag.retrieve(question)
        self.assertFalse(result['query_plan']['cross_format_identity'])
        self.assertGreater(result['stats']['paths'], 0)
        self.assertIn('免费增值', result['context'])
        self.assertIn('订阅制', result['context'])
        self.assertIn('2026-04-08', result['context'])


if __name__ == "__main__":
    unittest.main()
