#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/media_wiki_patch_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate media capability deltas and generated artifact manifests in wiki patch bundles.
Inputs: Media wiki patch policy, wiki patch runtime, media catalogs and examples.
Outputs: JSON-compatible MediaWikiPatchValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_media_wiki_patch_runtime.py
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
from typing import Any, Dict, List, Optional, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import unified_registry_runtime as urr


API_VERSION = "noemaforge.media-wiki-patch/v1"
POLICY_KIND = "MediaWikiPatchPolicy"
EXAMPLE_KIND = "MediaWikiPatchExampleSet"
REPORT_KIND = "MediaWikiPatchValidationReport"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
REQUIRED_FLAGS = {"--media-capability-report", "--artifact-manifest"}
REQUIRED_OUTPUTS = {"media_capability_delta.json", "generated_artifacts.json", "functional_delta.md", "wiki_patch_manifest.json"}
REQUIRED_ADAPTERS = {"voice_generation", "music_generation", "photo_generation", "video_generation", "image_analysis", "camera_mask_bridge"}
REQUIRED_ARTIFACT_FIELDS = {"artifact_id", "pipeline_id", "kind", "path", "sha256", "review_status"}
REQUIRED_DOCS = [
    "noemaforge/docs/README.md",
    "noemaforge/docs/TODO.md",
    "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
    "noemaforge/docs/reference/PROJECT_CONTEXT.md",
    "noemaforge/docs/history/CHANGELOG.md",
]


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


