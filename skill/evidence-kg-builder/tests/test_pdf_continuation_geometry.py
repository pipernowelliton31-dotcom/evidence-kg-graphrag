import sys
import unittest
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from parse_documents import _pdf_infer_header_schema, _pdf_row_from_schema, parse_manifest
from lean_graphrag import LeanGraphRAG


class PdfContinuationGeometryTests(unittest.TestCase):
    def test_header_x_bands_align_continuation_rows(self):
        words = [
            {"text": "工具", "x0": 10, "x1": 30, "top": 10, "bottom": 20},
            {"text": "用途", "x0": 50, "x1": 70, "top": 10, "bottom": 20},
            {"text": "备注", "x0": 90, "x1": 110, "top": 10, "bottom": 20},
            {"text": "ToolA", "x0": 10, "x1": 34, "top": 40, "bottom": 50},
            {"text": "搜索", "x0": 50, "x1": 70, "top": 40, "bottom": 50},
            {"text": "调研", "x0": 90, "x1": 110, "top": 40, "bottom": 50},
        ]
        schema = _pdf_infer_header_schema(words, [0, 5, 120, 25], [0, 0, 120, 60], 1)
        self.assertEqual(schema["header"], ["工具", "用途", "备注"])
        row = _pdf_row_from_schema(words, [0, 35, 120, 55], schema)
        self.assertEqual(row, ["ToolA", "搜索", "调研"])


class ActualPdfContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory(prefix='pdf_continuation_test_') as temp:
            folder = Path(temp)
            pdf = next((root / 'materials').glob('*.pdf'))
            manifest = folder / 'inputs.json'
            manifest.write_text(json.dumps({'root': str(pdf.parent),
                'files': [{'path': pdf.name, 'role': 'corpus'}]}), encoding='utf-8')
            state, _ = parse_manifest(manifest, folder / 'work', fresh=True)
            if state['documents'][0]['parse_status'] != 'parsed':
                raise AssertionError(state['documents'][0].get('parse_error'))
            cls.tables = [u for u in state['units'] if u.get('structured', {}).get('kind') == 'pdf_table']
            cls.parsed = state

    def table(self, page, table=1):
        return next(u['structured'] for u in self.tables
                    if u['locator']['page'] == page and u['locator']['table'] == table)

    def test_new_full_width_table_does_not_inherit_previous_unrelated_header(self):
        self.assertEqual(self.table(4)['header'],
                         ['产品名称', '产品类型', '定价', '适用平台', '有效期', '授权数', '备注'])
        self.assertIsNone(self.table(4)['schema_inherited_from_page'])
        self.assertEqual(self.table(7)['header'],
                         ['工具名称', '用途分类', '主要使用场景', '调用频次/月', '月度成本', '版本', '依赖产品', '备注'])
        self.assertIsNone(self.table(7)['schema_inherited_from_page'])

    def test_t2_continuation_preserves_perplexity_first_row_and_column_alignment(self):
        table = self.table(8)
        self.assertEqual(table['schema_inherited_from_page'], 7)
        self.assertEqual(table['header'], self.table(7)['header'])
        row = table['records'][0]
        self.assertEqual(row, ['Perplexity', '搜索', 'AI搜索', '约3千次', '20美元', 'v1', '竞品调研', '实时搜\n索'])

    def test_continuation_uses_bottom_table_when_previous_page_has_multiple_tables(self):
        header = self.table(15, 2)['header']
        self.assertIsNone(self.table(15, 2)['schema_inherited_from_page'])
        self.assertEqual(header[0], '标准名称')
        self.assertEqual(self.table(16)['header'], header)
        self.assertEqual(self.table(16)['schema_inherited_from_page'], 15)

    def test_q10_context_uses_tool_table_not_product_alias_table(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / '00_document_units.json').write_text(json.dumps(self.parsed), encoding='utf-8')
            (work / '04_knowledge_graph.json').write_text('{}', encoding='utf-8')
            rag = LeanGraphRAG(work, top_units=1, top_structured=1)
            result = rag.retrieve('PDF文档中的AI工具使用对照表（T2）的续表清空。请根据首页表头和续表数据，还原正确的列对应关系，并说明判断依据。同时，该表中哪些AI工具与"AI代码助手插件"存在直接或间接的关联？')
            self.assertEqual([t['locator']['page'] for t in result['table_hits']], [7, 8])
            self.assertEqual(result['stats']['table_columns'], 8)
            rows = [json.loads(line.split(' ', 1)[1]) for line in result['context'].splitlines()
                    if line.startswith('TABLE_ROW ')]
            self.assertEqual(len(rows), 27)
            row = next(r['values'] for r in rows if r['values'][0] == 'Perplexity')
            self.assertEqual(row[-2:], ['竞品调研', '实时搜\n索'])
            self.assertEqual(next(r['values'][5] for r in rows if r['values'][0] == 'Tableau'), 'v20\n24')


if __name__ == "__main__":
    unittest.main()
