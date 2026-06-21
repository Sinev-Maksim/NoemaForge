#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_route_distinction_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate that Model Selection and Model Evolution stay distinct in routing and GUI copy.
Inputs: model-route-distinction policy, Admin runtime, Admin GUI server and dashboard sources.
Outputs: JSON-compatible ModelRouteDistinctionValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_model_route_distinction_runtime.py
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
API_VERSION = "noemaforge.model-route-distinction/v1"
POLICY_KIND = "ModelRouteDistinctionPolicy"
REPORT_KIND = "ModelRouteDistinctionValidationReport"
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
    if str(policy.get("activation_state") or "") != "gui_model_selection_evolution_distinction":
        failures.append("policy_activation_state_invalid")
    for key in ["require_docs_and_changelog_refs", "require_no_live_model_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["required_runtime_scripts", "required_ui_files", "required_selection_tokens", "required_evolution_tokens", "required_ui_tokens"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    for key in ["selection_route", "evolution_route"]:
        route = policy.get(key)
        if not isinstance(route, dict):
            failures.append(f"policy_{key}_missing")
            continue
        for field in ["id", "intent", "execute_mode", "persona", "endpoint", "artifact_group"]:
            if not str(route.get(field) or "").strip():
                failures.append(f"policy_{key}_{field}_empty")
    if not isinstance(policy.get("route_samples"), list) or not policy.get("route_samples"):
        failures.append("policy_route_samples_empty")
    return failures


def _ensure_import_path() -> None:
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))


def _route_by_id(routes: Sequence[Dict[str, Any]], route_id: str) -> Dict[str, Any]:
    for route in routes:
        if str(route.get("id") or "") == route_id:
            return route
    return {}


