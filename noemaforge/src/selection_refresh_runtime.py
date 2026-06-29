#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/selection_refresh_runtime.py
Zone: release/package
Version: 0.33.0
Created: 2026-06-28
Modified: 2026-06-28
Purpose: Refresh older model-selection artifacts as reusable cache candidates.
Inputs: Existing firstboot selection artifacts, runtime status snapshots and main model manifest.
Outputs: Refreshed selection decision, staffing summary, provenance, invalidation and role mapping artifacts.
Side effects: Writes refreshed JSON artifacts only under the requested output directory.
Tests: noemaforge/tests/test_selection_refresh_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from noemaforge_version import RUNTIME_VERSION


API_VERSION = "noemaforge.model-selection-refresh/v1"
TEXT_STAGE_ALLOWED_FALLBACK_ROLES = [
    "operator.admin/administrator",
    "dev.work/solution_architect",
    "dev.work/qa",
    "knowledge.vault/researcher",
    "writing.story/writer",
    "system.guard/sr",
]
EXPLICIT_ROLE_FALLBACKS = {
    "dev.work/dev": ["dev.work/solution_architect", "dev.work/qa"],
    "dev.work/python_dev": ["dev.work/solution_architect", "dev.work/qa"],
    "dev.work/qa": ["dev.work/solution_architect"],
    "knowledge.vault/researcher": ["operator.admin/administrator", "writing.story/writer"],
}
GENERIC_TEXT_STAGE_TERMS = {
    "admin",
    "analysis",
    "architecture",
    "archive",
    "audit",
    "baseline",
    "chapter",
    "check",
    "classification",
    "cluster",
    "collect",
    "context",
    "decision",
    "docs",
    "document",
    "draft",
    "evidence",
    "fact",
    "gap",
    "inventory",
    "label",
    "lint",
    "merge",
    "metadata",
    "mvp",
    "outline",
    "plan",
    "prepared",
    "rc",
    "research",
    "review",
    "scope",
    "source",
    "status",
    "template",
    "triage",
    "validation",
    "wiki",
}
STAGE_CAPABILITIES = {
    "text_plan",
    "text_review",
    "text_status",
    "text_documentation",
    "audit",
    "handoff",
    "dev_plan",
    "dev_execute",
    "media_plan",
    "media_execute",
    "voice_execute",
    "vision_execute",
    "video_execute",
    "external_io",
    "unknown",
}
DETERMINISTIC_LOCAL_STAGE_CAPABILITIES = {
    "text_plan",
    "text_review",
    "text_status",
    "text_documentation",
    "audit",
    "handoff",
    "dev_plan",
    "media_plan",
}
BACKEND_REQUIRED_STAGE_CAPABILITIES = STAGE_CAPABILITIES - DETERMINISTIC_LOCAL_STAGE_CAPABILITIES
CAPABILITY_REQUIRED_BACKENDS = {
    "dev_execute": "real development adapter/backend with explicit patch/test execution authority",
    "media_execute": "explicit media generation adapter/backend",
    "voice_execute": "explicit voice/STT/TTS adapter with operator consent",
    "vision_execute": "explicit vision/VLM adapter with operator consent",
    "video_execute": "explicit video generation or video-processing adapter/backend",
    "external_io": "explicit external I/O adapter with capability-token policy",
    "unknown": "explicit stage adapter or manifest capability split",
}
PIPELINE_SCOPE_VALUES = {"prod_launchable", "degraded_plan_only", "adapter_required", "out_of_prod_scope"}
VERIFY_SCOPE_VALUES = {"prod", "degraded"}
PIPELINE_ADAPTER_REQUIREMENTS = {
    "music_generation": {
        "required_adapter": "audio.music_generate adapter with MusicGen or Stable-Audio backend",
        "required_capability": "media_execute",
    },
    "voice_generation": {
        "required_adapter": "audio.tts_generate adapter with Piper, Coqui, or Bark backend",
        "required_capability": "voice_execute",
    },
    "photo_generation": {
        "required_adapter": "image.photo_generate adapter with diffusion image backend",
        "required_capability": "media_execute",
    },
    "video_generation": {
        "required_adapter": "video.generate adapter with video generation backend",
        "required_capability": "video_execute",
    },
    "image_analysis": {
        "required_adapter": "image.metadata_and_caption adapter with local VLM caption backend",
        "required_capability": "vision_execute",
    },
    "camera_mask_bridge": {
        "required_adapter": "video_call.masks_virtual_camera adapter with segmentation and virtual-camera bridge",
        "required_capability": "vision_execute",
    },
    "image.metadata_and_caption": {
        "required_adapter": "image.metadata_and_caption adapter with local VLM caption backend",
        "required_capability": "vision_execute",
    },
    "audio.tts_generate": {
        "required_adapter": "audio.tts_generate adapter with Piper, Coqui, or Bark backend",
        "required_capability": "voice_execute",
    },
    "audio.music_generate": {
        "required_adapter": "audio.music_generate adapter with MusicGen or Stable-Audio backend",
        "required_capability": "media_execute",
    },
    "image.photo_generate": {
        "required_adapter": "image.photo_generate adapter with diffusion image backend",
        "required_capability": "media_execute",
    },
    "video.generate": {
        "required_adapter": "video.generate adapter with video generation backend",
        "required_capability": "video_execute",
    },
    "video_call.masks_virtual_camera": {
        "required_adapter": "video_call.masks_virtual_camera adapter with segmentation and virtual-camera bridge",
        "required_capability": "vision_execute",
    },
    "gui.persona_portraits": {
        "required_adapter": "persona portrait GUI launch/review adapter with explicit operator start",
        "required_capability": "external_io",
    },
    "gui.admin_console_api": {
        "required_adapter": "localhost Admin GUI/API launch adapter with explicit operator start",
        "required_capability": "external_io",
    },
    "admin.route_music_generation": {
        "required_adapter": "admin media-routing adapter for audio.music_generate plan creation",
        "required_capability": "external_io",
    },
    "admin.route_model_evolution": {
        "required_adapter": "admin model-evolution routing adapter with explicit operator approval",
        "required_capability": "external_io",
    },
}


