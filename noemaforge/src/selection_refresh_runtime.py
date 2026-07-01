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
ROLE_SELECTION_API_VERSION = "noemaforge.model-role-selection/v1"
ROLE_SELECTION_SCHEMA_VERSION = 2
SELECTION_MODES = {"fast", "normal", "full", "full_composite"}
ROLE_REQUIREMENTS = {
    "operator.admin/administrator": {"capability_class": "text_status", "required_capabilities": ["text_status", "text_review"]},
    "dev.work/solution_architect": {"capability_class": "dev_plan", "required_capabilities": ["dev_plan", "text_plan", "text_review"]},
    "dev.work/dev": {"capability_class": "dev_execute", "required_capabilities": ["dev_execute", "dev_plan"]},
    "dev.work/qa": {"capability_class": "audit", "required_capabilities": ["audit", "text_review"]},
    "knowledge.vault/researcher": {"capability_class": "text_plan", "required_capabilities": ["text_plan", "audit"]},
    "writing.story/writer": {"capability_class": "text_documentation", "required_capabilities": ["text_documentation", "text_plan"]},
}
VALID_SELECTION_STATES = {
    "valid_selected",
    "operator_confirmation_required",
    "adapter_required",
    "backend_unavailable",
    "insufficient_capability",
    "degraded_selected",
    "degraded_plan_only",
    "blocked_missing_worker",
    "blocked_backend_required",
    "blocked_placeholder_output",
    "out_of_prod_scope",
}
DEGRADED_FALLBACK_CAPABILITY_CLASSES = {
    "text_plan",
    "text_review",
    "audit",
    "handoff",
    "dev_plan",
    "media_plan",
}
EXECUTION_OR_BACKEND_CAPABILITY_CLASSES = {
    "dev_execute",
    "media_execute",
    "voice_execute",
    "vision_execute",
    "video_execute",
    "external_io",
    "unknown",
}
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


def _as_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def normalize_selection_mode(value: str = "") -> str:
    selected = str(value or "normal").strip().lower().replace("-", "_")
    aliases = {"composite": "full_composite", "fullcomposite": "full_composite"}
    selected = aliases.get(selected, selected)
    return selected if selected in SELECTION_MODES else "normal"


def _first_text(raw: Dict[str, Any], names: Iterable[str], default: str = "unknown") -> str:
    for name in names:
        value = str(raw.get(name) or "").strip()
        if value:
            return value
    return default


def _numeric_or_unknown(value: Any) -> Any:
    try:
        return int(value)
    except Exception:
        try:
            return float(value)
        except Exception:
            return "unknown"


def _metric_present(candidate: Dict[str, Any], measured: Dict[str, Any], key: str) -> bool:
    return candidate.get(key) is not None or measured.get(key) is not None


def _cost_tuple(candidate: Dict[str, Any]) -> tuple[int, float, str]:
    size_rank = {"tiny": 0, "small": 1, "medium": 2, "large": 3, "xlarge": 4, "unknown": 5}
    size = size_rank.get(str(candidate.get("size_class") or "unknown").lower(), 5)
    measured = candidate.get("measured") if isinstance(candidate.get("measured"), dict) else {}
    latency = _float(candidate.get("avg_latency_ms", measured.get("avg_latency_ms", 999999.0)), 999999.0)
    return (size, latency, str(candidate.get("model_id") or ""))


def _diverse_candidates(candidates: List[Dict[str, Any]], limit: int = 4) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    seen_dims: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        dims = (
            str(candidate.get("vendor") or "unknown"),
            str(candidate.get("architecture") or "unknown"),
            str(candidate.get("size_class") or "unknown"),
        )
        if dims in seen_dims and len(selected) >= 2:
            continue
        selected.append(candidate)
        seen_dims.add(dims)
        if len(selected) >= limit:
            break
    if len(selected) < min(2, len(candidates)):
        for candidate in candidates:
            if candidate not in selected:
                selected.append(candidate)
            if len(selected) >= min(2, len(candidates)):
                break
    return selected