def load_json(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_policy(path: Path | str) -> Dict[str, Any]:
    return load_json(path)


def load_example_set(path: Path | str) -> Dict[str, Any]:
    return load_json(path)


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


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
    for key in ["local_first_default", "require_registry_attachment", "require_docs_and_changelog_refs", "require_wiki_patch_runtime_extension"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    flags = set(_as_string_list(policy.get("required_create_flags")))
    failures.extend(f"policy_flag_missing:{item}" for item in sorted(REQUIRED_FLAGS.difference(flags)))
    outputs = set(_as_string_list(policy.get("required_bundle_outputs")))
    failures.extend(f"policy_output_missing:{item}" for item in sorted(REQUIRED_OUTPUTS.difference(outputs)))
    adapters = set(_as_string_list(policy.get("required_media_adapters")))
    failures.extend(f"policy_adapter_missing:{item}" for item in sorted(REQUIRED_ADAPTERS.difference(adapters)))
    fields = set(_as_string_list(policy.get("required_artifact_fields")))
    failures.extend(f"policy_artifact_field_missing:{item}" for item in sorted(REQUIRED_ARTIFACT_FIELDS.difference(fields)))
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
        for ref in ["configs/media-wiki-patch-policy.json", "src/media_wiki_patch_runtime.py", "src/wiki_patch_runtime.py", "prelaunch/governance/media_wiki_patch.example.json"]:
            if ref not in _as_string_list(pipeline.get("refs")):
                failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "entries": entries, "registry_report": report}


def _runtime_extension_failures(*, package_root: Path) -> List[str]:
    failures: List[str] = []
    text = load_text(package_root / "src" / "wiki_patch_runtime.py")
    for token in sorted(REQUIRED_FLAGS | REQUIRED_OUTPUTS):
        if token not in text:
            failures.append(f"wiki_patch_runtime_token_missing:{token}")
    for token in ["copy_optional_json_artifact", "media_capability_delta", "generated_artifacts"]:
        if token not in text:
            failures.append(f"wiki_patch_runtime_token_missing:{token}")
    return failures


def _media_surface_failures(*, package_root: Path) -> List[str]:
    failures: List[str] = []
    media_catalog = load_json(package_root / "configs" / "media-pipeline-catalog.json")
    telemetry_policy = load_json(package_root / "configs" / "media-adapter-telemetry-policy.json")
    catalog_contract = media_catalog.get("adapter_telemetry_contract") if isinstance(media_catalog.get("adapter_telemetry_contract"), dict) else {}
    if catalog_contract.get("id") != "media-adapter-telemetry-core":
        failures.append("media_catalog_telemetry_contract_missing")
    raw_adapters = (_policy_dict(telemetry_policy)).get("required_media_adapters")
    if isinstance(raw_adapters, list):
        seen = {str(item.get("pipeline_id") or "") for item in raw_adapters if isinstance(item, dict)}
        failures.extend(f"telemetry_adapter_missing:{item}" for item in sorted(REQUIRED_ADAPTERS.difference(seen)))
    else:
        failures.append("telemetry_adapters_missing")
    return failures


def _docs_failures(*, project_root: Path) -> Dict[str, Any]:
    failures: List[str] = []
    docs_seen: List[str] = []
    for rel in REQUIRED_DOCS:
        path = project_root / rel
        text = load_text(path) if path.exists() else ""
        if not text:
            failures.append(f"doc_missing:{rel}")
            continue
        docs_seen.append(rel)
        if "media-wiki-patch-core" not in text:
            failures.append(f"doc_token_missing:{rel}:media-wiki-patch-core")
    return {"failures": failures, "docs_seen": docs_seen}


def validate_artifact_manifest(artifacts: Any, policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    policy = _policy_dict(policy_payload)
    required_fields = set(_as_string_list(policy.get("required_artifact_fields"))) or REQUIRED_ARTIFACT_FIELDS
    failures: List[str] = []
    if not isinstance(artifacts, list) or not artifacts:
        return {"ok": False, "failures": ["artifact_manifest_empty"], "artifact_count": 0}
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            failures.append(f"artifact_not_object:{index}")
            continue
        for field in sorted(required_fields):
            if field not in item or str(item.get(field) or "") == "":
                failures.append(f"artifact_field_missing:{index}:{field}")
        pipeline_id = str(item.get("pipeline_id") or "")
        if pipeline_id not in REQUIRED_ADAPTERS:
            failures.append(f"artifact_pipeline_unknown:{index}:{pipeline_id}")
        sha = str(item.get("sha256") or "")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", sha):
            failures.append(f"artifact_sha256_invalid:{index}")
    return {"ok": not failures, "failures": sorted(failures), "artifact_count": len(artifacts)}


def validate_media_capability_delta(delta: Any) -> Dict[str, Any]:
    failures: List[str] = []
    if not isinstance(delta, dict):
        return {"ok": False, "failures": ["media_capability_delta_not_object"], "adapter_count": 0}
    adapters = delta.get("adapters") if isinstance(delta.get("adapters"), dict) else {}
    failures.extend(f"media_capability_adapter_missing:{item}" for item in sorted(REQUIRED_ADAPTERS.difference(adapters)))
    return {"ok": not failures, "failures": sorted(failures), "adapter_count": len(adapters)}


def validate_media_patch_manifest(manifest: Dict[str, Any], policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    media = manifest.get("media_capability_delta") if isinstance(manifest.get("media_capability_delta"), dict) else {}
    artifacts = manifest.get("generated_artifacts") if isinstance(manifest.get("generated_artifacts"), dict) else {}
    if media.get("present") is not True:
        failures.append("manifest_media_capability_delta_missing")
    if artifacts.get("present") is not True:
        failures.append("manifest_generated_artifacts_missing")
    for owner, item in [("media", media), ("artifacts", artifacts)]:
        path = str(item.get("path") or "")
        if item.get("present") is True and not path:
            failures.append(f"manifest_{owner}_path_missing")
    return {"ok": not failures, "failures": sorted(failures)}


def _example_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    policy = _policy_dict(payload)
    failures: List[str] = []
    scenario_results: List[Dict[str, Any]] = []
    refs_result = _resolve_refs(_as_string_list(policy.get("required_example_sets")), project_root=project_root, package_root=package_root, owner=str(payload.get("id") or "policy"))
    failures.extend(refs_result["failures"])
    for item in refs_result["resolved_refs"]:
        example_set = load_example_set(Path(item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{item['ref']}")
        if example_set.get("kind") != EXAMPLE_KIND:
            failures.append(f"example_set_kind_invalid:{item['ref']}")
        scenarios = example_set.get("scenarios") if isinstance(example_set.get("scenarios"), list) else []
        if not scenarios:
            failures.append(f"example_set_empty:{item['ref']}")
        for scenario in scenarios:
            scenario_id = str(scenario.get("id") or "<missing>") if isinstance(scenario, dict) else "<invalid>"
            media_result = validate_media_capability_delta((scenario or {}).get("media_capability_delta"))
            artifact_result = validate_artifact_manifest((scenario or {}).get("generated_artifacts"), payload)
            expected = set(_as_string_list((scenario or {}).get("expected_outputs")))
            failures.extend(f"example_expected_output_missing:{scenario_id}:{name}" for name in sorted(REQUIRED_OUTPUTS.difference(expected)))
            scenario_ref_result = _resolve_refs(_as_string_list((scenario or {}).get("refs")), project_root=project_root, package_root=package_root, owner=scenario_id)
            failures.extend(scenario_ref_result["failures"])
            failures.extend(f"example_media:{scenario_id}:{item}" for item in media_result["failures"])
            failures.extend(f"example_artifact:{scenario_id}:{item}" for item in artifact_result["failures"])
            scenario_results.append({"id": scenario_id, "ok": media_result["ok"] and artifact_result["ok"] and REQUIRED_OUTPUTS.issubset(expected), "artifact_count": artifact_result["artifact_count"], "adapter_count": media_result["adapter_count"]})
    return {
        "failures": failures,
        "scenario_results": scenario_results,
        "resolved_refs": refs_result["resolved_refs"],
        "missing_refs": refs_result["missing_refs"],
        "unsafe_refs": refs_result["unsafe_refs"],
    }


def synthetic_media_capability_delta() -> Dict[str, Any]:
    return {
        "adapters": {
            adapter: {"status": "plan_only" if adapter != "image_analysis" else "metadata_ready", "capability": adapter.replace("_generation", "").replace("_", "-")}
            for adapter in sorted(REQUIRED_ADAPTERS)
        }
    }


def synthetic_artifact_manifest(count: int = 6) -> List[Dict[str, Any]]:
    adapters = sorted(REQUIRED_ADAPTERS)
    rows: List[Dict[str, Any]] = []
    for index in range(count):
        adapter = adapters[index % len(adapters)]
        rows.append({
            "artifact_id": f"artifact:media:{adapter}:{index}",
            "pipeline_id": adapter,
            "kind": "plan",
            "path": f"state/media/{adapter}-{index}.json",
            "sha256": f"{index % 16:x}" * 64,
            "review_status": "planned_only",
        })
    return rows


def validate_media_wiki_patch_policy(
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
    failures: List[str] = []
    failures.extend(_policy_failures(payload))
    registry_result = _registry_failures(payload, project_root=project, package_root=package, registry_path=registry)
    failures.extend(registry_result["failures"])
    failures.extend(_runtime_extension_failures(package_root=package))
    failures.extend(_media_surface_failures(package_root=package))
    example_result = _example_failures(payload, project_root=project, package_root=package)
    failures.extend(example_result["failures"])
    docs_result = _docs_failures(project_root=project)
    failures.extend(docs_result["failures"])
    refs = sorted(set(_as_string_list(payload.get("refs"))))
    refs_result = _resolve_refs(refs, project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(refs_result["failures"])
    metrics = {
        "required_flags": len(REQUIRED_FLAGS),
        "required_outputs": len(REQUIRED_OUTPUTS),
        "required_media_adapters": len(REQUIRED_ADAPTERS),
        "required_artifact_fields": len(REQUIRED_ARTIFACT_FIELDS),
        "scenarios": len(example_result["scenario_results"]),
        "passing_scenarios": sum(1 for item in example_result["scenario_results"] if item["ok"]),
        "registry_entries": len(registry_result["entries"]),
        "docs_seen": len(docs_result["docs_seen"]),
    }
    checks = [
        {"id": "policy_shape", "status": "passed" if not any(item.startswith("policy_") for item in failures) else "failed"},
        {"id": "wiki_patch_runtime_extension", "status": "passed" if not any(item.startswith("wiki_patch_runtime_") for item in failures) else "failed"},
        {"id": "media_surface", "status": "passed" if not any(item.startswith("media_") or item.startswith("telemetry_") for item in failures) else "failed"},
        {"id": "examples", "status": "passed" if not any(item.startswith("example_") for item in failures) else "failed"},
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
        "scenario_results": example_result["scenario_results"],
        "resolved_refs": sorted(refs_result["resolved_refs"] + example_result["resolved_refs"], key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(refs_result["missing_refs"] + example_result["missing_refs"], key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(refs_result["unsafe_refs"] + example_result["unsafe_refs"], key=lambda item: (item["owner"], item["ref"])),
    }


def benchmark_media_wiki_patch(policy_payload: Dict[str, Any], *, iterations: int = 1000) -> Dict[str, Any]:
    media = synthetic_media_capability_delta()
    artifacts = synthetic_artifact_manifest()
    manifest = {
        "media_capability_delta": {"present": True, "path": "media_capability_delta.json"},
        "generated_artifacts": {"present": True, "path": "generated_artifacts.json"},
    }
    started = time.perf_counter()
    passed = 0
    for _ in range(iterations):
        media_ok = validate_media_capability_delta(media)["ok"]
        artifact_ok = validate_artifact_manifest(artifacts, policy_payload)["ok"]
        manifest_ok = validate_media_patch_manifest(manifest, policy_payload)["ok"]
        if media_ok and artifact_ok and manifest_ok:
            passed += 1
    elapsed = time.perf_counter() - started
    return {"iterations": iterations, "passed": passed, "failed": iterations - passed, "elapsed_sec": elapsed, "ok": passed == iterations}


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge media wiki patch contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()))
    parser.add_argument("--package-root", default="")
    parser.add_argument("--policy", default="noemaforge/configs/media-wiki-patch-policy.json")
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
    report = validate_media_wiki_patch_policy(
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
            "kind": "MediaWikiPatchValidationSummary",
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