def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json_dumps(data) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _first_existing(source: Path, names: Iterable[str]) -> Optional[Path]:
    for name in names:
        candidate = source / name
        if candidate.exists():
            return candidate
    return None


def selection_artifact_paths(source: Path) -> Dict[str, Path]:
    return {
        "decision": _first_existing(source, ["model-selection-decision.json", "10_model_selection_decision.json"]) or source / "model-selection-decision.json",
        "staffing": _first_existing(source, ["firstboot-staffing-summary.json", "09_firstboot_staffing_summary.json"]) or source / "firstboot-staffing-summary.json",
        "role_candidate_map": _first_existing(source, ["role-candidate-map.json", "11_role_candidate_map.json"]) or source / "role-candidate-map.json",
        "tournament": _first_existing(source, ["role-tournament-results.json", "12_role_tournament_results.json"]) or source / "role-tournament-results.json",
        "main_manifest": _first_existing(source, ["main_manifest.json", "26_main_manifest.json"]) or source / "main_manifest.json",
        "runtime_status": _first_existing(source, ["runtime-status-compact.json", "28_runtime_status_compact.json"]) or source / "runtime-status-compact.json",
    }


def _candidate_ok(candidate: Any) -> bool:
    if not isinstance(candidate, dict):
        return False
    if not str(candidate.get("model_id") or candidate.get("logical_model_id") or "").strip():
        return False
    if str(candidate.get("selection_status") or "") not in {"", "valid_measured", "reuse_verified", "reuse_with_warning"}:
        return False
    return any(candidate.get(key) is not None for key in ["score", "pass_rate", "json_parse_rate", "quality_score"])