def _selection_next_actions(state: str, *, required_capability: str = "", required_adapter: str = "") -> List[str]:
    if state == "valid_selected":
        return []
    if state == "operator_confirmation_required":
        return ["Confirm the epoch switch explicitly before applying the selected model."]
    if state == "adapter_required":
        adapter = required_adapter or "the required adapter"
        return [f"Install or configure {adapter}.", "Rerun selection after the adapter reports available."]
    if state == "backend_unavailable":
        return ["Start or repair the declared local backend explicitly.", "Rerun selection after backend readiness is real."]
    if state == "insufficient_capability":
        capability = required_capability or "the missing required capability"
        return [f"Provide a model or adapter with {capability}.", "Do not treat this candidate as selected output."]
    if state == "degraded_selected":
        return ["Use only for deterministic planning, review, audit, or handoff output.", "Block before any execution or backend-required stage."]
    if state == "degraded_plan_only":
        return ["Emit a real plan package.", "Do not mark backend execution stages completed."]
    if state == "blocked_missing_worker":
        return ["Register a deterministic local worker or provide a real stage artifact."]
    if state == "blocked_backend_required":
        return ["Install/configure the required backend and adapter.", "Register a real artifact after backend execution."]
    if state == "blocked_placeholder_output":
        return ["Replace placeholder output with a real deterministic artifact before completion."]
    if state == "out_of_prod_scope":
        return ["Exclude from production verification scope until explicitly promoted."]
    return ["Record a specific actionable remediation before continuing."]


def _required_adapter_for_candidate(candidate: Dict[str, Any], required_capability: str = "") -> str:
    explicit = str(candidate.get("required_adapter") or candidate.get("adapter") or "").strip()
    if explicit:
        return explicit
    return required_backend_for_capability(required_capability) if required_capability in BACKEND_REQUIRED_STAGE_CAPABILITIES else ""


def _gguf_shard_safety(raw: Dict[str, Any]) -> Dict[str, Any]:
    safety = raw.get("gguf_shard_safety")
    if isinstance(safety, dict):
        return dict(safety)
    path = str(raw.get("source_path") or raw.get("canonical_path") or raw.get("path") or "")
    name = Path(path).name.lower()
    match = re.search(r"-(\d{5})-of-(\d{5})\.gguf$", name)
    if not match:
        return {"state": "unknown" if path else "unknown", "reason": "not_declared"}
    shard_no = int(match.group(1))
    return {
        "state": "safe_head_shard" if shard_no == 1 else "blocked_non_head_shard",
        "shard_index": shard_no,
        "shard_count": int(match.group(2)),
    }


def _host_resource_fit_hints(raw: Dict[str, Any]) -> Dict[str, Any]:
    hints = raw.get("host_resource_fit_hints") or raw.get("resource_fit")
    if isinstance(hints, dict):
        return dict(hints)
    return {
        "state": str(raw.get("resource_fit_state") or "unknown"),
        "memory_fit": str(raw.get("memory_fit") or "unknown"),
        "gpu_fit": str(raw.get("gpu_fit") or "unknown"),
    }


