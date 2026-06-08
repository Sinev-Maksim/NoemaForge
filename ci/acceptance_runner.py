#!/usr/bin/env python3
"""NoemaForge artifact-driven acceptance harness (AAT).

Runs the acceptance suite and writes a verifiable outputs bundle under <results>/.
Unlike unit tests, every case ends in a saved, re-verifiable artifact so the suite
proves the *evidence chain*, not just that code executed.

Canonical results tree (created up-front, even for tiers not yet implemented):

    results/
      00-env/          environment capture
      10-integrity/    package/manifest/checksum integrity   (checksum_validation)
      20-install/      install dry-run + preflight            (best-effort)
      30-safety/       no-hidden-autostart / warmup modes     (pending slice)
      40-toolproxy/    capability tokens / isolation          (pending slice)
      50-epochs/       contract-epoch immutability            (pending slice)
      60-telemetry/    redaction-before-persistence           (pending slice)
      70-release/      signed manifest / provenance verify    (pending slice)
      summary.json     aggregate verdict + per-case status
      junit.xml        CI-consumable test report
      manifest.sha256  sha256 of every produced artifact (self-describing bundle)

Slice 1 implements the integrity tier end-to-end and best-effort install capture;
remaining tiers are recorded as ``pending`` so the bundle shape is stable while later
slices fill them in. The process exit code is non-zero only if an *implemented* case
fails, so the harness is safe to wire into CI immediately.

Usage:  python3 ci/acceptance_runner.py [results_dir]   (default: results)
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
VERIFIER = REPO / "noemaforge" / "src" / "manifest_checksum_exclusion_runtime.py"

TIERS = [
    "00-env",
    "10-integrity",
    "20-install",
    "30-safety",
    "40-toolproxy",
    "50-epochs",
    "60-telemetry",
    "70-release",
]

# Tiers populated by future slices; listed so the bundle advertises them as pending
# rather than silently omitting them.
PENDING_CASES = [
    ("no_hidden_autostart", "30-safety"),
    ("model_warmup_modes", "30-safety"),
    ("contract_epoch_immutability", "50-epochs"),
    ("signed_manifest_verification", "70-release"),
]


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_index_hashes() -> Dict[str, str]:
    """Reuse the release verifier's canonical (LF-blob) hashing so integrity is
    platform-independent and matches how SHA256SUMS was generated."""
    sys.path.insert(0, str(REPO / "noemaforge" / "src"))
    import manifest_checksum_exclusion_runtime as mcx  # noqa: E402

    return mcx._git_index_hashes(REPO)


# ── case: environment capture ────────────────────────────────────────────────
def case_env(results: Path) -> Dict[str, Any]:
    env = {
        "timestamp": _now(),
        "cwd": str(REPO),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "uname": " ".join(platform.uname()),
    }
    (results / "00-env" / "env.txt").write_text(
        "".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8"
    )
    _write_json(results / "00-env" / "env.json", env)
    return {"name": "environment_capture", "status": "pass", "tier": "00-env", "detail": env}


# ── case: checksum_validation ────────────────────────────────────────────────
def case_checksum_validation(results: Path) -> Dict[str, Any]:
    tier = results / "10-integrity"
    detail: Dict[str, Any] = {}
    ok = True

    # 1. canonical blob hashes (git-index), same source as SHA256SUMS.
    try:
        index = _git_index_hashes()
    except Exception as exc:  # noqa: BLE001
        index = {}
        detail["index_error"] = str(exc)
        ok = False

    # 2. .sha256 sidecars must match their targets.
    sidecars = {
        "MANIFEST.json.sha256": "MANIFEST.json",
        "SHA256SUMS.sha256": "noemaforge/checksums/SHA256SUMS",
        "noemaforge/docs/MANIFEST.json.sha256": "noemaforge/docs/MANIFEST.json",
    }
    sidecar_results: Dict[str, Any] = {}
    for sidecar, target in sidecars.items():
        sp = REPO / sidecar
        entry: Dict[str, Any] = {"target": target}
        if not sp.exists():
            entry["status"] = "sidecar_missing"
            ok = False
        elif target not in index:
            entry["status"] = "target_untracked"
            ok = False
        else:
            recorded = sp.read_text(encoding="utf-8").split()[0] if sp.read_text(encoding="utf-8").split() else ""
            actual = index[target]
            entry.update(recorded=recorded, actual=actual)
            entry["status"] = "ok" if recorded == actual else "mismatch"
            ok = ok and recorded == actual
        sidecar_results[sidecar] = entry
    detail["sidecars"] = sidecar_results

    # 3. authoritative manifest/checksum verifier (the same gate CI uses).
    try:
        proc = subprocess.run(
            [sys.executable, str(VERIFIER), "--summary", "--hash-source", "git-index"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        report = json.loads(proc.stdout)
        _write_json(tier / "verifier-report.json", report)
        detail["verifier"] = {
            "ok": report.get("ok"),
            "metrics": report.get("metrics"),
            "failures": report.get("failures", []),
        }
        ok = ok and bool(report.get("ok"))
    except Exception as exc:  # noqa: BLE001
        detail["verifier"] = {"error": str(exc)}
        ok = False

    _write_json(tier / "checksum_validation.json", {"status": "pass" if ok else "fail", "detail": detail})
    # human-readable summary
    lines = ["=== NoemaForge AAT checksum_validation ==="]
    for sidecar, entry in sidecar_results.items():
        lines.append(f"sidecar {sidecar}: {entry['status']}")
    lines.append(f"verifier ok: {detail.get('verifier', {}).get('ok')}")
    lines.append(f"overall: {'OK' if ok else 'FAIL'}")
    (tier / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "name": "checksum_validation",
        "status": "pass" if ok else "fail",
        "tier": "10-integrity",
        "detail": detail,
    }


# ── case: install_dry_run (best-effort) ──────────────────────────────────────
def case_install_dry_run(results: Path) -> Dict[str, Any]:
    """Capture a setup dry-run when the platform supports it. This is evidence
    capture, not a gate: it is recorded as ``skip`` (never ``fail``) when the
    environment cannot run it, so the harness stays green on a bare checkout."""
    tier = results / "20-install"
    setup = REPO / "setup.sh"
    if sys.platform.startswith("win") or not setup.exists():
        note = {"status": "skip", "reason": "setup.sh dry-run requires a POSIX shell"}
        _write_json(tier / "setup-dry-run.json", note)
        return {"name": "install_dry_run", "status": "skip", "tier": "20-install", "detail": note}
    try:
        proc = subprocess.run(
            ["bash", str(setup), "vm", "--model-profile", "minimal",
             "--gpu-policy", "on-demand", "--first-start", "none", "--dry-run"],
            cwd=str(REPO), capture_output=True, text=True, timeout=300, check=False,
        )
        (tier / "setup-dry-run.txt").write_text(proc.stdout + proc.stderr, encoding="utf-8")
        note = {"status": "captured", "returncode": proc.returncode}
    except Exception as exc:  # noqa: BLE001
        note = {"status": "skip", "reason": str(exc)}
    _write_json(tier / "setup-dry-run.json", note)
    # best-effort capture is never a hard failure
    return {"name": "install_dry_run", "status": "skip" if note["status"] != "captured" else "pass",
            "tier": "20-install", "detail": note}


# ── case: telemetry_privacy (redaction-before-persistence) ───────────────────
def case_telemetry_privacy(results: Path) -> Dict[str, Any]:
    """Prove the privacy filter redacts sensitive fields before an event/report is
    persisted: planted secret markers and path-like values must not survive into the
    stored artifact. Exercises the shipped ``sense_privacy_runtime`` filter, so this is
    real redaction (not a stub)."""
    tier = results / "60-telemetry"
    detail: Dict[str, Any] = {}
    ok = True
    markers = ["SK-LEAK-AKIA0001", "Bearer-TT-77", "hunter2pw", "ST-SESSION-9"]
    try:
        sys.path.insert(0, str(REPO / "noemaforge" / "src"))
        import sense_privacy_runtime as spr  # noqa: E402

        policy = {"forbidden_keys": ["password", "session_token"], "forbid_raw_paths": True}
        payload = {
            "event": "telemetry.sample",
            "api_secret": markers[0],
            "nested": {"auth_token": markers[1], "ok_field": "kept"},
            "password": markers[2],
            "home_path": "/home/operator/.ssh/id_rsa",
            "items": [{"session_token": markers[3]}, {"value": "kept"}],
        }
        result = spr.apply_privacy_filter(payload, policy)
        blob = json.dumps(result["filtered"], ensure_ascii=False)
        leaked = [m for m in markers if m in blob]
        forbidden_present = [k for k in ("api_secret", "auth_token", "password", "session_token") if k in blob]
        detail = {
            "redactions": len(result["redactions"]),
            "leaked_markers": leaked,
            "forbidden_keys_present": forbidden_present,
            "path_redacted": "/home/operator/.ssh/id_rsa" not in blob,
        }
        ok = not leaked and not forbidden_present and bool(result["redactions"]) and detail["path_redacted"]
        _write_json(
            tier / "redaction-check.json",
            {"status": "pass" if ok else "fail", "policy": policy,
             "filtered": result["filtered"], "redactions": result["redactions"], "detail": detail},
        )
    except Exception as exc:  # noqa: BLE001
        detail["error"] = str(exc)
        ok = False
        _write_json(tier / "redaction-check.json", {"status": "fail", "detail": detail})
    return {"name": "telemetry_privacy", "status": "pass" if ok else "fail",
            "tier": "60-telemetry", "detail": detail}


# ── case: capability_tokens (binding + revocation) ───────────────────────────
def case_capability_tokens(results: Path) -> Dict[str, Any]:
    """Prove capability tokens bind and revoke: a freshly minted token verifies, but
    a revoked (record removed), expired (zero-TTL), or tampered (wrong secret) token is
    rejected. Exercises the shipped ``caps`` token store in an isolated temp dir."""
    tier = results / "40-toolproxy"
    detail: Dict[str, Any] = {}
    ok = True
    tokens_dir = tempfile.mkdtemp(prefix="aat-caps-")
    try:
        sys.path.insert(0, str(REPO / "noemaforge" / "src"))
        import caps  # noqa: E402

        issued_to = {"role": "agent", "run_id": "aat-run", "project_id": "noemaforge"}
        capset = [{"action": "llm.chat"}]

        # 1. allowed: a freshly minted token verifies.
        token = caps.issue_token(tokens_dir, issued_to, capset, ttl_sec=600)
        ok1, rec1, why1 = caps.verify_token(tokens_dir, token)
        # 2. revoked: removing the record rejects the bearer.
        token_id = token.split(".", 1)[0]
        os.remove(os.path.join(tokens_dir, token_id + ".json"))
        ok2, _, why2 = caps.verify_token(tokens_dir, token)
        # 3. expired: a zero-TTL token is rejected.
        expired = caps.issue_token(tokens_dir, issued_to, capset, ttl_sec=0)
        ok3, _, why3 = caps.verify_token(tokens_dir, expired)
        # 4. tampered: a valid token_id with a forged secret is rejected.
        fresh = caps.issue_token(tokens_dir, issued_to, capset, ttl_sec=600)
        ok4, _, why4 = caps.verify_token(tokens_dir, fresh.split(".", 1)[0] + ".forged-secret")

        detail = {
            "allowed": {"accepted": ok1, "reason": why1, "epoch_id": (rec1 or {}).get("epoch_id")},
            "revoked": {"accepted": ok2, "reason": why2},
            "expired": {"accepted": ok3, "reason": why3},
            "tampered": {"accepted": ok4, "reason": why4},
        }
        ok = ok1 and not ok2 and not ok3 and not ok4
        _write_json(tier / "token-lifecycle.json", {"status": "pass" if ok else "fail", "detail": detail})
    except Exception as exc:  # noqa: BLE001
        detail["error"] = str(exc)
        ok = False
        _write_json(tier / "token-lifecycle.json", {"status": "fail", "detail": detail})
    finally:
        shutil.rmtree(tokens_dir, ignore_errors=True)
    return {"name": "capability_tokens", "status": "pass" if ok else "fail",
            "tier": "40-toolproxy", "detail": detail}


# ── case: toolproxy_isolation (local isolation posture) ──────────────────────
def case_toolproxy_isolation(results: Path) -> Dict[str, Any]:
    """Prove the shipped ToolProxy config is locally isolated and deny-by-default:
    the LLM gateway is reached over a UNIX socket (no remote host:port egress),
    executable access is a bounded allowlist (not open), and capability enforcement
    is on. A regression that opens remote HTTP or an unbounded exec surface fails here."""
    tier = results / "40-toolproxy"
    cfg_path = REPO / "noemaforge" / "configs" / "toolproxy.yaml"
    detail: Dict[str, Any] = {}
    ok = True
    try:
        import yaml  # noqa: E402

        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        gw = cfg.get("llm_gateway", {}) or {}
        execp = cfg.get("exec", {}) or {}
        enf = cfg.get("enforcement", {}) or {}

        endpoints = [str(gw.get("chat_endpoint", "")), str(gw.get("embed_endpoint", ""))]
        remote_endpoints = [e for e in endpoints if e and "localhost" not in e and "127.0.0.1" not in e]
        allow_bins = execp.get("allow_bins") or []
        gateway_unix = bool(gw.get("unix_socket"))
        exec_allowlisted = isinstance(allow_bins, list) and len(allow_bins) > 0 and "*" not in allow_bins
        enforcement_on = bool(enf.get("require_stream_id")) and bool(enf.get("enforce_issued_to_match_meta"))

        detail = {
            "gateway_unix_socket": gateway_unix,
            "remote_http_endpoints": remote_endpoints,
            "exec_allowlist": allow_bins,
            "exec_allowlisted_not_open": exec_allowlisted,
            "enforcement_on": enforcement_on,
            "log_denies": bool((cfg.get("logging") or {}).get("log_denies")),
        }
        ok = gateway_unix and not remote_endpoints and exec_allowlisted and enforcement_on
        _write_json(tier / "isolation.json", {"status": "pass" if ok else "fail", "detail": detail})
    except Exception as exc:  # noqa: BLE001
        detail["error"] = str(exc)
        ok = False
        _write_json(tier / "isolation.json", {"status": "fail", "detail": detail})
    return {"name": "toolproxy_isolation", "status": "pass" if ok else "fail",
            "tier": "40-toolproxy", "detail": detail}


def _junit(cases: List[Dict[str, Any]], results: Path) -> None:
    suite = ET.Element("testsuite", name="noemaforge-acceptance",
                       tests=str(len(cases)),
                       failures=str(sum(1 for c in cases if c["status"] == "fail")),
                       skipped=str(sum(1 for c in cases if c["status"] in ("skip", "pending"))),
                       timestamp=_now())
    for case in cases:
        tc = ET.SubElement(suite, "testcase", name=case["name"], classname=case.get("tier", ""))
        if case["status"] == "fail":
            ET.SubElement(tc, "failure", message=json.dumps(case.get("detail", {}))[:500])
        elif case["status"] in ("skip", "pending"):
            ET.SubElement(tc, "skipped", message=case["status"])
    ET.ElementTree(suite).write(str(results / "junit.xml"), encoding="utf-8", xml_declaration=True)


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    results = REPO / (argv[0] if argv else "results")
    for tier in TIERS:
        (results / tier).mkdir(parents=True, exist_ok=True)

    cases: List[Dict[str, Any]] = [
        case_env(results),
        case_checksum_validation(results),
        case_install_dry_run(results),
        case_capability_tokens(results),
        case_toolproxy_isolation(results),
        case_telemetry_privacy(results),
    ]
    for name, tier in PENDING_CASES:
        cases.append({"name": name, "status": "pending", "tier": tier,
                      "detail": {"reason": "implemented by a later AAT slice"}})

    implemented_fail = [c for c in cases if c["status"] == "fail"]
    summary = {
        "apiVersion": "noemaforge.acceptance/v1",
        "generated": _now(),
        "ok": not implemented_fail,
        "counts": {
            "pass": sum(1 for c in cases if c["status"] == "pass"),
            "fail": len(implemented_fail),
            "skip": sum(1 for c in cases if c["status"] == "skip"),
            "pending": sum(1 for c in cases if c["status"] == "pending"),
        },
        "cases": cases,
    }
    _write_json(results / "summary.json", summary)
    _junit(cases, results)

    # self-describing bundle: hash every artifact except the manifest itself.
    manifest_lines = []
    for path in sorted(results.rglob("*")):
        if path.is_file() and path.name != "manifest.sha256":
            rel = path.relative_to(results).as_posix()
            manifest_lines.append(f"{_sha256_file(path)}  {rel}")
    (results / "manifest.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    print(json.dumps({"ok": summary["ok"], "counts": summary["counts"],
                      "results": str(results)}, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