def _chosen_for_role(role_spec: Any) -> Dict[str, Any]:
    if not isinstance(role_spec, dict):
        return {}
    chosen = role_spec.get("chosen")
    if isinstance(chosen, dict):
        return chosen
    selected = role_spec.get("selected")
    if isinstance(selected, list) and selected and isinstance(selected[0], dict):
        return selected[0]
    return {}


def _diagnostics(decision: Dict[str, Any], staffing: Dict[str, Any], main_manifest: Dict[str, Any], runtime_status: Dict[str, Any]) -> List[str]:
    diagnostics: List[str] = []
    if str(decision.get("version") or "") and str(decision.get("version")) != RUNTIME_VERSION:
        diagnostics.extend(["stale_selection_artifacts", "selection_schema_mismatch"])
    gateway = runtime_status.get("gateway") if isinstance(runtime_status.get("gateway"), dict) else {}
    main_backend = runtime_status.get("main_backend") if isinstance(runtime_status.get("main_backend"), dict) else {}
    sockets = runtime_status.get("sockets") if isinstance(runtime_status.get("sockets"), dict) else {}
    gateway_socket_present = bool(sockets.get("/run/noemaforge/llm/gateway.sock"))
    backend_socket_present = bool(sockets.get("/run/noemaforge/llm/backends/main.sock"))
    if gateway and not bool(gateway.get("ok")):
        diagnostics.append("gateway_missing")
    if (bool(main_backend.get("ok")) or backend_socket_present) and (not bool(gateway.get("ok")) or not gateway_socket_present):
        diagnostics.append("backend_available_gateway_missing")
    active_model = runtime_status.get("active_model") if isinstance(runtime_status.get("active_model"), dict) else {}
    active_id = str(active_model.get("model_id") or "")
    manifest_id = str(main_manifest.get("model_id") or "")
    active_realpath = str(active_model.get("model_realpath") or "")
    manifest_source = str(main_manifest.get("source") or "")
    if manifest_id and active_id and manifest_id != active_id:
        diagnostics.append("model_manifest_realpath_mismatch")
    elif manifest_source and active_realpath and Path(manifest_source).name != Path(active_realpath).name:
        diagnostics.append("model_manifest_realpath_mismatch")
    if staffing.get("unstaffed_roles"):
        diagnostics.append("role_unstaffed")
    return sorted(set(diagnostics))


