#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/media_capture_privacy_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate media capture privacy gates for microphone, camera and virtual camera paths.
Inputs: noemaforge/configs/media-capture-privacy-policy.json and media capture examples.
Outputs: JSON-compatible MediaCapturePrivacyValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_media_capture_privacy_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.media-capture-privacy/v1"
POLICY_KIND = "MediaCapturePrivacyPolicy"
SET_KIND = "MediaCapturePrivacyExampleSet"
REPORT_KIND = "MediaCapturePrivacyValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_ACTIONS = {"voice.capture_live", "voice.transcribe_live", "camera.mask_virtual_camera"}
REQUIRED_DOCS = [
    "noemaforge/docs/README.md",
    "noemaforge/docs/TODO.md",
    "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
    "noemaforge/docs/reference/PROJECT_CONTEXT.md",
    "noemaforge/docs/history/CHANGELOG.md",
]
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")


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
    candidates = [("project", project_root / ref), ("package", package_root / ref)]
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


def load_policy(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_example_set(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _guarded_action_map(policy: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    actions = policy.get("guarded_actions") if isinstance(policy.get("guarded_actions"), list) else []
    return {str(item.get("action") or ""): item for item in actions if isinstance(item, dict)}


def validate_capture_request(request: Dict[str, Any], policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    policy = _policy_dict(policy_payload)
    request = request if isinstance(request, dict) else {}
    action = str(request.get("action") or "").strip()
    guard = _guarded_action_map(policy).get(action)
    failures: List[str] = []
    if not guard:
        failures.append("unknown_guarded_action")
        return {"ok": False, "decision": "block", "action": action, "failures": failures}
    if str(request.get("source") or "") != str(guard.get("source") or ""):
        failures.append("source_mismatch")
    if guard.get("target") and str(request.get("target") or "") != str(guard.get("target") or ""):
        failures.append("target_mismatch")
    if guard.get("require_operator_consent") is True and request.get("operator_consent") is not True:
        failures.append("operator_consent_required")
    if guard.get("require_visible_privacy_state") is True and request.get("visible_privacy_state") is not True:
        failures.append("visible_privacy_state_required")
    if guard.get("require_manual_operator_command") is True and request.get("manual_operator_command") is not True:
        failures.append("manual_operator_command_required")
    if guard.get("require_user_selected_target") is True and request.get("user_selected_target") is not True:
        failures.append("user_selected_target_required")
    if request.get("autostart") is not False:
        failures.append("autostart_forbidden")
    max_allowed = float(guard.get("max_seconds") or 0)
    requested_seconds = float(request.get("max_seconds") or 0)
    if max_allowed and requested_seconds > max_allowed:
        failures.append("max_seconds_exceeds_policy")
    return {"ok": not failures, "decision": "allow" if not failures else "block", "action": action, "failures": sorted(failures)}


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
    for key in ["local_first_default", "require_registry_attachment", "require_docs_and_changelog_refs"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    defaults = policy.get("capture_defaults") if isinstance(policy.get("capture_defaults"), dict) else {}
    for key in ["microphone_enabled_by_default", "camera_enabled_by_default", "virtual_camera_enabled_by_default"]:
        if defaults.get(key) is not False:
            failures.append(f"policy_default_{key}_not_false")
    action_map = _guarded_action_map(policy)
    missing = REQUIRED_ACTIONS.difference(action_map)
    failures.extend(f"policy_guarded_action_missing:{item}" for item in sorted(missing))
    for action, guard in sorted(action_map.items()):
        if guard.get("require_operator_consent") is not True:
            failures.append(f"policy_action_missing_operator_consent:{action}")
        if guard.get("require_visible_privacy_state") is not True:
            failures.append(f"policy_action_missing_visible_privacy_state:{action}")
        if guard.get("require_manual_operator_command") is not True:
            failures.append(f"policy_action_missing_manual_command:{action}")
        if guard.get("autostart") is not False:
            failures.append(f"policy_action_autostart_not_false:{action}")
        if float(guard.get("max_seconds") or 0) > 15:
            failures.append(f"policy_action_max_seconds_too_high:{action}")
    if not _as_string_list(policy.get("required_catalog_entries")):
        failures.append("policy_required_catalog_entries_empty")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {_registry_ref(entry): entry for entry in report.get("normalized_registry", {}).get("entries", []) if isinstance(entry, dict)}
    raw_entries = {_registry_ref(entry): entry for entry in registry.get("entries", []) if isinstance(entry, dict)}
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    if eval_ref not in entries:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    pipeline_ref = "pipeline:firstboot-model-selection:0.31.13.alpha-patched1"
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
    else:
        if eval_ref not in _as_string_list(pipeline.get("eval_pack_refs")):
            failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
        for ref in ["configs/media-capture-privacy-policy.json", "src/media_capture_privacy_runtime.py", "prelaunch/governance/media_capture_privacy.example.json"]:
            if ref not in _as_string_list(pipeline.get("refs")):
                failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "entries": entries, "registry_report": report}


def _surface_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    failures: List[str] = []
    media_catalog = load_json(package_root / "configs" / "media-pipeline-catalog.json")
    pipelines = load_json(package_root / "configs" / "pipelines.json")
    voice_policy = load_text(package_root / "configs" / "voice-backends-policy.yaml")
    static_paths = {
        "admin_runtime": package_root / "src" / "admin_runtime.py",
        "admin_gui_server": package_root / "src" / "admin_gui_server.py",
        "voice_ingest": package_root / "src" / "voice_ingest.py",
        "toolproxy": package_root / "src" / "toolproxy.py",
    }
    static_text = {key: load_text(path) for key, path in static_paths.items()}
    if "enabled: false" not in voice_policy or "microphone:" not in voice_policy:
        failures.append("voice_policy_default_disabled_missing")
    if "microphone:\n  enabled: false" not in voice_policy.replace("\r\n", "\n"):
        failures.append("voice_policy_microphone_default_disabled_missing")
    catalog_entries = {str(item.get("id") or ""): item for item in media_catalog.get("pipelines", []) if isinstance(item, dict)}
    for entry_id in _as_string_list(policy.get("required_catalog_entries")):
        entry = catalog_entries.get(entry_id)
        if not entry:
            failures.append(f"media_catalog_entry_missing:{entry_id}")
            continue
        notes = str(entry.get("notes") or "").lower()
        if entry.get("autostart") is not False:
            failures.append(f"media_catalog_autostart_not_false:{entry_id}")
        for token in ["no camera hijack", "no implicit capture", "visible privacy state"]:
            if token not in notes:
                failures.append(f"media_catalog_privacy_token_missing:{entry_id}:{token}")
    required_gates = policy.get("required_pipeline_gates") if isinstance(policy.get("required_pipeline_gates"), dict) else {}
    for pipeline_id, gates in required_gates.items():
        pipeline = pipelines.get(pipeline_id) if isinstance(pipelines.get(pipeline_id), dict) else {}
        quality_gates = set(_as_string_list(pipeline.get("quality_gates")))
        for gate in _as_string_list(gates):
            if gate not in quality_gates:
                failures.append(f"pipeline_gate_missing:{pipeline_id}:{gate}")
    required_tokens = policy.get("required_static_tokens") if isinstance(policy.get("required_static_tokens"), dict) else {}
    for owner, tokens in required_tokens.items():
        text = static_text.get(owner, "")
        lowered = text.lower()
        for token in _as_string_list(tokens):
            if token.lower() not in lowered:
                failures.append(f"static_token_missing:{owner}:{token}")
    docs_seen = []
    for rel in REQUIRED_DOCS:
        path = project_root / rel
        text = load_text(path) if path.exists() else ""
        if not text:
            failures.append(f"doc_missing:{rel}")
            continue
        docs_seen.append(rel)
        if "media-capture-privacy-core" not in text:
            failures.append(f"doc_token_missing:{rel}:media-capture-privacy-core")
    return {"failures": failures, "catalog_entries": sorted(catalog_entries), "docs_seen": docs_seen}


def validate_media_capture_privacy_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Optional[Path | str] = None,
    registry_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root)
    registry = _as_path(registry_path) if registry_path else package / "configs" / "unified-registry.json"
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    registry_result = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_result["failures"])
    surface = _surface_failures(payload, project_root=project, package_root=package)
    failures.extend(surface["failures"])
    refs = sorted(set(_as_string_list(payload.get("refs")) + _as_string_list(policy.get("required_example_sets"))))
    refs_result = _resolve_refs(refs, project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(refs_result["failures"])
    scenario_results: List[Dict[str, Any]] = []
    for item in _as_string_list(policy.get("required_example_sets")):
        resolved = _resolve_ref(item, project_root=project, package_root=package)
        if not resolved.get("ok"):
            continue
        example_set = load_example_set(Path(resolved["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{item}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{item}")
        scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
        if not scenarios:
            failures.append(f"example_set_empty:{item}")
        for scenario in scenarios:
            scenario_id = str(scenario.get("id") or "<missing>") if isinstance(scenario, dict) else "<invalid>"
            if not SAFE_ID_RE.match(scenario_id):
                failures.append(f"scenario_id_invalid:{scenario_id}")
            result = validate_capture_request((scenario or {}).get("request", {}), payload)
            expected_decision = str((scenario or {}).get("expected_decision") or "")
            expected_failures = sorted(_as_string_list((scenario or {}).get("expected_failures")))
            if result["decision"] != expected_decision:
                failures.append(f"scenario_decision_mismatch:{scenario_id}")
            for expected_failure in expected_failures:
                if expected_failure not in result["failures"]:
                    failures.append(f"scenario_expected_failure_missing:{scenario_id}:{expected_failure}")
            scenario_ref_result = _resolve_refs(_as_string_list((scenario or {}).get("refs")), project_root=project, package_root=package, owner=scenario_id)
            failures.extend(scenario_ref_result["failures"])
            scenario_results.append({"id": scenario_id, "decision": result["decision"], "ok": result["decision"] == expected_decision, "failures": result["failures"]})
    metrics = {
        "guarded_actions": len(_guarded_action_map(policy)),
        "scenarios": len(scenario_results),
        "passing_scenarios": sum(1 for item in scenario_results if item["ok"]),
        "refs": len(refs_result["resolved_refs"]) + len(refs_result["missing_refs"]) + len(refs_result["unsafe_refs"]),
        "resolved_refs": len(refs_result["resolved_refs"]),
        "registry_entries": len(registry_result["entries"]),
        "docs_seen": len(surface["docs_seen"]),
    }
    checks = [
        {"id": "policy_shape", "status": "passed" if not any(item.startswith("policy_") for item in failures) else "failed"},
        {"id": "privacy_gate_examples", "status": "passed" if metrics["passing_scenarios"] == metrics["scenarios"] else "failed"},
        {"id": "media_catalog", "status": "passed" if not any(item.startswith("media_catalog_") for item in failures) else "failed"},
        {"id": "voice_defaults", "status": "passed" if not any(item.startswith("voice_policy_") for item in failures) else "failed"},
        {"id": "registry_attachment", "status": "passed" if not any(item.startswith("registry_") for item in failures) else "failed"},
        {"id": "docs", "status": "passed" if not any(item.startswith("doc_") for item in failures) else "failed"},
    ]
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
        "scenario_results": sorted(scenario_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(refs_result["resolved_refs"], key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(refs_result["missing_refs"], key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(refs_result["unsafe_refs"], key=lambda item: (item["owner"], item["ref"])),
    }


def benchmark_media_capture_privacy(payload: Dict[str, Any], *, iterations: int = 500) -> Dict[str, Any]:
    allowed = {
        "action": "camera.mask_virtual_camera",
        "source": "camera",
        "target": "virtual_camera",
        "operator_consent": True,
        "visible_privacy_state": True,
        "manual_operator_command": True,
        "user_selected_target": True,
        "autostart": False,
        "max_seconds": 0,
    }
    blocked = {
        "action": "voice.capture_live",
        "source": "microphone",
        "operator_consent": False,
        "visible_privacy_state": False,
        "manual_operator_command": False,
        "autostart": True,
        "max_seconds": 60,
    }
    started = time.perf_counter()
    allowed_count = 0
    blocked_count = 0
    for index in range(iterations):
        request = copy.deepcopy(allowed if index % 2 == 0 else blocked)
        result = validate_capture_request(request, payload)
        if result["decision"] == "allow":
            allowed_count += 1
        else:
            blocked_count += 1
    elapsed = time.perf_counter() - started
    return {"iterations": iterations, "allowed": allowed_count, "blocked": blocked_count, "elapsed_sec": elapsed, "ok": allowed_count == iterations // 2 and blocked_count == iterations - iterations // 2}


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge media capture privacy gates.")
    parser.add_argument("--project-root", default=str(_default_project_root()))
    parser.add_argument("--package-root", default="")
    parser.add_argument("--policy", default="noemaforge/configs/media-capture-privacy-policy.json")
    parser.add_argument("--registry", default="")
    parser.add_argument("--summary", action="store_true")
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
    report = validate_media_capture_privacy_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    payload: Dict[str, Any]
    if args.summary:
        payload = {
            "apiVersion": report["apiVersion"],
            "kind": "MediaCapturePrivacyValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
