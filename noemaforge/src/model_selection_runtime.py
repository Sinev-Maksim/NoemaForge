#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_selection_runtime.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Create and manage model-selection plans and epoch candidate artifacts.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Existing module notes:
NoemaForge model-selection control-plane runtime.

This is a lightweight GUI/CLI bridge for 0.31.13.alpha. It creates an
operator-reviewable plan for first-start model optimization and, on apply,
writes an epoch-switch request artifact. Actual heavy selection is performed by
`sudo noemaforge first-start --<mode>`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

RUNTIME_VERSION = "0.31.13.alpha"
DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_MODEL_SELECTION_STATE", os.environ.get("NOEMAFORGE_MODEL_EVOLUTION_STATE", "/var/lib/noemaforge/model-selection")))


def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def safe_id(value: str, limit: int = 96) -> str:
    out = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "")).strip("_") or "model_selection"
    return out[:limit].strip("_") or "model_selection"


def normalize_mode(value: str) -> str:
    value = str(value or "normal").strip().lower().replace("-", "_")
    aliases = {"composite": "full_composite", "fullcomposite": "full_composite"}
    value = aliases.get(value, value)
    return value if value in {"fast", "normal", "full", "full_composite"} else "normal"


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(dumps(obj) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def mode_command(mode: str, composite_top_n: int, *, dry_run: bool = True, show: bool = True) -> str:
    if mode == "full_composite":
        base = f"sudo noemaforge first-start --full_composite {int(composite_top_n)}"
    else:
        base = f"sudo noemaforge first-start --{mode}"
    flags = []
    if dry_run:
        flags.append("--dry-run")
    if show:
        flags.append("--show-candidates")
        if mode == "full_composite":
            flags.append("--show-compositions")
    return " ".join([base, *flags])


def plan_doc(request: str, mode: str, scope: str, composite_top_n: int, apply: bool) -> Dict[str, Any]:
    return {
        "apiVersion": "noemaforge.model-selection/v1",
        "kind": "ModelSelectionChatPlan",
        "version": RUNTIME_VERSION,
        "created_at": nowz(),
        "request": request,
        "scope": scope or "active runtime",
        "mode": mode,
        "composite_top_n": int(composite_top_n),
        "apply_requested": bool(apply),
        "two_step_epoch_switch": True,
        "contract": {
            "fast": "first suitable measured candidate is accepted; QA != Developer; no composite testing",
            "normal": "retain at least two suitable candidates when available; choose best; QA != Developer; no composite testing",
            "full": "evaluate all available runnable models; choose best; QA != Developer; no composite testing",
            "full_composite": "evaluate all models, then evaluate/plan role compositions from top N candidates; N=0 means no top-limit before safety cap",
        },
        "commands": {
            "show_candidates": mode_command(mode, composite_top_n, dry_run=True, show=True),
            "apply_epoch": mode_command(mode, composite_top_n, dry_run=False, show=True),
        },
        "required_confirmation": "apply" if not apply else "operator explicitly requested apply, but epoch switch still requires sudo first-start command",
    }


def cmd_plan(args: argparse.Namespace) -> int:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    mode = normalize_mode(args.mode)
    run_id = safe_id(args.run_id or f"msel_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{mode}")
    run_dir = state / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    request = args.request or " ".join(args.text or []) or "model optimization"
    plan = plan_doc(request, mode, args.scope, args.composite_top_n, args.apply)
    rollback = {
        "apiVersion": "noemaforge.model-selection/v1",
        "kind": "ChatEpochRollbackPlan",
        "version": RUNTIME_VERSION,
        "created_at": nowz(),
        "run_id": run_id,
        "steps": [
            "Review candidate-selection-plan.json before applying.",
            "Keep current epoch id before any switch.",
            "If smoke fails, switch back to previous epoch and keep artifacts for audit.",
        ],
    }
    decision = {
        "apiVersion": "noemaforge.model-selection/v1",
        "kind": "ChatModelSelectionDecision",
        "version": RUNTIME_VERSION,
        "created_at": nowz(),
        "run_id": run_id,
        "status": "candidate_selection_requested" if not args.apply else "apply_command_ready",
        "mode": mode,
        "scope": args.scope,
        "next": [plan["commands"]["show_candidates"], plan["commands"]["apply_epoch"]],
    }
    artifacts = {
        "candidate_selection_plan": run_dir / "candidate-selection-plan.json",
        "model_selection_decision": run_dir / "model-selection-decision.json",
        "rollback_plan": run_dir / "rollback_plan.json",
    }
    write_json(artifacts["candidate_selection_plan"], plan)
    write_json(artifacts["model_selection_decision"], decision)
    write_json(artifacts["rollback_plan"], rollback)
    result = {
        "ok": True,
        "version": RUNTIME_VERSION,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "mode": mode,
        "scope": args.scope,
        "status": decision["status"],
        "artifacts": {k: str(v) for k, v in artifacts.items()},
        "reply": f"Model-selection mode selected: {mode}. Scope: {args.scope}. Selection plan is ready; candidates, decision and rollback plan are attached. Epoch is not applied without separate approve/apply.",
    }
    print(dumps(result) if args.json else str(run_dir))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noemaforge model-selection")
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    sub = parser.add_subparsers(dest="cmd", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("text", nargs="*")
    plan.add_argument("--request")
    plan.add_argument("--mode", default="normal")
    plan.add_argument("--scope", default="active runtime")
    plan.add_argument("--composite-top-n", type=int, default=0)
    plan.add_argument("--apply", action="store_true")
    plan.add_argument("--run-id")
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(func=cmd_plan)
    apply = sub.add_parser("apply")
    apply.add_argument("text", nargs="*")
    apply.add_argument("--request")
    apply.add_argument("--mode", default="normal")
    apply.add_argument("--scope", default="active runtime")
    apply.add_argument("--composite-top-n", type=int, default=0)
    apply.add_argument("--run-id")
    apply.add_argument("--json", action="store_true")
    apply.set_defaults(func=lambda args: cmd_plan(argparse.Namespace(**{**vars(args), "apply": True})))
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