def _route_report(policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    _ensure_import_path()
    import admin_runtime  # type: ignore

    selection_expected = policy.get("selection_route") if isinstance(policy.get("selection_route"), dict) else {}
    evolution_expected = policy.get("evolution_route") if isinstance(policy.get("evolution_route"), dict) else {}
    routes = getattr(admin_runtime, "ROUTES", [])
    selection_route = _route_by_id(routes, str(selection_expected.get("id") or ""))
    evolution_route = _route_by_id(routes, str(evolution_expected.get("id") or ""))
    for name, expected, actual in [
        ("selection", selection_expected, selection_route),
        ("evolution", evolution_expected, evolution_route),
    ]:
        if not actual:
            failures.append(f"{name}_route_missing")
            continue
        for field in ["id", "intent", "execute_mode"]:
            if str(actual.get(field) or "") != str(expected.get(field) or ""):
                failures.append(f"{name}_route_{field}_mismatch:{actual.get(field)}")
    if selection_route and evolution_route:
        for field in ["id", "label", "intent", "execute_mode"]:
            if str(selection_route.get(field) or "") == str(evolution_route.get(field) or ""):
                failures.append(f"routes_not_distinct:{field}")
        selection_cmds = " ".join(str(x) for x in selection_route.get("suggested_commands") or [])
        evolution_cmds = " ".join(str(x) for x in evolution_route.get("suggested_commands") or [])
        if "model-selection" not in selection_cmds or "first-start" not in selection_cmds:
            failures.append("selection_suggested_commands_do_not_name_selection")
        if "model-evolution" not in evolution_cmds:
            failures.append("evolution_suggested_commands_do_not_name_evolution")
    sample_reports: List[Dict[str, Any]] = []
    for sample in policy.get("route_samples") or []:
        if not isinstance(sample, dict):
            failures.append("route_sample_not_object")
            continue
        text = str(sample.get("text") or "")
        expected_id = str(sample.get("expected_id") or "")
        routed = admin_runtime.route_request(text)
        actual_id = str(routed.get("id") or "")
        ok = actual_id == expected_id
        if not ok:
            failures.append(f"route_sample_mismatch:{expected_id}:{actual_id}:{text}")
        sample_reports.append({
            "text": text,
            "expected_id": expected_id,
            "actual_id": actual_id,
            "intent": routed.get("intent"),
            "execute_mode": routed.get("execute_mode"),
            "ok": ok,
        })
    cross = policy.get("forbidden_cross_route_tokens") if isinstance(policy.get("forbidden_cross_route_tokens"), dict) else {}
    for token in _as_string_list(cross.get("selection_execute_modes")):
        if str(selection_route.get("execute_mode") or "") == token:
            failures.append(f"selection_cross_execute_mode:{token}")
    for token in _as_string_list(cross.get("evolution_execute_modes")):
        if str(evolution_route.get("execute_mode") or "") == token:
            failures.append(f"evolution_cross_execute_mode:{token}")
    return {
        "failures": failures,
        "selection_route": {k: selection_route.get(k) for k in ["id", "label", "intent", "pipeline_id", "execute_mode"]},
        "evolution_route": {k: evolution_route.get(k) for k in ["id", "label", "intent", "pipeline_id", "execute_mode"]},
        "samples": sample_reports,
    }


def _gui_source_report(policy: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    reports: List[Dict[str, Any]] = []
    source_texts: Dict[str, str] = {}
    for ref in _as_string_list(policy.get("required_runtime_scripts")) + _as_string_list(policy.get("required_ui_files")):
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        text = load_text(resolved["path"]) if resolved.get("ok") else ""
        source_texts[ref] = text
        local_failures: List[str] = []
        if not resolved.get("ok"):
            local_failures.append(f"source_missing:{ref}")
        reports.append({"ref": ref, "ok": not local_failures, "failures": local_failures, "resolved": resolved})
        failures.extend(local_failures)
    admin_gui = source_texts.get("noemaforge/src/admin_gui_server.py", "")
    app_js = source_texts.get("noemaforge/templates/pipeline-dashboard/app.js", "")
    index_html = source_texts.get("noemaforge/templates/pipeline-dashboard/index.html", "")
    selection_block = _slice_between(admin_gui, "def model_selection(", ["def model_selection_continue", "def epoch_apply"])
    evolution_block = _slice_between(admin_gui, "def model_evolution(", ["def workflow_stop", "def usecases"])
    for token in _as_string_list(policy.get("required_selection_tokens")):
        if token not in admin_gui:
            failures.append(f"selection_token_missing:{token}")
    for token in _as_string_list(policy.get("required_evolution_tokens")):
        if token not in admin_gui:
            failures.append(f"evolution_token_missing:{token}")
    for token in _as_string_list(policy.get("required_ui_tokens")):
        if token not in (app_js + "\n" + index_html):
            failures.append(f"ui_token_missing:{token}")
    selection_endpoint = str((policy.get("selection_route") or {}).get("endpoint") or "")
    evolution_endpoint = str((policy.get("evolution_route") or {}).get("endpoint") or "")
    if selection_endpoint and selection_endpoint not in selection_block:
        failures.append("selection_endpoint_missing_from_selection_block")
    if evolution_endpoint and evolution_endpoint not in evolution_block:
        failures.append("evolution_endpoint_missing_from_evolution_block")
    cross = policy.get("forbidden_cross_route_tokens") if isinstance(policy.get("forbidden_cross_route_tokens"), dict) else {}
    for token in _as_string_list(cross.get("selection_endpoints")):
        if token in selection_block:
            failures.append(f"selection_cross_endpoint:{token}")
    for token in _as_string_list(cross.get("evolution_endpoints")):
        if token in evolution_block:
            failures.append(f"evolution_cross_endpoint:{token}")
    if str((policy.get("selection_route") or {}).get("persona") or "") not in selection_block:
        failures.append("selection_persona_missing_from_selection_block")
    if str((policy.get("evolution_route") or {}).get("persona") or "") not in evolution_block:
        failures.append("evolution_persona_missing_from_evolution_block")
    return {
        "failures": failures,
        "reports": reports,
        "selection_block_chars": len(selection_block),
        "evolution_block_chars": len(evolution_block),
        "ui_chars": len(app_js) + len(index_html),
    }


def _usecase_report(policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    _ensure_import_path()
    import admin_gui_server  # type: ignore

    server = object.__new__(admin_gui_server.AdminGuiServer)
    selection_text = server.explain_usecase("что значит оптимизируй модель для dev team", "ru")
    evolution_text = server.explain_usecase("что значит эволюция модели", "ru")
    cases = server.usecases().get("usecases", [])
    case_titles = [str(item.get("title") or "") for item in cases if isinstance(item, dict)]
    case_summaries = [str(item.get("summary") or "") for item in cases if isinstance(item, dict)]
    selection_expected = str((policy.get("selection_route") or {}).get("artifact_group") or "")
    evolution_expected = str((policy.get("evolution_route") or {}).get("artifact_group") or "")
    if "отбор runtime-модели" not in selection_text or "Эпоха не меняется" not in selection_text:
        failures.append("selection_help_not_semantically_selection")
    if "measured improvement cycle" not in evolution_text or "не скрытое production-обучение" not in evolution_text:
        failures.append("evolution_help_not_semantically_evolution")
    if not any("Оптимизируй модель" in title for title in case_titles):
        failures.append("selection_usecase_title_missing")
    if not any("Эволюция модели" in title for title in case_titles):
        failures.append("evolution_usecase_title_missing")
    if not any("candidate" in summary or "отбор" in summary for summary in case_summaries):
        failures.append("selection_usecase_summary_missing")
    if not any("Measured improvement cycle" in summary or "mutation_plan" in summary for summary in case_summaries):
        failures.append("evolution_usecase_summary_missing")
    if selection_expected == evolution_expected:
        failures.append("artifact_group_policy_not_distinct")
    return {
        "failures": failures,
        "selection_help": selection_text,
        "evolution_help": evolution_text,
        "usecase_titles": case_titles,
    }


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
        "Model Selection",
        "Model Evolution",
        "visually and semantically distinct",
    ]
    reports: List[Dict[str, Any]] = []
    satisfied = False
    for path in docs:
        exists = path.exists()
        text = load_text(path) if exists else ""
        missing = [token for token in tokens if token and token not in text]
        if exists and not missing:
            satisfied = True
        reports.append({"path": _display_path(path), "ok": exists and not missing, "missing": missing, "exists": exists})
    # Documented in >=1 existing canonical doc, not every candidate (legacy/alt paths).
    if not satisfied:
        owner = str(payload.get("id") or "policy")
        failures.append(f"docs_tokens_missing:{owner}:{','.join(t for t in tokens if t)}")
    return {"failures": failures, "reports": reports}


def validate_model_route_distinction_policy(
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
    route = _route_report(policy)
    failures.extend(route["failures"])
    gui = _gui_source_report(policy, project_root=project, package_root=package)
    failures.extend(gui["failures"])
    usecases = _usecase_report(policy)
    failures.extend(usecases["failures"])
    docs = _docs_report(payload, project_root=project, package_root=package) if include_docs else {"failures": [], "reports": []}
    failures.extend(docs["failures"])
    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "route_samples": len(route["samples"]),
        "valid_route_samples": sum(1 for item in route["samples"] if item.get("ok")),
        "gui_source_reports": len(gui["reports"]),
        "docs_reports": len(docs["reports"]),
        "selection_block_chars": gui["selection_block_chars"],
        "evolution_block_chars": gui["evolution_block_chars"],
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
        "route": route,
        "gui": gui,
        "usecases": usecases,
        "docs": docs,
    }


def benchmark_route_distinction(*, package_root: Path | str, iterations: int = 200) -> Dict[str, Any]:
    root = Path(package_root).resolve()
    policy = load_policy(root / "configs" / "model-route-distinction-policy.json")
    started = time.perf_counter()
    failures = 0
    for _ in range(iterations):
        report = validate_model_route_distinction_policy(
            policy,
            project_root=root.parent,
            package_root=root,
            include_docs=False,
        )
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
        "kind": "ModelRouteDistinctionValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Model Selection vs Model Evolution route distinction")
    parser.add_argument("--policy", default=str(SRC_DIR.parent / "configs" / "model-route-distinction-policy.json"))
    parser.add_argument("--project-root", default=str(SRC_DIR.parent.parent))
    parser.add_argument("--package-root", default=str(SRC_DIR.parent))
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--skip-docs", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_model_route_distinction_policy(
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
