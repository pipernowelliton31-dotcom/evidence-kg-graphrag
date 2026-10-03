import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kg_core import _repair_version_types


class AlignmentRelationTypeTests(unittest.TestCase):
    def state(self, predicate, subject="version", obj="tool"):
        return {"extractions": {"u1": {
            "mentions": [
                {"mention_id": "tool", "name": "ExampleTool", "type": "AITool", "attributes": {}},
                {"mention_id": "version", "name": "ExampleTool v2.0", "type": "AITool", "attributes": {}},
            ],
            "relations": [{"subject": subject, "predicate": predicate, "object": obj}],
        }}, "audit": []}

    def test_unknown_incident_relation_preserves_types_and_relation(self):
        for subject, obj in (("version", "tool"), ("tool", "version")):
            with self.subTest(subject=subject, obj=obj):
                state = self.state("adapted_to", subject, obj)
                before = copy.deepcopy(state)
                self.assertEqual(_repair_version_types(state), [])
                self.assertEqual(state, before)

    def test_known_compatible_relation_still_allows_version_repair(self):
        state = self.state("version_of")
        before_relations = copy.deepcopy(state["extractions"]["u1"]["relations"])
        changes = _repair_version_types(state)
        self.assertEqual(len(changes), 1)
        self.assertEqual(state["extractions"]["u1"]["mentions"][1]["type"], "Version")
        self.assertEqual(state["extractions"]["u1"]["relations"], before_relations)

    def test_known_incompatible_relation_blocks_version_repair(self):
        state = self.state("uses")
        before = copy.deepcopy(state)
        self.assertEqual(_repair_version_types(state), [])
        self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
