#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import aat_allpipeline_runtime as aatpipe


class ClassifyPipelineForAATTests(unittest.TestCase):
    def test_plan_only_runs_automatically(self) -> None:
        self.assertEqual("run", aatpipe.classify_pipeline_for_aat("plan_only"))

    def test_ask_before_write_and_guided_readmostly_expect_a_gate(self) -> None:
        self.assertEqual("run_expect_gate", aatpipe.classify_pipeline_for_aat("ask_before_write"))
        self.assertEqual("run_expect_gate", aatpipe.classify_pipeline_for_aat("guided_readmostly"))

    def test_admin_explicit_and_manual_modes_are_skipped(self) -> None:
        for mode in ("guided_admin", "explicit_only", "manual_only"):
            self.assertEqual("skip", aatpipe.classify_pipeline_for_aat(mode), mode)

    def test_unknown_or_missing_mode_defaults_to_skip(self) -> None:
        self.assertEqual("skip", aatpipe.classify_pipeline_for_aat(""))
        self.assertEqual("skip", aatpipe.classify_pipeline_for_aat("some_future_mode_not_yet_reviewed"))


class BuildAatSampleRequestTests(unittest.TestCase):
    def test_uses_the_pipeline_description(self) -> None:
        text = aatpipe.build_aat_sample_request("book", "Ghostwrite a short story end to end.")
        self.assertIn("Ghostwrite a short story end to end.", text)
        self.assertTrue(text.startswith("[AAT smoke test]"))

    def test_falls_back_when_description_is_empty(self) -> None:
        text = aatpipe.build_aat_sample_request("mystery_pipeline", "")
        self.assertIn("mystery_pipeline", text)
        self.assertTrue(text.startswith("[AAT smoke test]"))


class ClassifyPipelineRunResultTests(unittest.TestCase):
    def test_clarification_required_is_blocked_pending_approval(self) -> None:
        self.assertEqual(
            "blocked_pending_approval",
            aatpipe.classify_pipeline_run_result({"ok": True, "clarification_required": True}),
        )

    def test_ready_for_admin_approval_status_is_blocked_pending_approval(self) -> None:
        self.assertEqual(
            "blocked_pending_approval",
            aatpipe.classify_pipeline_run_result({"ok": True, "status": "ready_for_admin_approval"}),
        )

    def test_ok_false_is_error(self) -> None:
        self.assertEqual("error", aatpipe.classify_pipeline_run_result({"ok": False, "error": "boom"}))

    def test_failed_status_is_error(self) -> None:
        self.assertEqual("error", aatpipe.classify_pipeline_run_result({"ok": True, "status": "failed"}))

    def test_normal_completion_is_passed(self) -> None:
        self.assertEqual("passed", aatpipe.classify_pipeline_run_result({"ok": True, "status": "created"}))

    def test_non_dict_result_is_error(self) -> None:
        self.assertEqual("error", aatpipe.classify_pipeline_run_result(None))
        self.assertEqual("error", aatpipe.classify_pipeline_run_result("not a dict"))