def refresh_selection_artifacts(source: Path | str, out_dir: Path | str, *, refresh_reason: str = "partial_refresh") -> Dict[str, Any]:
    source = Path(source)
    out_dir = Path(out_dir)
    paths = selection_artifact_paths(source)
    decision = read_json(paths["decision"], {})
    staffing = read_json(paths["staffing"], {})
    role_map = read_json(paths["role_candidate_map"], {})
    tournament = read_json(paths["tournament"], {})
    main_manifest = read_json(paths["main_manifest"], {})
    runtime_status = read_json(paths["runtime_status"], {})

    roles = role_map.get("roles") if isinstance(role_map.get("roles"), dict) else {}
    unstaffed = set(str(item) for item in staffing.get("unstaffed_roles", []) if str(item or "").strip())
    diagnostics = _diagnostics(decision, staffing, main_manifest, runtime_status)
    role_classifications: Dict[str, Dict[str, Any]] = {}
    refreshed_role_mapping: Dict[str, Dict[str, Any]] = {}
    invalidated: List[Dict[str, Any]] = []
    reused = revalidated = recomputed = invalid_count = 0
    null_before = 0
    null_after = 0

    all_roles = sorted(set(roles) | unstaffed)
    for role in all_roles:
        chosen = _chosen_for_role(roles.get(role))
        reasons: List[str] = []
        classification = "needs_recompute"
        if not chosen:
            null_before += 1
            null_after += 1
            reasons.append("role_mapping_missing" if role not in roles else "role_unstaffed")
            recomputed += 1
        elif role in unstaffed:
            reasons.append("role_unstaffed")
            classification = "needs_recompute"
            recomputed += 1
        elif not _candidate_ok(chosen):
            reasons.append("incompatible_or_invalid_candidate")
            classification = "invalidated"
            invalid_count += 1
            invalidated.append({"role_key": role, "reason": "incompatible_or_invalid_candidate", "candidate": chosen})
        else:
            classification = "reuse_with_warning" if diagnostics else "reuse_verified"
            reasons.extend(diagnostics)
            reused += 1
            if classification == "reuse_with_warning":
                revalidated += 1
            refreshed_role_mapping[role] = {
                "role_key": role,
                "model_id": chosen.get("model_id") or chosen.get("logical_model_id"),
                "logical_model_id": chosen.get("logical_model_id") or chosen.get("model_id"),
                "score": chosen.get("score"),
                "pass_rate": chosen.get("pass_rate"),
                "json_parse_rate": chosen.get("json_parse_rate"),
                "quality_score": chosen.get("quality_score"),
                "selection_status": classification,
                "source_selection_version": decision.get("version"),
            }
        role_classifications[role] = {
            "role_key": role,
            "classification": classification,
            "reasons": sorted(set(reasons)),
            "candidate_model_id": chosen.get("model_id") if isinstance(chosen, dict) else None,
        }

    selected_model_ids = sorted({str(item.get("model_id") or "") for item in refreshed_role_mapping.values() if item.get("model_id")})
    acceptance_state = "degraded_selected" if null_after or diagnostics else "selection_refreshed"
    report = {
        "apiVersion": API_VERSION,
        "kind": "SelectionRefreshReport",
        "version": RUNTIME_VERSION,
        "created_at": nowz(),
        "source_selection_version": decision.get("version"),
        "target_runtime_version": RUNTIME_VERSION,
        "source_artifact_paths": {key: str(path) for key, path in paths.items() if path.exists()},
        "reused_role_count": reused,
        "revalidated_role_count": revalidated,
        "recomputed_role_count": recomputed,
        "invalidated_role_count": invalid_count,
        "null_role_count_before": null_before,
        "null_role_count_after": null_after,
        "cache_reuse_ratio": round(reused / max(1, len(all_roles)), 4),
        "refresh_reason": refresh_reason,
        "refresh_mode": "partial",
        "acceptance_state": acceptance_state,
        "diagnostics": diagnostics,
        "role_classifications": role_classifications,
    }
    refreshed_decision = {
        **{k: v for k, v in decision.items() if k not in {"version", "chosen_by_role"}},
        "apiVersion": "noemaforge.model-selection/v1",
        "kind": "ModelSelectionDecision",
        "version": RUNTIME_VERSION,
        "created_at": nowz(),
        "source_selection_version": decision.get("version"),
        "refresh_mode": "partial",
        "refresh_report": str(out_dir / "selection-refresh-report.json"),
        "provenance": str(out_dir / "selection-refresh-provenance.json"),
        "invalidation_report": str(out_dir / "selection-refresh-invalidations.json"),
        "diagnostics": diagnostics,
        "chosen_by_role": refreshed_role_mapping,
        "role_classifications": role_classifications,
    }
    refreshed_staffing = {
        **staffing,
        "apiVersion": "noemaforge.firstbootstaffing/v1",
        "kind": "FirstbootStaffingSummary",
        "version": RUNTIME_VERSION,
        "source_selection_version": decision.get("version"),
        "staffing_state": acceptance_state,
        "selected_model_ids": selected_model_ids,
        "selected_model_count": len(selected_model_ids),
        "diagnostics": diagnostics,
        "refresh_report": str(out_dir / "selection-refresh-report.json"),
    }
    provenance = {
        "apiVersion": API_VERSION,
        "kind": "SelectionRefreshProvenance",
        "version": RUNTIME_VERSION,
        "created_at": report["created_at"],
        "source_selection_version": decision.get("version"),
        "target_runtime_version": RUNTIME_VERSION,
        "source_artifact_paths": report["source_artifact_paths"],
        "source_selection_mode": decision.get("mode") or tournament.get("selection_mode"),
        "source_staffing_state": staffing.get("staffing_state"),
        "preserved_measurements": sorted(refreshed_role_mapping),
        "requires_revalidation": sorted(role for role, item in role_classifications.items() if item["classification"] == "needs_revalidation"),
        "requires_recompute": sorted(role for role, item in role_classifications.items() if item["classification"] == "needs_recompute"),
    }
    invalidation_report = {
        "apiVersion": API_VERSION,
        "kind": "SelectionInvalidationReport",
        "version": RUNTIME_VERSION,
        "created_at": report["created_at"],
        "diagnostics": diagnostics,
        "invalidated": invalidated,
        "needs_recompute": provenance["requires_recompute"],
    }
    role_mapping_doc = {
        "apiVersion": API_VERSION,
        "kind": "RefreshedRoleMapping",
        "version": RUNTIME_VERSION,
        "created_at": report["created_at"],
        "selection_status": acceptance_state,
        "diagnostics": diagnostics,
        "needs_recompute": provenance["requires_recompute"],
        "roles": refreshed_role_mapping,
        "fallback_policy": {
            "explicit_role_fallbacks": EXPLICIT_ROLE_FALLBACKS,
            "generic_text_stage_allowed_roles": TEXT_STAGE_ALLOWED_FALLBACK_ROLES,
        },
    }
    write_json(out_dir / "model-selection-decision.json", refreshed_decision)
    write_json(out_dir / "firstboot-staffing-summary.json", refreshed_staffing)
    write_json(out_dir / "selection-refresh-report.json", report)
    write_json(out_dir / "selection-refresh-provenance.json", provenance)
    write_json(out_dir / "selection-refresh-invalidations.json", invalidation_report)
    write_json(out_dir / "refreshed-role-mapping.json", role_mapping_doc)
    return report | {"artifacts": {
        "model_selection_decision": str(out_dir / "model-selection-decision.json"),
        "firstboot_staffing_summary": str(out_dir / "firstboot-staffing-summary.json"),
        "refresh_report": str(out_dir / "selection-refresh-report.json"),
        "provenance": str(out_dir / "selection-refresh-provenance.json"),
        "invalidation_report": str(out_dir / "selection-refresh-invalidations.json"),
        "refreshed_role_mapping": str(out_dir / "refreshed-role-mapping.json"),
    }}


