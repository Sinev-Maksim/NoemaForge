#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/artifact_card_affordance_runtime.py
Zone: gui/control-plane
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate guarded open/download affordances for installed Admin GUI artifact cards.
Inputs: Artifact card affordance policy, Admin GUI server source and dashboard UI files.
Outputs: JSON-compatible ArtifactCardAffordanceValidationReport artifacts.
Side effects: None unless tests create temporary fixture files.
Tests: noemaforge/tests/test_artifact_card_affordance_runtime.py
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
from typing import Any, Dict, List, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.artifact-card-affordance/v1"
POLICY_KIND = "ArtifactCardAffordancePolicy"
EXAMPLE_KIND = "ArtifactCardAffordanceExampleSet"
REPORT_KIND = "ArtifactCardAffordanceValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_DOCS = [
    "noemaforge/docs/README.md",
    "noemaforge/docs/TODO.md",
    "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
    "noemaforge/docs/reference/PROJECT_CONTEXT.md",
    "noemaforge/docs/history/CHANGELOG.md",
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


def load_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_policy(path: Path | str) -> Dict[str, Any]:
    return load_json(path)


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
    for key in ["local_first_default", "require_registry_attachment", "require_docs_and_changelog_refs", "require_guarded_path_resolution"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for key in ["required_api_paths", "required_runtime_tokens", "required_frontend_tokens", "allowed_root_tokens", "required_docs"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
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
        for ref in ["configs/artifact-card-affordance-policy.json", "src/artifact_card_affordance_runtime.py", "src/admin_gui_server.py"]:
            if ref not in _as_string_list(pipeline.get("refs")):
                failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "entries": entries, "registry_report": report}


def _source_failures(policy: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    server_text = load_text(package_root / "src" / "admin_gui_server.py")
    app_text = load_text(package_root / "templates" / "pipeline-dashboard" / "app.js")
    index_text = load_text(package_root / "templates" / "pipeline-dashboard" / "index.html")
    css_text = load_text(package_root / "templates" / "pipeline-dashboard" / "artifact-affordances.css")
    for token in _as_string_list(policy.get("required_api_paths")) + _as_string_list(policy.get("required_runtime_tokens")) + _as_string_list(policy.get("allowed_root_tokens")):
        if token not in server_text:
            failures.append(f"server_token_missing:{token}")
    combined_ui = "\n".join([app_text, index_text, css_text])
    for token in _as_string_list(policy.get("required_frontend_tokens")):
        if token not in combined_ui:
            failures.append(f"frontend_token_missing:{token}")
    return {"failures": failures, "source_lengths": {"admin_gui_server": len(server_text), "app_js": len(app_text), "index_html": len(index_text), "artifact_css": len(css_text)}}


def _docs_failures(*, project_root: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    docs_seen: List[str] = []
    required = _as_string_list(policy.get("required_docs")) or REQUIRED_DOCS
    for rel in required:
        path = project_root / rel
        text = load_text(path) if path.exists() else ""
        if not text:
            failures.append(f"doc_missing:{rel}")
            continue
        docs_seen.append(rel)
        if "artifact-card-affordance-core" not in text:
            failures.append(f"doc_token_missing:{rel}:artifact-card-affordance-core")
    return {"failures": failures, "docs_seen": docs_seen}


def build_offline_artifact_server(*, package_root: Path | str, scratch_root: Path | str) -> Any:
    import admin_gui_server  # type: ignore

    root = Path(package_root).resolve()
    scratch = Path(scratch_root).resolve()
    server = object.__new__(admin_gui_server.AdminGuiServer)
    server.root = root
    server.state = scratch / "pipelines"
    server.persona_state = scratch / "personas"
    server.evolution_state = scratch / "model-evolution"
    server.model_selection_state = scratch / "model-selection"
    server.dev_team_state = scratch / "dev-team"
    server.data_root = scratch / "data"
    server.gui_state_dir = server.data_root / "gui"
    server.jobs_dir = server.data_root / "jobs"
    server.tasks_dir = server.data_root / "tasks"
    server.review_dir = server.data_root / "review"
    server.runtime_dir = server.data_root / "runtime"
    server.ui_dir = root / "templates" / "pipeline-dashboard"
    for path in [server.state, server.evolution_state, server.model_selection_state, server.dev_team_state, server.data_root]:
        path.mkdir(parents=True, exist_ok=True)
    return server


def validate_artifact_card_affordance_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Path | str | None = None,
    registry_path: Path | str | None = None,
) -> Dict[str, Any]:
    started = time.perf_counter()
    project = Path(project_root).resolve()
    package = Path(package_root).resolve()
    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    refs_report = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "artifact-card-affordance"))
    failures.extend(refs_report["failures"])
    source = _source_failures(policy, package_root=package)
    failures.extend(source["failures"])
    docs = _docs_failures(project_root=project, policy=policy)
    failures.extend(docs["failures"])
    registry = _registry_failures(
        payload,
        project_root=project,
        package_root=package,
        registry_path=Path(registry_path) if registry_path else package / "configs" / "unified-registry.json",
    )
    failures.extend(registry["failures"])
    metrics = {
        "api_paths": len(_as_string_list(policy.get("required_api_paths"))),
        "runtime_tokens": len(_as_string_list(policy.get("required_runtime_tokens"))),
        "frontend_tokens": len(_as_string_list(policy.get("required_frontend_tokens"))),
        "allowed_roots": len(_as_string_list(policy.get("allowed_root_tokens"))),
        "docs_seen": len(docs["docs_seen"]),
        "registry_entries": len(registry["entries"]),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "id": payload.get("id"),
        "version": payload.get("version"),
        "ok": not failures,
        "created_at": _nowz(),
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "failures": sorted(set(failures)),
        "metrics": metrics,
        "refs": refs_report,
        "source": source,
        "docs": docs,
    }


def validate_summary(*, project_root: Path, package_root: Path, policy_path: Path) -> Dict[str, Any]:
    report = validate_artifact_card_affordance_policy(load_policy(policy_path), project_root=project_root, package_root=package_root, policy_path=policy_path)
    return {
        "apiVersion": API_VERSION,
        "kind": "ArtifactCardAffordanceValidationSummary",
        "ok": report["ok"],
        "created_at": report["created_at"],
        "failures": report["failures"],
        "metrics": report["metrics"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge artifact card affordance contracts.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--package-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--policy", default="noemaforge/configs/artifact-card-affordance-policy.json")
    parser.add_argument("--summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = Path(args.project_root).resolve()
    package = Path(args.package_root).resolve()
    policy_path = (project / args.policy).resolve() if not Path(args.policy).is_absolute() else Path(args.policy).resolve()
    doc = validate_summary(project_root=project, package_root=package, policy_path=policy_path) if args.summary else validate_artifact_card_affordance_policy(load_policy(policy_path), project_root=project, package_root=package, policy_path=policy_path)
    print(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if doc.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
