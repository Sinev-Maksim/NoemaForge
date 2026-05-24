#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/onboarding_ladder_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the primary onboarding documentation ladder.
Inputs: Onboarding ladder policy, primary docs, registry and example scenarios.
Outputs: JSON-compatible OnboardingLadderValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_onboarding_ladder_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.onboarding-ladder/v1"
POLICY_KIND = "OnboardingLadderPolicy"
SET_KIND = "OnboardingLadderExampleSet"
REPORT_KIND = "OnboardingLadderValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_ORDER = [
    "docs/README.md",
    "docs/onboarding/QUICKSTART_VM.md",
    "docs/onboarding/SETUP_MODES.md",
    "docs/onboarding/PRODUCTION_INSTALL_TRIXIE.md",
    "docs/onboarding/MVP_OPERATOR_GUIDE.md",
]
REGISTRY_REFS = [
    "configs/onboarding-ladder-policy.json",
    "contracts/onboarding_ladder.schema.json",
    "src/onboarding_ladder_runtime.py",
    "tests/test_onboarding_ladder_runtime.py",
    "tests/test_onboarding_ladder_qa.py",
    "tests/test_onboarding_ladder_performance.py",
    "prelaunch/governance/onboarding_ladder.example.json",
    "docs/README.md",
    "docs/TODO.md",
    "docs/onboarding/QUICKSTART_VM.md",
    "docs/onboarding/SETUP_MODES.md",
    "docs/onboarding/PRODUCTION_INSTALL_TRIXIE.md",
    "docs/onboarding/MVP_OPERATOR_GUIDE.md",
    "docs/backlog/ROADMAP_AND_TODO.md",
    "docs/history/CHANGELOG.md",
    "docs/reference/PROJECT_CONTEXT.md",
]
PIPELINE_REFS = [
    "configs/onboarding-ladder-policy.json",
    "src/onboarding_ladder_runtime.py",
    "prelaunch/governance/onboarding_ladder.example.json",
    "docs/onboarding/QUICKSTART_VM.md",
    "docs/onboarding/PRODUCTION_INSTALL_TRIXIE.md",
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


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _contains(text: str, needle: str) -> bool:
    return _norm(needle) in _norm(text)


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
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            failures.append(f"unsafe_ref:{owner}:{ref}")
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            failures.append(f"missing_ref:{owner}:{ref}")
    return {"failures": failures, "resolved_refs": resolved_refs}


def load_policy(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_example_set(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_ref(ref: str, *, project_root: Path, package_root: Path, failures: List[str]) -> str:
    resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
    if not resolved["ok"]:
        failures.append(f"doc_missing:{ref}")
        return ""
    return Path(resolved["path"]).read_text(encoding="utf-8")


def analyze_onboarding_docs(
    *,
    project_root: Path,
    package_root: Path,
    required_order: Sequence[str] = REQUIRED_ORDER,
    forbidden_primary_leads: Sequence[str] = (),
) -> Dict[str, Any]:
    failures: List[str] = []
    docs = {ref: _read_ref(ref, project_root=project_root, package_root=package_root, failures=failures) for ref in required_order}
    readme = docs.get("docs/README.md", "")
    quickstart = docs.get("docs/onboarding/QUICKSTART_VM.md", "")
    setup_modes = docs.get("docs/onboarding/SETUP_MODES.md", "")
    production = docs.get("docs/onboarding/PRODUCTION_INSTALL_TRIXIE.md", "")

    checks = {
        "readme_five_minute": "## 5-Minute Overview" in readme,
        "readme_links_quickstart": "docs/onboarding/QUICKSTART_VM.md" in readme,
        "readme_links_setup_modes": "docs/onboarding/SETUP_MODES.md" in readme,
        "readme_links_production_after_quickstart": "docs/onboarding/PRODUCTION_INSTALL_TRIXIE.md" in readme and readme.find("docs/onboarding/QUICKSTART_VM.md") < readme.find("docs/onboarding/PRODUCTION_INSTALL_TRIXIE.md"),
        "quickstart_first_success": "first-success VM path" in quickstart or "first public-MWP path" in quickstart,
        "quickstart_vm_selftest": "./setup.sh --mode vm --dry-run --selftest" in quickstart,
        "quickstart_no_install": "no install" in quickstart and "no model download" in quickstart,
        "setup_modes_differences": all(label in setup_modes for label in ["VM mode", "Host mode", "Docker-dev mode", "macOS-dev mode"]),
        "production_after_quickstart": "only after `docs/onboarding/QUICKSTART_VM.md` passes" in production,
        "production_host_install": "sudo ./setup.sh --mode host" in production,
        "production_next_operator_guide": "docs/onboarding/MVP_OPERATOR_GUIDE.md" in production,
    }
    primary_lead = "\n".join([line for line in readme.splitlines() if line.strip()][:80])
    for phrase in forbidden_primary_leads:
        if phrase and _contains(primary_lead, phrase):
            checks["primary_docs_do_not_lead_windows_lab"] = False
            failures.append(f"forbidden_primary_lead:{phrase}")
            break
    else:
        checks["primary_docs_do_not_lead_windows_lab"] = True
    for key, ok in checks.items():
        if not ok and not any(item.startswith(f"doc_check_failed:{key}") for item in failures):
            failures.append(f"doc_check_failed:{key}")
    return {"apiVersion": API_VERSION, "kind": "OnboardingDocsAnalysis", "ok": not failures, "failures": failures, "checks": checks}


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
    if str(policy.get("activation_state") or "") != "primary_docs_ladder":
        failures.append("policy_activation_state_invalid")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if _as_string_list(policy.get("required_order")) != REQUIRED_ORDER:
        failures.append("policy_required_order_invalid")
    for key in ["required_boundary_refs", "primary_docs", "required_example_sets"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    if not _as_string_list(policy.get("forbidden_primary_leads")):
        failures.append("policy_forbidden_primary_leads_empty")
    return failures


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {_registry_ref(entry): entry for entry in report.get("normalized_registry", {}).get("entries", []) if isinstance(entry, dict)}
    raw_entries = {_registry_ref(entry): entry for entry in registry.get("entries", []) if isinstance(entry, dict)}
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    eval_entry = entries.get(eval_ref)
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        refs = set(_as_string_list(eval_entry.get("refs")))
        for ref in REGISTRY_REFS:
            if ref not in refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")
    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    pipeline_eval_refs: List[str] = []
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
    else:
        pipeline_eval_refs = _as_string_list(pipeline.get("eval_pack_refs"))
        pipeline_refs = _as_string_list(pipeline.get("refs"))
        if eval_ref not in pipeline_eval_refs:
            failures.append(f"registry_pipeline_eval_pack_ref_missing:{pipeline_ref}:{eval_ref}")
        for ref in PIPELINE_REFS:
            if ref not in pipeline_refs:
                failures.append(f"registry_pipeline_ref_missing:{pipeline_ref}:{ref}")
    return {"failures": failures, "registry_report": report, "eval_ref": eval_ref, "pipeline_eval_refs": pipeline_eval_refs}


def evaluate_example_set(example_set: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    if example_set.get("apiVersion") != API_VERSION:
        failures.append("example_api_version_invalid")
    if example_set.get("kind") != SET_KIND:
        failures.append("example_kind_invalid")
    scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
    expected_starts = REQUIRED_ORDER[:-1]
    seen = set()
    for scenario in scenarios:
        start = str(scenario.get("start_page") or "")
        next_page = str(scenario.get("next_page") or "")
        expected = _as_string_list(scenario.get("expected"))
        seen.add(start)
        if start not in REQUIRED_ORDER:
            failures.append(f"example_start_invalid:{start}")
        if next_page not in REQUIRED_ORDER[1:]:
            failures.append(f"example_next_invalid:{next_page}")
        if not expected:
            failures.append(f"example_expected_empty:{start}")
    for start in expected_starts:
        if start not in seen:
            failures.append(f"example_start_missing:{start}")
    return {"ok": not failures, "failures": failures, "scenarios": len(scenarios)}


def validate_onboarding_ladder_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path,
    package_root: Path,
    registry_path: Path | None = None,
) -> Dict[str, Any]:
    registry_path = registry_path or package_root / "configs" / "unified-registry.json"
    policy = _policy_dict(payload)
    failures = _policy_failures(payload)
    refs = _resolve_refs(payload.get("refs", []), project_root=project_root, package_root=package_root, owner=str(payload.get("id") or "policy"))
    failures.extend(refs["failures"])

    docs_report = analyze_onboarding_docs(
        project_root=project_root,
        package_root=package_root,
        required_order=_as_string_list(policy.get("required_order")) or REQUIRED_ORDER,
        forbidden_primary_leads=_as_string_list(policy.get("forbidden_primary_leads")),
    )
    failures.extend(docs_report["failures"])

    registry = _registry_failures(payload, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures.extend(registry["failures"])

    boundary = str(policy.get("boundary_phrase") or "")
    boundary_hits = []
    for ref in _as_string_list(policy.get("required_boundary_refs")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved["ok"]:
            failures.append(f"boundary_ref_missing:{ref}")
            continue
        if _contains(Path(resolved["path"]).read_text(encoding="utf-8"), boundary):
            boundary_hits.append(ref)
        else:
            failures.append(f"boundary_phrase_missing:{ref}")

    example_reports = []
    for ref in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        if not resolved["ok"]:
            failures.append(f"example_ref_missing:{ref}")
            continue
        report = evaluate_example_set(load_example_set(resolved["path"]))
        example_reports.append({"ref": ref, **report})
        failures.extend([f"example_invalid:{ref}:{item}" for item in report["failures"]])

    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "policy_id": payload.get("id"),
        "docs": docs_report,
        "registry": {"eval_ref": registry["eval_ref"], "pipeline_eval_refs": registry["pipeline_eval_refs"]},
        "examples": example_reports,
        "resolved_refs": refs["resolved_refs"],
        "metrics": {
            "refs": len(payload.get("refs", [])) if isinstance(payload.get("refs"), list) else 0,
            "resolved_refs": len(refs["resolved_refs"]),
            "ladder_steps": len(policy.get("required_order", [])) if isinstance(policy.get("required_order"), list) else 0,
            "boundary_refs": len(boundary_hits),
            "examples": len(example_reports),
            "registry_entries": len(registry["registry_report"].get("normalized_registry", {}).get("entries", [])),
        },
    }


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate NoemaForge onboarding ladder policy")
    package_root = Path(__file__).resolve().parent.parent
    project_root = package_root.parent
    ap.add_argument("--policy", default=str(package_root / "configs" / "onboarding-ladder-policy.json"))
    ap.add_argument("--project-root", default=str(project_root))
    ap.add_argument("--package-root", default=str(package_root))
    ap.add_argument("--registry", default="")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args(argv)
    pkg = Path(args.package_root).resolve()
    proj = Path(args.project_root).resolve()
    registry = Path(args.registry).resolve() if args.registry else pkg / "configs" / "unified-registry.json"
    report = validate_onboarding_ladder_policy(load_policy(args.policy), project_root=proj, package_root=pkg, registry_path=registry)
    if args.summary:
        print(json.dumps({"ok": report["ok"], "failures": report["failures"], "metrics": report["metrics"]}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
