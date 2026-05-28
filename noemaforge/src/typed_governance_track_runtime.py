#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/typed_governance_track_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate typed governance contract dependency tracking across governance packs.
Inputs: noemaforge/configs/typed-governance-track.json, Unified Registry and track examples.
Outputs: JSON-compatible TypedGovernanceTrackValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_typed_governance_track_runtime.py
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

import production_ai_contracts as pac
import unified_registry_runtime as urr


API_VERSION = "noemaforge.typed-governance/v1"
POLICY_KIND = "TypedGovernanceTrackPolicy"
SET_KIND = "TypedGovernanceTrackSet"
TRACK_KIND = "TypedGovernanceTrack"
REPORT_KIND = "TypedGovernanceTrackValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_STAGE_ORDER = [
    "concept_frame",
    "sense_state_privacy",
    "drive_state",
    "honesty_protocol",
    "slop_critic",
    "detection_verdict",
    "research_packet",
    "pipeline_rfc",
]
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


def _contract_refs(contract: Dict[str, Any]) -> List[str]:
    refs = [
        str(contract.get("policy_ref") or ""),
        str(contract.get("schema_ref") or ""),
        str(contract.get("runtime_ref") or ""),
    ]
    refs.extend(_as_string_list(contract.get("test_refs")))
    return [ref for ref in refs if ref]


