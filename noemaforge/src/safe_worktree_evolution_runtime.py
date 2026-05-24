#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/safe_worktree_evolution_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate safe worktree planning for the evolution pipeline.
Inputs: Safe worktree evolution policy, example contract and pipeline runtime source.
Outputs: JSON-compatible SafeWorktreeEvolutionValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_safe_worktree_evolution_runtime.py, QA and performance tests.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence


API_VERSION = "noemaforge.safe-worktree-evolution/v1"
POLICY_KIND = "SafeWorktreeEvolutionPolicy"
EXAMPLE_KIND = "SafeWorktreeEvolutionExampleSet"
REPORT_KIND = "SafeWorktreeEvolutionValidationReport"
POLICY_ID = "safe-worktree-evolution-core"
PRIMARY_TODO = "Add safe worktree creation for evolution pipeline."

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "safe-worktree-evolution-policy.json"
DEFAULT_EXAMPLE = PROJECT_ROOT / "prelaunch" / "governance" / "safe_worktree_evolution.example.json"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_HELPERS = [
    "build_evolution_worktree_plan",
    "safe_evolution_worktree_branch",
    "validate_worktree_ref",
    "path_is_under",
]
REQUIRED_CONTROLS = [
    "plan_is_default",
    "apply_requires_explicit_flag",
    "degraded_mutation_guard_required",
    "evolution_pipeline_only",
    "branch_namespace_required",
    "base_ref_sanitized",
    "destination_under_run_worktrees",
    "subprocess_uses_argv_list",
    "no_shell_command_string",
    "artifact_registered_after_apply",
    "event_emitted_for_plan_and_apply",
    "docs_changelog_trace_required",
]
SUMMARY_FIELDS = [
    "helper_count",
    "controls_true",
    "blocked_case_count",
    "plan_default",
    "destination_guard",
    "branch_guard",
]


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    local = str(ref or "").strip().replace("\\", "/")
    candidates = [("project", project_root / local), ("package", package_root / local)]
    if not local.startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / local))
    checked: List[str] = []
    for owner, path in candidates:
        checked.append(_display_path(path))
        if path.exists():
            return {"ok": True, "ref": ref, "resolved_under": owner, "path": _display_path(path), "checked": checked}
    return {"ok": False, "ref": ref, "resolved_under": "", "path": "", "checked": checked}


def _resolve_refs(refs: Sequence[str], *, project_root: Path, package_root: Path, owner: str) -> Dict[str, Any]:
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            failures.append(f"unsafe_ref:{owner}:{ref}")
            unsafe_refs.append({"owner": owner, "ref": ref})
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        resolved["owner"] = owner
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            failures.append(f"missing_ref:{owner}:{ref}")
            missing_refs.append(resolved)
    return {"failures": failures, "resolved_refs": resolved_refs, "missing_refs": missing_refs, "unsafe_refs": unsafe_refs}


def load_policy(policy_path: Path | str = DEFAULT_POLICY) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_example(example_path: Path | str = DEFAULT_EXAMPLE) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if payload.get("id") != POLICY_ID:
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "safe_evolution_worktree_contract":
        failures.append("policy_activation_state_invalid")
    if str(policy.get("required_pipeline_ref") or "") != "pipeline:firstboot-model-selection:0.32.1":
        failures.append("policy_required_pipeline_ref_invalid")
    if PRIMARY_TODO not in _as_string_list(policy.get("closed_todo_refs")):
        failures.append("policy_closed_todo_ref_missing")
    if str(policy.get("pipeline_id") or "") != "evolution":
        failures.append("policy_pipeline_id_invalid")
    if str(policy.get("branch_namespace") or "") != "noemaforge/evolution/":
        failures.append("policy_branch_namespace_invalid")
    if str(policy.get("required_cli") or "") != "noemaforge pipeline worktree create":
        failures.append("policy_required_cli_invalid")
    helpers = _as_string_list(policy.get("required_runtime_helpers"))
    for helper in REQUIRED_HELPERS:
        if helper not in helpers:
            failures.append(f"policy_helper_missing:{helper}")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"control_{key}_not_true")
    if _as_string_list(policy.get("summary_fields")) != SUMMARY_FIELDS:
        failures.append("policy_summary_fields_invalid")
    if policy.get("require_registry_attachment") is not True:
        failures.append("policy_require_registry_attachment_not_true")
    if policy.get("require_docs_and_changelog_refs") is not True:
        failures.append("policy_require_docs_and_changelog_refs_not_true")
    if not _as_string_list(policy.get("required_outputs")):
        failures.append("policy_required_outputs_empty")
    if not _as_string_list(policy.get("required_refs")):
        failures.append("policy_required_refs_empty")
    return failures


