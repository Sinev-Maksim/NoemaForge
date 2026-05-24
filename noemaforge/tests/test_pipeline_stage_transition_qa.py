from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline_stage_transition_runtime as pstr


class PipelineStageTransitionQATests(unittest.TestCase):
    def test_docs_and_registry_record_closed_stage_transition_item(self) -> None:
        docs = [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]
        for path in docs:
            self.assertIn("pipeline-stage-transition-core", path.read_text(encoding="utf-8"))
        closed_line = "[x] Add stage transition commands: `advance`, `pause`, `resume`, `fail`, `approve`."
        self.assertIn(closed_line, (ROOT / "docs" / "TODO.md").read_text(encoding="utf-8"))
        self.assertIn(closed_line, (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8"))

        registry = json.loads((ROOT / "configs" / "unified-registry.json").read_text(encoding="utf-8"))
        refs = {f"{entry['kind']}:{entry['id']}:{entry['version']}": entry for entry in registry["entries"]}
        self.assertIn("eval-pack:pipeline-stage-transition-core:0.32.1", refs)
        self.assertIn(
            "eval-pack:pipeline-stage-transition-core:0.32.1",
            refs["pipeline:firstboot-model-selection:0.32.1"]["eval_pack_refs"],
        )

    def test_static_runtime_tokens_cover_all_transition_commands(self) -> None:
        payload = pstr.load_json(ROOT / "configs" / "pipeline-stage-transition-policy.json")
        static = pstr._static_failures(payload)
        self.assertEqual([], static["failures"])


if __name__ == "__main__":
    unittest.main()

