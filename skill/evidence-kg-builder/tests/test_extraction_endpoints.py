import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kg_core import accept_extractions, empty_alignment


class ExtractionEndpointTests(unittest.TestCase):
    def test_invalid_endpoints_do_not_abort_valid_facts(self):
        state = {
            "fingerprint": "test",
            "units": [{"unit_id": "u1", "document_id": "d1", "content_md": "Example", "locator": {}}],
            "extractions": {}, "alignment": empty_alignment(), "audit": [],
        }
        for invalid in (["m2"], {"local_id": "m2"}, None, 2):
            for endpoint in ("subject", "object"):
                with self.subTest(invalid=invalid, endpoint=endpoint):
                    relation = {"subject": "m1", "predicate": "uses", "object": "m2"}
                    bad_relation = {**relation, endpoint: invalid}
                    response = {"fingerprint": "test", "tasks": [{
                        "task_id": "u1",
                        "mentions": [
                            {"local_id": "m1", "type": "Product", "name": "Example product"},
                            {"local_id": "m2", "type": "AITool", "name": "Example tool"},
                        ],
                        "relations": [bad_relation, relation],
                        "assertions": [{"subject": "m1", "predicate": "attribute",
                                        "qualifiers": {"attribute": "formats"}, "value": ["PDF", "Word"]}],
                    }]}
                    before = copy.deepcopy(state)
                    result = accept_extractions(state, response)["extractions"]["u1"]
                    self.assertEqual(state, before)
                    self.assertEqual(len(result["relations"]), 1)
                    self.assertEqual(result["relations"][0]["predicate"], "uses")
                    self.assertIn("skipped_unresolved_relation_endpoint", result["warnings"])
                    self.assertEqual(result["assertions"][0]["value"], ["PDF", "Word"])


if __name__ == "__main__":
    unittest.main()
