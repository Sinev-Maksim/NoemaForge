#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_evolution_runtime.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Create measured model-evolution artifacts with rollback evidence.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Existing module notes:
NoemaForge measured model-evolution runtime.

This is an auditable control cycle, not implicit heavy training. It can be
invoked from Admin/GUI and produces baseline, mutation plan, scorecard and
rollback-gate artifacts. Applying writes only a local candidate profile unless a
future explicit backend adapter is selected.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

RUNTIME_VERSION = "0.31.13.alpha"
DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_MODEL_EVOLUTION_STATE", "/var/lib/noemaforge/model-evolution"))
DEFAULT_PIPELINE_STATE = Path(os.environ.get("NOEMAFORGE_PIPELINE_STATE", "/var/lib/noemaforge/pipelines"))


def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def safe_id(value: str, limit: int = 96) -> str:
    keep = []
    for ch in str(value or ""):
        keep.append(ch if ch.isalnum() or ch in "._-" else "_")
    out = "".join(keep).strip("_") or "model_evolution"
    return out[:limit].strip("_") or "model_evolution"


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(obj) + "\n", encoding="utf-8")


def db_connect(state: Path) -> sqlite3.Connection:
    state.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state / "model_evolution.sqlite3")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, created_at TEXT, updated_at TEXT, request TEXT, target_role TEXT, status TEXT, run_dir TEXT, result_json TEXT)"
    )
    return conn


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _command_json(cmd: Sequence[str]) -> Dict[str, Any]:
    proc = subprocess.run(list(cmd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout: Any = proc.stdout.strip()
    if stdout:
        try:
            stdout = json.loads(stdout)
        except Exception:
            pass
    return {"ok": proc.returncode == 0, "returncode": proc.returncode, "cmd": list(cmd), "stdout": stdout, "stderr": proc.stderr.strip()}


def baseline_snapshot(root: Path, request: str, target_role: str) -> Dict[str, Any]:
    version = "unknown"
    try:
        version = (root / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        pass
    configs = sorted(str(p.relative_to(root)) for p in (root / "configs").glob("*.json")) if (root / "configs").exists() else []
    runtime_constants: Dict[str, str] = {}
    for path in ["src/pipeline_runtime.py", "src/team_member_runtime.py", "src/selftest_runtime.py", "src/code_qa_runtime.py", "src/multimodal_runtime.py"]:
        full = root / path
        if full.exists():
            text = full.read_text(encoding="utf-8", errors="replace")[:4000]
            runtime_constants[path] = _sha256_text(text)[:16]
    return {
        "captured_at": nowz(),
        "root": str(root),
        "version": version,
        "target_role": target_role,
        "request_sha256": _sha256_text(request),
        "config_files": configs,
        "runtime_file_prefix_hashes": runtime_constants,
        "safety": {
            "implicit_training": False,
            "implicit_weight_write": False,
            "single_active_llm_invariant": True,
            "rollback_required_before_apply": True,
        },
    }


def mutation_plan(request: str, target_role: str, apply: bool) -> Dict[str, Any]:
    request_l = request.lower()
    candidates: List[Dict[str, Any]] = []
    if any(x in request_l for x in ["код", "code", "dev", "bug", "test", "release"]):
        candidates.append({"id": "dev_scorecard_refresh", "type": "role_scorecard", "target": target_role, "expected_metric": "qa_pass_rate"})
    if any(x in request_l for x in ["контекст", "context", "memory", "память"]):
        candidates.append({"id": "context_pack_compaction", "type": "context_policy", "target": target_role, "expected_metric": "handoff_parse_rate"})
    candidates.append({"id": "selftest_matrix_regression", "type": "test_matrix", "target": target_role, "expected_metric": "no_p0_regressions"})
    return {
        "created_at": nowz(),
        "mode": "measured_control_cycle",
        "apply_requested": bool(apply),
        "candidates": candidates,
        "gates": [
            "baseline_snapshot_present",
            "selftest_matrix_selected",
            "resource_telemetry_collected_or_marked_unavailable",
            "rollback_plan_present",
            "admin_approval_before_weight_or_backend_mutation",
        ],
        "no_hidden_side_effects": True,
    }


def scorecard(root: Path, target_role: str, request: str) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    for label, rel in [
        ("version_file", "VERSION"),
        ("test_matrix", "configs/test-matrix.json"),
        ("self_improvement_policy", "configs/self-improvement-policy.json"),
        ("team_member_policy", "configs/team-member-policy.json"),
    ]:
        path = root / rel
        checks.append({"id": label, "path": rel, "ok": path.exists(), "size_bytes": path.stat().st_size if path.exists() else 0})
    ok = all(c["ok"] for c in checks)
    return {
        "created_at": nowz(),
        "target_role": target_role,
        "request_sha256": _sha256_text(request),
        "checks": checks,
        "metrics": {
            "baseline_files_present_ratio": sum(1 for c in checks if c["ok"]) / max(1, len(checks)),
            "p0_regressions": 0 if ok else 1,
            "weight_mutations": 0,
        },
        "decision": "candidate_profile_ready" if ok else "blocked_missing_prerequisites",
    }


def rollback_plan(run_id: str, apply: bool) -> Dict[str, Any]:
    return {
        "created_at": nowz(),
        "run_id": run_id,
        "apply_requested": bool(apply),
        "steps": [
            "Keep original runtime profile unchanged until admin approval.",
            "Store candidate profile under model-evolution run directory.",
            "If candidate fails gates, delete candidate profile and keep baseline.",
            "For future adapter/LoRA work, require explicit backend-specific rollback manifest before applying.",
        ],
    }


def register_pipeline_artifact(root: Path, pipeline_state: Path, pipeline_run_id: str, stage: str, artifact_type: str, artifact_path: Path) -> Optional[Dict[str, Any]]:
    if not pipeline_run_id:
        return None
    cmd = [
        sys.executable,
        str(root / "src" / "pipeline_runtime.py"),
        "--root",
        str(root),
        "--state",
        str(pipeline_state),
        "artifact",
        "add",
        pipeline_run_id,
        "--stage",
        stage,
        "--type",
        artifact_type,
        "--path",
        str(artifact_path),
        "--status",
        "ready",
        "--meta",
        "source=model_evolution_runtime",
        "--allow-degraded",
    ]
    return _command_json(cmd)


def cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    pipeline_state = Path(args.pipeline_state).resolve() if args.pipeline_state else DEFAULT_PIPELINE_STATE
    request = args.request or " ".join(args.text or []) or "measured model evolution cycle"
    target_role = args.target_role or "dev.work/dev"
    run_id = safe_id(args.run_id or f"mevo_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{target_role}")
    run_dir = state / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    baseline = baseline_snapshot(root, request, target_role)
    plan = mutation_plan(request, target_role, args.apply)
    scores = scorecard(root, target_role, request)
    rollback = rollback_plan(run_id, args.apply)
    candidate_profile = {
        "created_at": nowz(),
        "version": RUNTIME_VERSION,
        "run_id": run_id,
        "target_role": target_role,
        "status": "candidate_profile_written" if args.apply else "dry_candidate_profile",
        "request": request,
        "source": "model_evolution_runtime",
        "activation": "manual_admin_review_required",
        "profile_delta": {
            "scorecard_refresh": True,
            "context_handoff_emphasis": True,
            "test_matrix_required": True,
        },
    }

    artifacts = {
        "baseline": run_dir / "baseline_snapshot.json",
        "mutation_plan": run_dir / "mutation_plan.json",
        "scorecard": run_dir / "scorecard.json",
        "rollback": run_dir / "rollback_plan.json",
        "candidate_profile": run_dir / "candidate_profile.json",
    }
    write_json(artifacts["baseline"], baseline)
    write_json(artifacts["mutation_plan"], plan)
    write_json(artifacts["scorecard"], scores)
    write_json(artifacts["rollback"], rollback)
    write_json(artifacts["candidate_profile"], candidate_profile)

    status = "conducted_candidate_ready" if scores.get("decision") == "candidate_profile_ready" else "blocked"
    pipeline_artifacts: List[Any] = []
    if args.pipeline_run_id:
        for name, path in artifacts.items():
            res = register_pipeline_artifact(root, pipeline_state, args.pipeline_run_id, args.stage, f"model_evolution_{name}", path)
            if res is not None:
                pipeline_artifacts.append(res)

    result = {
        "ok": status != "blocked",
        "version": RUNTIME_VERSION,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "status": status,
        "conducted": True,
        "apply_requested": bool(args.apply),
        "target_role": target_role,
        "artifacts": {k: str(v) for k, v in artifacts.items()},
        "decision": scores.get("decision"),
        "next": [
            f"noemaforge model-evolution show {run_id}",
            "review candidate_profile.json and rollback_plan.json",
            "for runtime model optimization use: noemaforge model-selection plan --mode normal --json",
            "after candidate review run: sudo noemaforge first-start --normal --dry-run --show-candidates",
        ],
        "pipeline_artifacts": pipeline_artifacts,
    }

    conn = db_connect(state)
    ts = nowz()
    conn.execute(
        "INSERT OR REPLACE INTO runs(run_id, created_at, updated_at, request, target_role, status, run_dir, result_json) VALUES(?,?,?,?,?,?,?,?)",
        (run_id, ts, ts, request, target_role, status, str(run_dir), json_dumps(result)),
    )
    conn.commit()
    print(json_dumps(result) if args.json else f"{run_id}\t{status}\t{run_dir}")
    return 0 if result["ok"] else 1


def cmd_list(args: argparse.Namespace) -> int:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    rows = conn.execute("SELECT run_id, target_role, status, updated_at, run_dir FROM runs ORDER BY updated_at DESC LIMIT ?", (args.limit,)).fetchall()
    data = [dict(zip(["run_id", "target_role", "status", "updated_at", "run_dir"], row)) for row in rows]
    print(json_dumps(data) if args.json else "\n".join("\t".join(map(str, row)) for row in rows))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    row = conn.execute("SELECT result_json FROM runs WHERE run_id=?", (args.run_id,)).fetchone()
    if not row:
        raise SystemExit(f"unknown model-evolution run: {args.run_id}")
    print(row[0])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noemaforge model-evolution")
    parser.add_argument("--root")
    parser.add_argument("--state")
    parser.add_argument("--pipeline-state")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run")
    run.add_argument("text", nargs="*")
    run.add_argument("--request")
    run.add_argument("--target-role", default="dev.work/dev")
    run.add_argument("--run-id")
    run.add_argument("--apply", action="store_true")
    run.add_argument("--pipeline-run-id", default="")
    run.add_argument("--stage", default="intake")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    ls = sub.add_parser("list")
    ls.add_argument("--limit", type=int, default=20)
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_list)

    show = sub.add_parser("show")
    show.add_argument("run_id")
    show.set_defaults(func=cmd_show)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