def _example_failures(example: Dict[str, Any], *, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    if example.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example.get("kind") != EXAMPLE_KIND:
        failures.append("example_kind_invalid")
    accepted = example.get("accepted_plan") if isinstance(example.get("accepted_plan"), dict) else {}
    if accepted.get("pipeline_id") != policy.get("pipeline_id"):
        failures.append("example_pipeline_id_mismatch")
    if not str(accepted.get("branch") or "").startswith(str(policy.get("branch_namespace") or "")):
        failures.append("example_branch_namespace_mismatch")
    if accepted.get("applied_by_default") is not False:
        failures.append("example_plan_default_invalid")
    blocked = example.get("blocked_cases") if isinstance(example.get("blocked_cases"), list) else []
    blocked_reasons = {str(item.get("reason") or "") for item in blocked if isinstance(item, dict)}
    for reason in [
        "worktree_requires_evolution_pipeline",
        "unsafe_branch_namespace",
        "worktree_path_outside_run_dir",
        "unsafe_base_ref",
    ]:
        if reason not in blocked_reasons:
            failures.append(f"example_blocked_reason_missing:{reason}")
    expected = example.get("expected_summary") if isinstance(example.get("expected_summary"), dict) else {}
    summary = {
        "helper_count": len(_as_string_list(policy.get("required_runtime_helpers"))),
        "controls_true": sum(1 for key in REQUIRED_CONTROLS if policy.get("controls", {}).get(key) is True),
        "blocked_case_count": len(blocked),
        "plan_default": accepted.get("applied_by_default") is False,
        "destination_guard": "worktree_path_outside_run_dir" in blocked_reasons,
        "branch_guard": "unsafe_branch_namespace" in blocked_reasons,
    }
    for key in SUMMARY_FIELDS:
        if summary.get(key) != expected.get(key):
            failures.append(f"example_summary_mismatch:{key}")
    return {"failures": failures, "summary": summary}


def _pipeline_runtime_failures(source_text: str, policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    for helper in _as_string_list(policy.get("required_runtime_helpers")):
        if f"def {helper}" not in source_text:
            failures.append(f"runtime_helper_missing:{helper}")
    required_tokens = [
        'if str(run.get("pipeline_id") or "") != "evolution"',
        'EVOLUTION_WORKTREE_BRANCH_PREFIX = "noemaforge/evolution/"',
        "worktree_path_outside_run_dir",
        "unsafe_branch_namespace",
        'validate_worktree_ref(base or "HEAD", field="base_ref")',
        "subprocess.run(cmd, text=True, capture_output=True)",
        'guard_degraded_mutation("pipeline worktree create --apply"',
        'register_artifact(conn, args.run_id, str(run["current_stage"]), "worktree"',
        'emit(conn, args.run_id, "worktree_plan"',
        'emit(conn, args.run_id, "worktree_created"',
        'wtcreate.add_argument("--apply", action="store_true")',
    ]
    for token in required_tokens:
        if token not in source_text:
            failures.append(f"runtime_token_missing:{token[:48]}")
    if "shell=True" in source_text:
        failures.append("runtime_shell_true_forbidden")
    return failures


def validate_safe_worktree_evolution_policy(
    policy_payload: Dict[str, Any],
    *,
    project_root: Path | str = PROJECT_ROOT,
    package_root: Path | str = PACKAGE_ROOT,
    example_path: Path | str = DEFAULT_EXAMPLE,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    failures: List[str] = []
    failures.extend(_policy_failures(policy_payload))
    policy = _policy_dict(policy_payload)

    refs = _as_string_list(policy_payload.get("refs")) + _as_string_list(policy.get("required_refs"))
    ref_report = _resolve_refs(refs, project_root=project, package_root=package, owner=POLICY_ID)
    failures.extend(ref_report["failures"])

    example_report = _example_failures(load_example(example_path), policy=policy)
    failures.extend(example_report["failures"])

    runtime_ref = _resolve_ref("src/pipeline_runtime.py", project_root=project, package_root=package)
    if runtime_ref["ok"]:
        source_text = Path(runtime_ref["path"]).read_text(encoding="utf-8", errors="replace")
        failures.extend(_pipeline_runtime_failures(source_text, policy))
    else:
        failures.append("pipeline_runtime_missing")

    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "id": POLICY_ID,
        "failures": sorted(set(failures)),
        "safe_worktree_evolution_summary": example_report["summary"],
        "resolved_refs": ref_report["resolved_refs"],
        "missing_refs": ref_report["missing_refs"],
        "unsafe_refs": ref_report["unsafe_refs"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge safe evolution worktree contract.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="Policy JSON path.")
    parser.add_argument("--example", default=str(DEFAULT_EXAMPLE), help="Example JSON path.")
    parser.add_argument("--summary", action="store_true", help="Emit compact summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    report = validate_safe_worktree_evolution_policy(load_policy(args.policy), example_path=args.example)
    payload: Dict[str, Any]
    if args.summary:
        payload = {
            "apiVersion": API_VERSION,
            "kind": "SafeWorktreeEvolutionSummary",
            "id": POLICY_ID,
            "ok": report["ok"],
            "failures": report["failures"],
            "summary": report["safe_worktree_evolution_summary"],
        }
    else:
        payload = report
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