def normalize_inventory_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize model inventory records before scoring.

    The scorer treats vendor, architecture and size as comparison dimensions,
    not as hard-coded preferences. Missing backend or adapter declarations are
    preserved as degraded states instead of being converted into success.
    """
    normalized: List[Dict[str, Any]] = []
    for raw in records:
        if not isinstance(raw, dict):
            continue
        model_id = str(raw.get("model_id") or raw.get("logical_model_id") or raw.get("id") or "").strip()
        if not model_id:
            continue
        capabilities = sorted(set(_as_list(raw.get("capabilities"))) | set(_as_list(raw.get("capability_classes"))))
        measured = raw.get("measured") if isinstance(raw.get("measured"), dict) else {}
        size_b = raw.get("size_bytes")
        size_label = str(raw.get("size_class") or raw.get("size") or "").strip()
        if not size_label:
            params_b = _float(raw.get("params_b"), -1.0)
            if params_b >= 13:
                size_label = "large"
            elif params_b >= 3:
                size_label = "medium"
            elif params_b >= 0:
                size_label = "small"
            elif size_b is not None and _float(size_b) >= 8_000_000_000:
                size_label = "large"
            else:
                size_label = "unknown"
        vendor = _first_text(raw, ["vendor", "provider", "publisher"], "unknown").lower()
        family = _first_text(raw, ["family", "architecture_family", "model_family"], "unknown").lower()
        architecture = _first_text(raw, ["architecture", "arch", "family"], "unknown").lower()
        backend_status = str(raw.get("backend_status") or ("available" if raw.get("backend_available", True) else "unavailable")).strip().lower()
        adapter_status = str(raw.get("adapter_status") or ("available" if raw.get("adapter_available", True) else "required")).strip().lower()
        normalized.append({
            **raw,
            "model_id": model_id,
            "provider": _first_text(raw, ["provider", "vendor", "publisher"], "unknown").lower(),
            "vendor": vendor or "unknown",
            "architecture": architecture or "unknown",
            "family": family or "unknown",
            "size_class": size_label,
            "quantization": _first_text(raw, ["quantization", "quant", "quant_method"], "unknown").lower(),
            "context_window": _numeric_or_unknown(raw.get("context_window") or raw.get("context_length") or raw.get("n_ctx")),
            "modalities": sorted(set(_as_list(raw.get("modalities"))) or {"text"}),
            "capabilities": capabilities,
            "backend_status": backend_status or "unknown",
            "adapter_status": adapter_status or "unknown",
            "measured_metrics": {
                "pass_rate": raw.get("pass_rate", measured.get("pass_rate", "unknown")),
                "quality_score": raw.get("quality_score", measured.get("quality_score", "unknown")),
                "json_parse_rate": raw.get("json_parse_rate", measured.get("json_parse_rate", "unknown")),
                "avg_latency_ms": raw.get("avg_latency_ms", measured.get("avg_latency_ms", "unknown")),
                "startup_success_rate": raw.get("startup_success_rate", measured.get("startup_success_rate", "unknown")),
                "readiness_success_rate": raw.get("readiness_success_rate", measured.get("readiness_success_rate", "unknown")),
                "failure_rate": raw.get("failure_rate", measured.get("failure_rate", "unknown")),
                "error_rate": raw.get("error_rate", measured.get("error_rate", "unknown")),
            },
            "source_path": str(raw.get("source_path") or raw.get("canonical_path") or raw.get("path") or ""),
            "gguf_shard_safety": _gguf_shard_safety(raw),
            "host_resource_fit_hints": _host_resource_fit_hints(raw),
            "inventory_source": str(raw.get("inventory_source") or raw.get("source") or "unknown"),
        })
    return sorted(normalized, key=lambda item: (str(item.get("model_id")), str(item.get("vendor")), str(item.get("architecture"))))


def score_candidate_for_role(candidate: Dict[str, Any], role_key: str, *, role_requirements: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    req = dict(role_requirements or ROLE_REQUIREMENTS.get(role_key) or {})
    role_capability_class = str(req.get("capability_class") or "unknown")
    required = set(_as_list(req.get("required_capabilities")))
    capabilities = set(_as_list(candidate.get("capabilities")))
    missing = sorted(required - capabilities)
    required_capability = missing[0] if missing else str(req.get("capability_class") or "")
    required_adapter = _required_adapter_for_candidate(candidate, required_capability)
    degraded_reason = ""
    if str((candidate.get("gguf_shard_safety") or {}).get("state") or "") == "blocked_non_head_shard":
        state = "backend_unavailable"
        degraded_reason = "candidate_is_non_head_gguf_shard"
    elif str(candidate.get("backend_status") or "") not in {"", "available", "ready", "ok"}:
        state = "backend_unavailable"
        degraded_reason = "candidate_backend_not_available"
    elif str(candidate.get("adapter_status") or "") in {"required", "missing", "unavailable"}:
        state = "adapter_required"
        degraded_reason = "candidate_adapter_required"
    elif missing:
        coverage = 0.0 if not required else (len(required & capabilities) / len(required))
        if role_capability_class in DEGRADED_FALLBACK_CAPABILITY_CLASSES and coverage > 0.0:
            state = "degraded_selected"
            degraded_reason = "partial_capability_coverage_for_plan_review_audit_handoff"
        else:
            state = "insufficient_capability"
            degraded_reason = "missing_required_capability"
    else:
        state = "valid_selected"
    measured = candidate.get("measured") if isinstance(candidate.get("measured"), dict) else {}
    pass_rate = _float(candidate.get("pass_rate", measured.get("pass_rate", 0.0)))
    quality = _float(candidate.get("quality_score", measured.get("quality_score", candidate.get("score", 0.0))))
    json_rate = _float(candidate.get("json_parse_rate", measured.get("json_parse_rate", 0.0)))
    latency_ms = max(1.0, _float(candidate.get("avg_latency_ms", measured.get("avg_latency_ms", 2500.0)), 2500.0))
    latency_score = min(1.0, 1000.0 / latency_ms)
    startup_success = _float(candidate.get("startup_success_rate", measured.get("startup_success_rate", 0.0)))
    readiness_success = _float(candidate.get("readiness_success_rate", measured.get("readiness_success_rate", startup_success)))
    failure_rate = max(0.0, min(1.0, _float(candidate.get("failure_rate", measured.get("failure_rate", 0.0)))))
    error_rate = max(0.0, min(1.0, _float(candidate.get("error_rate", measured.get("error_rate", failure_rate)))))
    reliability_score = max(0.0, ((startup_success + readiness_success) / 2.0) - max(failure_rate, error_rate))
    capability_score = 1.0 if not required else (len(required & capabilities) / len(required))
    diversity_score = _float(
        candidate.get("fairness_diversity_score", candidate.get("diversity_score", measured.get("fairness_diversity_score", 0.0)))
    )
    resource_hints = candidate.get("host_resource_fit_hints") if isinstance(candidate.get("host_resource_fit_hints"), dict) else {}
    resource_state = str(resource_hints.get("state") or resource_hints.get("memory_fit") or "unknown").lower()
    resource_fit_penalty = 0.0
    if resource_state in {"tight", "marginal", "warning"}:
        resource_fit_penalty = 0.08
    elif resource_state in {"poor", "no_fit", "insufficient", "blocked"}:
        resource_fit_penalty = 0.18
    metric_keys = ["pass_rate", "quality_score", "json_parse_rate", "avg_latency_ms", "startup_success_rate", "readiness_success_rate", "failure_rate"]
    present_metrics = [key for key in metric_keys if _metric_present(candidate, measured, key)]
    confidence = round(min(1.0, len(present_metrics) / len(metric_keys)), 6)
    if len(present_metrics) < 3:
        confidence = min(confidence, 0.34)
    base_score = round(
        (pass_rate * 0.30)
        + (quality * 0.27)
        + (json_rate * 0.18)
        + (latency_score * 0.08)
        + (capability_score * 0.10)
        + (reliability_score * 0.05)
        + (diversity_score * 0.02)
        - resource_fit_penalty,
        6,
    )
    base_score = max(0.0, base_score)
    score = base_score
    if state == "degraded_selected":
        score = round(base_score * 0.72, 6)
    elif state != "valid_selected":
        score = 0.0
    scoring_rationale = {
        "pass_rate": pass_rate,
        "quality_score": quality,
        "json_parse_rate": json_rate,
        "latency_ms": latency_ms,
        "latency_score": round(latency_score, 6),
        "startup_success_rate": startup_success,
        "readiness_success_rate": readiness_success,
        "failure_rate": failure_rate,
        "error_rate": error_rate,
        "reliability_score": round(reliability_score, 6),
        "capability_coverage_ratio": round(capability_score, 6),
        "resource_fit_penalty": resource_fit_penalty,
        "confidence": confidence,
        "metric_presence": sorted(present_metrics),
        "fairness_diversity_score": diversity_score,
        "base_score": base_score,
        "degraded_score_multiplier": 0.72 if state == "degraded_selected" else 1.0,
        "final_score": score,
        "weights": {
            "pass_rate": 0.30,
            "quality_score": 0.27,
            "json_parse_rate": 0.18,
            "latency_penalty": 0.08,
            "capability_coverage_ratio": 0.10,
            "startup_readiness_failure_rate": 0.05,
            "fairness_diversity": 0.02,
        },
    }
    return {
        "model_id": candidate.get("model_id"),
        "role_key": role_key,
        "selection_state": state,
        "degraded_reason": degraded_reason,
        "required_capability": required_capability if state != "valid_selected" else "",
        "required_adapter": required_adapter if state in {"adapter_required", "blocked_backend_required"} else "",
        "next_actions": _selection_next_actions(state, required_capability=required_capability, required_adapter=required_adapter),
        "evidence": {
            "role_capability_class": role_capability_class,
            "candidate_capabilities": sorted(capabilities),
            "required_capabilities": sorted(required),
            "missing_capabilities": missing,
            "backend_status": str(candidate.get("backend_status") or ""),
            "adapter_status": str(candidate.get("adapter_status") or ""),
            "inventory_source": str(candidate.get("inventory_source") or "unknown"),
            "source_path": str(candidate.get("source_path") or ""),
            "gguf_shard_safety": dict(candidate.get("gguf_shard_safety") or {}),
            "host_resource_fit_hints": dict(candidate.get("host_resource_fit_hints") or {}),
        },
        "score": score,
        "missing_capabilities": missing,
        "vendor": candidate.get("vendor"),
        "provider": candidate.get("provider"),
        "architecture": candidate.get("architecture"),
        "family": candidate.get("family"),
        "size_class": candidate.get("size_class"),
        "quantization": candidate.get("quantization"),
        "context_window": candidate.get("context_window"),
        "modalities": candidate.get("modalities"),
        "scoring_rationale": scoring_rationale,
        "measured": {
            "pass_rate": pass_rate,
            "quality_score": quality,
            "json_parse_rate": json_rate,
            "avg_latency_ms": latency_ms,
            "startup_success_rate": startup_success,
            "readiness_success_rate": readiness_success,
            "failure_rate": failure_rate,
            "error_rate": error_rate,
        },
    }


def _candidate_summary(scored: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "candidate_count": len(scored),
        "valid_count": sum(1 for item in scored if item.get("selection_state") == "valid_selected"),
        "degraded_count": sum(1 for item in scored if item.get("selection_state") == "degraded_selected"),
        "adapter_required_count": sum(1 for item in scored if item.get("selection_state") == "adapter_required"),
        "backend_unavailable_count": sum(1 for item in scored if item.get("selection_state") == "backend_unavailable"),
        "insufficient_capability_count": sum(1 for item in scored if item.get("selection_state") == "insufficient_capability"),
        "top_candidates": [
            {
                "model_id": item.get("model_id"),
                "selection_state": item.get("selection_state"),
                "score": item.get("score"),
                "vendor": item.get("vendor"),
                "architecture": item.get("architecture"),
                "size_class": item.get("size_class"),
            }
            for item in scored[:5]
        ],
    }


def _comparison_set(scored: List[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
    selectable = [item for item in scored if item.get("selection_state") in {"valid_selected", "degraded_selected"}]
    if mode == "fast":
        valid = [item for item in selectable if item.get("selection_state") == "valid_selected"]
        return sorted(valid or selectable, key=_cost_tuple)[:1]
    if mode == "normal":
        return _diverse_candidates(selectable, limit=4)
    return selectable


def _choose_from_scored(scored: List[Dict[str, Any]], mode: str) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    compared = _comparison_set(scored, mode)
    valid = [item for item in compared if item.get("selection_state") == "valid_selected"]
    degraded = [item for item in compared if item.get("selection_state") == "degraded_selected"]
    if mode == "fast" and valid:
        return sorted(valid, key=_cost_tuple)[0], compared
    if valid:
        return sorted(valid, key=lambda item: (-_float(item.get("score")), str(item.get("model_id"))))[0], compared
    if degraded:
        return sorted(degraded, key=lambda item: (-_float(item.get("score")), str(item.get("model_id"))))[0], compared
    return (scored[0] if scored else {}), compared


def _build_composition_plan(role_results: Dict[str, Any], top_n: int) -> Dict[str, Any]:
    limit = int(top_n) if int(top_n) > 0 else 0
    selected: Dict[str, Any] = {}
    used_by_role: Dict[str, str] = {}
    constraints: List[Dict[str, Any]] = []
    for role_key, role_doc in sorted(role_results.items()):
        candidates = [
            item for item in role_doc.get("candidates", [])
            if item.get("selection_state") == "valid_selected"
        ]
        if limit:
            candidates = candidates[:limit]
        chosen = candidates[0] if candidates else {}
        if role_key == "dev.work/qa":
            dev_model = used_by_role.get("dev.work/dev")
            alternatives = [item for item in candidates if str(item.get("model_id") or "") != dev_model]
            if dev_model and alternatives:
                chosen = alternatives[0]
            elif dev_model and chosen and str(chosen.get("model_id") or "") == dev_model:
                constraints.append({
                    "constraint": "QA != Developer",
                    "state": "blocked",
                    "role_key": role_key,
                    "model_id": dev_model,
                    "reason": "no_distinct_valid_qa_candidate",
                })
                chosen = {}
        if chosen:
            selected[role_key] = {
                "model_id": chosen.get("model_id"),
                "score": chosen.get("score"),
                "vendor": chosen.get("vendor"),
                "architecture": chosen.get("architecture"),
                "size_class": chosen.get("size_class"),
            }
            used_by_role[role_key] = str(chosen.get("model_id") or "")
    if "dev.work/dev" in used_by_role and "dev.work/qa" in used_by_role:
        constraints.append({
            "constraint": "QA != Developer",
            "state": "satisfied" if used_by_role["dev.work/dev"] != used_by_role["dev.work/qa"] else "blocked",
        })
    return {
        "apiVersion": "noemaforge.model-role-composition/v1",
        "kind": "RoleCompositionPlan",
        "schema_version": 1,
        "selection_mode": "full_composite",
        "top_n": limit,
        "selected_by_role": selected,
        "hard_constraints": constraints or [{"constraint": "QA != Developer", "state": "not_applicable"}],
    }


def build_role_selection_mapping(
    inventory: Iterable[Dict[str, Any]],
    role_requirements: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    current_epoch_id: str = "",
    proposed_epoch_id: str = "",
    operator_confirmed: bool = False,
    selection_mode: str = "normal",
    composite_top_n: int = 0,
    inventory_source: str = "",
    previous_mapping: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    requirements = role_requirements or ROLE_REQUIREMENTS
    candidates = normalize_inventory_records(inventory)
    selection_mode = normalize_selection_mode(selection_mode)
    role_results: Dict[str, Any] = {}
    for role_key, req in sorted(requirements.items()):
        scored = [score_candidate_for_role(candidate, role_key, role_requirements=req) for candidate in candidates]
        scored = sorted(scored, key=lambda item: (-_float(item.get("score")), str(item.get("model_id"))))
        chosen, compared = _choose_from_scored(scored, selection_mode)
        if not chosen:
            chosen = scored[0] if scored else {
                "selection_state": "backend_unavailable",
                "degraded_reason": "no_inventory_candidates",
                "required_capability": str(req.get("capability_class") or ""),
                "required_adapter": "",
                "next_actions": _selection_next_actions("backend_unavailable"),
                "evidence": {"role_capability_class": str(req.get("capability_class") or ""), "candidate_count": 0},
                "score": 0.0,
                "scoring_rationale": {"final_score": 0.0},
            }
        state = str(chosen.get("selection_state") or "backend_unavailable")
        if state == "valid_selected" and proposed_epoch_id and current_epoch_id and proposed_epoch_id != current_epoch_id and not operator_confirmed:
            state = "operator_confirmation_required"
            chosen = {
                **chosen,
                "selection_state": state,
                "degraded_reason": "operator_confirmation_required_for_epoch_switch",
                "required_capability": "",
                "required_adapter": "",
                "next_actions": _selection_next_actions(state),
            }
        role_results[role_key] = {
            "role_id": role_key,
            "role_key": role_key,
            "stage_capability": str(req.get("capability_class") or "unknown"),
            "requirements": req,
            "selected_model_id": str(chosen.get("model_id") or ""),
            "selection_state": state,
            "degraded_reason": str(chosen.get("degraded_reason") or ""),
            "required_capability": str(chosen.get("required_capability") or ""),
            "required_adapter": str(chosen.get("required_adapter") or ""),
            "score": chosen.get("score", 0.0),
            "next_actions": list(chosen.get("next_actions") or []),
            "evidence": dict(chosen.get("evidence") or {}),
            "scoring_rationale": dict(chosen.get("scoring_rationale") or {}),
            "candidate_summary": _candidate_summary(scored),
            "comparison_set": [item.get("model_id") for item in compared],
            "inventory_source": inventory_source or str((chosen.get("evidence") or {}).get("inventory_source") or "unknown"),
            "chosen": chosen,
            "candidates": scored,
        }
    states = sorted({str(item.get("selection_state")) for item in role_results.values()})
    composition_plan = _build_composition_plan(role_results, composite_top_n) if selection_mode == "full_composite" else None
    selected_mapping = {role: item.get("selected_model_id") for role, item in sorted(role_results.items())}
    previous_selected = {}
    if isinstance(previous_mapping, dict):
        previous_roles = previous_mapping.get("roles") if isinstance(previous_mapping.get("roles"), dict) else previous_mapping
        for role, item in (previous_roles or {}).items():
            if isinstance(item, dict):
                previous_selected[str(role)] = str(item.get("selected_model_id") or item.get("model_id") or "")
            else:
                previous_selected[str(role)] = str(item or "")
    mapping_changed = bool(previous_selected) and previous_selected != selected_mapping
    operator_gate_required = bool(
        (proposed_epoch_id and current_epoch_id and proposed_epoch_id != current_epoch_id and not operator_confirmed)
        or (mapping_changed and not operator_confirmed)
    )
    return {
        "apiVersion": ROLE_SELECTION_API_VERSION,
        "kind": "RoleSelectionMapping",
        "version": RUNTIME_VERSION,
        "created_at": nowz(),
        "schema_version": ROLE_SELECTION_SCHEMA_VERSION,
        "current_epoch_id": current_epoch_id,
        "proposed_epoch_id": proposed_epoch_id,
        "operator_confirmed": bool(operator_confirmed),
        "operator_confirmation_required": operator_gate_required,
        "selection_mode": selection_mode,
        "composite_top_n": int(composite_top_n),
        "selection_states": states,
        "valid_selection_states": sorted(VALID_SELECTION_STATES),
        "inventory_source": inventory_source or "unknown",
        "selected_mapping": selected_mapping,
        "applied_mapping": previous_selected,
        "proposed_mapping": selected_mapping if operator_gate_required or mapping_changed else {},
        "rollback_evidence": {
            "previous_mapping_available": bool(previous_selected),
            "previous_mapping": previous_selected,
            "message": "Keep previous mapping until operator confirms epoch/model composition changes.",
        },
        "fairness_controls": {
            "compare_dimensions": ["size_class", "architecture", "vendor"],
            "hardcoded_vendor_preference": False,
            "capability_class_separation": True,
            "rationale": "Diverse comparison sets include size, architecture and vendor/provider where hard constraints leave alternatives.",
        },
        "composition_plan": composition_plan,
        "roles": role_results,
    }


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
            selection_state = "valid_selected"
            degraded_reason = "runtime_diagnostics_present" if diagnostics else ""
            refreshed_role_mapping[role] = {
                "role_key": role,
                "model_id": chosen.get("model_id") or chosen.get("logical_model_id"),
                "logical_model_id": chosen.get("logical_model_id") or chosen.get("model_id"),
                "score": chosen.get("score"),
                "pass_rate": chosen.get("pass_rate"),
                "json_parse_rate": chosen.get("json_parse_rate"),
                "quality_score": chosen.get("quality_score"),
                "selection_status": classification,
                "selection_state": selection_state,
                "degraded_reason": degraded_reason,
                "required_capability": "",
                "required_adapter": "",
                "next_actions": _selection_next_actions(selection_state),
                "evidence": {
                    "source_role_mapping": "reused_selection_artifact",
                    "classification": classification,
                    "diagnostics": diagnostics,
                    "candidate_selection_status": chosen.get("selection_status"),
                },
                "scoring_rationale": {
                    "source": "preserved_measurement",
                    "score": chosen.get("score"),
                    "pass_rate": chosen.get("pass_rate"),
                    "quality_score": chosen.get("quality_score"),
                    "json_parse_rate": chosen.get("json_parse_rate"),
                },
                "source_selection_version": decision.get("version"),
            }
        role_classifications[role] = {
            "role_key": role,
            "classification": classification,
            "reasons": sorted(set(reasons)),
            "candidate_model_id": chosen.get("model_id") if isinstance(chosen, dict) else None,
            "selection_state": refreshed_role_mapping.get(role, {}).get("selection_state") or ("blocked_missing_worker" if classification == "needs_recompute" else "insufficient_capability"),
            "degraded_reason": refreshed_role_mapping.get(role, {}).get("degraded_reason") or ("role_requires_recompute" if classification == "needs_recompute" else ""),
            "required_capability": refreshed_role_mapping.get(role, {}).get("required_capability") or "",
            "required_adapter": refreshed_role_mapping.get(role, {}).get("required_adapter") or "",
            "next_actions": refreshed_role_mapping.get(role, {}).get("next_actions") or _selection_next_actions("blocked_missing_worker" if classification == "needs_recompute" else "insufficient_capability"),
            "evidence": refreshed_role_mapping.get(role, {}).get("evidence") or {"classification": classification, "reasons": sorted(set(reasons))},
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
        "selection_state": "degraded_selected" if acceptance_state == "degraded_selected" else "valid_selected",
        "valid_selection_states": sorted(VALID_SELECTION_STATES),
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
    if normalized in {"development_plan", "dev_plan", "implementation_plan", "patch_plan", "mutation_plan", "validation_plan", "release_readiness", "rollback_plan"}:
        return "dev_plan"
    if normalized in {"development_execute", "dev_execute", "implementation_execute", "patch_execute", "patch_generation_or_adapter_required", "test_execution_or_adapter_required"}:
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
    if terms & {"status", "state", "current", "repo", "goal", "health", "safe", "orient", "intake", "chat"}:
        return "text_status"
    if terms & {"documentation", "docs", "doc", "changelog", "wiki"}:
        return "text_documentation"
    if terms & {"audit", "test", "testing", "qa", "validation", "smoke", "fact", "inventory", "optimization", "performance", "budget", "analysis", "check"}:
        return "audit"
    if terms & {"plan", "planning", "outline", "research", "source", "architecture", "clarification", "release", "pipeline", "graph", "relation", "entity", "provenance", "drafting", "draft", "issue", "decomposition"}:
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
    if any(term in terms for term in {"dev", "development", "implementation", "code", "refactor", "patch", "module"}):
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
            selection_state = str(item.get("selection_state") or "valid_selected")
            return {
                "ok": True,
                "diagnostics": diagnostics,
                "requested_role": requested,
                "resolved_role": role,
                "fallback_used": fallback_used,
                "fallback_policy": "explicit" if fallback_used and role in EXPLICIT_ROLE_FALLBACKS.get(requested, []) else ("generic_text_stage" if fallback_used else "exact"),
                "model_id": item.get("model_id"),
                "worker_status": "registered_from_refreshed_selection",
                "selection_state": selection_state,
                "degraded_reason": str(item.get("degraded_reason") or ""),
                "required_capability": str(item.get("required_capability") or ""),
                "required_adapter": str(item.get("required_adapter") or ""),
                "next_actions": list(item.get("next_actions") or []),
                "evidence": dict(item.get("evidence") or {}),
                "scoring_rationale": dict(item.get("scoring_rationale") or {}),
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
        "selection_state": "blocked_missing_worker",
        "degraded_reason": missing,
        "required_capability": "",
        "required_adapter": "",
        "next_actions": _selection_next_actions("blocked_missing_worker"),
        "evidence": {"requested_role": requested, "needs_recompute": list(mapping_doc.get("needs_recompute", []) or [])},
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
