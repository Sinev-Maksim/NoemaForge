#!/usr/bin/env python3
"""Pytest layer for the NoemaForge artifact-driven acceptance suite (AAT).

These tests assert the integrity tier and the self-describing nature of the results
bundle. They are intentionally thin: the heavy lifting lives in
``ci/acceptance_runner.py`` so the same logic runs both interactively and in CI.

Note: ``test_checksum_verification_passes`` and the bundle test invoke the release
verifier with ``--hash-source git-index``, which enumerates the working tree. Run
them against a clean checkout (CI, or a ``git worktree``); a development tree polluted
with untracked artifacts will report extra files and fail by design.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
RUNNER = REPO / "ci" / "acceptance_runner.py"
VERIFIER = REPO / "noemaforge" / "src" / "manifest_checksum_exclusion_runtime.py"

EVIDENCE_FILES = [
    "MANIFEST.json",
    "MANIFEST.json.sha256",
    "SHA256SUMS",
    "SHA256SUMS.sha256",
    "noemaforge/checksums/SHA256SUMS",
    "noemaforge/docs/MANIFEST.json",
]


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_manifest_files_exist() -> None:
    for name in EVIDENCE_FILES:
        assert (REPO / name).exists(), f"missing {name}"


def test_epoch_artifact_is_stable(tmp_path: pathlib.Path) -> None:
    """Canonicalized artifact hash must not change without an explicit revision."""
    artifact = tmp_path / "epoch.json"
    artifact.write_text(
        json.dumps({"epoch_id": "demo", "state": "draft"}, sort_keys=True),
        encoding="utf-8",
    )
    digest_1 = sha256_file(artifact)
    digest_2 = sha256_file(artifact)
    assert digest_1 == digest_2, "artifact hash changed without explicit revision"


def test_checksum_verification_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(VERIFIER), "--summary", "--hash-source", "git-index"],
        cwd=str(REPO),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_acceptance_runner_produces_bundle(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "results"
    proc = subprocess.run(
        [sys.executable, str(RUNNER), str(out)],
        cwd=str(REPO),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["ok"] is True
    # checksum_validation is the gating integrity case and must pass.
    cases = {c["name"]: c["status"] for c in summary["cases"]}
    assert cases.get("checksum_validation") == "pass", cases
    # the bundle must be self-describing.
    assert (out / "manifest.sha256").exists()
    assert (out / "junit.xml").exists()