def _stage_terms(stage: str) -> set[str]:
    return {item for item in re.split(r"[^a-z0-9]+", str(stage or "").lower()) if item}


def _stage_term_list(stage: str) -> List[str]:
    return [item for item in re.split(r"[^a-z0-9]+", str(stage or "").lower()) if item]


def classify_stage_capability(stage: str, *, pipeline_id: str = "", permission_mode: str = "") -> str:
    """Classify a pipeline stage into the deterministic capability taxonomy."""
    del pipeline_id
    normalized = "_".join(_stage_term_list(stage))
    terms = _stage_terms(stage)
    permission = str(permission_mode or "").casefold()
    if normalized == "development":
        return "dev_plan" if permission == "plan_only" else "dev_execute"
    if normalized in {"development_plan", "dev_plan", "implementation_plan", "patch_plan"}:
        return "dev_plan"
    if normalized in {"development_execute", "dev_execute", "implementation_execute", "patch_execute"}:
        return "dev_execute"
    if terms & {"voice", "audio", "tts", "stt", "microphone", "transcribe", "speech"}:
        return "media_plan" if terms & {"plan", "planning", "spec", "metadata", "review"} else "voice_execute"
    if terms & {"vision", "vlm", "image_analysis", "camera"}:
        return "media_plan" if terms & {"plan", "planning", "spec", "metadata", "review"} else "vision_execute"
    if terms & {"video", "movie", "clip"}:
        return "media_plan" if terms & {"plan", "planning", "spec", "metadata", "review"} else "video_execute"
    if terms & {"media", "image", "photo", "music", "generation", "generate", "mask", "segmentation"}:
        return "media_plan" if terms & {"plan", "planning", "spec", "metadata", "review", "catalog"} else "media_execute"
    if terms & {"external", "network", "upload", "download", "publish", "export", "import", "sync", "remote"}:
        return "external_io" if not terms & {"plan", "review", "audit"} else "text_plan"
    if terms & {"handoff", "support", "bundle"}:
        return "handoff"
    if terms & {"review", "approval", "merge"}:
        return "text_review"
    if terms & {"status", "health", "safe", "orient", "intake", "chat"}:
        return "text_status"
    if terms & {"documentation", "docs", "doc", "changelog", "wiki"}:
        return "text_documentation"
    if terms & {"audit", "test", "testing", "qa", "validation", "smoke", "fact", "inventory", "optimization", "performance", "budget", "analysis", "check"}:
        return "audit"
    if terms & {"plan", "planning", "outline", "research", "source", "architecture", "clarification", "release", "pipeline", "graph", "relation", "entity", "provenance", "drafting", "draft"}:
        return "text_plan"
    return "unknown"


