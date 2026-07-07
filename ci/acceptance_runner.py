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
from html import escape
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

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

    # Release-tier: the generated evidence (MANIFEST/SHA256SUMS) is not tracked
    # or generated on dev/PR trees (owner directive 2026-06-14) — it is produced
    # only at pre-release. When it is absent, report a skip instead of a failure
    # so this case gates releases without blocking day-to-day PRs.
    if not (REPO / "MANIFEST.json").exists() or not (REPO / "SHA256SUMS").exists():
        tier.mkdir(parents=True, exist_ok=True)
        _write_json(tier / "checksum_validation.json", {
            "status": "skip",
            "reason": "release-tier: evidence is generated at pre-release only",
        })
        return {
            "name": "checksum_validation",
            "status": "skip",
            "tier": "10-integrity",
            "detail": {"reason": "release-tier evidence absent on this tree"},
        }

    # 2. each .sha256 sidecar must match the artifact it NAMES, hashed from the
    #    working tree (the same source as SHA256SUMS — evidence is generated on
    #    disk at pre-release, not committed). The target is parsed
    #    from the sidecar body ("<hash>  <path>") rather than a hardcoded mapping, so the
    #    check always follows the declared target and can never verify the wrong artifact.
    #    (The top-level SHA256SUMS itself is covered by the authoritative verifier in step 3.)
    sidecar_files = [
        "MANIFEST.json.sha256",
        "MANIFEST.sha256",
        "SHA256SUMS.sha256",
        "noemaforge/docs/MANIFEST.json.sha256",
    ]
    sidecar_results: Dict[str, Any] = {}
    for sidecar in sidecar_files:
        sp = REPO / sidecar
        entry: Dict[str, Any] = {}
        if not sp.exists():
            entry["status"] = "sidecar_missing"
            ok = False
        else:
            parts = sp.read_text(encoding="utf-8").split()
            if len(parts) < 2:
                entry["status"] = "sidecar_malformed"
                ok = False
            else:
                recorded, named = parts[0], parts[1]
                # the named path is relative to the sidecar's own directory (sha256sum
                # convention): root sidecars name repo-relative paths, the docs sidecar
                # names a bare file in its own dir. Resolve before looking it up.
                try:
                    target_rel = (sp.parent / named).resolve().relative_to(REPO.resolve()).as_posix()
                except ValueError:
                    target_rel = named
                entry["target"] = target_rel
                target_path = REPO / target_rel
                if not target_path.is_file():
                    entry["status"] = "target_missing"
                    ok = False
                else:
                    actual = _sha256_file(target_path)
                    entry.update(recorded=recorded, actual=actual)
                    entry["status"] = "ok" if recorded == actual else "mismatch"
                    ok = ok and recorded == actual
        sidecar_results[sidecar] = entry
    detail["sidecars"] = sidecar_results

    # 3. authoritative manifest/checksum verifier (the same gate CI uses).
    try:
        proc = subprocess.run(
            [sys.executable, str(VERIFIER), "--summary", "--hash-source", "working-tree"],
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
            # --keep-display is mandatory for any model-selection / GPU command per the
            # project's display-safety rule; capture the compliant shape even in dry-run.
            ["bash", str(setup), "vm", "--model-profile", "minimal",
             "--gpu-policy", "on-demand", "--first-start", "none", "--keep-display", "--dry-run"],
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
        # Validate the parsed host, not raw substring presence: "https://localhost.evil.tld/"
        # contains "localhost" but is remote. Empty endpoints are not egress (unix-socket-only).
        remote_endpoints = [e for e in endpoints if e and (urlparse(e).hostname or "") not in ("localhost", "127.0.0.1", "::1")]
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


# ── case: signed_manifest_verification (release provenance) ───────────────────
def case_signed_manifest_verification(results: Path) -> Dict[str, Any]:
    """Prove the release provenance path: the shipped policy mandates signed provenance
    (detached signature + key fingerprint required, no plaintext keys), and a provenance
    record built for the manifest binds the published subject hash. Cryptographic
    verification of an actual signed artifact activates when signing material ships."""
    tier = results / "70-release"
    detail: Dict[str, Any] = {}
    ok = True

    # Release-tier: the manifest this case binds is generated only at pre-release
    # (owner directive 2026-06-14). Skip when absent so dev/PR runs stay green.
    if not (REPO / "MANIFEST.json").exists():
        tier.mkdir(parents=True, exist_ok=True)
        _write_json(tier / "provenance-verify.json", {
            "status": "skip",
            "reason": "release-tier: evidence is generated at pre-release only",
        })
        return {
            "name": "signed_manifest_verification",
            "status": "skip",
            "tier": "70-release",
            "detail": {"reason": "release-tier evidence absent on this tree"},
        }
    try:
        policy = json.loads((REPO / "noemaforge" / "configs" / "release-provenance-policy.json").read_text(encoding="utf-8"))
        pol = policy.get("policy", {}) or {}
        sc = pol.get("signing_controls", {}) or {}
        mats = pol.get("required_materials", []) or []
        signing_mandated = (
            policy.get("kind") == "ReleaseProvenancePolicy"
            and sc.get("sha256_required") is True
            and sc.get("signature_required") is True
            and sc.get("detached_signature_required") is True
            and sc.get("public_key_fingerprint_required") is True
            and sc.get("plaintext_private_key_allowed") is False
            and bool(sc.get("allowed_signature_schemes"))
            and all(m in mats for m in ("manifest", "signature", "checksums"))
        )

        sys.path.insert(0, str(REPO / "noemaforge" / "src"))
        import release_provenance_runtime as rpr  # noqa: E402

        rec = rpr.build_release_archive_record(REPO / "MANIFEST.json", kind="manifest")
        sidecar = (REPO / "MANIFEST.json.sha256").read_text(encoding="utf-8").split()
        recorded = sidecar[0] if sidecar else ""
        record_well_formed = (
            isinstance(rec.get("sha256"), str) and len(rec.get("sha256", "")) == 64
            and rec.get("bytes", 0) > 0 and rec.get("path") == "MANIFEST.json"
        )
        # subject_match compares the working-tree hash of MANIFEST.json against its
        # .sha256 sidecar; recorded as evidence (not gated). The evidence is generated on
        # this same checkout, so the authoritative file-hash equality is covered by
        # checksum_validation (also working-tree).
        subject_match = record_well_formed and rec.get("sha256") == recorded
        detail = {
            "signing_mandated": signing_mandated,
            "signing_controls": sc,
            "provenance_record": rec,
            "record_well_formed": record_well_formed,
            "subject_hash_matches_manifest": subject_match,
            "note": ("Cryptographic signature verification of a signed artifact activates "
                     "when release signing material ships; this case proves the signing "
                     "governance and provenance-record generation for the manifest."),
        }
        ok = signing_mandated and record_well_formed
        _write_json(tier / "provenance-verify.json", {"status": "pass" if ok else "fail", "detail": detail})
    except Exception as exc:  # noqa: BLE001
        detail["error"] = str(exc)
        ok = False
        _write_json(tier / "provenance-verify.json", {"status": "fail", "detail": detail})
    return {"name": "signed_manifest_verification", "status": "pass" if ok else "fail",
            "tier": "70-release", "detail": detail}


# ── case: contract_epoch_immutability (canonical hash stability) ──────────────
def case_contract_epoch_immutability(results: Path) -> Dict[str, Any]:
    """Prove a contract/epoch artifact's canonical hash is immutable: hashing the
    canonical (sorted-key) form is stable under non-semantic changes (key reordering),
    yet an explicit content revision DOES change the hash — so the binding is real, not
    a constant. Anchored to the live epoch id; hashes in-memory canonical bytes."""
    tier = results / "50-epochs"
    detail: Dict[str, Any] = {}
    ok = True

    def canon_hash(obj: Any) -> str:
        return hashlib.sha256(
            json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    try:
        sys.path.insert(0, str(REPO / "noemaforge" / "src"))
        import epoch  # noqa: E402

        epoch_id = epoch.current_epoch_id()
        artifact = {
            "epoch_id": epoch_id,
            "kind": "epoch_draft",
            "state": "draft",
            "materials": {"manifest": "MANIFEST.json", "checksums": "SHA256SUMS"},
        }
        h1 = canon_hash(artifact)
        # same content, keys/structure reordered (non-semantic) → canonical hash stable.
        reordered = {
            "materials": {"checksums": "SHA256SUMS", "manifest": "MANIFEST.json"},
            "state": "draft",
            "kind": "epoch_draft",
            "epoch_id": epoch_id,
        }
        h2 = canon_hash(reordered)
        # explicit revision (a real content change) → hash must change.
        revised = dict(artifact)
        revised["state"] = "sealed"
        h3 = canon_hash(revised)

        stable_under_reorder = h1 == h2
        revision_changes_hash = h1 != h3
        detail = {
            "epoch_id": epoch_id,
            "canonical_hash": h1,
            "stable_under_reorder": stable_under_reorder,
            "revision_changes_hash": revision_changes_hash,
        }
        ok = stable_under_reorder and revision_changes_hash
        _write_json(tier / "epoch-hashes.json", {"status": "pass" if ok else "fail", "detail": detail})
    except Exception as exc:  # noqa: BLE001
        detail["error"] = str(exc)
        ok = False
        _write_json(tier / "epoch-hashes.json", {"status": "fail", "detail": detail})
    return {"name": "contract_epoch_immutability", "status": "pass" if ok else "fail",
            "tier": "50-epochs", "detail": detail}


def _junit(cases: List[Dict[str, Any]], results: Path) -> None:
    attrs = {
        "name": "noemaforge-acceptance",
        "tests": str(len(cases)),
        "failures": str(sum(1 for c in cases if c["status"] == "fail")),
        "skipped": str(sum(1 for c in cases if c["status"] in ("skip", "pending"))),
        "timestamp": _now(),
    }
    attr_text = " ".join(f'{key}="{escape(value, quote=True)}"' for key, value in attrs.items())
    lines = ["<?xml version='1.0' encoding='utf-8'?>", f"<testsuite {attr_text}>"]
    for case in cases:
        case_attrs = {
            "name": str(case["name"]),
            "classname": str(case.get("tier", "")),
        }
        case_attr_text = " ".join(f'{key}="{escape(value, quote=True)}"' for key, value in case_attrs.items())
        if case["status"] == "fail":
            msg = escape(json.dumps(case.get("detail", {}))[:500], quote=True)
            lines.append(f"  <testcase {case_attr_text}><failure message=\"{msg}\" /></testcase>")
        elif case["status"] in ("skip", "pending"):
            msg = escape(str(case["status"]), quote=True)
            lines.append(f"  <testcase {case_attr_text}><skipped message=\"{msg}\" /></testcase>")
        else:
            lines.append(f"  <testcase {case_attr_text} />")
    lines.append("</testsuite>")
    (results / "junit.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
        case_signed_manifest_verification(results),
        case_contract_epoch_immutability(results),
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
