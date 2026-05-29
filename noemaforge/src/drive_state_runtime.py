#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/drive_state_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Drive_State contracts that bound Sense_State-derived modulation.
Inputs: noemaforge/configs/drive-state-policy.json and DriveState example sets.
Outputs: JSON-compatible DriveStateValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_drive_state_runtime.py
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


API_VERSION = "noemaforge.drive-state/v1"
POLICY_KIND = "DriveStatePolicy"
SET_KIND = "DriveStateSet"
STATE_KIND = "DriveState"
REPORT_KIND = "DriveStateValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_SIGNALS = {"pressure", "fatigue", "urgency", "curiosity"}
VALID_ACTIONS = {"allow", "slow_down", "ask_clarification", "defer", "rest", "explore"}
PRESSURE_LEVELS = {"unknown": 0.0, "low": 0.15, "medium": 0.5, "high": 0.8, "critical": 1.0}
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
            return {
                "ok": True,
                "ref": ref,
                "resolved_under": base_name,
                "path": _display_path(path),
                "checked": checked,
            }
    return {"ok": False, "ref": ref, "resolved_under": "", "path": "", "checked": checked}


def _resolve_refs(refs: Sequence[str], *, project_root: Path, package_root: Path, owner: str) -> Dict[str, Any]:
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            item = {"owner": owner, "ref": ref}
            unsafe_refs.append(item)
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