def deterministic_local_worker_allowed(capability: str) -> bool:
    return str(capability or "unknown") in DETERMINISTIC_LOCAL_STAGE_CAPABILITIES


def required_backend_for_capability(capability: str) -> str:
    return CAPABILITY_REQUIRED_BACKENDS.get(str(capability or "unknown"), CAPABILITY_REQUIRED_BACKENDS["unknown"])


def normalize_verify_scope(value: str = "") -> str:
    selected = str(value or os.environ.get("NOEMAFORGE_VERIFY_SCOPE") or "prod").strip().lower()
    return selected if selected in VERIFY_SCOPE_VALUES else "prod"


def pipeline_scope_policy(pipeline: Dict[str, Any], *, pipeline_id: str = "") -> Dict[str, Any]:
    pid = str(pipeline_id or pipeline.get("id") or "")
    explicit = str(pipeline.get("pipeline_scope") or pipeline.get("scope") or "").strip()
    stages = [str(stage) for stage in (pipeline.get("stages") or [])]
    capabilities = [
        classify_stage_capability(stage, pipeline_id=pid, permission_mode=str(pipeline.get("permission_mode") or ""))
        for stage in stages
    ]
    backend_required = [capability for capability in capabilities if capability in BACKEND_REQUIRED_STAGE_CAPABILITIES]
    adapter_requirement = PIPELINE_ADAPTER_REQUIREMENTS.get(pid) or {}
    required_capability = str(adapter_requirement.get("required_capability") or "").strip()
    required_adapter = str(adapter_requirement.get("required_adapter") or "").strip()
    if required_capability:
        backend_required.append(required_capability)
    if explicit in PIPELINE_SCOPE_VALUES:
        scope = explicit
        reason = "explicit_catalog_scope"
    elif str(pipeline.get("source_catalog") or "") == "media-pipeline-catalog":
        scope = "adapter_required"
        reason = "media_catalog_adapter_entry"
    elif str(pipeline.get("permission_mode") or "") in {"explicit_only", "manual_only"}:
        scope = "adapter_required"
        reason = "explicit_or_manual_permission_mode"
    elif backend_required:
        scope = "degraded_plan_only"
        reason = "backend_required_stage_present"
    else:
        scope = "prod_launchable"
        reason = "deterministic_local_capabilities"
    required_adapters = sorted({required_backend_for_capability(capability) for capability in backend_required})
    if required_adapter:
        required_adapters = sorted(set(required_adapters + [required_adapter]))
    next_actions = []
    if required_adapter and required_capability:
        next_actions = [
            f"Configure {required_adapter}.",
            f"Grant capability-token policy for {required_capability}.",
            "Rerun verify-all-pipelines-local with the real adapter available.",
        ]
    elif required_adapters:
        next_actions = [
            f"Configure {required_adapters[0]}.",
            "Rerun verify-all-pipelines-local with the real adapter available.",
        ]
    return {
        "scope": scope,
        "reason": reason,
        "stage_capabilities": capabilities,
        "backend_required_capabilities": sorted(set(backend_required)),
        "required_adapter": required_adapter or (required_adapters[0] if required_adapters else ""),
        "required_capability": required_capability or (sorted(set(backend_required))[0] if backend_required else ""),
        "required_adapters": required_adapters,
        "required_capabilities": sorted(set(backend_required)),
        "next_actions": next_actions,
        "degraded_plan_artifact": "final_degraded_plan_package.json",
    }


