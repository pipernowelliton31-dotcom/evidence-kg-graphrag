import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lean_graphrag import LeanGraphRAG


class TableContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.header = ['工具名称', '用途分类', '主要使用场景', '调用频次/月', '月度成本', '版本', '依赖产品', '备注']
        self.units = [self.table('head', 31, self.header,
                                [['ToolA', '编程', '插件开发', '8万次', '20美元', 'v2', 'product-x', '主力IDE']]),
                      self.table('tail', 32, self.header,
                                [['SearchB', '搜索', 'AI搜索', '3千次', '20美元', 'v1', '竞品调研', '实时搜索'],
                                 ['ChartC', '分析', '数据分析', '1千次', '15美元', 'v2024', '收入分析', '数据可视化']], 31),
                      self.table('distractor', 41, ['产品', '别名'], [['AI代码助手插件', 'product-x']])]
        self.question = 'PDF中AI工具使用对照表的续表缺少表头，请还原列对应关系。同时哪些工具与AI代码助手插件有关？'

    @staticmethod
    def table(uid, page, header, rows, inherited=None):
        return {'unit_id': uid, 'document_id': 'pdf', 'locator': {'page': page, 'table': 1, 'row_start': 1},
                'content_md': ' | '.join(header) + '\n' + '\n'.join(' | '.join(row) for row in rows),
                'structured': {'kind': 'pdf_table', 'header': header, 'records': rows,
                               'schema_inherited_from_page': inherited}}

    def rag(self, **kwargs):
        parsed = {'documents': [{'document_id': 'pdf', 'path': 'spec.pdf', 'format': 'pdf'},
                                {'document_id': 'xls', 'path': 'ops.xlsx', 'format': 'xlsx'}], 'units': self.units}
        for name, value in [('00_document_units.json', parsed), ('04_knowledge_graph.json', {})]:
            (self.work / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return LeanGraphRAG(self.work, **kwargs)

    @staticmethod
    def blocks(context, prefix):
        return [json.loads(line[len(prefix) + 1:]) for line in context.splitlines() if line.startswith(prefix + ' ')]

    def test_reconstruction_preserves_all_columns_and_continuation_despite_small_top_k(self):
        result = self.rag(top_units=1, top_structured=1).retrieve(self.question)
        schemas = self.blocks(result['context'], 'TABLE_SCHEMA')
        self.assertEqual([s['locator']['page'] for s in schemas], [31, 32])
        self.assertTrue(all(s['header'] == self.header and s['column_count'] == 8 for s in schemas))
        rows = self.blocks(result['context'], 'TABLE_ROW')
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]['values'][-2:], ['竞品调研', '实时搜索'])
        self.assertEqual(rows[2]['values'][5], 'v2024')
        self.assertEqual(result['stats']['table_rows'], 3)

    def test_schema_width_is_discovered_and_empty_cell_does_not_shift_columns(self):
        self.units = [self.table('head', 6, ['工具', '关联产品', '备注'], [['ToolA', 'x', '首选']]),
                      self.table('tail', 7, ['工具', '关联产品', '备注'], [['ToolB', '', '备用']], 6)]
        result = self.rag().retrieve(self.question)
        schemas = self.blocks(result['context'], 'TABLE_SCHEMA')
        self.assertEqual([s['column_count'] for s in schemas], [3, 3])
        self.assertEqual(self.blocks(result['context'], 'TABLE_ROW')[1]['values'], ['ToolB', '', '备用'])

    def test_serialized_geometry_and_chunked_rows_keep_continuation_group(self):
        self.units[0]['locator']['bbox'] = ['10', '100', '400', '700']
        self.units[1]['locator']['bbox'] = ['10.0', '50', '400.0', '700']
        chunk = self.table('head_chunk', 31, self.header,
                           [['ToolE', '编程', '插件开发', '1千次', '5美元', 'v1', 'x', '备用']])
        chunk['locator'].update({'row_start': 2, 'bbox': ['10', '100', '400', '700']})
        self.units.append(chunk)
        result = self.rag().retrieve(self.question)
        self.assertEqual(result['stats']['table_units'], 3)
        self.assertEqual(result['stats']['table_rows'], 4)

    def test_related_excel_cell_includes_named_row_companions(self):
        self.units.append({'unit_id': 'sheet', 'document_id': 'xls', 'content_md': '工具使用统计 AI代码助手插件',
            'locator': {'sheet': '工具使用统计'}, 'structured': {'kind': 'xlsx_cells', 'header_rows': [1],
            'records': [{'row': 1, 'cells': [{'coordinate': 'A1', 'raw': '工具名称'}, {'coordinate': 'B1', 'raw': '关联产品'}]},
                        {'row': 2, 'cells': [{'coordinate': 'A2', 'raw': 'ToolD'}, {'coordinate': 'B2', 'raw': 'AI代码助手插件'}]}]}})
        result = self.rag().retrieve(self.question)
        rows = self.blocks(result['context'], 'STRUCTURED_ROW')
        self.assertTrue(any({c['cell']: c['value'] for c in row['cells']} ==
                            {'A2': 'ToolD', 'B2': 'AI代码助手插件'} for row in rows))

    def test_budget_keeps_json_atomic_and_reports_omitted_table_rows(self):
        self.units[1]['structured']['records'][0][-1] = '很长的备注' * 1500
        result = self.rag(context_chars=2200).retrieve(self.question)
        self.assertLessEqual(len(result['context']), 2200)
        schemas = self.blocks(result['context'], 'TABLE_SCHEMA')
        self.assertEqual(len(schemas), 2)
        rows = self.blocks(result['context'], 'TABLE_ROW')
        coverage = self.blocks(result['context'], 'TABLE_COVERAGE')[0]
        self.assertEqual(coverage['rows_included'], len(rows))
        self.assertEqual(coverage['rows_omitted'], 3 - len(rows))
        self.assertGreater(coverage['rows_omitted'], 0)


if __name__ == '__main__':
    unittest.main()
