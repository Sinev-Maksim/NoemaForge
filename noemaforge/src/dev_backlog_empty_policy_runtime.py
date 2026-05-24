#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/dev_backlog_empty_policy_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate empty Dev backlog creates a bounded seed self-optimization plan only.
Inputs: dev-backlog-empty policy and Dev Team runtime source.
Outputs: JSON-compatible DevBacklogEmptyValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_dev_backlog_empty_policy_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import dev_team_runtime as dtr


API_VERSION = "noemaforge.dev-backlog-empty/v1"
POLICY_KIND = "DevBacklogEmptyPolicy"
REPORT_KIND = "DevBacklogEmptyValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")


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
    candidates = [("project", project_root / ref), ("package", package_root / ref)]
    if not ref.startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / ref))
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
            unsafe_refs.append({"owner": owner, "ref": ref})
            failures.append(f"unsafe_ref:{owner}:{ref}")
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        resolved["owner"] = owner
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            missing_refs.append(resolved)
            failures.append(f"missing_ref:{owner}:{ref}")
    return {"failures": failures, "resolved_refs": resolved_refs, "missing_refs": missing_refs, "unsafe_refs": unsafe_refs}


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _slice_between(text: str, start_marker: str, end_markers: Sequence[str]) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    ends = [text.find(marker, start + len(start_marker)) for marker in end_markers]
    ends = [pos for pos in ends if pos > start]
    end = min(ends) if ends else len(text)
    return text[start:end]


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "empty_dev_backlog_seed_plan_only":
        failures.append("policy_activation_state_invalid")
    for key in ["require_docs_and_changelog_refs", "require_no_live_dependency", "forbid_auto_apply", "require_admin_approval"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if int(policy.get("max_steps_bound") or 0) > 5:
        failures.append("policy_max_steps_bound_too_high")
    if int(policy.get("time_budget_minutes_bound") or 0) > 30:
        failures.append("policy_time_budget_minutes_bound_too_high")
    for key in ["required_dev_team_tokens", "required_plan_fields"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _source_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    resolved = _resolve_ref("noemaforge/src/dev_team_runtime.py", project_root=project_root, package_root=package_root)
    text = load_text(resolved["path"]) if resolved.get("ok") else ""
    if not resolved.get("ok"):
        failures.append("dev_team_runtime_missing")
    for token in _as_string_list(policy.get("required_dev_team_tokens")):
        if token not in text:
            failures.append(f"dev_team_token_missing:{token}")
    seed_parser_block = _slice_between(text, 'seed = sub.add_parser("seed-self-improvement-plan")', ['rep = sub.add_parser("replace")'])
    if not seed_parser_block:
        failures.append("seed_parser_block_missing")
    if "--apply" in seed_parser_block:
        failures.append("seed_parser_exposes_apply")
    return {"failures": failures, "resolved": resolved, "dev_team_chars": len(text), "seed_parser_chars": len(seed_parser_block)}


def build_empty_backlog_policy_fixture() -> Dict[str, Any]:
    empty_plan = dtr.build_empty_backlog_seed_self_optimization_plan(
        [],
        max_steps=99,
        time_budget_minutes=999,
        request="Fixture empty Dev backlog",
    )
    nonempty_plan = dtr.build_empty_backlog_seed_self_optimization_plan(
        [{"title": "Existing Dev task", "category": "dev_team", "status": "pending"}],
        max_steps=3,
        time_budget_minutes=20,
        request="Fixture non-empty Dev backlog",
    )
    completed_only_plan = dtr.build_empty_backlog_seed_self_optimization_plan(
        [{"title": "Completed Dev task", "category": "dev_team", "status": "completed"}],
        max_steps=3,
        time_budget_minutes=20,
        request="Fixture completed-only Dev backlog",
    )
    return {
        "empty_plan": empty_plan,
        "nonempty_plan": nonempty_plan,
        "completed_only_plan": completed_only_plan,
    }


def _workflow_report(policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    fixture = build_empty_backlog_policy_fixture()
    empty = fixture["empty_plan"]
    nonempty = fixture["nonempty_plan"]
    completed_only = fixture["completed_only_plan"]
    for field in _as_string_list(policy.get("required_plan_fields")):
        if field not in empty:
            failures.append(f"empty_seed_plan_field_missing:{field}")
    if empty.get("seed_created") is not True:
        failures.append("empty_backlog_seed_not_created")
    if completed_only.get("seed_created") is not True:
        failures.append("completed_only_backlog_seed_not_created")
    if nonempty.get("seed_created") is not False:
        failures.append("nonempty_backlog_seed_created")
    for plan_name, plan in [("empty", empty), ("nonempty", nonempty), ("completed_only", completed_only)]:
        if plan.get("auto_apply") is not False:
            failures.append(f"{plan_name}_plan_auto_apply_not_false")
        if plan.get("applied") is not False:
            failures.append(f"{plan_name}_plan_applied_not_false")
    if empty.get("plan_status") != "draft_review_required":
        failures.append("empty_plan_not_draft_review_required")
    if empty.get("requires_admin_approval") is not True:
        failures.append("empty_plan_admin_approval_not_required")
    if empty.get("execution_policy") != "plan_only_no_auto_apply":
        failures.append("empty_plan_execution_policy_invalid")
    budget = empty.get("improvement_budget") if isinstance(empty.get("improvement_budget"), dict) else {}
    if budget.get("bounded") is not True:
        failures.append("empty_plan_budget_not_bounded")
    if int(budget.get("max_steps") or 0) > int(policy.get("max_steps_bound") or 5):
        failures.append("empty_plan_max_steps_unbounded")
    if int(budget.get("time_budget_minutes") or 0) > int(policy.get("time_budget_minutes_bound") or 30):
        failures.append("empty_plan_time_budget_unbounded")
    if budget.get("until_stop") is not False:
        failures.append("empty_plan_until_stop_not_false")
    for action in empty.get("actions", []):
        if not isinstance(action, dict) or action.get("apply") is not False:
            failures.append("empty_plan_action_apply_not_false")
    for forbidden in ["write_file", "replace", "set_version", "apply_patch", "run_privileged_command", "auto_apply"]:
        if forbidden not in empty.get("forbidden_actions", []):
            failures.append(f"empty_plan_forbidden_action_missing:{forbidden}")
    return {"failures": failures, "fixture": fixture}


def _docs_report(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    docs = [
        project_root / "TODO.md",
        package_root / "TODO.md",
        project_root / "docs" / "TODO.md",
        package_root / "docs" / "TODO.md",
        project_root / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        package_root / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        project_root / "CHANGELOG.md",
        project_root / "RELEASE_NOTES.md",
        project_root / "docs" / "history" / "CHANGELOG.md",
        package_root / "docs" / "history" / "CHANGELOG.md",
    ]
    tokens = [
        str(payload.get("id") or ""),
        "bounded seed self-optimization plan",
        "not an auto-apply change",
    ]
    reports: List[Dict[str, Any]] = []
    for path in docs:
        text = load_text(path) if path.exists() else ""
        missing = [token for token in tokens if token and token not in text]
        if missing:
            failures.append(f"docs_tokens_missing:{_display_path(path)}:{','.join(missing)}")
        reports.append({"path": _display_path(path), "ok": not missing, "missing": missing})
    return {"failures": failures, "reports": reports}


def validate_dev_backlog_empty_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Path | str | None = None,
    include_docs: bool = True,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(ref_report["failures"])
    source = _source_report(policy, project_root=project, package_root=package)
    failures.extend(source["failures"])
    workflow = _workflow_report(policy)
    failures.extend(workflow["failures"])
    docs = _docs_report(payload, project_root=project, package_root=package) if include_docs else {"failures": [], "reports": []}
    failures.extend(docs["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "dev_team_chars": source["dev_team_chars"],
        "seed_parser_chars": source["seed_parser_chars"],
        "seed_actions": len(workflow["fixture"]["empty_plan"].get("actions", [])),
        "docs_reports": len(docs["reports"]),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "id": str(payload.get("id") or ""),
        "version": str(payload.get("version") or ""),
        "ok": not failures,
        "validated_at": _nowz(),
        "policy_path": _display_path(Path(policy_path).resolve()) if policy_path else "",
        "failures": failures,
        "metrics": metrics,
        "refs": ref_report,
        "source": source,
        "workflow": workflow,
        "docs": docs,
    }


def benchmark_dev_backlog_empty_policy(*, package_root: Path | str, iterations: int = 80) -> Dict[str, Any]:
    root = Path(package_root).resolve()
    policy = load_policy(root / "configs" / "dev-backlog-empty-policy.json")
    started = time.perf_counter()
    failures = 0
    for _ in range(iterations):
        report = validate_dev_backlog_empty_policy(policy, project_root=root.parent, package_root=root, include_docs=False)
        if not report.get("ok"):
            failures += 1
    elapsed = time.perf_counter() - started
    return {
        "ok": failures == 0,
        "iterations": iterations,
        "failures": failures,
        "elapsed_seconds": round(elapsed, 6),
        "iterations_per_second": round(iterations / elapsed, 3) if elapsed else iterations,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "DevBacklogEmptyValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge empty Dev backlog seed-plan policy")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "dev-backlog-empty-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--skip-docs", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_dev_backlog_empty_policy(
        load_policy(args.policy),
        project_root=Path(args.project_root),
        package_root=Path(args.package_root),
        policy_path=Path(args.policy),
        include_docs=not args.skip_docs,
    )
    print(json.dumps(build_summary(report) if args.summary else report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
