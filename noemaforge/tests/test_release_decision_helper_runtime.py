#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import release_decision_helper_runtime as rdh


class ReleaseDecisionHelperRuntimeTests(unittest.TestCase):
    def test_json_boolean_payload_builds_decision_without_python_literal_typo(self) -> None:
        source_gate = json.loads('{"ok": true, "evidence": "repo-evidenced", "failures": []}')
        known_findings = json.loads('{"known_findings": [{"id": "known-doc-only", "blocking": false}]}')

        report = rdh.build_release_decision_report(source_gate, known_findings)

        self.assertTrue(report["ok"], report)
        self.assertEqual("pass", report["decision"])
        self.assertFalse(report["live_evidence_claimed"])
        self.assertEqual(0, report["known_findings"]["blocking"])

    def test_blocking_known_finding_blocks_release_decision(self) -> None:
        report = rdh.build_release_decision_report(
            {"ok": True, "evidence": "repo-evidenced"},
            {"known_findings": [{"id": "uat-breaker", "blocking": True, "resolved": False}]},
        )

        self.assertFalse(report["ok"])
        self.assertEqual("block", report["decision"])
        self.assertEqual(["uat-breaker"], report["known_findings"]["blocking_ids"])

    def test_source_gate_construction_failure_writes_json_and_markdown_reports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_release_decision_") as td:
            result = rdh.run_release_decision_helper(
                source_gate_payload={"failures": []},
                known_findings_payload={"known_findings": []},
                out_dir=td,
            )

            self.assertFalse(result["ok"])
            self.assertEqual(rdh.FAILURE_KIND, result["kind"])
            self.assertEqual("source_gate_construction", result["phase"])
            json_path = Path(result["paths"]["json"])
            md_path = Path(result["paths"]["markdown"])
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            failure = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual("source_gate_missing_ok", failure["error"])
            self.assertIn("error_type: ValueError", md_path.read_text(encoding="utf-8"))

    def test_cli_json_parse_failure_still_writes_failure_reports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_release_decision_cli_") as td:
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = rdh.main([
                    "--source-gate",
                    '{"ok": true',
                    "--known-findings",
                    '{"known_findings": []}',
                    "--out-dir",
                    td,
                ])

            self.assertEqual(1, exit_code)
            self.assertIn('"kind": "ReleaseDecisionFailureReport"', stdout.getvalue())
            failure_path = Path(td) / "release-decision-failure.json"
            self.assertTrue(failure_path.exists())
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
            self.assertEqual(rdh.FAILURE_KIND, failure["kind"])
            self.assertEqual("JSONDecodeError", failure["error_type"])


if __name__ == "__main__":
    unittest.main()
