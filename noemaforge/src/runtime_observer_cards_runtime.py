#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/runtime_observer_cards_runtime.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Runtime observer cards for gateway/backend smoke affirmation.
Inputs: Runtime observer cards policy, Admin GUI server source and dashboard assets.
Outputs: JSON-compatible RuntimeObserverCardsValidationReport artifacts.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_runtime_observer_cards_runtime.py
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
from typing import Any, Dict, List, Sequence


API_VERSION = "noemaforge.runtime-observer-cards/v1"
POLICY_KIND = "RuntimeObserverCardsPolicy"
REPORT_KIND = "RuntimeObserverCardsValidationReport"
POLICY_ID = "runtime-observer-cards-core"
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
    if str(policy.get("activation_state") or "") != "gateway_backend_smoke_observer_cards":
        failures.append("policy_activation_state_invalid")
    if str(policy.get("endpoint") or "") != "/api/runtime/observer-cards":
        failures.append("policy_endpoint_invalid")
    for key in ["require_registry_attachment", "require_docs_and_changelog_refs", "require_no_live_host_dependency"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in [
        "required_card_ids",
        "required_server_tokens",
        "required_frontend_tokens",
        "required_style_tokens",
        "required_runtime_scripts",
        "required_runtime_tokens",
        "required_docs",
    ]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def _token_report(ref: str, tokens: Sequence[str], *, project_root: Path, package_root: Path, owner: str) -> Dict[str, Any]:
    resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
    text = Path(resolved["path"]).read_text(encoding="utf-8", errors="replace") if resolved.get("ok") else ""
    failures: List[str] = []
    if not resolved.get("ok"):
        failures.append(f"{owner}_missing:{ref}")
    for token in tokens:
        if text and token not in text:
            failures.append(f"{owner}_token_missing:{ref}:{token}")
    return {"ref": ref, "ok": not failures, "failures": failures, "resolved": resolved}


def synthetic_runtime_status(*, gateway_active: bool = True, backend_active: bool = True, sockets_present: bool = True) -> Dict[str, Any]:
    return {
        "sockets": {
            "/run/noemaforge/llm/gateway.sock": sockets_present,
            "/run/noemaforge/llm/backends/main.sock": sockets_present and backend_active,
            "/run/brainos/llm/gateway.sock": False,
        },
        "gateway": {"ok": gateway_active, "returncode": 0 if gateway_active else 3, "stdout": "active" if gateway_active else "inactive"},
        "main_backend": {"ok": backend_active, "returncode": 0 if backend_active else 3, "stdout": "active" if backend_active else "inactive"},
        "main_manifest": {"model_id": "main-local-test"},
        "device_policy": {"policy": "auto"},
    }


def validate_runtime_observer_cards_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Path | str | None = None,
) -> Dict[str, Any]:
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    ref_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    doc_report = _resolve_refs(_as_string_list(policy.get("required_docs")), project_root=project, package_root=package, owner="policy.required_docs")
    server_report = _token_report("noemaforge/src/admin_gui_server.py", _as_string_list(policy.get("required_server_tokens")), project_root=project, package_root=package, owner="server")
    frontend_report = _token_report("noemaforge/templates/pipeline-dashboard/app.js", _as_string_list(policy.get("required_frontend_tokens")), project_root=project, package_root=package, owner="frontend")
    index_report = _token_report("noemaforge/templates/pipeline-dashboard/index.html", ["observer-cards.css", "runtime-observer-cards"], project_root=project, package_root=package, owner="index")
    style_report = _token_report("noemaforge/templates/pipeline-dashboard/observer-cards.css", _as_string_list(policy.get("required_style_tokens")), project_root=project, package_root=package, owner="style")
    runtime_reports = [
        _token_report(script, _as_string_list(policy.get("required_runtime_tokens")), project_root=project, package_root=package, owner="runtime")
        for script in _as_string_list(policy.get("required_runtime_scripts"))
    ]
    failures.extend(ref_report["failures"])
    failures.extend(doc_report["failures"])
    failures.extend(server_report["failures"])
    failures.extend(frontend_report["failures"])
    failures.extend(index_report["failures"])
    failures.extend(style_report["failures"])
    for report in runtime_reports:
        failures.extend(report["failures"])

    required_cards = set(_as_string_list(policy.get("required_card_ids")))
    card_ids_in_source = set()
    server_text = Path(server_report["resolved"]["path"]).read_text(encoding="utf-8", errors="replace") if server_report["resolved"].get("ok") else ""
    for card_id in required_cards:
        if card_id in server_text:
            card_ids_in_source.add(card_id)
        else:
            failures.append(f"server_card_id_missing:{card_id}")

    metrics = {
        "refs": len(_as_string_list(payload.get("refs"))),
        "resolved_refs": len(ref_report["resolved_refs"]),
        "required_docs": len(_as_string_list(policy.get("required_docs"))),
        "required_cards": len(required_cards),
        "cards_in_source": len(card_ids_in_source),
        "runtime_reports": len(runtime_reports),
        "valid_runtime_reports": sum(1 for item in runtime_reports if item.get("ok")),
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
        "docs": doc_report,
        "server": server_report,
        "frontend": frontend_report,
        "index": index_report,
        "style": style_report,
        "runtime": runtime_reports,
    }


def build_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": "RuntimeObserverCardsValidationSummary",
        "ok": bool(report.get("ok")),
        "id": report.get("id"),
        "version": report.get("version"),
        "metrics": report.get("metrics", {}),
        "failures": report.get("failures", []),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Runtime observer cards contract.")
    parser.add_argument("--policy", default="noemaforge/configs/runtime-observer-cards-policy.json")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--package-root", default="noemaforge")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    package_root = (project_root / args.package_root).resolve() if not Path(args.package_root).is_absolute() else Path(args.package_root).resolve()
    policy_path = Path(args.policy)
    policy = load_policy(policy_path if policy_path.is_absolute() else project_root / policy_path)
    report = validate_runtime_observer_cards_policy(policy, project_root=project_root, package_root=package_root, policy_path=policy_path)
    print(json.dumps(build_summary(report) if args.summary else report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
