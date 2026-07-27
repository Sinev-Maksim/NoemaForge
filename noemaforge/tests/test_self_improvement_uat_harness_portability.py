"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_self_improvement_uat_harness_portability.py
Zone: release/package
Purpose: Prove that the self-improvement UAT tracked-tree fingerprint is repository-root relative.
Inputs: Temporary Git repository and the packaged UAT harness source.
Outputs: Test assertions only.
Side effects: Temporary files under pytest tmp_path.
Tests: pytest -q noemaforge/tests/test_self_improvement_uat_harness_portability.py
Notes: UAT request findings resolution; no production repository mutation.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


HARNESS = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "uat"
    / "run-self-improvement-uat-preflight.sh"
)
FINGERPRINT_PIPE = (
    'git -C "$REPO_ROOT" ls-files -z | '
    '(cd "$REPO_ROOT" && xargs -0 -r sha256sum) | '
    "sha256sum | awk '{print $1}'"
)


def test_harness_uses_repository_root_for_both_fingerprints() -> None:
    text = HARNESS.read_text(encoding="utf-8")
    assert text.count(FINGERPRINT_PIPE) == 2


@pytest.mark.skipif(
    shutil.which("bash") is None
    or shutil.which("git") is None
    or shutil.which("sha256sum") is None,
    reason="requires bash, git and GNU sha256sum",
)
def test_fingerprint_runs_from_unrelated_working_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repository"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()

    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    tracked = repo / "tracked file.txt"
    tracked.write_text("first\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "--", tracked.name], check=True)

    env = dict(os.environ)
    env["REPO_ROOT"] = str(repo)

    first = subprocess.run(
        ["bash", "-lc", FINGERPRINT_PIPE],
        cwd=outside,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert re.fullmatch(r"[0-9a-f]{64}", first)

    tracked.write_text("second\n", encoding="utf-8")
    second = subprocess.run(
        ["bash", "-lc", FINGERPRINT_PIPE],
        cwd=outside,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()

    assert re.fullmatch(r"[0-9a-f]{64}", second)
    assert second != first
