#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/alpha_backlog_fence_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate that selected alpha-prep packs stay backlog-only until explicit gate-stability review.
Inputs: noemaforge/configs/alpha-backlog-fence.json, Unified Registry and fence examples.
Outputs: JSON-compatible AlphaBacklogFenceValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_alpha_backlog_fence_runtime.py
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
from typing import Any, Dict, List, Optional, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.alpha-backlog/v1"
POLICY_KIND = "AlphaBacklogFencePolicy"
SET_KIND = "AlphaBacklogFenceSet"
FENCE_KIND = "AlphaBacklogFence"
REPORT_KIND = "AlphaBacklogFenceValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_FENCE_STATUSES = {"active", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,180}$")


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_path(value: Path | str) -> Path:
    return Path(value).resolve()


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    candidates = [
        ("package", package_root / ref),
        ("project", project_root / ref),
    ]
    if not str(ref).startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / ref))

    checked: List[str] = []
    for base_name, path in candidates:
        checked.append(_display_path(path))
        if path.exists():
            return {"ok": True, "ref": ref, "resolved_under": base_name, "path": _display_path(path), "checked": checked}
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


def load_example_set(example_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _protected_items(policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = policy.get("protected_refs") if isinstance(policy.get("protected_refs"), list) else []
    return [item for item in items if isinstance(item, dict)]


def _protected_refs(policy: Dict[str, Any]) -> List[str]:
    return [str(item.get("ref") or "") for item in _protected_items(policy) if str(item.get("ref") or "")]


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_POLICY_STATUSES:
        failures.append("policy_status_invalid")
    expected = {
        "mode": "offline_contract",
        "activation_state": "backlog_only",
        "promotion_blocked_until": "manual_alpha_gate_stability_review",
    }
    for key, expected_value in expected.items():
        if str(policy.get(key) or "") != expected_value:
            failures.append(f"policy_{key}_invalid")
    for key in [
        "require_trace_id",
        "require_registry_attachment",
        "require_docs_and_changelog_refs",
        "require_no_live_dependency",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if policy.get("allow_auto_promotion") is not False:
        failures.append("policy_allow_auto_promotion_not_false")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    if not _protected_items(policy):
        failures.append("policy_protected_refs_empty")
    for item in _protected_items(policy):
        ref = str(item.get("ref") or "")
        if not ref.startswith("eval-pack:"):
            failures.append(f"policy_protected_ref_invalid:{ref}")
        if not _as_string_list(item.get("allowed_statuses")):
            failures.append(f"policy_allowed_statuses_empty:{ref}")
        if not _as_string_list(item.get("blocked_statuses")):
            failures.append(f"policy_blocked_statuses_empty:{ref}")
        if not str(item.get("reason") or "").strip():
            failures.append(f"policy_protected_reason_empty:{ref}")
    if not _as_string_list(policy.get("required_gate_refs")):
        failures.append("policy_required_gate_refs_empty")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _registry_failures(
    payload: Dict[str, Any],
    *,
    project_root: Path,
    package_root: Path,
    registry_path: Path,
) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {
        _registry_ref(entry): entry
        for entry in report.get("normalized_registry", {}).get("entries", [])
        if isinstance(entry, dict)
    }
    raw_entries = {
        _registry_ref(entry): entry
        for entry in registry.get("entries", [])
        if isinstance(entry, dict)
    }

    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    pipeline_eval_refs: List[str] = []
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
    else:
        pipeline_eval_refs = _as_string_list(pipeline.get("eval_pack_refs"))

    for item in _protected_items(policy):
        ref = str(item.get("ref") or "")
        entry = raw_entries.get(ref) or entries.get(ref)
        if not entry:
            failures.append(f"registry_protected_ref_missing:{ref}")
            continue
        status = str(entry.get("status") or "")
        allowed = set(_as_string_list(item.get("allowed_statuses")))
        blocked = set(_as_string_list(item.get("blocked_statuses")))
        if status not in allowed:
            failures.append(f"registry_protected_ref_status_not_allowed:{ref}:{status}")
        if status in blocked:
            failures.append(f"registry_protected_ref_promoted:{ref}:{status}")
        if ref not in pipeline_eval_refs:
            failures.append(f"registry_pipeline_protected_ref_missing:{ref}")

    for gate_ref in _as_string_list(policy.get("required_gate_refs")):
        if gate_ref not in entries:
            failures.append(f"registry_required_gate_missing:{gate_ref}")

    return {
        "failures": failures,
        "registry_report": report,
        "entries": entries,
        "pipeline_eval_refs": pipeline_eval_refs,
    }


def _fence_failures(fence: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    failures: List[str] = []
    fence_id = str(fence.get("id") or "<missing>")
    protected_refs = set(_protected_refs(policy))
    required_gate_refs = set(_as_string_list(policy.get("required_gate_refs")))
    if fence.get("apiVersion") != API_VERSION:
        failures.append(f"fence_api_version_invalid:{fence_id}")
    if fence.get("kind") != FENCE_KIND:
        failures.append(f"fence_kind_invalid:{fence_id}")
    if not SAFE_ID_RE.match(fence_id):
        failures.append(f"fence_id_invalid:{fence_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(fence.get("trace_id") or "")):
        failures.append(f"fence_trace_id_invalid:{fence_id}")
    if str(fence.get("status") or "") not in VALID_FENCE_STATUSES:
        failures.append(f"fence_status_invalid:{fence_id}:{fence.get('status')}")
    protected_ref = str(fence.get("protected_ref") or "")
    if protected_ref not in protected_refs:
        failures.append(f"fence_protected_ref_not_in_policy:{fence_id}:{protected_ref}")
    if str(fence.get("activation_state") or "") != "backlog_only":
        failures.append(f"fence_activation_state_not_backlog_only:{fence_id}")
    if str(fence.get("protected_until") or "") != str(policy.get("promotion_blocked_until") or ""):
        failures.append(f"fence_protected_until_mismatch:{fence_id}:{fence.get('protected_until')}")
    if fence.get("alpha_gates_stable") is not False:
        failures.append(f"fence_alpha_gates_stable_not_false:{fence_id}")
    if policy.get("require_no_live_dependency") is True and fence.get("live_dependency_required") is not False:
        failures.append(f"fence_live_dependency_required:{fence_id}")
    promotion = fence.get("promotion") if isinstance(fence.get("promotion"), dict) else {}
    if promotion.get("auto_promotion_allowed") is not False:
        failures.append(f"fence_auto_promotion_allowed:{fence_id}")
    if promotion.get("promotion_blocked") is not True:
        failures.append(f"fence_promotion_not_blocked:{fence_id}")
    if promotion.get("manual_review_required") is not True:
        failures.append(f"fence_manual_review_not_required:{fence_id}")

    evidence = fence.get("required_evidence") if isinstance(fence.get("required_evidence"), list) else []
    evidence_refs = {str(item.get("ref") or "") for item in evidence if isinstance(item, dict)}
    if not required_gate_refs.issubset(evidence_refs):
        failures.append(f"fence_required_evidence_missing:{fence_id}")
    for item in evidence:
        if not isinstance(item, dict):
            failures.append(f"fence_required_evidence_not_object:{fence_id}")
            continue
        ref = str(item.get("ref") or "")
        if ref not in required_gate_refs:
            failures.append(f"fence_unknown_evidence_ref:{fence_id}:{ref}")
        if item.get("present") is not True:
            failures.append(f"fence_evidence_not_present:{fence_id}:{ref}")
    return failures


def validate_alpha_backlog_fence_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Optional[Path | str] = None,
    registry_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root)
    if not project.exists():
        raise FileNotFoundError(project)
    if not package.exists():
        raise FileNotFoundError(package)
    registry = _as_path(registry_path) if registry_path else package / "configs" / "unified-registry.json"

    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    registry_result = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_result["failures"])

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    fence_results: List[Dict[str, Any]] = []

    refs_result = _resolve_refs(
        sorted(set(_as_string_list(payload.get("refs")))),
        project_root=project,
        package_root=package,
        owner=str(payload.get("id") or "policy"),
    )
    failures.extend(refs_result["failures"])
    all_resolved_refs.extend(refs_result["resolved_refs"])
    all_missing_refs.extend(refs_result["missing_refs"])
    all_unsafe_refs.extend(refs_result["unsafe_refs"])

    example_ref_results = _resolve_refs(
        _as_string_list(policy.get("required_example_sets")),
        project_root=project,
        package_root=package,
        owner="required_example_sets",
    )
    failures.extend(example_ref_results["failures"])
    all_resolved_refs.extend(example_ref_results["resolved_refs"])
    all_missing_refs.extend(example_ref_results["missing_refs"])
    all_unsafe_refs.extend(example_ref_results["unsafe_refs"])

    for item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{item['ref']}")
        fences = example_set.get("fences") if isinstance(example_set.get("fences"), list) else []
        if not fences:
            failures.append(f"example_set_fences_empty:{item['ref']}")
        for fence in fences:
            if not isinstance(fence, dict):
                failures.append(f"fence_not_object:{item['ref']}")
                continue
            fence_id = str(fence.get("id") or "<missing>")
            fence_failures = _fence_failures(fence, payload)
            fence_ref_result = _resolve_refs(
                _as_string_list(fence.get("refs")),
                project_root=project,
                package_root=package,
                owner=fence_id,
            )
            fence_failures.extend(fence_ref_result["failures"])
            failures.extend(fence_failures)
            all_resolved_refs.extend(fence_ref_result["resolved_refs"])
            all_missing_refs.extend(fence_ref_result["missing_refs"])
            all_unsafe_refs.extend(fence_ref_result["unsafe_refs"])
            fence_results.append(
                {
                    "id": fence_id,
                    "ok": not fence_failures,
                    "protected_ref": str(fence.get("protected_ref") or ""),
                    "status": str(fence.get("status") or ""),
                    "failures": sorted(set(fence_failures)),
                }
            )

    checks = [
        {"id": "backlog_only", "status": "passed" if not any("backlog_only" in item or "alpha_gates_stable" in item for item in failures) else "failed"},
        {"id": "promotion_blocked", "status": "passed" if not any("promotion" in item or "promoted" in item for item in failures) else "failed"},
        {"id": "registry_attachment", "status": "passed" if not any("registry_" in item for item in failures) else "failed"},
        {"id": "no_live_dependency", "status": "passed" if not any("live_dependency" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "fences": len(fence_results),
        "passing_fences": sum(1 for item in fence_results if item["ok"]),
        "protected_refs": len(_protected_refs(policy)),
        "required_gate_refs": len(_as_string_list(policy.get("required_gate_refs"))),
        "registry_entries": len(registry_result["entries"]),
        "refs": len(all_resolved_refs) + len(all_missing_refs) + len(all_unsafe_refs),
        "resolved_refs": len(all_resolved_refs),
        "missing_refs": len(all_missing_refs),
        "unsafe_refs": len(all_unsafe_refs),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "policy_path": str(policy_path or ""),
        "registry_path": _display_path(registry),
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "metrics": metrics,
        "checks": checks,
        "fence_results": sorted(fence_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def alpha_backlog_fence_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("alpha_backlog_fence_report_required")
    status = "passed" if report.get("ok") else "failed"
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "safety_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
        ],
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge alpha backlog-only fences.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/alpha-backlog-fence.json",
        help="Policy path, absolute or relative to project root.",
    )
    parser.add_argument("--registry", default="", help="Optional Unified Registry path.")
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path
    registry_path = Path(args.registry) if args.registry else package_root / "configs" / "unified-registry.json"
    if not registry_path.is_absolute():
        registry_path = project_root / registry_path

    report = validate_alpha_backlog_fence_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "AlphaBacklogFenceValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "policy_path": report["policy_path"],
            "registry_path": report["registry_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
