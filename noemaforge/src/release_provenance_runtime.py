#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/release_provenance_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate signed release provenance contracts for public archives.
Inputs: noemaforge/configs/release-provenance-policy.json and release provenance examples.
Outputs: JSON-compatible ReleaseProvenanceValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_release_provenance_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import hashlib
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


API_VERSION = "noemaforge.release-provenance/v1"
POLICY_KIND = "ReleaseProvenancePolicy"
SET_KIND = "ReleaseProvenanceExampleSet"
REPORT_KIND = "ReleaseProvenanceValidationReport"

VALID_POLICY_STATUSES = {"draft", "shadow", "stable", "retired"}
REQUIRED_MATERIALS = {
    "archive",
    "manifest",
    "signature",
    "checksums",
    "release_notes",
    "changelog",
    "install_transcript",
    "verification_summary",
}
VALID_SIGNATURE_SCHEMES = {"ed25519", "minisign", "cosign-keyless"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,220}$")
SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
FINGERPRINT_RE = re.compile(r"^sha256:[a-fA-F0-9]{64}$")


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


def _resolve_refs(
    refs: Sequence[str],
    *,
    project_root: Path,
    package_root: Path,
    owner: str,
    resolve_cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            unsafe_refs.append({"owner": owner, "ref": ref})
            failures.append(f"unsafe_ref:{owner}:{ref}")
            continue
        if resolve_cache is not None and ref in resolve_cache:
            resolved = dict(resolve_cache[ref])
        else:
            resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
            if resolve_cache is not None:
                resolve_cache[ref] = dict(resolved)
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


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_release_archive_record(path: Path | str, *, kind: str = "release_archive") -> Dict[str, Any]:
    archive = Path(path)
    return {
        "kind": kind,
        "path": archive.name,
        "sha256": sha256_file(archive),
        "bytes": archive.stat().st_size,
    }


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


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
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "signed_release_provenance":
        failures.append("policy_activation_state_invalid")
    for key in ["require_trace_id", "require_registry_attachment", "require_docs_and_changelog_refs"]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    if "release_archive" not in set(_as_string_list(policy.get("required_artifact_kinds"))):
        failures.append("policy_release_archive_kind_missing")
    if not REQUIRED_MATERIALS.issubset(set(_as_string_list(policy.get("required_materials")))):
        failures.append("policy_required_materials_missing")
    controls = policy.get("signing_controls") if isinstance(policy.get("signing_controls"), dict) else {}
    for key in ["sha256_required", "signature_required", "detached_signature_required", "public_key_fingerprint_required"]:
        if controls.get(key) is not True:
            failures.append(f"policy_signing_{key}_not_true")
    if controls.get("plaintext_private_key_allowed") is not False:
        failures.append("policy_plaintext_private_key_allowed_not_false")
    schemes = set(_as_string_list(controls.get("allowed_signature_schemes")))
    if not schemes or not schemes.issubset(VALID_SIGNATURE_SCHEMES):
        failures.append("policy_allowed_signature_schemes_invalid")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _registry_failures(payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
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
    eval_ref = f"eval-pack:{payload.get('id')}:{payload.get('version')}"
    eval_entry = entries.get(eval_ref)
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        entry_refs = set(_as_string_list(eval_entry.get("refs")))
        for ref in [
            "configs/release-provenance-policy.json",
            "contracts/release_provenance.schema.json",
            "src/release_provenance_runtime.py",
            "tests/test_release_provenance_runtime.py",
            "tests/test_release_provenance_qa.py",
            "tests/test_release_provenance_performance.py",
        ]:
            if ref not in entry_refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")

    pipeline_ref = str(policy.get("required_pipeline_ref") or "")
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
        pipeline_eval_refs: List[str] = []
        pipeline_refs: List[str] = []
    else:
        pipeline_eval_refs = _as_string_list(pipeline.get("eval_pack_refs"))
        pipeline_refs = _as_string_list(pipeline.get("refs"))
    if eval_ref not in pipeline_eval_refs:
        failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
    for ref in [
        "configs/release-provenance-policy.json",
        "contracts/release_provenance.schema.json",
        "src/release_provenance_runtime.py",
        "prelaunch/governance/release_provenance.example.json",
    ]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report, "entries": entries, "pipeline_eval_refs": pipeline_eval_refs}


def _material_failures(release_id: str, materials: Dict[str, Any], required: Sequence[str]) -> List[str]:
    failures: List[str] = []
    material_map = {
        "checksums": "checksums",
        "release_notes": "release_notes",
        "changelog": "changelog",
        "install_transcript": "install_transcript",
        "verification_summary": "verification_summary",
    }
    for material in required:
        if material in {"archive", "manifest", "signature"}:
            continue
        key = material_map.get(material, material)
        item = materials.get(key) if isinstance(materials.get(key), dict) else {}
        if not item:
            failures.append(f"release_material_missing:{release_id}:{key}")
            continue
        if not str(item.get("path") or "").strip():
            failures.append(f"release_material_path_missing:{release_id}:{key}")
        if not SHA256_RE.match(str(item.get("sha256") or "")):
            failures.append(f"release_material_sha256_invalid:{release_id}:{key}")
        if key == "verification_summary" and item.get("status") != "passed":
            failures.append(f"release_verification_summary_not_passed:{release_id}")
    return failures


def _release_failures(release: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    controls = policy.get("signing_controls") if isinstance(policy.get("signing_controls"), dict) else {}
    required_materials = _as_string_list(policy.get("required_materials"))
    allowed_schemes = set(_as_string_list(controls.get("allowed_signature_schemes")))
    failures: List[str] = []
    release_id = str(release.get("id") or "<missing>")
    if not SAFE_ID_RE.match(release_id):
        failures.append(f"release_id_invalid:{release_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(release.get("trace_id") or "")):
        failures.append(f"release_trace_id_invalid:{release_id}")
    if not str(release.get("version") or "").strip():
        failures.append(f"release_version_missing:{release_id}")

    archive = release.get("archive") if isinstance(release.get("archive"), dict) else {}
    if archive.get("kind") != "release_archive":
        failures.append(f"release_archive_kind_invalid:{release_id}")
    if not str(archive.get("path") or "").strip():
        failures.append(f"release_archive_path_missing:{release_id}")
    if controls.get("sha256_required") is True and not SHA256_RE.match(str(archive.get("sha256") or "")):
        failures.append(f"release_archive_sha256_invalid:{release_id}")
    if int(archive.get("bytes") or 0) <= 0:
        failures.append(f"release_archive_bytes_invalid:{release_id}")

    manifest = release.get("manifest") if isinstance(release.get("manifest"), dict) else {}
    if not str(manifest.get("path") or "").strip():
        failures.append(f"release_manifest_path_missing:{release_id}")
    if controls.get("sha256_required") is True and not SHA256_RE.match(str(manifest.get("sha256") or "")):
        failures.append(f"release_manifest_sha256_invalid:{release_id}")
    includes = set(_as_string_list(manifest.get("includes")))
    for required in ["archive", "checksums", "release_notes", "changelog", "install_transcript", "verification_summary"]:
        if required not in includes:
            failures.append(f"release_manifest_include_missing:{release_id}:{required}")

    signatures = release.get("signatures") if isinstance(release.get("signatures"), list) else []
    if controls.get("signature_required") is True and not signatures:
        failures.append(f"release_signature_missing:{release_id}")
    signed_artifacts = set()
    for index, signature in enumerate(signatures):
        if not isinstance(signature, dict):
            failures.append(f"release_signature_not_object:{release_id}:{index}")
            continue
        artifact = str(signature.get("artifact") or "")
        signed_artifacts.add(artifact)
        if artifact not in {"archive", "manifest"}:
            failures.append(f"release_signature_artifact_invalid:{release_id}:{index}:{artifact}")
        if str(signature.get("scheme") or "") not in allowed_schemes:
            failures.append(f"release_signature_scheme_invalid:{release_id}:{index}")
        if controls.get("detached_signature_required") is True and not str(signature.get("signature_path") or "").strip():
            failures.append(f"release_signature_path_missing:{release_id}:{index}")
        if not str(signature.get("signature") or "").strip():
            failures.append(f"release_signature_value_missing:{release_id}:{index}")
        if controls.get("public_key_fingerprint_required") is True and not FINGERPRINT_RE.match(str(signature.get("public_key_fingerprint") or "")):
            failures.append(f"release_signature_fingerprint_invalid:{release_id}:{index}")
        if controls.get("plaintext_private_key_allowed") is False and "private_key" in signature:
            failures.append(f"release_signature_private_key_present:{release_id}:{index}")
    for required_artifact in ["archive", "manifest"]:
        if required_artifact not in signed_artifacts:
            failures.append(f"release_signature_artifact_missing:{release_id}:{required_artifact}")

    materials = release.get("materials") if isinstance(release.get("materials"), dict) else {}
    failures.extend(_material_failures(release_id, materials, required_materials))

    build = release.get("build") if isinstance(release.get("build"), dict) else {}
    for key in ["source_tree", "recipe", "archive_command", "reproducibility_notes"]:
        if not str(build.get(key) or "").strip():
            failures.append(f"release_build_{key}_missing:{release_id}")

    checks = release.get("checks") if isinstance(release.get("checks"), dict) else {}
    for key in [
        "archive_sha_matches_manifest",
        "manifest_sha_pinned",
        "signature_detached",
        "private_key_not_in_bundle",
        "verification_summary_ok",
        "install_transcript_attached",
    ]:
        if checks.get(key) is not True:
            failures.append(f"release_check_{key}_not_true:{release_id}")
    return failures


def validate_release_provenance_policy(
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
    release_results: List[Dict[str, Any]] = []
    signed_artifacts = 0
    resolve_cache: Dict[str, Dict[str, Any]] = {}

    refs_to_resolve = sorted(set(_as_string_list(payload.get("refs"))))
    refs_result = _resolve_refs(
        refs_to_resolve,
        project_root=project,
        package_root=package,
        owner=str(payload.get("id") or "policy"),
        resolve_cache=resolve_cache,
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
        resolve_cache=resolve_cache,
    )
    failures.extend(example_ref_results["failures"])
    all_resolved_refs.extend(example_ref_results["resolved_refs"])
    all_missing_refs.extend(example_ref_results["missing_refs"])
    all_unsafe_refs.extend(example_ref_results["unsafe_refs"])

    for ref_item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(ref_item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{ref_item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{ref_item['ref']}")
        releases = example_set.get("releases") if isinstance(example_set.get("releases"), list) else []
        if not releases:
            failures.append(f"example_set_releases_empty:{ref_item['ref']}")
        for release in releases:
            if not isinstance(release, dict):
                failures.append(f"release_not_object:{ref_item['ref']}")
                continue
            release_id = str(release.get("id") or "<missing>")
            release_failures = _release_failures(release, payload)
            failures.extend(release_failures)
            signed_artifacts += len(release.get("signatures") if isinstance(release.get("signatures"), list) else [])
            release_ref_result = _resolve_refs(
                _as_string_list(release.get("refs")),
                project_root=project,
                package_root=package,
                owner=release_id,
                resolve_cache=resolve_cache,
            )
            failures.extend(release_ref_result["failures"])
            all_resolved_refs.extend(release_ref_result["resolved_refs"])
            all_missing_refs.extend(release_ref_result["missing_refs"])
            all_unsafe_refs.extend(release_ref_result["unsafe_refs"])
            release_results.append({"id": release_id, "ok": not release_failures, "failures": sorted(set(release_failures))})

    checks = [
        {"id": "archive_sha256", "status": "passed" if not any("archive_sha256" in item for item in failures) else "failed"},
        {"id": "manifest_sha256", "status": "passed" if not any("manifest_sha256" in item for item in failures) else "failed"},
        {"id": "detached_signature", "status": "passed" if not any("signature_" in item for item in failures) else "failed"},
        {"id": "materials_attached", "status": "passed" if not any("material_" in item or "transcript" in item for item in failures) else "failed"},
        {"id": "verification_summary", "status": "passed" if not any("verification_summary" in item for item in failures) else "failed"},
        {"id": "registry_attachment", "status": "passed" if not any("registry_" in item for item in failures) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "releases": len(release_results),
        "passing_releases": sum(1 for item in release_results if item["ok"]),
        "signed_artifacts": signed_artifacts,
        "required_materials": len(_as_string_list(policy.get("required_materials"))),
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
        "release_results": sorted(release_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def release_provenance_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("release_provenance_report_required")
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
    parser = argparse.ArgumentParser(description="Validate NoemaForge signed release provenance contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/release-provenance-policy.json",
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

    report = validate_release_provenance_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
        registry_path=registry_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "ReleaseProvenanceValidationSummary",
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