class RunAllPipelinesAatTests(unittest.TestCase):
    def _catalog(self) -> dict:
        return {
            "safe_plan": {"description": "A safe planning pipeline.", "permission_mode": "plan_only"},
            "gated_write": {"description": "A pipeline that writes after approval.", "permission_mode": "ask_before_write"},
            "admin_only": {"description": "Admin-only maintenance pipeline.", "permission_mode": "guided_admin"},
            "manual_only": {"description": "Requires a human at the keyboard.", "permission_mode": "manual_only"},
        }

    def test_skips_admin_and_manual_pipelines_without_calling_run(self) -> None:
        called = []

        def fake_run(pipeline_id, request_text):
            called.append(pipeline_id)
            return {"ok": True, "status": "created"}

        report = aatpipe.run_all_pipelines_aat(catalog=self._catalog(), run_pipeline_fn=fake_run)

        self.assertNotIn("admin_only", called)
        self.assertNotIn("manual_only", called)
        self.assertIn("safe_plan", called)
        self.assertIn("gated_write", called)

        by_pipeline = {c["pipeline"]: c for c in report["cases"]}
        self.assertEqual("skipped", by_pipeline["admin_only"]["status"])
        self.assertEqual("skipped", by_pipeline["manual_only"]["status"])
        self.assertEqual("passed", by_pipeline["safe_plan"]["status"])

    def test_one_pipeline_raising_does_not_stop_the_batch(self) -> None:
        def flaky_run(pipeline_id, request_text):
            if pipeline_id == "safe_plan":
                raise RuntimeError("simulated crash")
            return {"ok": True, "status": "created"}

        report = aatpipe.run_all_pipelines_aat(catalog=self._catalog(), run_pipeline_fn=flaky_run)

        self.assertEqual(4, report["total"])
        by_pipeline = {c["pipeline"]: c for c in report["cases"]}
        self.assertEqual("error", by_pipeline["safe_plan"]["status"])
        self.assertIn("simulated crash", by_pipeline["safe_plan"]["error"])
        # the other runnable pipeline still executed despite the crash above
        self.assertEqual("passed", by_pipeline["gated_write"]["status"])

    def test_gated_pipeline_reaching_approval_is_not_a_failure(self) -> None:
        def gate_run(pipeline_id, request_text):
            return {"ok": True, "status": "ready_for_admin_approval", "clarification_required": False}

        report = aatpipe.run_all_pipelines_aat(catalog=self._catalog(), run_pipeline_fn=gate_run)
        by_pipeline = {c["pipeline"]: c for c in report["cases"]}
        self.assertEqual("blocked_pending_approval", by_pipeline["gated_write"]["status"])
        # counted separately from both "passed" and "error"
        self.assertIn("blocked_pending_approval", report["counts"])

    def test_on_progress_called_once_per_catalog_entry_in_order(self) -> None:
        progress_calls = []

        def fake_run(pipeline_id, request_text):
            return {"ok": True, "status": "created"}

        aatpipe.run_all_pipelines_aat(
            catalog=self._catalog(),
            run_pipeline_fn=fake_run,
            on_progress=lambda current, total, pipeline_id: progress_calls.append((current, total, pipeline_id)),
        )

        self.assertEqual(4, len(progress_calls))
        self.assertEqual([1, 2, 3, 4], [c[0] for c in progress_calls])
        self.assertTrue(all(c[1] == 4 for c in progress_calls))

    def test_persona_fn_is_applied_per_pipeline(self) -> None:
        def fake_run(pipeline_id, request_text):
            return {"ok": True, "status": "created"}

        report = aatpipe.run_all_pipelines_aat(
            catalog=self._catalog(),
            run_pipeline_fn=fake_run,
            persona_fn=lambda pipeline_id: f"persona-for-{pipeline_id}",
        )
        by_pipeline = {c["pipeline"]: c for c in report["cases"]}
        self.assertEqual("persona-for-safe_plan", by_pipeline["safe_plan"]["persona"])

    def test_empty_catalog_returns_empty_report(self) -> None:
        report = aatpipe.run_all_pipelines_aat(catalog={}, run_pipeline_fn=lambda p, r: {"ok": True})
        self.assertEqual(0, report["total"])
        self.assertEqual([], report["cases"])


class WriteAatAllpipelineReportTests(unittest.TestCase):
    def test_writes_json_and_markdown_pair(self) -> None:
        report = {
            "generated": "2026-07-25T12:00:00Z",
            "total": 1,
            "counts": {"passed": 1},
            "cases": [
                {"pipeline": "safe_plan", "case": "aat_smoke_test", "status": "passed", "artifact": "", "error": "", "duration_s": 0.1, "persona": "Admin"},
            ],
        }
        with tempfile.TemporaryDirectory(prefix="nf_aat_report_") as td:
            paths = aatpipe.write_aat_allpipeline_report(Path(td), report)
            json_path = Path(paths["json"])
            md_path = Path(paths["markdown"])
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())

            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(1, loaded["total"])

            md_text = md_path.read_text(encoding="utf-8")
            self.assertIn("safe_plan", md_text)
            self.assertIn("passed", md_text)

    def test_error_text_with_pipe_character_does_not_break_markdown_table(self) -> None:
        report = {
            "generated": "2026-07-25T12:00:00Z",
            "total": 1,
            "counts": {"error": 1},
            "cases": [
                {"pipeline": "p", "case": "aat_smoke_test", "status": "error", "artifact": "", "error": "bad | pipe\nand newline", "duration_s": 0.0, "persona": "Admin"},
            ],
        }
        with tempfile.TemporaryDirectory(prefix="nf_aat_report_") as td:
            paths = aatpipe.write_aat_allpipeline_report(Path(td), report)
            md_text = Path(paths["markdown"]).read_text(encoding="utf-8")
            self.assertIn("bad \\| pipe and newline", md_text)


if __name__ == "__main__":
    unittest.main()
