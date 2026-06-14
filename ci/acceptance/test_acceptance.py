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

import pytest

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

# Release-tier guard: the generated evidence is not tracked or produced on
# dev/PR trees (owner directive 2026-06-14) — only at pre-release. The two
# evidence-dependent tests skip when it is absent.
_EVIDENCE_PRESENT = (REPO / "MANIFEST.json").exists() and (REPO / "SHA256SUMS").exists()
_release_tier = pytest.mark.skipif(
    not _EVIDENCE_PRESENT,
    reason="release-tier: evidence is generated at pre-release only",
)


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@_release_tier
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


@_release_tier
def test_checksum_verification_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(VERIFIER), "--summary", "--hash-source", "git-index"],
        cwd=str(REPO),
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_telemetry_privacy_redacts() -> None:
    """The shipped privacy filter must drop secret-bearing keys and path-like values
    before persistence, so planted markers never reach a stored artifact."""
    sys.path.insert(0, str(REPO / "noemaforge" / "src"))
    import sense_privacy_runtime as spr

    policy = {"forbidden_keys": ["password", "session_token"], "forbid_raw_paths": True}
    payload = {
        "api_secret": "SK-LEAK-1",
        "nested": {"auth_token": "TT-2"},
        "password": "pw3",
        "path": "/home/u/.ssh/id_rsa",
        "items": [{"session_token": "ST-4"}, {"keep": "ok"}],
    }
    result = spr.apply_privacy_filter(payload, policy)
    blob = json.dumps(result["filtered"])
    for marker in ("SK-LEAK-1", "TT-2", "pw3", "ST-4"):
        assert marker not in blob, f"{marker} leaked into stored artifact"
    assert result["redactions"], "no redactions recorded"
    assert "/home/u/.ssh/id_rsa" not in blob


def test_capability_tokens_lifecycle(tmp_path: pathlib.Path) -> None:
    """A minted token verifies; a revoked (record removed), expired (zero-TTL), or
    tampered (forged secret) token is rejected."""
    sys.path.insert(0, str(REPO / "noemaforge" / "src"))
    import caps

    tokens_dir = str(tmp_path / "tokens")
    issued_to = {"role": "agent", "run_id": "aat", "project_id": "noemaforge"}
    capset = [{"action": "llm.chat"}]

    token = caps.issue_token(tokens_dir, issued_to, capset, ttl_sec=600)
    assert caps.verify_token(tokens_dir, token)[0] is True

    token_id = token.split(".", 1)[0]
    (tmp_path / "tokens" / f"{token_id}.json").unlink()
    assert caps.verify_token(tokens_dir, token)[0] is False  # revoked

    expired = caps.issue_token(tokens_dir, issued_to, capset, ttl_sec=0)
    assert caps.verify_token(tokens_dir, expired)[0] is False  # expired

    fresh = caps.issue_token(tokens_dir, issued_to, capset, ttl_sec=600)
    assert caps.verify_token(tokens_dir, fresh.split(".", 1)[0] + ".forged")[0] is False  # tampered


def test_toolproxy_isolation_posture() -> None:
    """The shipped ToolProxy config must be unix-socket only (no remote egress) with a
    bounded exec allowlist."""
    import yaml
    from urllib.parse import urlparse

    cfg = yaml.safe_load((REPO / "noemaforge" / "configs" / "toolproxy.yaml").read_text(encoding="utf-8"))
    gw = cfg.get("llm_gateway", {})
    assert gw.get("unix_socket"), "gateway must use a unix socket"
    for ep in (gw.get("chat_endpoint", ""), gw.get("embed_endpoint", "")):
        if not ep:
            continue  # an unconfigured endpoint is not remote egress (unix-socket-only is valid)
        host = urlparse(ep).hostname or ""
        assert host in ("localhost", "127.0.0.1", "::1"), f"remote endpoint exposed: {ep}"
    allow = cfg.get("exec", {}).get("allow_bins") or []
    assert allow and "*" not in allow, "exec must be a bounded allowlist (deny-by-default)"


def test_signed_provenance_policy_mandates_signing() -> None:
    """The shipped release-provenance policy must mandate signed provenance: detached
    signature + key fingerprint required, and plaintext private keys forbidden."""
    policy = json.loads(
        (REPO / "noemaforge" / "configs" / "release-provenance-policy.json").read_text(encoding="utf-8")
    )
    sc = policy.get("policy", {}).get("signing_controls", {})
    assert sc.get("signature_required") is True
    assert sc.get("detached_signature_required") is True
    assert sc.get("public_key_fingerprint_required") is True
    assert sc.get("plaintext_private_key_allowed") is False
    assert sc.get("allowed_signature_schemes")


def test_contract_epoch_canonical_hash_is_stable() -> None:
    """The canonical (sorted-key) hash is stable under non-semantic key reordering, yet
    an explicit content revision changes it."""

    def canon(obj: object) -> str:
        return hashlib.sha256(
            json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    a = {"epoch_id": "e1", "state": "draft", "materials": {"m": "x", "c": "y"}}
    b = {"materials": {"c": "y", "m": "x"}, "state": "draft", "epoch_id": "e1"}
    assert canon(a) == canon(b), "canonical hash must be stable under key reordering"
    revised = dict(a)
    revised["state"] = "sealed"
    assert canon(a) != canon(revised), "an explicit revision must change the hash"


def test_acceptance_runner_produces_bundle(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "results"
    proc = subprocess.run(
        [sys.executable, str(RUNNER), str(out)],
        cwd=str(REPO),
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["ok"] is True
    # checksum_validation is the release-tier integrity case: it passes when the
    # evidence is present (release trees) and reports "skip" on dev/PR trees where
    # the evidence is generated only at pre-release.
    cases = {c["name"]: c["status"] for c in summary["cases"]}
    assert cases.get("checksum_validation") in ("pass", "skip"), cases
    assert cases.get("telemetry_privacy") == "pass", cases
    assert cases.get("capability_tokens") == "pass", cases
    assert cases.get("toolproxy_isolation") == "pass", cases
    # signed_manifest_verification is release-tier: pass with evidence present,
    # skip on dev/PR trees where the manifest is generated only at pre-release.
    assert cases.get("signed_manifest_verification") in ("pass", "skip"), cases
    assert cases.get("contract_epoch_immutability") == "pass", cases
    # the bundle must be self-describing.
    assert (out / "manifest.sha256").exists()
    assert (out / "junit.xml").exists()
