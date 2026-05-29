#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/locale_main_chat_surface_runtime.py
Zone: gui/i18n
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate /api/locales messages and localized Admin GUI main chat labels.
Inputs: Locale main chat policy, locale JSON files, Admin GUI server source and dashboard UI files.
Outputs: JSON-compatible LocaleMainChatSurfaceValidationReport artifacts.
Side effects: None; tests use in-memory fixtures only.
Tests: noemaforge/tests/test_locale_main_chat_surface_runtime.py
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

import unified_registry_runtime as urr


API_VERSION = "noemaforge.locale-main-chat-surface/v1"
POLICY_KIND = "LocaleMainChatSurfacePolicy"
REPORT_KIND = "LocaleMainChatSurfaceValidationReport"
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


def load_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


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
    for key in ["local_first_default", "require_registry_attachment", "require_docs_and_changelog_refs"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if policy.get("api_path") != "/api/locales":
        failures.append("policy_api_path_invalid")
    for key in ["required_locales", "required_message_keys", "required_frontend_tokens", "required_main_chat_ids", "ru_disallowed_fragments", "required_docs"]:
        if not _as_string_list(policy.get(key)):
            failures.append(f"policy_{key}_empty")
    return failures


def build_offline_locale_server(*, package_root: Path | str) -> Any:
    import admin_gui_server  # type: ignore

    root = Path(package_root).resolve()
    server = object.__new__(admin_gui_server.AdminGuiServer)
    server.root = root
    server._read_json = lambda path, default: load_json(path) if Path(path).exists() else default
    return server


def _locale_report(policy: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    payload = build_offline_locale_server(package_root=package_root).locales()
    locales = payload.get("locales") if isinstance(payload.get("locales"), list) else []
    messages = payload.get("messages") if isinstance(payload.get("messages"), dict) else {}
    for locale in _as_string_list(policy.get("required_locales")):
        if locale not in locales:
            failures.append(f"locale_missing:{locale}")
        msg = messages.get(locale) if isinstance(messages.get(locale), dict) else {}
        for key in _as_string_list(policy.get("required_message_keys")):
            if not str(msg.get(key) or "").strip():
                failures.append(f"message_key_missing:{locale}:{key}")
    ru = messages.get("ru") if isinstance(messages.get("ru"), dict) else {}
    ru_surface = "\n".join(str(ru.get(key) or "") for key in _as_string_list(policy.get("required_message_keys")))
    for fragment in _as_string_list(policy.get("ru_disallowed_fragments")):
        if fragment and fragment in ru_surface:
            failures.append(f"ru_mixed_fragment:{fragment}")
    return {"failures": failures, "payload": payload, "locales": locales, "message_locale_count": len(messages)}


def _source_report(policy: Dict[str, Any], *, package_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    server_text = load_text(package_root / "src" / "admin_gui_server.py")
    app_text = load_text(package_root / "templates" / "pipeline-dashboard" / "app.js")
    index_text = load_text(package_root / "templates" / "pipeline-dashboard" / "index.html")
    for token in ["/api/locales", "def locales", "\"messages\": messages"]:
        if token not in server_text:
            failures.append(f"server_token_missing:{token}")
    for token in _as_string_list(policy.get("required_frontend_tokens")):
        if token not in app_text:
            failures.append(f"frontend_token_missing:{token}")
    for token in _as_string_list(policy.get("required_main_chat_ids")):
        if token not in index_text and token not in app_text:
            failures.append(f"main_chat_id_missing:{token}")
    main_chat = ""
    if '<section class="chat' in index_text:
        main_chat = index_text.split('<section class="chat', 1)[1].split("</section>", 1)[0]
    for fragment in ["Steps", "Minutes", "until stop", "Stop loop", "Pipeline Dock", "Search pipeline", "+ New pipeline"]:
        if fragment in main_chat:
            failures.append(f"initial_main_chat_mixed_fragment:{fragment}")
    return {"failures": failures, "source_lengths": {"admin_gui_server": len(server_text), "app_js": len(app_text), "index_html": len(index_text)}}


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _registry_report(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {_registry_ref(entry): entry for entry in report.get("normalized_registry", {}).get("entries", []) if isinstance(entry, dict)}
    raw_entries = {_registry_ref(entry): entry for entry in registry.get("entries", []) if isinstance(entry, dict)}
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    if eval_ref not in entries:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    pipeline_ref = "pipeline:firstboot-model-selection:0.32.2"
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
    else:
        if eval_ref not in _as_string_list(pipeline.get("eval_pack_refs")):
            failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
        for ref in ["configs/locale-main-chat-surface-policy.json", "src/locale_main_chat_surface_runtime.py", "templates/pipeline-dashboard/app.js"]:
            if ref not in _as_string_list(pipeline.get("refs")):
                failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "entries": entries, "registry_report": report}


def _docs_report(*, project_root: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    docs_seen: List[str] = []
    for rel in _as_string_list(policy.get("required_docs")):
        path = project_root / rel
        text = load_text(path) if path.exists() else ""
        if not text:
            failures.append(f"doc_missing:{rel}")
            continue
        docs_seen.append(rel)
        if "locale-main-chat-surface-core" not in text:
            failures.append(f"doc_token_missing:{rel}:locale-main-chat-surface-core")
    return {"failures": failures, "docs_seen": docs_seen}


def validate_locale_main_chat_surface_policy(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    started = time.perf_counter()
    policy = _policy_dict(payload)
    failures: List[str] = []
    refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project_root, package_root=package_root, owner=str(payload.get("id") or "locale-main-chat-surface-core"))
    locale = _locale_report(policy, package_root=package_root)
    source = _source_report(policy, package_root=package_root)
    registry = _registry_report(payload, project_root=project_root, package_root=package_root, registry_path=registry_path)
    docs = _docs_report(project_root=project_root, policy=policy)
    for part in [_policy_failures(payload), refs["failures"], locale["failures"], source["failures"], registry["failures"], docs["failures"]]:
        failures.extend(part)
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "created_at": _nowz(),
        "ok": not failures,
        "failures": failures,
        "metrics": {
            "locales": len(locale["locales"]),
            "message_locale_count": locale["message_locale_count"],
            "required_keys": len(_as_string_list(policy.get("required_message_keys"))),
            "main_chat_ids": len(_as_string_list(policy.get("required_main_chat_ids"))),
            "docs_seen": len(docs["docs_seen"]),
            "registry_entries": len(registry["entries"]),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        },
        "refs": refs,
        "locale": locale,
        "source": source,
        "registry": registry,
        "docs": docs,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate localized main chat surface contract.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--package-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--policy", default="configs/locale-main-chat-surface-policy.json")
    parser.add_argument("--registry", default="configs/unified-registry.json")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()
    package_root = Path(args.package_root).resolve()
    report = validate_locale_main_chat_surface_policy(
        load_json(package_root / args.policy),
        project_root=project_root,
        package_root=package_root,
        registry_path=package_root / args.registry,
    )
    if args.summary:
        keep = {k: report[k] for k in ["apiVersion", "kind", "created_at", "ok", "failures", "metrics"]}
        print(json.dumps(keep, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