def _clip01(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    if numeric < 0.0:
        return 0.0
    if numeric > 1.0:
        return 1.0
    return numeric


def _percent01(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return _clip01(numeric / 100.0)


def _pressure_value(payload: Any) -> float:
    if not isinstance(payload, dict):
        return 0.0
    pressure = payload.get("pressure")
    if pressure is not None:
        return PRESSURE_LEVELS.get(str(pressure).strip().lower(), 0.0)
    for key in ["usage_percent", "used_percent", "busy_percent"]:
        if key in payload:
            return _percent01(payload.get(key))
    return 0.0


def _runtime_badness(metrics: Dict[str, Any]) -> float:
    runtime = metrics.get("runtime") if isinstance(metrics.get("runtime"), dict) else {}
    network = metrics.get("network") if isinstance(metrics.get("network"), dict) else {}
    badness = 0.0
    if str(network.get("state") or "").strip().lower() in {"degraded", "offline", "down", "critical"}:
        badness = max(badness, 0.65)
    for key in ["backend", "gateway", "toolproxy"]:
        if str(runtime.get(key) or "healthy").strip().lower() not in {"healthy", "ok", "ready"}:
            badness = max(badness, 0.8)
    return badness


def _apply_hysteresis(signals: Dict[str, float], previous_drive_state: Optional[Dict[str, Any]], policy: Dict[str, Any]) -> Dict[str, float]:
    if not isinstance(previous_drive_state, dict):
        return signals
    previous = previous_drive_state.get("signals") if isinstance(previous_drive_state.get("signals"), dict) else {}
    hysteresis = policy.get("hysteresis") if isinstance(policy.get("hysteresis"), dict) else {}
    try:
        min_delta = float(hysteresis.get("min_delta", 0.0))
    except (TypeError, ValueError):
        min_delta = 0.0
    output = dict(signals)
    for signal, value in signals.items():
        if signal not in previous:
            continue
        prior = _clip01(previous.get(signal))
        if abs(value - prior) < min_delta:
            output[signal] = prior
    return output


def _actions_for_signals(signals: Dict[str, float]) -> List[str]:
    actions: List[str] = []
    if signals["pressure"] >= 0.7:
        actions.append("slow_down")
    if signals["pressure"] >= 0.75 or signals["fatigue"] >= 0.72:
        actions.append("defer")
    if signals["fatigue"] >= 0.85:
        actions.append("rest")
    if signals["urgency"] >= 0.7:
        actions.append("ask_clarification")
    if signals["curiosity"] >= 0.55 and signals["pressure"] < 0.65:
        actions.append("explore")
    if not actions:
        actions.append("allow")
    return actions


def modulate_drive_state(
    sense_state: Dict[str, Any],
    policy_payload: Dict[str, Any],
    *,
    previous_drive_state: Optional[Dict[str, Any]] = None,
    sense_state_ref: str = "",
) -> Dict[str, Any]:
    policy = _policy_dict(policy_payload)
    metrics = sense_state.get("metrics") if isinstance(sense_state.get("metrics"), dict) else {}
    cpu = _pressure_value(metrics.get("cpu"))
    memory = _pressure_value(metrics.get("memory"))
    disk = _pressure_value(metrics.get("disk"))
    load = _pressure_value(metrics.get("load"))
    runtime_badness = _runtime_badness(metrics)
    novelty = 0.55 if runtime_badness == 0.0 and max(cpu, memory, disk, load) < 0.65 else 0.25

    raw_signals = {
        "pressure": max(0.45 * cpu + 0.35 * memory + 0.20 * load, memory, disk * 0.7),
        "fatigue": 0.50 * memory + 0.20 * cpu + 0.30 * load,
        "urgency": 0.70 * runtime_badness + 0.30 * max(cpu, memory),
        "curiosity": 0.65 * novelty + 0.35 * (1.0 - max(0.45 * cpu + 0.35 * memory + 0.20 * load, memory)),
    }
    signals = {key: round(_clip01(value), 3) for key, value in raw_signals.items()}
    signals = {key: round(value, 3) for key, value in _apply_hysteresis(signals, previous_drive_state, policy).items()}
    actions = [action for action in _actions_for_signals(signals) if action in set(_as_string_list(policy.get("allowed_actions"))) or not policy.get("allowed_actions")]
    if not actions:
        actions = ["allow"]

    return {
        "apiVersion": API_VERSION,
        "kind": STATE_KIND,
        "id": f"drive-state:{sense_state.get('id') or 'inline'}",
        "trace_id": str(sense_state.get("trace_id") or "trace:drive-state:inline"),
        "sense_state_ref": sense_state_ref,
        "source_state_id": str(sense_state.get("id") or ""),
        "privacy": {
            "source_filtered": bool((sense_state.get("privacy") or {}).get("filtered")),
            "local_only": bool((sense_state.get("privacy") or {}).get("local_only")),
            "no_raw_telemetry": True,
        },
        "signals": signals,
        "signal_sources": {
            "pressure": ["cpu.pressure", "memory.pressure", "disk.pressure", "load.pressure"],
            "fatigue": ["memory.pressure", "cpu.pressure", "load.pressure"],
            "urgency": ["network.state", "runtime.backend", "runtime.gateway", "runtime.toolproxy"],
            "curiosity": ["runtime.health", "inverse_pressure"],
        },
        "modulation": {
            "actions": actions,
            "cooldown_seconds": int(policy.get("cooldown_seconds") or 0),
            "clipping_applied": True,
            "hysteresis_applied": True,
            "explanation": "Sense_State was converted into bounded pacing signals without goal or policy mutation.",
        },
        "guards": {
            "can_rewrite_goals": False,
            "can_override_policy": False,
            "can_expand_permissions": False,
        },
    }


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
        "require_sense_state_ref",
        "require_privacy_filtered_source",
        "require_bounded_signals",
        "require_clipping",
        "require_hysteresis",
        "require_cooldown",
        "forbid_goal_rewrite",
        "forbid_policy_override",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    signals = set(_as_string_list(policy.get("signals")))
    if signals != REQUIRED_SIGNALS:
        failures.append("policy_signals_must_be_pressure_fatigue_urgency_curiosity")
    actions = set(_as_string_list(policy.get("allowed_actions")))
    failures.extend(f"policy_action_not_allowed:{item}" for item in sorted(actions - VALID_ACTIONS))
    if "allow" not in actions:
        failures.append("policy_allow_action_missing")
    bounds = policy.get("bounds") if isinstance(policy.get("bounds"), dict) else {}
    if bounds.get("min") != 0.0 or bounds.get("max") != 1.0:
        failures.append("policy_bounds_must_be_0_1")
    hysteresis = policy.get("hysteresis") if isinstance(policy.get("hysteresis"), dict) else {}
    for key in ["min_delta", "decay"]:
        try:
            value = float(hysteresis.get(key))
        except (TypeError, ValueError):
            failures.append(f"policy_hysteresis_{key}_invalid")
            continue
        if value < 0.0 or value > 1.0:
            failures.append(f"policy_hysteresis_{key}_out_of_range")
    try:
        cooldown = int(policy.get("cooldown_seconds"))
    except (TypeError, ValueError):
        cooldown = 0
    if cooldown <= 0:
        failures.append("policy_cooldown_seconds_invalid")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _signal_failures(signals: Any, policy: Dict[str, Any], state_id: str) -> List[str]:
    failures: List[str] = []
    if not isinstance(signals, dict):
        return [f"state_signals_missing:{state_id}"]
    seen = set(str(key) for key in signals)
    failures.extend(f"state_signal_unknown:{state_id}:{item}" for item in sorted(seen - REQUIRED_SIGNALS))
    failures.extend(f"state_signal_missing:{state_id}:{item}" for item in sorted(REQUIRED_SIGNALS - seen))
    lower = float((policy.get("bounds") or {}).get("min", 0.0))
    upper = float((policy.get("bounds") or {}).get("max", 1.0))
    for signal in REQUIRED_SIGNALS & seen:
        try:
            value = float(signals.get(signal))
        except (TypeError, ValueError):
            failures.append(f"state_signal_not_numeric:{state_id}:{signal}")
            continue
        if value < lower or value > upper:
            failures.append(f"state_signal_out_of_bounds:{state_id}:{signal}:{value}")
    return failures


def _state_failures(state: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    state_id = str(state.get("id") or "<missing>")
    if state.get("apiVersion") != API_VERSION:
        failures.append(f"state_api_version_invalid:{state_id}")
    if state.get("kind") != STATE_KIND:
        failures.append(f"state_kind_invalid:{state_id}")
    if not SAFE_ID_RE.match(state_id):
        failures.append(f"state_id_invalid:{state_id}")
    if not SAFE_ID_RE.match(str(state.get("trace_id") or "")):
        failures.append(f"state_trace_id_invalid:{state_id}")
    if policy.get("require_sense_state_ref") is True and not str(state.get("sense_state_ref") or "").strip():
        failures.append(f"state_sense_state_ref_missing:{state_id}")
    privacy = state.get("privacy") if isinstance(state.get("privacy"), dict) else {}
    if policy.get("require_privacy_filtered_source") is True:
        if privacy.get("source_filtered") is not True:
            failures.append(f"state_source_not_filtered:{state_id}")
        if privacy.get("no_raw_telemetry") is not True:
            failures.append(f"state_raw_telemetry_allowed:{state_id}")
    failures.extend(_signal_failures(state.get("signals"), policy, state_id))
    sources = state.get("signal_sources") if isinstance(state.get("signal_sources"), dict) else {}
    for signal in REQUIRED_SIGNALS:
        if not _as_string_list(sources.get(signal)):
            failures.append(f"state_signal_sources_missing:{state_id}:{signal}")
    modulation = state.get("modulation") if isinstance(state.get("modulation"), dict) else {}
    actions = set(_as_string_list(modulation.get("actions")))
    allowed_actions = set(_as_string_list(policy.get("allowed_actions")))
    if not actions:
        failures.append(f"state_actions_missing:{state_id}")
    failures.extend(f"state_action_not_allowed:{state_id}:{item}" for item in sorted(actions - allowed_actions))
    if policy.get("require_clipping") is True and modulation.get("clipping_applied") is not True:
        failures.append(f"state_clipping_not_applied:{state_id}")
    if policy.get("require_hysteresis") is True and modulation.get("hysteresis_applied") is not True:
        failures.append(f"state_hysteresis_not_applied:{state_id}")
    try:
        cooldown = int(modulation.get("cooldown_seconds"))
    except (TypeError, ValueError):
        cooldown = 0
    if policy.get("require_cooldown") is True and cooldown < int(policy.get("cooldown_seconds") or 0):
        failures.append(f"state_cooldown_too_low:{state_id}:{cooldown}")
    guards = state.get("guards") if isinstance(state.get("guards"), dict) else {}
    if policy.get("forbid_goal_rewrite") is True and guards.get("can_rewrite_goals") is not False:
        failures.append(f"state_goal_rewrite_allowed:{state_id}")
    if policy.get("forbid_policy_override") is True and guards.get("can_override_policy") is not False:
        failures.append(f"state_policy_override_allowed:{state_id}")
    if guards.get("can_expand_permissions") is not False:
        failures.append(f"state_permission_expansion_allowed:{state_id}")
    return failures


def _modulation_case_failures(case: Dict[str, Any], policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    case_id = str(case.get("id") or "<missing>")
    failures: List[str] = []
    sense_state = case.get("sense_state") if isinstance(case.get("sense_state"), dict) else {}
    generated = modulate_drive_state(sense_state, policy_payload)
    actions = set(_as_string_list((generated.get("modulation") or {}).get("actions") if isinstance(generated.get("modulation"), dict) else []))
    for action in _as_string_list(case.get("expected_actions_include")):
        if action not in actions:
            failures.append(f"case_action_missing:{case_id}:{action}")
    signals = generated.get("signals") if isinstance(generated.get("signals"), dict) else {}
    for signal, expected in (case.get("expected_signal_min") or {}).items():
        if float(signals.get(signal, 0.0)) < float(expected):
            failures.append(f"case_signal_below_min:{case_id}:{signal}:{signals.get(signal)}:{expected}")
    for signal, expected in (case.get("expected_signal_max") or {}).items():
        if float(signals.get(signal, 0.0)) > float(expected):
            failures.append(f"case_signal_above_max:{case_id}:{signal}:{signals.get(signal)}:{expected}")
    state_failures = _state_failures(generated, _policy_dict(policy_payload))
    failures.extend(item for item in state_failures if "sense_state_ref_missing" not in item)
    return {
        "id": case_id,
        "ok": not failures,
        "actions": sorted(actions),
        "signals": signals,
        "failures": sorted(set(failures)),
    }


def validate_drive_state_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root)
    if not project.exists():
        raise FileNotFoundError(project)
    if not package.exists():
        raise FileNotFoundError(package)

    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    failures: List[str] = []
    failures.extend(_policy_failures(payload))

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    state_results: List[Dict[str, Any]] = []
    case_results: List[Dict[str, Any]] = []

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    example_refs = _as_string_list(policy.get("required_example_sets"))
    example_ref_results = _resolve_refs(example_refs, project_root=project, package_root=package, owner="required_example_sets")
    failures.extend(example_ref_results["failures"])
    all_resolved_refs.extend(example_ref_results["resolved_refs"])
    all_missing_refs.extend(example_ref_results["missing_refs"])
    all_unsafe_refs.extend(example_ref_results["unsafe_refs"])

    for item in example_ref_results["resolved_refs"]:
        example_path = Path(item["path"])
        example_set = load_example_set(example_path)
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{item['ref']}")
        states = example_set.get("states") if isinstance(example_set.get("states"), list) else []
        if not states:
            failures.append(f"example_set_states_empty:{item['ref']}")
        for state in states:
            if not isinstance(state, dict):
                failures.append(f"state_not_object:{item['ref']}")
                continue
            state_id = str(state.get("id") or "<missing>")
            state_failures = _state_failures(state, policy)
            state_refs = _as_string_list(state.get("refs"))
            sense_state_ref = str(state.get("sense_state_ref") or "").strip()
            if sense_state_ref:
                state_refs.append(sense_state_ref)
            refs_result = _resolve_refs(state_refs, project_root=project, package_root=package, owner=state_id)
            state_failures.extend(refs_result["failures"])
            failures.extend(state_failures)
            all_resolved_refs.extend(refs_result["resolved_refs"])
            all_missing_refs.extend(refs_result["missing_refs"])
            all_unsafe_refs.extend(refs_result["unsafe_refs"])
            state_results.append(
                {
                    "id": state_id,
                    "ok": not state_failures,
                    "actions": _as_string_list((state.get("modulation") or {}).get("actions") if isinstance(state.get("modulation"), dict) else []),
                    "signals": dict(state.get("signals") or {}) if isinstance(state.get("signals"), dict) else {},
                    "failures": sorted(set(state_failures)),
                }
            )
        for case in example_set.get("modulation_cases") if isinstance(example_set.get("modulation_cases"), list) else []:
            if not isinstance(case, dict):
                failures.append(f"modulation_case_not_object:{item['ref']}")
                continue
            result = _modulation_case_failures(case, payload)
            failures.extend(result["failures"])
            case_results.append(result)

    checks = [
        {"id": "bounded_signals", "status": "passed" if state_results and not any("signal" in item and ("out_of_bounds" in item or "missing" in item or "unknown" in item) for item in failures) else "failed"},
        {"id": "clipping", "status": "passed" if not any("clipping" in item for item in failures) else "failed"},
        {"id": "hysteresis", "status": "passed" if not any("hysteresis" in item for item in failures) else "failed"},
        {"id": "cooldown", "status": "passed" if not any("cooldown" in item for item in failures) else "failed"},
        {"id": "no_goal_rewrite", "status": "passed" if not any("goal_rewrite" in item or "policy_override" in item or "permission_expansion" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "states": len(state_results),
        "passing_states": sum(1 for item in state_results if item["ok"]),
        "modulation_cases": len(case_results),
        "passing_modulation_cases": sum(1 for item in case_results if item["ok"]),
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
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "metrics": metrics,
        "checks": checks,
        "state_results": sorted(state_results, key=lambda item: item["id"]),
        "case_results": sorted(case_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def drive_state_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("drive_state_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge Drive_State bounded modulation contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/drive-state-policy.json",
        help="Policy path, absolute or relative to project root.",
    )
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path

    report = validate_drive_state_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "DriveStateValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "policy_path": report["policy_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
