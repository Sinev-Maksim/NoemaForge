#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/unified_registry_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Unified Registry refs, eval-pack links and required-kind coverage.
Inputs: noemaforge/configs/unified-registry.json plus local project/package roots.
Outputs: JSON-compatible UnifiedRegistryValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_unified_registry_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import production_ai_contracts as pac


VALIDATION_KIND = "UnifiedRegistryValidationReport"


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_path(value: Path | str) -> Path:
    return Path(value).resolve()


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text:
        return False
    if text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


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


def load_registry(registry_path: Path | str) -> Dict[str, Any]:
    path = Path(registry_path)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_unified_registry(
    registry: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Optional[Path | str] = None,
    registry_path: Path | str = "",
    required_kinds: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root or (project / "noemaforge"))
    required = set(required_kinds or pac.REGISTRY_KINDS)

    failures: List[str] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_eval_pack_refs: List[Dict[str, Any]] = []

    try:
        normalized = pac.normalize_registry(registry)
    except Exception as exc:
        return {
            "apiVersion": pac.API_VERSION,
            "kind": VALIDATION_KIND,
            "ok": False,
            "created_at": _nowz(),
            "registry_path": str(registry_path or ""),
            "project_root": _display_path(project),
            "package_root": _display_path(package),
            "failures": [f"normalize_failed:{exc}"],
            "metrics": {
                "entries": 0,
                "refs": 0,
                "resolved_refs": 0,
                "missing_refs": 0,
                "missing_eval_pack_refs": 0,
            },
            "normalized_registry": {},
        }

    status = pac.summarize_contract_status(normalized, required_kinds=required)
    missing_required_kinds = list(status.get("missing_kinds") or [])
    if missing_required_kinds:
        failures.extend(f"missing_kind:{kind}" for kind in missing_required_kinds)

    index = pac.registry_index(normalized)
    eval_pack_keys = {key for key, entry in index.items() if entry.get("kind") == "eval-pack"}

    for entry in normalized["entries"]:
        owner = pac.registry_key(entry)
        for ref in entry.get("refs") or []:
            ref_text = str(ref)
            if not _is_safe_relative_ref(ref_text):
                unsafe_refs.append({"registry_ref": owner, "ref": ref_text})
                failures.append(f"unsafe_ref:{owner}:{ref_text}")
                continue
            resolved = _resolve_ref(ref_text, project_root=project, package_root=package)
            resolved["registry_ref"] = owner
            if resolved["ok"]:
                resolved_refs.append(resolved)
            else:
                missing_refs.append(resolved)
                failures.append(f"missing_ref:{owner}:{ref_text}")

        for eval_ref in entry.get("eval_pack_refs") or []:
            ref_text = str(eval_ref)
            if ref_text not in eval_pack_keys:
                missing_eval_pack_refs.append({"registry_ref": owner, "eval_pack_ref": ref_text})
                failures.append(f"missing_eval_pack_ref:{owner}:{ref_text}")

    total_refs = sum(len(entry.get("refs") or []) for entry in normalized["entries"])
    return {
        "apiVersion": pac.API_VERSION,
        "kind": VALIDATION_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "registry_path": str(registry_path or ""),
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(failures),
        "missing_required_kinds": sorted(missing_required_kinds),
        "active_registry_refs": pac.active_registry_refs(normalized),
        "metrics": {
            "entries": len(normalized["entries"]),
            "refs": total_refs,
            "resolved_refs": len(resolved_refs),
            "missing_refs": len(missing_refs),
            "unsafe_refs": len(unsafe_refs),
            "missing_eval_pack_refs": len(missing_eval_pack_refs),
            "eval_pack_refs": sum(len(entry.get("eval_pack_refs") or []) for entry in normalized["entries"]),
        },
        "resolved_refs": sorted(resolved_refs, key=lambda item: (item["registry_ref"], item["ref"])),
        "missing_refs": sorted(missing_refs, key=lambda item: (item["registry_ref"], item["ref"])),
        "unsafe_refs": sorted(unsafe_refs, key=lambda item: (item["registry_ref"], item["ref"])),
        "missing_eval_pack_refs": sorted(
            missing_eval_pack_refs,
            key=lambda item: (item["registry_ref"], item["eval_pack_ref"]),
        ),
        "normalized_registry": normalized,
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Unified Registry refs and eval-pack links.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--registry",
        default="noemaforge/configs/unified-registry.json",
        help="Registry path, absolute or relative to project root.",
    )
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    registry_path = Path(args.registry)
    if not registry_path.is_absolute():
        registry_path = project_root / registry_path

    report = validate_unified_registry(
        load_registry(registry_path),
        project_root=project_root,
        package_root=package_root,
        registry_path=registry_path,
    )
    payload: Dict[str, Any]
    if args.summary:
        payload = {
            "apiVersion": report["apiVersion"],
            "kind": "UnifiedRegistryValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "registry_path": report["registry_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
            "active_registry_refs": report["active_registry_refs"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