def verifier_acceptance_counts(verdicts: Iterable[str], entries: Optional[Iterable[Dict[str, Any]]] = None, *, verify_scope: str = "prod") -> Dict[str, int]:
    verify_scope = normalize_verify_scope(verify_scope)
    counts = {
        "completed_real_count": 0,
        "completed_degraded_scope_count": 0,
        "fail_actionably_count": 0,
        "blocked_missing_worker_count": 0,
        "blocked_backend_required_count": 0,
        "blocked_worker_cannot_execute_count": 0,
        "excluded_from_prod_scope_count": 0,
        "incomplete_count": 0,
        "unknown_count": 0,
        "placeholder_count": 0,
        "hang_or_loop_count": 0,
    }
    source = list(entries or [])
    if not source:
        source = [{"verdict": verdict} for verdict in verdicts]
    for entry in source:
        value = str((entry or {}).get("verdict") or "UNKNOWN")
        policy = (entry or {}).get("pipeline_scope_policy") if isinstance(entry, dict) else {}
        scope = str((policy or {}).get("scope") or "")
        if value == "COMPLETED_REAL_OUTPUT":
            counts["completed_real_count"] += 1
        elif value == "COMPLETED_DEGRADED_PLAN_PACKAGE":
            counts["completed_degraded_scope_count"] += 1
            if verify_scope != "degraded" or scope != "degraded_plan_only":
                counts["fail_actionably_count"] += 1
        elif value == "DEGRADED_PLAN_ONLY_DEFERRED":
            counts["excluded_from_prod_scope_count"] += 1
            if verify_scope == "degraded" and scope == "degraded_plan_only":
                counts["fail_actionably_count"] += 1
        elif value == "OUT_OF_PROD_SCOPE":
            counts["excluded_from_prod_scope_count"] += 1
        elif value == "ADAPTER_REQUIRED_DEFERRED":
            counts["excluded_from_prod_scope_count"] += 1
            counts["blocked_backend_required_count"] += 1
        elif value in {"FAIL_ACTIONABLY", "BLOCKED_WORKER_CANNOT_EXECUTE", "BLOCKED_BACKEND_REQUIRED"}:
            counts["fail_actionably_count"] += 1
            if value == "BLOCKED_BACKEND_REQUIRED":
                counts["blocked_backend_required_count"] += 1
            if value == "BLOCKED_WORKER_CANNOT_EXECUTE":
                counts["blocked_worker_cannot_execute_count"] += 1
        elif value == "BLOCKED_MISSING_WORKER":
            counts["blocked_missing_worker_count"] += 1
        elif value == "INCOMPLETE":
            counts["incomplete_count"] += 1
        elif value == "HANG_OR_LOOP":
            counts["hang_or_loop_count"] += 1
        elif value in {"COMPLETED_WITH_PLACEHOLDER", "PLACEHOLDER_OUTPUT"}:
            counts["placeholder_count"] += 1
        else:
            counts["unknown_count"] += 1
    counts["acceptance_failure_count"] = (
        counts["fail_actionably_count"]
        + counts["placeholder_count"]
        + counts["incomplete_count"]
        + counts["unknown_count"]
        + counts["hang_or_loop_count"]
        + counts["blocked_missing_worker_count"]
    )
    return counts


