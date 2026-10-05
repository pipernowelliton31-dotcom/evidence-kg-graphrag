import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kg_core import (CONFIG, _repair_identity_metadata, _supported_inline_business_codes,
                     accept_extractions, empty_alignment, initialize_alignment, mentions)


class IdentifierOwnershipTests(unittest.TestCase):
    def extract(self, text, items):
        state = {"fingerprint": "test", "config": dict(CONFIG), "units": [{
            "unit_id": "u1", "document_id": "d1", "locator": {}, "content_md": text,
        }], "extractions": {}, "alignment": empty_alignment(), "audit": []}
        return accept_extractions(state, {"fingerprint": "test", "tasks": [{
            "task_id": "u1", "mentions": items, "relations": [], "assertions": [],
        }]})

    def test_page_review_code_does_not_merge_unrelated_products(self):
        text = "Atlas、素材库、周报生成器均在本页。Atlas 的评审编号 RV-2031\n-0412。"
        state = self.extract(text, [
            {"local_id": str(i), "type": "Product", "name": name}
            for i, name in enumerate(["Atlas", "素材库", "周报生成器"])
        ])
        initialize_alignment(state)
        self.assertEqual(len(state["alignment"]["clusters"]), 3)
        self.assertTrue(all(not m["identifiers"] for m in mentions(state).values()))

    def test_record_codes_do_not_become_actor_or_version_ids(self):
        text = "评审编号 RV-2031-0412；变更记录编码 CHG-031；张三维护 Atlas v2。"
        state = self.extract(text, [
            {"local_id": "actor", "type": "Actor", "name": "张三"},
            {"local_id": "version", "type": "Version", "name": "Atlas v2"},
        ])
        self.assertTrue(all(not m["identifiers"] for m in mentions(state).values()))

    def test_repair_also_removes_unowned_event_codes(self):
        state = self.extract("评审编号 RV-2031-0412；发布调整方案", [{
            "local_id": "e", "type": "Event", "name": "发布调整方案",
        }])
        m = next(iter(mentions(state).values()))
        m["identifiers"].append({"value": "RV-2031-0412", "scope": "inline_event_code",
                                 "evidence": copy.deepcopy(m["evidence"])})
        _repair_identity_metadata(state)
        self.assertEqual(m["identifiers"], [])

    def test_cli_reset_archives_polluted_checkpoint_and_invalidates_old_graph(self):
        state = self.extract("Atlas(AC-47)", [{
            "local_id": "p", "type": "Product", "name": "Atlas(AC-47)",
        }])
        state.update(schema_version="1.3", engine_version="4.0.0", engine_signature="old-engine",
                     documents=[], source_root=".")
        initialize_alignment(state)
        before = copy.deepcopy(state)
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / "state.json").write_text(json.dumps(state), encoding="utf-8")
            parsed = {"fingerprint": "test", "documents": [], "units": state["units"]}
            (work / "00_document_units.json").write_text(json.dumps(parsed), encoding="utf-8")
            for name in ("03_canonical_facts.json", "04_knowledge_graph.json"):
                (work / name).write_text('{"old": true}', encoding="utf-8")
            result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] /
                "scripts/kg_pipeline.py"), "reset-alignment", "--work", str(work)],
                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            after = json.loads((work / "state.json").read_text(encoding="utf-8"))
            self.assertNotEqual(after["fingerprint"], before["fingerprint"])
            self.assertEqual(after["extractions"], before["extractions"])
            self.assertEqual(after["alignment"]["mapping"], {})
            self.assertEqual(json.loads((work / "00_document_units.json").read_text(
                encoding="utf-8"))["units"], before["units"])
            self.assertEqual(json.loads((work / "00_document_units.json").read_text(
                encoding="utf-8"))["fingerprint"], after["fingerprint"])
            self.assertFalse((work / "04_knowledge_graph.json").exists())
            self.assertFalse((work / "03_canonical_facts.json").exists())
            archived = list((work / "archive").glob("*/state.json"))
            self.assertEqual(len(archived), 1)
            self.assertEqual(json.loads(archived[0].read_text(encoding="utf-8")), before)

    def test_explicit_own_codes_still_anchor_identity(self):
        cases = [
            (["Atlas(AC-47)"], "Atlas(AC-47)", {"AC-47"}),
            (["Atlas", "AC-47"], "Atlas；业务代码 AC-47", {"AC-47"}),
            (["评审记录RV-2031-0412"], "评审编号 RV-2031-0412", {"RV-2031-0412"}),
            (["Atlas v2"], "Atlas v2，版本编号 v2", set()),
            (["Atlas(AC-47)"], "没有编号", set()),
            (["Atlas(AC-470)"], "业务代码 AC-47", set()),
        ]
        for labels, text, expected in cases:
            with self.subTest(labels=labels):
                self.assertEqual(_supported_inline_business_codes(labels, text), expected)

    def test_repair_removes_old_derived_codes_preserving_explicit_identifiers(self):
        state = self.extract("Atlas(AC-47)，评审编号 RV-2031-0412", [{
            "local_id": "p", "type": "Product", "name": "Atlas(AC-47)",
            "identifiers": [{"value": "MANUAL-7", "scope": "catalog"}],
        }])
        m = next(iter(mentions(state).values()))
        m["identifiers"].append({"value": "RV-2031-0412", "scope": "inline_product_code",
                                 "evidence": copy.deepcopy(m["evidence"])})
        _repair_identity_metadata(state)
        self.assertEqual({(i["scope"], i["value"]) for i in m["identifiers"]},
                         {("catalog", "MANUAL-7"), ("inline_product_code", "AC-47")})


if __name__ == "__main__":
    unittest.main()