def _contracts_by_stage(policy: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    contracts = policy.get("required_contracts") if isinstance(policy.get("required_contracts"), list) else []
    return {str(item.get("stage") or ""): item for item in contracts if isinstance(item, dict)}


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
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
    for key in [
        "require_trace_id",
        "require_dependency_order",
        "require_registry_attachment",
        "require_policy_schema_runtime_tests",
        "require_docs_and_changelog_refs",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if _as_string_list(policy.get("required_stage_order")) != REQUIRED_STAGE_ORDER:
        failures.append("policy_required_stage_order_invalid")
    contracts = _contracts_by_stage(policy)
    if set(contracts) != set(REQUIRED_STAGE_ORDER):
        failures.append("policy_required_contracts_incomplete")
    for stage in REQUIRED_STAGE_ORDER:
        contract = contracts.get(stage, {})
        if not str(contract.get("eval_pack_ref") or "").startswith("eval-pack:"):
            failures.append(f"policy_contract_eval_pack_ref_invalid:{stage}")
        if not all(_contract_refs(contract)):
            failures.append(f"policy_contract_refs_incomplete:{stage}")
        if len(_as_string_list(contract.get("test_refs"))) < 3:
            failures.append(f"policy_contract_tests_incomplete:{stage}")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
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
    entries = { _registry_ref(entry): entry for entry in report.get("normalized_registry", {}).get("entries", []) }
    raw_entries = {
        _registry_ref(entry): entry
        for entry in registry.get("entries", [])
        if isinstance(entry, dict)
    }
    contracts = _contracts_by_stage(policy)
    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    pipeline = entries.get(pipeline_ref)
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
        pipeline_eval_refs: List[str] = []
        pipeline_refs: List[str] = []
    else:
        raw_pipeline = raw_entries.get(pipeline_ref, pipeline)
        pipeline_eval_refs = _as_string_list(raw_pipeline.get("eval_pack_refs"))
        pipeline_refs = _as_string_list(raw_pipeline.get("refs"))

    eval_order = [contracts[stage]["eval_pack_ref"] for stage in REQUIRED_STAGE_ORDER if stage in contracts]
    pipeline_positions: List[int] = []
    for stage in REQUIRED_STAGE_ORDER:
        contract = contracts.get(stage, {})
        eval_pack_ref = str(contract.get("eval_pack_ref") or "")
        entry = entries.get(eval_pack_ref)
        if not entry:
            failures.append(f"registry_eval_pack_missing:{stage}:{eval_pack_ref}")
            continue
        entry_refs = set(_as_string_list(entry.get("refs")))
        for ref in _contract_refs(contract):
            if ref not in entry_refs:
                failures.append(f"registry_eval_pack_ref_missing:{stage}:{eval_pack_ref}:{ref}")
        if eval_pack_ref not in pipeline_eval_refs:
            failures.append(f"registry_pipeline_eval_pack_missing:{stage}:{eval_pack_ref}")
        else:
            pipeline_positions.append(pipeline_eval_refs.index(eval_pack_ref))
        for ref in _contract_refs(contract)[:3]:
            if ref not in pipeline_refs:
                failures.append(f"registry_pipeline_ref_missing:{stage}:{ref}")
    if pipeline_positions != sorted(pipeline_positions) or len(pipeline_positions) != len(eval_order):
        failures.append("registry_pipeline_eval_pack_order_invalid")
    return {
        "failures": failures,
        "registry_report": report,
        "entries": entries,
        "pipeline_eval_refs": pipeline_eval_refs,
    }


def _track_failures(track: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    contracts = _contracts_by_stage(policy)
    failures: List[str] = []
    track_id = str(track.get("id") or "<missing>")
    if track.get("apiVersion") != API_VERSION:
        failures.append(f"track_api_version_invalid:{track_id}")
    if track.get("kind") != TRACK_KIND:
        failures.append(f"track_kind_invalid:{track_id}")
    if not SAFE_ID_RE.match(track_id):
        failures.append(f"track_id_invalid:{track_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(track.get("trace_id") or "")):
        failures.append(f"track_trace_id_invalid:{track_id}")
    if str(track.get("status") or "") not in {"draft", "ready", "blocked", "retired"}:
        failures.append(f"track_status_invalid:{track_id}:{track.get('status')}")
    if str(track.get("pipeline_ref") or "") != str(policy.get("required_pipeline_ref") or ""):
        failures.append(f"track_pipeline_ref_mismatch:{track_id}:{track.get('pipeline_ref')}")
    if _as_string_list(track.get("stage_order")) != _as_string_list(policy.get("required_stage_order")):
        failures.append(f"track_stage_order_invalid:{track_id}")
    stages = track.get("stages") if isinstance(track.get("stages"), list) else []
    stage_names = [str(item.get("stage") or "") for item in stages if isinstance(item, dict)]
    if stage_names != REQUIRED_STAGE_ORDER:
        failures.append(f"track_stages_order_invalid:{track_id}")
    seen: set[str] = set()
    for item in stages:
        if not isinstance(item, dict):
            failures.append(f"track_stage_not_object:{track_id}")
            continue
        stage = str(item.get("stage") or "")
        contract = contracts.get(stage, {})
        if stage not in REQUIRED_STAGE_ORDER:
            failures.append(f"track_stage_unknown:{track_id}:{stage}")
            continue
        for dependency in _as_string_list(item.get("depends_on")):
            if dependency not in seen:
                failures.append(f"track_dependency_after_stage:{track_id}:{stage}:{dependency}")
        seen.add(stage)
        if str(item.get("eval_pack_ref") or "") != str(contract.get("eval_pack_ref") or ""):
            failures.append(f"track_eval_pack_ref_mismatch:{track_id}:{stage}:{item.get('eval_pack_ref')}")
        if item.get("required_refs_present") is not True:
            failures.append(f"track_required_refs_not_present:{track_id}:{stage}")
    finalization = track.get("finalization") if isinstance(track.get("finalization"), dict) else {}
    for key in ["dependency_order_checked", "registry_attachment_checked", "docs_and_changelog_checked"]:
        if finalization.get(key) is not True:
            failures.append(f"track_finalization_{key}_not_true:{track_id}")
    return failures


def validate_typed_governance_track_policy(
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
    track_results: List[Dict[str, Any]] = []

    refs_to_resolve = _as_string_list(payload.get("refs"))
    for contract in _contracts_by_stage(policy).values():
        refs_to_resolve.extend(_contract_refs(contract))
    policy_refs = _resolve_refs(sorted(set(refs_to_resolve)), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    example_ref_results = _resolve_refs(_as_string_list(policy.get("required_example_sets")), project_root=project, package_root=package, owner="required_example_sets")
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
        tracks = example_set.get("tracks") if isinstance(example_set.get("tracks"), list) else []
        if not tracks:
            failures.append(f"example_set_tracks_empty:{item['ref']}")
        for track in tracks:
            if not isinstance(track, dict):
                failures.append(f"track_not_object:{item['ref']}")
                continue
            track_id = str(track.get("id") or "<missing>")
            track_failures = _track_failures(track, payload)
            refs_result = _resolve_refs(_as_string_list(track.get("refs")), project_root=project, package_root=package, owner=track_id)
            track_failures.extend(refs_result["failures"])
            failures.extend(track_failures)
            all_resolved_refs.extend(refs_result["resolved_refs"])
            all_missing_refs.extend(refs_result["missing_refs"])
            all_unsafe_refs.extend(refs_result["unsafe_refs"])
            track_results.append(
                {
                    "id": track_id,
                    "ok": not track_failures,
                    "status": str(track.get("status") or ""),
                    "stages": len(track.get("stages") if isinstance(track.get("stages"), list) else []),
                    "failures": sorted(set(track_failures)),
                }
            )

    checks = [
        {"id": "dependency_order", "status": "passed" if not any("order" in item or "dependency" in item for item in failures) else "failed"},
        {"id": "registry_attachment", "status": "passed" if not any("registry_" in item for item in failures) else "failed"},
        {"id": "policy_schema_runtime_tests", "status": "passed" if not any("contract" in item or "ref_missing" in item for item in failures) else "failed"},
        {"id": "docs_and_changelog_refs", "status": "passed" if not any("docs" in item or "changelog" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "tracks": len(track_results),
        "passing_tracks": sum(1 for item in track_results if item["ok"]),
        "contracts": len(_contracts_by_stage(policy)),
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
        "track_results": sorted(track_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def typed_governance_track_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("typed_governance_track_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge typed governance contract tracking.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/typed-governance-track.json",
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

    report = validate_typed_governance_track_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "TypedGovernanceTrackValidationSummary",
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
