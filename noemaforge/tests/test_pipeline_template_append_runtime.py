#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_template_append_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate reviewed pipeline template catalog append invariants.
Inputs: Workspace template-append policy and synthetic workflow templates.
Outputs: unittest assertions only.
Side effects: Temporary files under unittest temp directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline_runtime as prt
import pipeline_template_append_runtime as ptar
import production_ai_contracts as pac


def call_pipeline(argv: list[str]) -> tuple[int, dict]:
    stdout = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(stdout):
        try:
            prt.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, json.loads(stdout.getvalue())


def make_source(tmp: Path) -> Path:
    source = tmp / "source.json"
    source.write_text(
        json.dumps({"name": "T", "nodes": [{"name": "Webhook"}, {"name": "Normalize"}], "connections": {}}),
        encoding="utf-8",
    )
    return source


class PipelineTemplateAppendRuntimeTests(unittest.TestCase):
    def test_workspace_pipeline_template_append_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "pipeline-template-append-policy.json"
        validation = ptar.validate_pipeline_template_append_policy(
            ptar.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])

        gate = pac.evaluate_gate(
            {"change_id": "pipeline-template-append-core", "domain": "pipeline"},
            ptar.pipeline_template_append_report_to_gate_evidence(validation, artifact_uri="reports/pipeline-template-append.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_template_append_requires_approval_before_catalog_write(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = make_source(tmp)
            draft = tmp / "draft.json"
            out = tmp / "pipelines.local.json"
            code, imported = call_pipeline(["template-import", str(source), "--pipeline-id", "pytest_import", "--out", str(draft), "--root", str(ROOT)])
            denied_code, denied = call_pipeline(["template-append", str(draft), "--out", str(out), "--root", str(ROOT)])

        self.assertEqual(0, code)
        self.assertTrue(imported["ok"])
        self.assertEqual(1, denied_code)
        self.assertFalse(denied["ok"])
        self.assertTrue(denied["ready_to_append"])
        self.assertEqual("--approve", denied["requires"])
        self.assertFalse(out.exists())

    def test_template_append_approved_write_records_review(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = make_source(tmp)
            draft = tmp / "draft.json"
            out = tmp / "pipelines.local.json"
            call_pipeline(["template-import", str(source), "--pipeline-id", "pytest_reviewed", "--out", str(draft), "--root", str(ROOT)])
            code, appended = call_pipeline([
                "template-append",
                str(draft),
                "--approve",
                "--approved-by",
                "qa-operator",
                "--out",
                str(out),
                "--root",
                str(ROOT),
            ])
            catalog = json.loads(out.read_text(encoding="utf-8"))

        self.assertEqual(0, code)
        self.assertTrue(appended["ok"])
        self.assertIn("pytest_reviewed", appended["added"])
        self.assertEqual("qa-operator", catalog["pytest_reviewed"]["review"]["approved_by"])
        self.assertEqual("switchable", catalog["pytest_reviewed"]["llm_policy"]["mode"])
        self.assertEqual(1, catalog["pytest_reviewed"]["llm_policy"]["max_active_llms"])

    def test_malformed_template_append_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            draft = tmp / "bad-draft.json"
            draft.write_text(json.dumps({"bad": "not-a-template"}), encoding="utf-8")
            out = tmp / "pipelines.local.json"
            code, result = call_pipeline(["template-append", str(draft), "--approve", "--out", str(out), "--root", str(ROOT)])

        self.assertEqual(1, code)
        self.assertFalse(result["ok"])
        self.assertIn("draft contains no pipeline templates", result["problems"])
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
