#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_uat_runtime.py
Zone: tests
Purpose: Integration test for the one-command UAT runner (uat_runtime). Verifies
         the full sequence on one pipeline: event recording starts, the pipeline
         runs headless with its artifacts collected into the bundle, recording
         stops, and a manifest + summary are written and returned.
Inputs: uat_runtime + the packaged pipeline catalog.
Outputs: pytest pass/fail.
Side effects: spawns one pipeline run; writes only under a tempdir.
Notes: Code comments are English-only. Headless (--no-gui); the GUI launch is
       exercised on the target host.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import uat_runtime  # noqa: E402

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


class UATRuntimeTests(unittest.TestCase):
    def test_uat_run_records_events_and_bundles_artifacts(self) -> None:
        out = Path(tempfile.mkdtemp(prefix="nf_uat_test_"))
        try:
            rc = uat_runtime.main([
                "run", "--root", str(PACKAGE_ROOT), "--out", str(out),
                "--no-gui", "--pipelines", "public_mwp",
            ])
            self.assertEqual(rc, 0)

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["kind"], "NoemaForgeUATBundle")
            self.assertEqual(manifest["summary"]["total"], 1)
            self.assertFalse(manifest["gui_launched"])

            # Step 1 + 4: a start and a stop marker were recorded.
            self.assertGreaterEqual(manifest["event_count"], 2)
            self.assertTrue((out / "events" / "events.jsonl").is_file())

            # Step 3: the pipeline ran and its artifacts were collected.
            result = manifest["pipelines"][0]
            self.assertEqual(result["pipeline"], "public_mwp")
            self.assertEqual(result["status"], "ok")
            self.assertGreater(int(result["artifact_count"]), 0)

            self.assertTrue((out / "summary.md").is_file())
            self.assertTrue((out / "pipelines" / "public_mwp" / "run_dir").is_dir())
        finally:
            shutil.rmtree(out, ignore_errors=True)


    def test_run_pipeline_rejects_unsafe_pipeline_id(self) -> None:
        # The injection / path-traversal guard: a pipeline_id carrying shell or path
        # metacharacters must be rejected before it can reach the subprocess argv or
        # the bundle path — the finding is fixed at the source, not suppressed.
        bundle = Path(tempfile.mkdtemp(prefix="nf_uat_guard_"))
        try:
            for bad in ("../evil", "a;rm -rf /", "a b", "a/b", "a|b", "$(x)", "-flag", ""):
                with self.subTest(pipeline_id=bad):
                    with self.assertRaises(ValueError):
                        uat_runtime._run_pipeline(
                            bad, package_root=PACKAGE_ROOT, bundle=bundle,
                            env={}, request="x", dry_run=True, timeout=5,
                        )
        finally:
            shutil.rmtree(bundle, ignore_errors=True)

    def test_safe_pipeline_id_accepts_catalog_shape(self) -> None:
        for good in ("public_mwp", "dev-pipeline.member_cells", "a", "X9_-."):
            with self.subTest(pipeline_id=good):
                self.assertIsNotNone(uat_runtime._SAFE_PIPELINE_ID.fullmatch(good))

    def test_pipeline_run_command_allowlist_is_single_fixed_entry(self) -> None:
        allowlist = uat_runtime._pipeline_run_command_allowlist(
            PACKAGE_ROOT, "public_mwp", "request", "run_id", True,
        )

        self.assertEqual(list(allowlist), [uat_runtime._PIPELINE_RUN_COMMAND])
        argv = allowlist[uat_runtime._PIPELINE_RUN_COMMAND]
        self.assertEqual(argv[0], sys.executable)
        self.assertEqual(argv[2:5], ["run", "public_mwp", "--task-id"])
        self.assertIn("--dry-run", argv)

    def test_dev_extra_includes_jsonschema_for_clean_venv_collection(self) -> None:
        report = uat_runtime._check_dev_dependency_contract(PACKAGE_ROOT.parent)

        self.assertTrue(report["ok"], report)
        self.assertIn("jsonschema", report["detail"]["requirements"])

    def test_compileall_check_does_not_write_source_pycache(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_uat_compile_guard_") as tmp:
            package = Path(tmp) / "noemaforge"
            src = package / "src"
            src.mkdir(parents=True)
            (src / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")

            report = uat_runtime._check_compileall(package)

            self.assertTrue(report["ok"], report)
            self.assertFalse((src / "__pycache__").exists())
            self.assertEqual([], list(src.rglob("*.pyc")))

    def test_compileall_check_reports_syntax_failures_without_pycache(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_uat_compile_fail_") as tmp:
            package = Path(tmp) / "noemaforge"
            src = package / "src"
            src.mkdir(parents=True)
            (src / "bad.py").write_text("def broken(:\n", encoding="utf-8")

            report = uat_runtime._check_compileall(package)

            self.assertFalse(report["ok"], report)
            self.assertEqual(1, report["detail"]["failure_count"])
            self.assertEqual("src/bad.py", report["detail"]["failures"][0]["file"])
            self.assertFalse((src / "__pycache__").exists())
            self.assertEqual([], list(src.rglob("*.pyc")))

    def test_default_uat_branch_is_derived_from_runtime_version(self) -> None:
        self.assertEqual(uat_runtime.RUNTIME_VERSION, uat_runtime._DEFAULT_UAT_VERSION)
        self.assertEqual(
            f"release/{uat_runtime.RUNTIME_VERSION}-dev",
            uat_runtime._DEFAULT_UAT_BRANCH,
        )

    def test_version_files_check_covers_all_tracked_release_versions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_uat_version_files_") as tmp:
            project = Path(tmp)
            package = project / "noemaforge"
            (project / "docs").mkdir(parents=True)
            (package / "docs").mkdir(parents=True)
            for path in (
                project / "VERSION",
                project / "docs" / "VERSION",
                package / "VERSION",
                package / "docs" / "VERSION",
            ):
                path.write_text(uat_runtime.RUNTIME_VERSION + "\n", encoding="utf-8")

            report = uat_runtime._check_version_files(
                project, package, expected_version=uat_runtime.RUNTIME_VERSION,
            )

            self.assertTrue(report["ok"], report)
            self.assertIn("docs/VERSION", report["detail"]["files"])
            self.assertIn("noemaforge/docs/VERSION", report["detail"]["files"])

            (project / "docs" / "VERSION").write_text("0.0.0\n", encoding="utf-8")
            report = uat_runtime._check_version_files(
                project, package, expected_version=uat_runtime.RUNTIME_VERSION,
            )

            self.assertFalse(report["ok"], report)
            self.assertIn("version_mismatch:docs/VERSION", report["detail"]["failures"])

    def test_git_branch_check_reports_launch_error(self) -> None:
        with mock.patch.object(uat_runtime, "_run_check_command", side_effect=OSError("git unavailable")):
            report = uat_runtime._check_git_branch_and_clean(
                PACKAGE_ROOT.parent,
                expected_branch=uat_runtime._DEFAULT_UAT_BRANCH,
                timeout=5,
            )

        self.assertFalse(report["ok"], report)
        self.assertEqual("launch_error", report["detail"]["error"])

    def test_command_check_reports_launch_error(self) -> None:
        with mock.patch.object(uat_runtime, "_run_check_command", side_effect=OSError("cannot spawn")):
            report = uat_runtime._command_check(
                "sample",
                [sys.executable, "--version"],
                cwd=PACKAGE_ROOT.parent,
                timeout=5,
                message="sample command",
            )

        self.assertFalse(report["ok"], report)
        self.assertEqual("launch_error", report["detail"]["error"])

    def test_uat_check_report_fails_when_dev_import_is_missing(self) -> None:
        def fake_import(name: str):
            if name == "jsonschema":
                raise ModuleNotFoundError("jsonschema")
            return object()

        args = Namespace(
            root=str(PACKAGE_ROOT),
            project_root=str(PACKAGE_ROOT.parent),
            expected_branch=uat_runtime._DEFAULT_UAT_BRANCH,
            expected_version=uat_runtime.RUNTIME_VERSION,
            pytest_target=str(PACKAGE_ROOT / "tests" / "test_functional_branch_manifests.py"),
            collect_timeout=10,
            command_timeout=10,
            skip_git=True,
        )
        fake_command = uat_runtime._check_result("cmd", True)
        with mock.patch.object(uat_runtime, "_command_check", return_value=fake_command), \
                mock.patch.object(uat_runtime, "_check_compileall", return_value=uat_runtime._check_result("compileall_src", True)), \
                mock.patch.object(uat_runtime.importlib, "import_module", side_effect=fake_import):
            report = uat_runtime.build_uat_check_report(args)

        self.assertFalse(report["ok"])
        self.assertIn("dev_dependency_imports", report["summary"]["failed_ids"])
        imports = [check for check in report["checks"] if check["id"] == "dev_dependency_imports"][0]
        self.assertIn("jsonschema", imports["detail"]["missing"][0])
        self.assertIs(report["live_evidence_claimed"], False)

    def test_uat_check_report_uses_collect_docs_and_help_gates(self) -> None:
        calls = []

        def fake_command(check_id: str, cmd, **kwargs):
            calls.append((check_id, list(cmd), kwargs))
            return uat_runtime._check_result(check_id, True)

        args = Namespace(
            root=str(PACKAGE_ROOT),
            project_root=str(PACKAGE_ROOT.parent),
            expected_branch=uat_runtime._DEFAULT_UAT_BRANCH,
            expected_version=uat_runtime.RUNTIME_VERSION,
            pytest_target=str(PACKAGE_ROOT / "tests" / "test_functional_branch_manifests.py"),
            collect_timeout=10,
            command_timeout=10,
            skip_git=True,
        )
        with mock.patch.object(uat_runtime, "_command_check", side_effect=fake_command), \
                mock.patch.object(uat_runtime, "_check_compileall", return_value=uat_runtime._check_result("compileall_src", True)), \
                mock.patch.object(uat_runtime.importlib, "import_module", return_value=object()):
            report = uat_runtime.build_uat_check_report(args)

        self.assertTrue(report["ok"], report)
        self.assertEqual([item[0] for item in calls], ["pytest_collect", "docs_hygiene", "uat_runner_help"])
        collect_cmd = calls[0][1]
        self.assertEqual(collect_cmd[:4], [sys.executable, "-m", "pytest", "--collect-only"])
        self.assertIn("test_functional_branch_manifests.py", collect_cmd[-1])
        self.assertIn("docs_hygiene_runtime.py", calls[1][1][1])
        self.assertEqual(calls[2][1][-1], "--help")


if __name__ == "__main__":
    unittest.main()
