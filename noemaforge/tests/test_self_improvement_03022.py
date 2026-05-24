"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_self_improvement_03022.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "noemaforge"


def env_for(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["NOEMAFORGE_ROOT"] = str(ROOT)
    env["NOEMAFORGE_PIPELINE_STATE"] = str(tmp_path / "pipelines")
    env["NOEMAFORGE_PERSONA_STATE"] = str(tmp_path / "personas")
    env["NOEMAFORGE_TESTBENCH_STATE"] = str(tmp_path / "testbench")
    env["NOEMAFORGE_WIKI_PATCH_STATE"] = str(tmp_path / "wiki_patches")
    env["NOEMAFORGE_ALLOW_DEGRADED_MUTATION"] = "1"
    return env


def test_testbench_catalog_and_quick_run(tmp_path: Path) -> None:
    env = env_for(tmp_path)
    catalog = subprocess.check_output([str(CLI), "testbench", "catalog", "--json", "--root", str(ROOT), "--state", str(tmp_path / "testbench")], text=True, env=env)
    cat = json.loads(catalog)
    assert cat["ok"] is True
    assert cat["case_count"] >= 10
    out_dir = tmp_path / "quick"
    summary_raw = subprocess.check_output([str(CLI), "testbench", "run", "--suite", "quick", "--out-dir", str(out_dir), "--state", str(tmp_path / "testbench_state"), "--root", str(ROOT), "--json"], text=True, env=env)
    report = json.loads(summary_raw)
    assert report["summary"]["ok"] is True
    assert report["summary"]["failed"] == 0
    assert (out_dir / "selftest-report.json").exists()
    result_files = sorted(out_dir.glob("cases/*/repeat_1/result.json"))
    assert result_files
    first_case = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert "metrics" in first_case
    assert "duration_sec" in first_case["metrics"]
    assert "max_rss_kib" in first_case["metrics"]


def test_wiki_patch_bundle_create_and_apply_dry_run(tmp_path: Path) -> None:
    env = env_for(tmp_path)
    wiki_repo = tmp_path / "wiki"
    wiki_repo.mkdir()
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps({"failed": 1, "duration_ms_total": 100.0}), encoding="utf-8")
    after.write_text(json.dumps({"failed": 0, "duration_ms_total": 90.0}), encoding="utf-8")
    created_raw = subprocess.check_output([
        str(CLI), "wiki-patch", "create",
        "--wiki-repo", str(wiki_repo),
        "--source-root", str(ROOT),
        "--state", str(tmp_path / "wiki_patches"),
        "--title", "pytest wiki patch",
        "--description", "pytest functional change",
        "--metrics-before", str(before),
        "--metrics-after", str(after),
        "--include", "docs/wiki/README.md",
        "--json",
    ], text=True, env=env)
    created = json.loads(created_raw)
    assert created["ok"] is True
    patch_dir = Path(created["patch_dir"])
    assert (patch_dir / "functional_delta.md").exists()
    assert (patch_dir / "metrics_delta.json").exists()
    assert (patch_dir / "patch.diff").exists()
    dry = subprocess.check_output([str(CLI), "wiki-patch", "apply", "--patch-dir", str(patch_dir), "--wiki-repo", str(wiki_repo), "--dry-run"], text=True, env=env)
    assert json.loads(dry)["dry_run"] is True


def test_self_improvement_configs_are_packaged() -> None:
    for rel in [
        "configs/test-matrix.json",
        "configs/telemetry-policy.json",
        "configs/self-improvement-policy.json",
    ]:
        path = ROOT / rel
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] in {"0.30.22", "0.31.0", (ROOT / "VERSION").read_text(encoding="utf-8").strip()}