def preferred_role_for_stage(pipeline_id: str, stage: str) -> str:
    text = f"{pipeline_id} {stage}".lower()
    terms = _stage_terms(text)
    if any(term in terms for term in {"test", "testing", "qa", "validation", "smoke"}):
        return "dev.work/qa"
    if any(term in terms for term in {"dev", "development", "code", "refactor", "patch", "module"}):
        return "dev.work/dev"
    if any(term in terms for term in {"research", "source", "citation", "knowledge", "graph"}):
        return "knowledge.vault/researcher"
    if any(term in terms for term in {"write", "writer", "draft", "book", "chapter", "story"}):
        return "writing.story/writer"
    return "operator.admin/administrator"


def is_generic_text_stage(stage: str) -> bool:
    return bool(_stage_terms(stage) & GENERIC_TEXT_STAGE_TERMS)


def resolve_stage_worker(mapping_doc: Dict[str, Any], *, pipeline_id: str, stage: str) -> Dict[str, Any]:
    roles = mapping_doc.get("roles") if isinstance(mapping_doc.get("roles"), dict) else {}
    diagnostics = list(mapping_doc.get("diagnostics") or [])
    requested = preferred_role_for_stage(pipeline_id, stage)
    role_order = [requested, *EXPLICIT_ROLE_FALLBACKS.get(requested, [])]
    if is_generic_text_stage(stage):
        role_order.extend(TEXT_STAGE_ALLOWED_FALLBACK_ROLES)
    seen: set[str] = set()
    for role in role_order:
        if role in seen:
            continue
        seen.add(role)
        item = roles.get(role)
        if isinstance(item, dict) and item.get("model_id"):
            fallback_used = role != requested
            return {
                "ok": True,
                "diagnostics": diagnostics,
                "requested_role": requested,
                "resolved_role": role,
                "fallback_used": fallback_used,
                "fallback_policy": "explicit" if fallback_used and role in EXPLICIT_ROLE_FALLBACKS.get(requested, []) else ("generic_text_stage" if fallback_used else "exact"),
                "model_id": item.get("model_id"),
                "worker_status": "registered_from_refreshed_selection",
            }
    missing = "role_unstaffed" if requested in mapping_doc.get("needs_recompute", []) else "role_mapping_missing"
    return {
        "ok": False,
        "diagnostics": sorted(set([*diagnostics, missing, "worker_not_registered"])),
        "requested_role": requested,
        "resolved_role": "",
        "fallback_used": False,
        "fallback_policy": "",
        "model_id": "",
        "worker_status": "worker_not_registered",
    }


def load_refreshed_role_mapping(path: Path | str | None = None) -> Dict[str, Any]:
    candidates: List[Path] = []
    if path:
        candidates.append(Path(path))
    env = os.environ.get("NOEMAFORGE_REFRESHED_ROLE_MAPPING")
    if env:
        candidates.append(Path(env))
    refresh_dir = os.environ.get("NOEMAFORGE_SELECTION_REFRESH_DIR")
    if refresh_dir:
        candidates.append(Path(refresh_dir) / "refreshed-role-mapping.json")
    for candidate in candidates:
        if candidate.exists():
            loaded = read_json(candidate, {})
            if isinstance(loaded, dict):
                return loaded
    return {}


def cmd_refresh(args: argparse.Namespace) -> int:
    report = refresh_selection_artifacts(args.source, args.out, refresh_reason=args.reason)
    print(json_dumps(report))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="selection-refresh")
    parser.add_argument("source")
    parser.add_argument("--out", required=True)
    parser.add_argument("--reason", default="partial_refresh")
    parser.set_defaults(func=cmd_refresh)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
