#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/role_tournament.py
# Zone: first-start/model-staffing
# Purpose: Run role-aware lightweight tournaments: top-K candidates per role, not a global top-K.
# Callers: noemaforge tournament, firstboot_orchestrator.
# Inputs: model-inventory.json, role-catalog.yaml, generated eval packs, ModelStore, llama.cpp runtime.
# Outputs: role-eligibility-matrix.json, role-tournament-results.json, role-shortlists/*.json, role-candidate-map.json, synthetic scorecards.
# Safety notes: starts at most one GGUF backend at a time and stops it before moving to the next candidate.
# === End NoemaForge File Header ===

import argparse
import atexit
import datetime as dt
import http.client
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

try:
    import vault_inventory
    import dataset_inventory
except Exception:  # pragma: no cover
    sys.path.insert(0, "/opt/noemaforge/src")
    import vault_inventory  # type: ignore
    import dataset_inventory  # type: ignore

try:
    import runtime_safety  # type: ignore
except Exception:  # pragma: no cover
    runtime_safety = None  # type: ignore

try:
    import model_inventory_normalize  # type: ignore
except Exception:  # pragma: no cover
    model_inventory_normalize = None  # type: ignore

DEFAULT_INVENTORY = "/var/lib/noemaforge/bootstrap/model-inventory.json"
DEFAULT_ROLE_CATALOG = "/opt/noemaforge/configs/role-catalog.yaml"
DEFAULT_PACK_ROOT = "/var/lib/noemaforge/eval-packs/first-start-light"
DEFAULT_STATE_DIR = "/var/lib/noemaforge/bootstrap"
DEFAULT_MODELSTORE = "/var/lib/modelstore"
DEFAULT_SCORECARDS = "/var/lib/noemaforge/model_scorecards"
SCORECARD_DEVICE_ALIASES = {"cuda": "gpu", "nvidia": "gpu", "cpu": "cpu", "gpu": "gpu"}

MANDATORY_CORE_ROLES = [
    "operator.admin/administrator",
    "system.guard/surgeon",
    "dev.work/solution_architect",
    "writing.story/writer",
]


UNTRUSTED_DEFAULT_PATTERN = re.compile(
    r"(uncensored|aggressive|jailbreak|roleplay[-_ ]?uncensored|abliterated|nsfw|no[-_ ]?guard|no[-_ ]?censor)",
    flags=re.I,
)
_ACTIVE_BACKENDS: set[str] = set()
_CLEANUP_INSTALLED = False


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, default)).strip())
    except Exception:
        return default


def _selection_timeout_defaults(selection_mode: str) -> Tuple[int, int]:
    mode = normalize_selection_mode(selection_mode) if "normalize_selection_mode" in globals() else str(selection_mode or "normal")
    per_model = {"fast": 120, "normal": 300, "full": 600, "full_composite": 600}.get(mode, 300)
    total = {"fast": 600, "normal": 1800, "full": 7200, "full_composite": 7200}.get(mode, 1800)
    return per_model, total


def _model_default_block_reason(model: Dict[str, Any]) -> str:
    """Block risky/untrusted naming patterns from default first-start.

    Operators can override explicitly with NOEMAFORGE_TOURNAMENT_INCLUDE_UNVERIFIED=1.
    This does not delete or quarantine files; it only excludes them from automatic
    default staffing, matching the pre-alpha safety policy.
    """
    if _env_bool("NOEMAFORGE_TOURNAMENT_INCLUDE_UNVERIFIED", False):
        return ""
    fields = [
        model.get("model_id"),
        model.get("display_name"),
        model.get("source_path"),
        model.get("canonical_path"),
    ]
    text = "\n".join(str(x or "") for x in fields)
    m = UNTRUSTED_DEFAULT_PATTERN.search(text)
    if m:
        return f"default_safety_filter:{m.group(1).lower()}"
    return ""


def _append_jsonl(path: str, rec: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def emit_progress(state_dir: str, **payload: Any) -> None:
    rec = {"ts": now(), **payload}
    try:
        write_json(os.path.join(state_dir, "role-tournament-progress.json"), rec)
        _append_jsonl(os.path.join(state_dir, "role-tournament-progress.jsonl"), rec)
    except Exception:
        pass


def persist_model_run_records(state_dir: str, records: List[Dict[str, Any]]) -> None:
    try:
        write_json(os.path.join(state_dir, "model-run-records.json"), records)
    except Exception:
        pass

RUNTIME_FAILURE_REASONS = {
    "socket_timeout",
    "warmup_failed",
    "warmup_timeout",
    "backend_loading",
    "empty_ready_probe",
    "model_timeout",
    "per_model_timeout",
    "total_timeout",
    "task_timeout",
    "process_error",
    "oom",
    "invalid_gguf",
    "bad_shard",
    "systemctl_start_failed",
    "stage_failed",
    "runtime_safety_blocked",
}


def _is_runtime_failure_reason(reason: str) -> bool:
    text = str(reason or "").lower()
    return any(token in text for token in RUNTIME_FAILURE_REASONS) or any(token in text for token in ("timeout", "failed", "error", "crash", "exception", "traceback", "http_5", "http_503"))


def _load_model_health_registry(state_dir: str) -> Dict[str, Any]:
    path = os.path.join(state_dir, "model-health-registry.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {"apiVersion": "noemaforge.modelhealth/v1", "kind": "ModelHealthRegistry", "updated_at": now(), "models": {}}


def _write_model_health_registry(state_dir: str, registry: Dict[str, Any]) -> None:
    registry["updated_at"] = now()
    write_json(os.path.join(state_dir, "model-health-registry.json"), registry)
    failed = []
    for mid, rec in sorted((registry.get("models") or {}).items()):
        if rec.get("exclude_from_selection") or rec.get("health_state") == "failed_runtime" or rec.get("health_state") == "failed_any_reason":
            failed.append({
                "model_id": mid,
                "logical_model_id": rec.get("logical_model_id"),
                "health_state": rec.get("health_state"),
                "failure_reason": rec.get("failure_reason"),
                "exclude_from_further_checks": bool(rec.get("exclude_from_further_checks")),
                "exclude_from_selection": bool(rec.get("exclude_from_selection")),
            })
    write_json(os.path.join(state_dir, "model-exclusion-list.json"), {"apiVersion": "noemaforge.modelhealth/v1", "kind": "ModelExclusionList", "updated_at": now(), "models": failed})
    write_json(os.path.join(state_dir, "model-failure-report.json"), {"apiVersion": "noemaforge.modelhealth/v1", "kind": "ModelFailureReport", "updated_at": now(), "failures": failed})


def _mark_model_failed(state_dir: str, registry: Dict[str, Any], *, model_id: str, logical_model_id: str, reason: str, roles_invalidated: Optional[List[str]] = None, strict: bool = False) -> Dict[str, Any]:
    rec = dict((registry.setdefault("models", {}).get(model_id)) or {})
    rec.update({
        "model_id": model_id,
        "logical_model_id": logical_model_id,
        "health_state": "failed_runtime" if not strict else "failed_any_reason",
        "failure_reason": reason,
        "first_failed_at": rec.get("first_failed_at") or now(),
        "last_failed_at": now(),
        "exclude_from_further_checks": True,
        "exclude_from_selection": True,
        "invalidated_roles": sorted(set((rec.get("invalidated_roles") or []) + (roles_invalidated or []))),
        "retry_policy": {"default_retry": False, "allowed_with_flag": "--retry-failed-models"},
    })
    registry["models"][model_id] = rec
    _write_model_health_registry(state_dir, registry)
    emit_progress(state_dir, phase="model_health_registry_write", model_id=model_id, logical_model_id=logical_model_id, health_state=rec["health_state"], reason=reason, invalidated_role_count=len(rec.get("invalidated_roles") or []), score="n/a")
    return rec


def _mark_model_partial_valid(state_dir: str, registry: Dict[str, Any], *, model_id: str, logical_model_id: str, reason: str, retained_roles: Optional[List[str]] = None) -> Dict[str, Any]:
    """Record partial runtime exhaustion without excluding already valid role scores.

    In patched7 this is the key distinction: a model that starts and produces
    valid role scores but then runs out of per-model budget is not a bad model.
    It should stop further checks for this run, but its measured successful
    role results remain eligible for selection.
    """
    rec = dict((registry.setdefault("models", {}).get(model_id)) or {})
    rec.update({
        "model_id": model_id,
        "logical_model_id": logical_model_id,
        "health_state": "partial_valid_budget_exhausted",
        "failure_reason": reason,
        "first_failed_at": rec.get("first_failed_at") or now(),
        "last_failed_at": now(),
        "exclude_from_further_checks": True,
        "exclude_from_selection": False,
        "retained_roles": sorted(set((rec.get("retained_roles") or []) + (retained_roles or []))),
        "invalidated_roles": rec.get("invalidated_roles") or [],
        "retry_policy": {"default_retry": False, "allowed_with_flag": "--retry-failed-models"},
    })
    registry["models"][model_id] = rec
    _write_model_health_registry(state_dir, registry)
    emit_progress(state_dir, phase="model_partial_valid", model_id=model_id, logical_model_id=logical_model_id, health_state=rec["health_state"], reason=reason, retained_role_count=len(rec.get("retained_roles") or []), exclude_from_selection=False, score="n/a")
    return rec


def _valid_roles_for_model(role_results: Dict[str, Any], model_id: str) -> List[str]:
    roles: List[str] = []
    for role_key, role_rec in role_results.items():
        for result in role_rec.get("results") or []:
            if str(result.get("model_id") or "") == model_id and str(result.get("selection_status") or "") == "valid_measured" and float(result.get("score") or 0.0) > 0.0:
                roles.append(role_key)
                break
    return sorted(set(roles))


def _order_roles_for_model(role_keys: Sequence[str]) -> List[str]:
    # Mandatory core roles are evaluated first so normal mode can staff the
    # public alpha kernel before spending time on optional roles.
    prio = {rk: i for i, rk in enumerate(MANDATORY_CORE_ROLES)}
    return sorted([str(r) for r in role_keys], key=lambda rk: (prio.get(rk, 1000), rk))


def _is_infrastructure_start_failure(reason: str) -> bool:
    text = str(reason or "").lower()
    return text.startswith("systemctl_start_failed:5") or "unit not found" in text or "no such file or directory" in text and "systemctl" in text


def _write_runtime_infrastructure_failure(state_dir: str, *, model_id: str, logical_model_id: str, reason: str) -> None:
    doc = {
        "apiVersion": "noemaforge.runtimeinfra/v1",
        "kind": "RuntimeInfrastructureFailure",
        "updated_at": now(),
        "model_id": model_id,
        "logical_model_id": logical_model_id,
        "reason": reason,
        "message": "Model backend infrastructure failed before evaluation. Models were not marked as bad.",
        "checks": [
            "systemctl cat noemaforge-llama@.service",
            "systemctl status noemaforge-llm-gateway.service noemaforge-llama@main.service",
            "ls -lah /opt/noemaforge/bin/llama-server /opt/noemaforge/bin/llama-server-cpu /opt/noemaforge/bin/llama-server-cuda",
        ],
    }
    write_json(os.path.join(state_dir, "runtime-infrastructure-failure.json"), doc)
    emit_progress(state_dir, phase="runtime_infrastructure_failed", model_id=model_id, logical_model_id=logical_model_id, reason=reason, score="n/a")


def _is_model_excluded(registry: Dict[str, Any], model_id: str) -> bool:
    rec = (registry.get("models") or {}).get(model_id) or {}
    return bool(rec.get("exclude_from_further_checks") or rec.get("exclude_from_selection"))


def _invalidate_model_results(role_results: Dict[str, Any], *, model_id: str, reason: str) -> List[str]:
    invalidated: List[str] = []
    for role_key, role_rec in role_results.items():
        for result in role_rec.get("results") or []:
            if str(result.get("model_id") or "") == model_id and str(result.get("selection_status") or "") == "valid_measured":
                result["previous_selection_status"] = result.get("selection_status")
                result["selection_status"] = "invalidated_model_failure"
                result["score"] = 0.0
                result["invalidated_by"] = reason
                invalidated.append(role_key)
    return invalidated


def _result_has_runtime_error(result: Dict[str, Any]) -> str:
    if str(result.get("selection_status") or "") == "invalid_backend_calls":
        return "invalid_backend_calls"
    for tr in result.get("task_results") or []:
        err = str(tr.get("error") or "").strip()
        if err and _is_runtime_failure_reason(err):
            return err[:160]
    return ""


def _pids_for_backend(modelstore_id: str) -> List[int]:
    sock = f"/run/noemaforge/llm/backends/{modelstore_id}.sock"
    try:
        cp = subprocess.run(["pgrep", "-f", sock], text=True, capture_output=True, timeout=5)
    except Exception:
        return []
    out: List[int] = []
    for line in (cp.stdout or "").splitlines():
        try:
            pid = int(line.strip())
        except Exception:
            continue
        if pid > 1 and pid != os.getpid():
            out.append(pid)
    return out


def _kill_backend_processes(modelstore_id: str, sig: int) -> None:
    for pid in _pids_for_backend(modelstore_id):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass
        except Exception:
            pass


def cleanup_active_backends() -> None:
    for backend_id in list(_ACTIVE_BACKENDS):
        try:
            stop_gguf_backend(backend_id)
        except Exception:
            pass


def install_cleanup_handlers() -> None:
    global _CLEANUP_INSTALLED
    if _CLEANUP_INSTALLED:
        return
    _CLEANUP_INSTALLED = True
    atexit.register(cleanup_active_backends)

    def _handler(signum: int, frame: Any) -> None:  # pragma: no cover - signal path
        cleanup_active_backends()
        raise SystemExit(128 + int(signum))

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def safe_id(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.@-]+", "_", str(raw or "")).strip("._-")[:160] or "model"


def role_file_id(role_key: str) -> str:
    # 0.31.13.alpha-patched1 fix: use the same naming as dataset_inventory.role_safe().
    return safe_id(role_key.replace("/", "__").replace(".", "_"))


def load_yaml(path: str) -> Dict[str, Any]:
    if yaml is None or not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        obj = yaml.safe_load(f) or {}
    return obj if isinstance(obj, dict) else {}


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    return obj if isinstance(obj, dict) else {}


def write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def role_defs(catalog: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    defaults = dict(catalog.get("defaults") or {})
    roles = dict(catalog.get("roles") or {})
    out: Dict[str, Dict[str, Any]] = {}
    for key, val in roles.items():
        rec = dict(defaults)
        if isinstance(val, dict):
            rec.update(val)
        rec["role_key"] = str(key)
        rec["top_k"] = int(rec.get("top_k") or (catalog.get("selection") or {}).get("top_k_per_role") or 8)
        rec["tasks_per_model"] = int(rec.get("tasks_per_model") or (catalog.get("selection") or {}).get("tasks_per_role") or 10)
        out[str(key)] = rec
    return out


def cap_match(model: Dict[str, Any], role: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    caps = set(str(x) for x in (model.get("capabilities") or []))
    required = [str(x) for x in (role.get("required_capabilities") or [])]
    optional = [str(x) for x in (role.get("optional_capabilities") or [])]
    missing = [x for x in required if x not in caps]
    matched = [x for x in required + optional if x in caps]
    return len(missing) == 0, matched, missing


def runtime_state(model: Dict[str, Any]) -> Dict[str, Any]:
    probe = dict(model.get("runtime_probe") or {})
    fmt = str(model.get("artifact_format") or "")
    if fmt == "gguf":
        path = os.environ.get("NOEMAFORGE_LLAMA_SERVER", "/opt/noemaforge/bin/llama-server")
        source = str(model.get("source_path") or model.get("canonical_path") or "")
        safe = True
        reason = "ok"
        if runtime_safety is not None:
            safe, reason, _ = runtime_safety.validate_artifact_path(source)
        probe.update({"runtime_family": "llama.cpp", "available": os.path.exists(path) and os.access(path, os.X_OK) and safe, "probe": path, "runtime_safety": reason})
    available = bool(probe.get("available"))
    implemented = fmt == "gguf" and str(probe.get("runtime_family") or model.get("runtime_family") or "") == "llama.cpp"
    return {"available": available, "implemented": implemented, "probe": probe}


def normalize_inventory_for_scoring(inventory: Dict[str, Any]) -> Dict[str, Any]:
    if model_inventory_normalize is None:
        return inventory
    return model_inventory_normalize.normalize_inventory_models(inventory, require_complete=False)


def build_eligibility(inventory: Dict[str, Any], roles: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    inventory = normalize_inventory_for_scoring(inventory)
    matrix: Dict[str, Any] = {"apiVersion": "noemaforge.roles/v1", "kind": "RoleEligibilityMatrix", "updated_at": now(), "roles": {}, "models": {}}
    models = list(inventory.get("models") or [])
    for role_key, rdef in roles.items():
        role_rec = {"eligible": 0, "runnable_now": 0, "runtime_missing": 0, "runner_not_implemented": 0, "models": []}
        for m in models:
            ok, matched, missing = cap_match(m, rdef)
            if not ok:
                continue
            rt = runtime_state(m)
            runnable = bool(rt["available"] and rt["implemented"] and m.get("artifact_valid", True))
            reason = "runnable" if runnable else ("runtime_missing" if not rt["available"] else "runner_not_implemented")
            if runnable:
                role_rec["runnable_now"] += 1
            elif not rt["available"]:
                role_rec["runtime_missing"] += 1
            else:
                role_rec["runner_not_implemented"] += 1
            role_rec["eligible"] += 1
            role_rec["models"].append({
                "model_id": m.get("model_id"),
                "display_name": m.get("display_name"),
                "artifact_format": m.get("artifact_format"),
                "runtime_family": m.get("runtime_family"),
                "source_path": m.get("source_path") or m.get("canonical_path"),
                "matched_capabilities": matched,
                "missing_capabilities": missing,
                "runnable_now": runnable,
                "reason": reason,
            })
        matrix["roles"][role_key] = role_rec
    for m in models:
        eligible_roles = []
        for role_key, rdef in roles.items():
            ok, matched, missing = cap_match(m, rdef)
            if ok:
                eligible_roles.append(role_key)
        matrix["models"][str(m.get("model_id") or "")] = {"eligible_roles": eligible_roles, "capabilities": m.get("capabilities") or [], "runtime": runtime_state(m)}
    return matrix


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, unix_socket_path: str, timeout: float = 30.0):
        super().__init__("localhost", timeout=timeout)
        self.unix_socket_path = unix_socket_path
    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.unix_socket_path)


def _looks_like_loading(value: str) -> bool:
    text = str(value or "").lower()
    return any(token in text for token in ("loading model", "model is loading", "please wait", "server loading"))


def backend_chat(sock: str, prompt: str, model: str = "local", timeout: float = 60.0) -> Tuple[bool, str, float, str]:
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are NoemaForge first-start evaluator. Follow the task exactly. Prefer concise structured answers."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": _env_int("NOEMAFORGE_TOURNAMENT_MAX_TOKENS", 96),
    }).encode("utf-8")
    t0 = time.time()
    conn = UnixHTTPConnection(sock, timeout=timeout)
    try:
        conn.request("POST", "/v1/chat/completions", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        ms = (time.time() - t0) * 1000.0
        if resp.status >= 400:
            return False, "", ms, f"http_{resp.status}:{raw[:300]}"
        if _looks_like_loading(raw):
            return False, "", ms, f"backend_loading:{raw[:300]}"
        obj = json.loads(raw)
        content = str(((obj.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        if _looks_like_loading(content):
            return False, "", ms, f"backend_loading:{content[:300]}"
        if not content.strip():
            return False, "", ms, "empty_response"
        return True, content, ms, ""
    except Exception as e:
        return False, "", (time.time() - t0) * 1000.0, repr(e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def try_json(text: str) -> bool:
    s = text.strip()
    candidates = [s]
    m = re.search(r"\{.*\}", s, flags=re.S)
    if m:
        candidates.append(m.group(0))
    for c in candidates:
        try:
            json.loads(c)
            return True
        except Exception:
            continue
    return False


def score_task(task: Dict[str, Any], ok: bool, response: str, latency_ms: float, error: str) -> Dict[str, Any]:
    expect_json = bool(task.get("expect_json"))
    contains = [str(x).lower() for x in (task.get("contains_any") or [])]
    response = response or ""
    resp_l = response.lower()
    nonempty = bool(response.strip())

    # 0.31.13.alpha-patched1 fix: no semantic/JSON/contains credit for failed or empty backend calls.
    if not ok or not nonempty:
        json_ok = False
        contains_ok = False
        passed = False
        quality = 0.0
    else:
        json_ok = try_json(response) if expect_json else True
        contains_ok = True if not contains else any(x.lower() in resp_l for x in contains)
        passed = bool(json_ok and contains_ok)
        quality = 0.25  # backend call succeeded
        quality += 0.25  # non-empty answer
        if json_ok:
            quality += 0.25
        if contains_ok:
            quality += 0.25

    return {
        "task_id": task.get("id"),
        "ok": ok,
        "passed": passed,
        "json_ok": json_ok,
        "contains_ok": contains_ok,
        "latency_ms": round(latency_ms, 1),
        "error": error,
        "response_preview": response[:500],
        "quality": round(quality, 3),
    }


def load_tasks(pack_root: str, role_key: str, limit: int) -> List[Dict[str, Any]]:
    path = os.path.join(pack_root, f"{role_file_id(role_key)}.jsonl")
    tasks: List[Dict[str, Any]] = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    tasks.append(json.loads(line))
                except Exception:
                    continue
    return tasks[:max(1, int(limit))]


def write_modelstore_manifest(modelstore_root: str, model: Dict[str, Any], model_id: str) -> Dict[str, Any]:
    models_dir = Path(modelstore_root) / "models"
    target = models_dir / model_id
    target.mkdir(parents=True, exist_ok=True)
    source = str(model.get("source_path") or model.get("canonical_path") or "")
    if not source:
        raise RuntimeError(f"model {model.get('model_id')} has no source_path")
    if runtime_safety is not None:
        ok_safe, reason, meta = runtime_safety.validate_artifact_path(source)
        if not ok_safe:
            raise RuntimeError(f"runtime safety rejected artifact for {model.get('model_id')}: {reason} {meta}")
    link = target / "model.gguf"
    if link.exists() or link.is_symlink():
        link.unlink()
    os.symlink(source, str(link))
    manifest = {
        "apiVersion": "noemaforge.model/v1",
        "kind": "ModelArtifact",
        "model_id": model_id,
        "logical_model_id": model.get("model_id"),
        "format": model.get("artifact_format"),
        "artifact_path": source,
        "source_path": source,
        "all_artifacts": model.get("all_artifacts") or [source],
        "capabilities": model.get("capabilities") or [],
        "runtime_family": model.get("runtime_family"),
        "trust": "unknown",
        "notes": "staged by role-aware first-start tournament v0.31.13.alpha-patched1",
    }
    if yaml is not None:
        with open(target / "manifest.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(manifest, f, sort_keys=False, allow_unicode=True)
    else:
        with open(target / "manifest.yaml", "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    return {"model_id": model_id, "manifest": str(target / "manifest.yaml"), "source": source}


def wait_socket(sock: str, timeout_sec: int = 90) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if os.path.exists(sock) and stat_is_socket(sock):
            return True
        time.sleep(1)
    return False


def stat_is_socket(path: str) -> bool:
    try:
        import stat
        return stat.S_ISSOCK(os.stat(path).st_mode)
    except Exception:
        return False


def systemctl(*args: str) -> int:
    try:
        return subprocess.call(["systemctl", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return 127


def start_gguf_backend(modelstore_id: str) -> Tuple[bool, str, str]:
    sock = f"/run/noemaforge/llm/backends/{modelstore_id}.sock"
    if runtime_safety is not None:
        ok_safe, reason, meta = runtime_safety.validate_modelstore_backend(DEFAULT_MODELSTORE, modelstore_id)
        if not ok_safe:
            return False, sock, f"runtime_safety_blocked:{reason}:{meta}"
    try:
        os.makedirs(os.path.dirname(sock), exist_ok=True)
        try:
            os.unlink(sock)
        except FileNotFoundError:
            pass
        except Exception:
            pass
        unit = f"noemaforge-llama@{modelstore_id}.service"
        rc = systemctl("start", unit)
        if rc != 0:
            return False, sock, f"systemctl_start_failed:{rc}"
        if not wait_socket(sock, timeout_sec=_env_int("NOEMAFORGE_TOURNAMENT_SOCKET_TIMEOUT", 90)):
            return False, sock, "socket_timeout"
        _ACTIVE_BACKENDS.add(modelstore_id)
        return True, sock, ""
    except Exception as e:
        return False, sock, repr(e)


def warmup_backend(sock: str, modelstore_id: str) -> Tuple[bool, Dict[str, Any]]:
    timeout_sec = _env_int("NOEMAFORGE_TOURNAMENT_WARMUP_TIMEOUT", 90)
    interval = float(os.environ.get("NOEMAFORGE_TOURNAMENT_WARMUP_INTERVAL", "3"))
    deadline = time.time() + timeout_sec
    attempts = 0
    last_error = ""
    last_preview = ""
    started_at = time.time()
    while time.time() < deadline:
        attempts += 1
        ok, content, ms, err = backend_chat(
            sock,
            "Warm-up check. Reply with exactly READY when the model is available.",
            model=modelstore_id,
            timeout=float(_env_int("NOEMAFORGE_TOURNAMENT_WARMUP_CHAT_TIMEOUT", 15)),
        )
        if ok and re.search(r"\bREADY\b", content.strip(), flags=re.I):
            return True, {
                "attempts": attempts,
                "duration_sec": round(time.time() - started_at, 1),
                "last_latency_ms": round(ms, 1),
                "response_preview": content[:160],
                "ready_probe": True,
            }
        last_error = err or ("warmup_not_ready_response" if content.strip() else "warmup_empty_response")
        last_preview = content[:160]
        time.sleep(interval)
    return False, {
        "attempts": attempts,
        "duration_sec": round(time.time() - started_at, 1),
        "last_error": last_error,
        "last_response_preview": last_preview,
    }


def stop_gguf_backend(modelstore_id: str) -> None:
    unit = f"noemaforge-llama@{modelstore_id}.service"
    systemctl("stop", unit)
    deadline = time.time() + _env_int("NOEMAFORGE_TOURNAMENT_STOP_TIMEOUT", 20)
    while time.time() < deadline:
        if not _pids_for_backend(modelstore_id):
            break
        time.sleep(1)
    if _pids_for_backend(modelstore_id):
        systemctl("kill", "--signal=TERM", unit)
        _kill_backend_processes(modelstore_id, signal.SIGTERM)
        time.sleep(3)
    if _pids_for_backend(modelstore_id):
        systemctl("kill", "--signal=KILL", unit)
        _kill_backend_processes(modelstore_id, signal.SIGKILL)
    _ACTIVE_BACKENDS.discard(modelstore_id)
    try:
        os.unlink(f"/run/noemaforge/llm/backends/{modelstore_id}.sock")
    except Exception:
        pass


def run_role_tasks_for_model(model: Dict[str, Any], modelstore_id: str, role_key: str, role_def: Dict[str, Any], pack_root: str, sock: str, *, deadline: Optional[float] = None, state_dir: str = DEFAULT_STATE_DIR) -> Dict[str, Any]:
    tasks = load_tasks(pack_root, role_key, int(role_def.get("tasks_per_model") or 10))
    task_results: List[Dict[str, Any]] = []
    if not tasks:
        return {
            "model_id": modelstore_id,
            "logical_model_id": model.get("model_id"),
            "display_name": model.get("display_name"),
            "role_key": role_key,
            "tasks": 0,
            "score": 0.0,
            "selection_status": "no_eval_tasks",
            "valid_backend_rate": 0.0,
            "nonempty_rate": 0.0,
            "pass_rate": 0.0,
            "json_parse_rate": 0.0,
            "quality_score": 0.0,
            "avg_latency_ms": 0.0,
            "task_results": [],
        }
    for task_idx, task in enumerate(tasks, start=1):
        if deadline is not None and time.time() >= deadline:
            task_results.append(score_task(task, False, "", 0.0, "per_model_timeout_before_task"))
            break
        prompt = str(task.get("prompt") or task.get("query") or "")
        task_timeout = float(_env_int("NOEMAFORGE_TOURNAMENT_TASK_TIMEOUT", 30))
        if deadline is not None:
            remaining = max(1.0, deadline - time.time())
            task_timeout = min(task_timeout, remaining)
        emit_progress(state_dir, phase="task", model_id=modelstore_id, logical_model_id=model.get("model_id"), role_key=role_key, task_index=task_idx, total_tasks=len(tasks), deadline_remaining_sec=round(max(0.0, (deadline or time.time()) - time.time()), 1) if deadline else None, score="pending", score_status="pending")
        ok, content, ms, err = backend_chat(sock, prompt, model=modelstore_id, timeout=task_timeout)
        task_results.append(score_task(task, ok, content, ms, err))
    n = max(1, len(task_results))
    ok_rate = sum(1 for x in task_results if x.get("ok")) / n
    nonempty_rate = sum(1 for x in task_results if str(x.get("response_preview") or "").strip()) / n
    pass_rate = sum(1 for x in task_results if x.get("passed")) / n
    json_rate = sum(1 for x in task_results if x.get("json_ok")) / n
    quality = sum(float(x.get("quality") or 0.0) for x in task_results) / n
    avg_lat = sum(float(x.get("latency_ms") or 0.0) for x in task_results) / n
    # Latency is a tie-breaker, not a primary rank. Cap contribution to avoid size-as-ranking.
    latency_component = max(0.0, min(1.0, 1.0 - (avg_lat / 120000.0)))
    if ok_rate <= 0.0 or nonempty_rate <= 0.0:
        score = 0.0
        selection_status = "invalid_backend_calls"
    elif pass_rate <= 0.0:
        # No positive score for candidates that never pass a role task.
        # They remain measured for diagnostics but are excluded from the selected pool.
        score = 0.0
        selection_status = "measured_no_passes"
    else:
        score = 0.45 * pass_rate + 0.20 * json_rate + 0.25 * quality + 0.10 * latency_component
        selection_status = "valid_measured"
    return {
        "model_id": modelstore_id,
        "logical_model_id": model.get("model_id"),
        "display_name": model.get("display_name"),
        "role_key": role_key,
        "tasks": len(task_results),
        "score": round(score, 4),
        "selection_status": selection_status,
        "valid_backend_rate": round(ok_rate, 4),
        "nonempty_rate": round(nonempty_rate, 4),
        "pass_rate": round(pass_rate, 4),
        "json_parse_rate": round(json_rate, 4),
        "quality_score": round(quality, 4),
        "avg_latency_ms": round(avg_lat, 1),
        "task_results": task_results,
    }


def write_scorecard(scorecards_dir: str, result: Dict[str, Any]) -> None:
    role_key = str(result.get("role_key") or "")
    if "/" in role_key:
        stream, role = role_key.split("/", 1)
    else:
        stream, role = "unknown", role_key
    model_id = safe_id(str(result.get("model_id") or ""))
    runtime_device = SCORECARD_DEVICE_ALIASES.get(
        str(result.get("runtime_device") or os.environ.get("NOEMAFORGE_SCORECARD_DEVICE") or "").strip().lower(),
        "unspecified",
    )
    device_root = os.path.join(scorecards_dir, runtime_device) if runtime_device in {"cpu", "gpu"} else scorecards_dir
    sid = stream.replace("/", "_")
    rid = role.replace("/", "_")
    path = os.path.join(device_root, model_id, f"{sid}__{rid}__llm.json")
    card = {
        "schema_version": "noemaforge.model_scorecard/v1",
        "created_at": now(),
        "source": "role_tournament_v0.31.13.alpha-patched1",
        "model_id": model_id,
        "runtime_device": runtime_device,
        "stream_id": stream,
        "role": role,
        "cap": "llm",
        "suite": "first_start_light_10",
        "overall_score": result.get("score"),
        "quality_score": result.get("quality_score"),
        "pass_rate": result.get("pass_rate"),
        "json_parse_rate": result.get("json_parse_rate"),
        "avg_latency_ms": result.get("avg_latency_ms"),
        "tasks": result.get("tasks"),
    }
    write_json(path, card)




def normalize_selection_mode(value: str) -> str:
    value = str(value or "normal").strip().lower().replace("-", "_")
    aliases = {"full_composite": "full_composite", "composite": "full_composite", "fullcomposite": "full_composite"}
    value = aliases.get(value, value)
    if value not in {"fast", "normal", "full", "full_composite"}:
        return "normal"
    return value


def role_has_valid_candidate(role_results: Dict[str, Any], role_key: str) -> bool:
    for rec in role_results.get(role_key, {}).get("results") or []:
        if str(rec.get("selection_status") or "") == "valid_measured" and float(rec.get("score") or 0.0) > 0.0:
            return True
    return False


def all_roles_have_fast_candidate(role_results: Dict[str, Any]) -> bool:
    return all(role_has_valid_candidate(role_results, role_key) for role_key in role_results)


def role_valid_candidate_count(role_results: Dict[str, Any], role_key: str) -> int:
    return sum(1 for rec in (role_results.get(role_key, {}).get("results") or []) if rec.get("selection_status") == "valid_measured" and float(rec.get("score") or 0.0) > 0.0)


def role_required_count(role_results: Dict[str, Any], role_key: str) -> int:
    return max(1, int(role_results.get(role_key, {}).get("top_k") or 1))


def role_has_required_candidates(role_results: Dict[str, Any], role_key: str) -> bool:
    return role_valid_candidate_count(role_results, role_key) >= role_required_count(role_results, role_key)


def all_roles_have_required_candidates(role_results: Dict[str, Any]) -> bool:
    return bool(role_results) and all(role_has_required_candidates(role_results, role_key) for role_key in role_results)


def _role_family(role_key: str) -> str:
    text = str(role_key or "").lower().replace("_", ".")
    if "qa" in text or "quality" in text or "test" in text:
        return "qa"
    if "dev" in text or "developer" in text or "code" in text:
        return "developer"
    if "arch" in text or "architect" in text:
        return "architecture"
    return "other"


def _violates_composition_constraints(combo: Dict[str, str]) -> List[str]:
    reasons: List[str] = []
    dev_models = {mid for rk, mid in combo.items() if mid and _role_family(rk) == "developer"}
    qa_models = {mid for rk, mid in combo.items() if mid and _role_family(rk) == "qa"}
    if dev_models and qa_models and dev_models.intersection(qa_models):
        reasons.append("QA != Developer")
    return reasons


def build_composition_plan(role_candidate_map: Dict[str, Any], *, top_n: int = 0, max_enum: int = 100000) -> Dict[str, Any]:
    """Build a bounded composition plan for --full_composite.

    top_n=0 means no top limit. 0.31.13.alpha-patched1 never materializes
    partial/empty compositions and applies the easy hard constraint QA != Developer
    when enough role metadata is available.
    """
    roles = role_candidate_map.get("roles") or {}
    pools: Dict[str, List[str]] = {}
    missing_roles: List[str] = []
    for role_key, rec in roles.items():
        selected = [str(x.get("model_id") or "") for x in (rec.get("selected") or []) if str(x.get("model_id") or "")]
        if top_n and top_n > 0:
            selected = selected[:top_n]
        pools[role_key] = selected
        if not selected:
            missing_roles.append(role_key)
    hard_constraints = ["QA != Developer", "single_active_llm_runtime", "no_invalid_backend_calls", "no_non_head_gguf_shards"]
    total = 0 if missing_roles else 1
    if not missing_roles:
        for vals in pools.values():
            total *= len(vals)
    plan: Dict[str, Any] = {
        "apiVersion": "noemaforge.model-selection/v1",
        "kind": "CompositeSelectionPlan",
        "created_at": now(),
        "top_n": int(top_n),
        "top_n_unlimited": int(top_n) == 0,
        "roles": {k: {"candidate_count": len(v), "candidates": v, "role_family": _role_family(k)} for k, v in pools.items()},
        "missing_candidate_roles": missing_roles,
        "estimated_compositions": total,
        "materialized": False,
        "max_materialized": max_enum,
        "hard_constraints": hard_constraints,
        "constraint_filter": {"applied": ["QA != Developer"], "rejected": 0},
    }
    if missing_roles:
        plan["deferred_reason"] = "one_or_more_roles_have_no_valid_measured_candidates"
        plan["next"] = ["review role-candidate-map.json", "rerun with a less strict scope or add models for missing roles"]
        return plan
    if total <= max_enum:
        role_keys = sorted(pools)
        combos: List[Dict[str, str]] = []
        rejected = 0
        def rec(idx: int, cur: Dict[str, str]) -> None:
            nonlocal rejected
            if len(combos) >= max_enum:
                return
            if idx >= len(role_keys):
                reasons = _violates_composition_constraints(cur)
                if reasons:
                    rejected += 1
                    return
                combos.append(dict(cur)); return
            rk = role_keys[idx]
            for mid in pools.get(rk) or []:
                cur[rk] = mid
                rec(idx + 1, cur)
                cur.pop(rk, None)
        rec(0, {})
        plan["materialized"] = True
        plan["compositions"] = combos
        plan["constraint_filter"]["rejected"] = rejected
        plan["valid_compositions"] = len(combos)
        if not combos:
            plan["deferred_reason"] = "all_compositions_rejected_by_hard_constraints"
    else:
        plan["deferred_reason"] = "composition_count_exceeds_safe_materialization_limit"
        plan["next"] = ["rerun with --full_composite N where N is small, e.g. 3", "increase NOEMAFORGE_COMPOSITE_MAX_ENUM only after reviewing estimate"]
    return plan

def run_tournament(
    inventory: Dict[str, Any],
    catalog: Dict[str, Any],
    *,
    pack_root: str = DEFAULT_PACK_ROOT,
    state_dir: str = DEFAULT_STATE_DIR,
    modelstore_root: str = DEFAULT_MODELSTORE,
    scorecards_dir: str = DEFAULT_SCORECARDS,
    runtime_mode: str = "probe",
    role_filter: str = "",
    selection_mode: str = "normal",
    composite_top_n: int = -1,
) -> Dict[str, Any]:
    inventory = normalize_inventory_for_scoring(inventory)
    selection_mode = normalize_selection_mode(selection_mode)
    if runtime_mode == "run":
        install_cleanup_handlers()
    default_per_model_timeout, default_total_timeout = _selection_timeout_defaults(selection_mode)
    per_model_timeout = _env_int("NOEMAFORGE_TOURNAMENT_PER_MODEL_TIMEOUT", default_per_model_timeout)
    total_timeout = _env_int("NOEMAFORGE_TOURNAMENT_TOTAL_TIMEOUT", default_total_timeout)
    tournament_started_at = time.time()
    total_deadline = tournament_started_at + max(1, total_timeout)
    roles_all = role_defs(catalog)
    roles = {k: v for k, v in roles_all.items() if not role_filter or k == role_filter}
    if selection_mode == "fast":
        for rec in roles.values():
            rec["top_k"] = 1
    elif selection_mode == "normal":
        for rec in roles.values():
            rec["top_k"] = 2
    matrix = build_eligibility(inventory, roles)
    os.makedirs(state_dir, exist_ok=True)
    # Reset streaming progress artifacts at the beginning of each run.
    stale_files = ["role-tournament-progress.json", "role-tournament-progress.jsonl", "model-run-records.json", "role-candidate-map.filtered.json"]
    if _env_bool("NOEMAFORGE_TOURNAMENT_CLEAR_MODEL_HEALTH", False):
        stale_files.extend(["model-health-registry.json", "model-exclusion-list.json", "model-failure-report.json"])
    for stale_name in stale_files:
        try:
            os.unlink(os.path.join(state_dir, stale_name))
        except FileNotFoundError:
            pass
        except Exception:
            pass
    write_json(os.path.join(state_dir, "role-eligibility-matrix.json"), matrix)
    emit_progress(state_dir, phase="start", selection_mode=selection_mode, runtime_mode=runtime_mode, per_model_timeout_sec=per_model_timeout, total_timeout_sec=total_timeout, roles=len(roles), runnable_models=sum(1 for _mid, _mrec in (matrix.get("models") or {}).items() if (_mrec.get("runtime") or {}).get("available") and (_mrec.get("runtime") or {}).get("implemented") and _mrec.get("eligible_roles")))

    role_results: Dict[str, Any] = {}
    model_run_records: List[Dict[str, Any]] = []
    model_health_registry = _load_model_health_registry(state_dir)
    retry_failed_models = _env_bool("NOEMAFORGE_TOURNAMENT_RETRY_FAILED_MODELS", False)
    strict_any_fail = _env_bool("NOEMAFORGE_TOURNAMENT_STRICT_ANY_FAIL", False)
    exclude_failed_from_selection = _env_bool("NOEMAFORGE_TOURNAMENT_EXCLUDE_FAILED_FROM_SELECTION", True)
    for role_key, rdef in roles.items():
        role_results[role_key] = {"role_key": role_key, "top_k": int(rdef.get("top_k") or 8), "tasks_per_model": int(rdef.get("tasks_per_model") or 10), "selection_mode": selection_mode, "results": [], "selected": [], "not_selected": [], "blocked": []}

    if runtime_mode == "probe":
        for role_key, rec in matrix.get("roles", {}).items():
            role_results[role_key]["blocked"] = [m for m in rec.get("models") or [] if not m.get("runnable_now")]
            role_results[role_key]["probe_only"] = True
        return finalize_results(inventory, role_results, model_run_records, state_dir, selection_mode=selection_mode, composite_top_n=composite_top_n)

    # Evaluate model once, then run every eligible role-specific pack while it is loaded.
    models_by_id = {str(m.get("model_id") or ""): m for m in inventory.get("models") or []}
    runnable_ids = []
    for mid, mrec in matrix.get("models", {}).items():
        rt = mrec.get("runtime") or {}
        if rt.get("available") and rt.get("implemented") and mrec.get("eligible_roles"):
            runnable_ids.append(mid)
    # Stable order from inventory, not by size. This ensures size is not a rank signal.
    ordered = [str(m.get("model_id") or "") for m in inventory.get("models") or [] if str(m.get("model_id") or "") in runnable_ids]
    for model_index, mid in enumerate(ordered, start=1):
        if time.time() >= total_deadline:
            emit_progress(state_dir, phase="total_timeout", selection_mode=selection_mode, processed_models=len(model_run_records), total_models=len(ordered))
            break
        model = models_by_id.get(mid) or {}
        fmt = str(model.get("artifact_format") or "")
        mstore_id = safe_id(mid)
        rec: Dict[str, Any] = {"model_id": mstore_id, "logical_model_id": mid, "runtime_family": model.get("runtime_family"), "artifact_format": fmt, "started": False, "roles": [], "model_index": model_index, "total_models": len(ordered)}
        if _is_model_excluded(model_health_registry, mstore_id) and not retry_failed_models:
            rec["reason"] = "previously_failed_runtime"
            rec["health"] = (model_health_registry.get("models") or {}).get(mstore_id)
            model_run_records.append(rec)
            persist_model_run_records(state_dir, model_run_records)
            emit_progress(state_dir, phase="model_skip_failed", model_id=mstore_id, logical_model_id=mid, reason=rec["reason"], score="n/a")
            continue
        model_deadline = min(total_deadline, time.time() + max(1, per_model_timeout))
        rec["deadline_sec"] = int(max(1, model_deadline - time.time()))
        block_reason = _model_default_block_reason(model)
        if block_reason:
            rec["reason"] = "default_safety_filter"
            rec["quarantine"] = {"default_excluded": True, "reason": block_reason, "override_env": "NOEMAFORGE_TOURNAMENT_INCLUDE_UNVERIFIED=1"}
            model_run_records.append(rec)
            persist_model_run_records(state_dir, model_run_records)
            emit_progress(state_dir, phase="model_blocked", model_id=mstore_id, logical_model_id=mid, reason=block_reason, model_index=model_index, total_models=len(ordered), score="n/a")
            continue
        emit_progress(state_dir, phase="model_start", model_id=mstore_id, logical_model_id=mid, model_index=model_index, total_models=len(ordered), per_model_timeout_sec=int(max(1, model_deadline - time.time())))
        if fmt != "gguf":
            rec["reason"] = "runner_not_implemented_for_first_start"
            model_run_records.append(rec)
            persist_model_run_records(state_dir, model_run_records)
            emit_progress(state_dir, phase="model_skipped", model_id=mstore_id, logical_model_id=mid, reason=rec["reason"])
            continue
        try:
            write_modelstore_manifest(modelstore_root, model, mstore_id)
        except Exception as e:
            rec["reason"] = f"stage_failed:{e!r}"
            _mark_model_failed(state_dir, model_health_registry, model_id=mstore_id, logical_model_id=mid, reason=rec["reason"])
            model_run_records.append(rec)
            persist_model_run_records(state_dir, model_run_records)
            emit_progress(state_dir, phase="model_failed", model_id=mstore_id, logical_model_id=mid, reason=rec["reason"], score="n/a")
            continue
        ok, sock, err = start_gguf_backend(mstore_id)
        if not ok:
            rec["reason"] = err
            if _is_infrastructure_start_failure(err):
                rec["infrastructure_failure"] = True
                model_run_records.append(rec)
                persist_model_run_records(state_dir, model_run_records)
                _write_runtime_infrastructure_failure(state_dir, model_id=mstore_id, logical_model_id=mid, reason=err)
                emit_progress(state_dir, phase="model_failed_infrastructure", model_id=mstore_id, logical_model_id=mid, reason=err, score="n/a")
                stop_gguf_backend(mstore_id)
                break
            _mark_model_failed(state_dir, model_health_registry, model_id=mstore_id, logical_model_id=mid, reason=err)
            model_run_records.append(rec)
            persist_model_run_records(state_dir, model_run_records)
            emit_progress(state_dir, phase="model_failed", model_id=mstore_id, logical_model_id=mid, reason=err, score="n/a")
            stop_gguf_backend(mstore_id)
            continue
        rec["started"] = True
        rec["socket"] = sock
        emit_progress(state_dir, phase="warmup_start", model_id=mstore_id, logical_model_id=mid, socket=sock, deadline_remaining_sec=round(max(0.0, model_deadline - time.time()), 1), score="n/a")
        warm_ok, warm_meta = warmup_backend(sock, mstore_id)
        rec["warmup"] = warm_meta
        if not warm_ok:
            rec["reason"] = "warmup_failed"
            _mark_model_failed(state_dir, model_health_registry, model_id=mstore_id, logical_model_id=mid, reason="warmup_failed")
            model_run_records.append(rec)
            persist_model_run_records(state_dir, model_run_records)
            emit_progress(state_dir, phase="warmup_failed", model_id=mstore_id, logical_model_id=mid, warmup=warm_meta, score="n/a")
            stop_gguf_backend(mstore_id)
            continue
        try:
            for role_key in _order_roles_for_model(matrix.get("models", {}).get(mid, {}).get("eligible_roles") or []):
                if time.time() >= model_deadline:
                    rec["reason"] = "per_model_timeout"
                    retained = _valid_roles_for_model(role_results, mstore_id)
                    if retained:
                        rec["partial_valid"] = True
                        rec["retained_roles"] = retained
                        _mark_model_partial_valid(state_dir, model_health_registry, model_id=mstore_id, logical_model_id=mid, reason="partial_valid_budget_exhausted", retained_roles=retained)
                        emit_progress(state_dir, phase="model_timeout", model_id=mstore_id, logical_model_id=mid, role_key=role_key, elapsed_sec=round(time.time() - (model_deadline - per_model_timeout), 1), retained_role_count=len(retained), score="n/a")
                    else:
                        _mark_model_failed(state_dir, model_health_registry, model_id=mstore_id, logical_model_id=mid, reason=rec["reason"], roles_invalidated=[])
                        emit_progress(state_dir, phase="model_timeout", model_id=mstore_id, logical_model_id=mid, role_key=role_key, elapsed_sec=round(time.time() - (model_deadline - per_model_timeout), 1), score="n/a")
                        emit_progress(state_dir, phase="model_disqualified", model_id=mstore_id, logical_model_id=mid, reason=rec["reason"], invalidated_role_count=0, exclude_from_further_checks=True, score="n/a")
                    break
                if time.time() >= total_deadline:
                    rec["reason"] = "total_timeout"
                    retained = _valid_roles_for_model(role_results, mstore_id)
                    if retained:
                        rec["partial_valid"] = True
                        rec["retained_roles"] = retained
                        _mark_model_partial_valid(state_dir, model_health_registry, model_id=mstore_id, logical_model_id=mid, reason="partial_valid_total_timeout", retained_roles=retained)
                    else:
                        _mark_model_failed(state_dir, model_health_registry, model_id=mstore_id, logical_model_id=mid, reason=rec["reason"], roles_invalidated=[])
                    emit_progress(state_dir, phase="total_timeout", model_id=mstore_id, logical_model_id=mid, role_key=role_key, score="n/a")
                    break
                if role_key not in roles:
                    continue
                if selection_mode == "fast" and role_has_valid_candidate(role_results, role_key):
                    continue
                if selection_mode == "normal" and role_has_required_candidates(role_results, role_key):
                    continue
                rdef = roles[role_key]
                emit_progress(state_dir, phase="role_eval_start", model_id=mstore_id, logical_model_id=mid, role_key=role_key, selected_count=role_valid_candidate_count(role_results, role_key), required_count=role_required_count(role_results, role_key), deadline_remaining_sec=round(max(0.0, model_deadline - time.time()), 1))
                result = run_role_tasks_for_model(model, mstore_id, role_key, rdef, pack_root, sock, deadline=model_deadline, state_dir=state_dir)
                role_results[role_key]["results"].append(result)
                rec["roles"].append({"role_key": role_key, "score": result.get("score"), "selection_status": result.get("selection_status")})
                write_scorecard(scorecards_dir, result)
                persist_model_run_records(state_dir, model_run_records + [rec])
                emit_progress(state_dir, phase="role_eval_done", model_id=mstore_id, logical_model_id=mid, role_key=role_key, score=result.get("score"), selection_status=result.get("selection_status"), pass_rate=result.get("pass_rate"))
                runtime_failure = _result_has_runtime_error(result)
                quality_failure = str(result.get("selection_status") or "") == "measured_no_passes"
                if runtime_failure or (strict_any_fail and quality_failure):
                    rec["reason"] = runtime_failure or "strict_any_fail:measured_no_passes"
                    retained = _valid_roles_for_model(role_results, mstore_id)
                    # If this model has already produced valid scores, keep them and
                    # stop further checks. Do not globally exclude the model from
                    # selection merely because a later role exhausted budget or failed.
                    if runtime_failure and retained and str(result.get("selection_status") or "") == "valid_measured":
                        rec["partial_valid"] = True
                        rec["retained_roles"] = retained
                        _mark_model_partial_valid(state_dir, model_health_registry, model_id=mstore_id, logical_model_id=mid, reason=f"partial_valid_runtime_event:{runtime_failure}", retained_roles=retained)
                        emit_progress(state_dir, phase="model_partial_valid", model_id=mstore_id, logical_model_id=mid, role_key=role_key, reason=rec["reason"], retained_role_count=len(retained), exclude_from_selection=False, score="n/a")
                    else:
                        invalidated = [] if retained else _invalidate_model_results(role_results, model_id=mstore_id, reason=rec["reason"])
                        if retained:
                            _mark_model_partial_valid(state_dir, model_health_registry, model_id=mstore_id, logical_model_id=mid, reason=f"partial_valid_runtime_event:{runtime_failure}", retained_roles=retained)
                            emit_progress(state_dir, phase="model_partial_valid", model_id=mstore_id, logical_model_id=mid, role_key=role_key, reason=rec["reason"], retained_role_count=len(retained), exclude_from_selection=False, score="n/a")
                        else:
                            _mark_model_failed(state_dir, model_health_registry, model_id=mstore_id, logical_model_id=mid, reason=rec["reason"], roles_invalidated=invalidated, strict=bool(strict_any_fail and quality_failure and not runtime_failure))
                            emit_progress(state_dir, phase="model_disqualified", model_id=mstore_id, logical_model_id=mid, role_key=role_key, reason=rec["reason"], invalidated_role_count=len(invalidated), exclude_from_further_checks=True, score="n/a")
                    break
        finally:
            stop_gguf_backend(mstore_id)
        rec.setdefault("finished_at", now())
        rec.setdefault("duration_sec", round(max(0.0, per_model_timeout - max(0.0, model_deadline - time.time())), 1))
        model_run_records.append(rec)
        persist_model_run_records(state_dir, model_run_records)
        emit_progress(state_dir, phase="model_done", model_id=mstore_id, logical_model_id=mid, reason=rec.get("reason", "completed"), roles_evaluated=len(rec.get("roles") or []))
        if selection_mode == "fast" and all_roles_have_fast_candidate(role_results):
            break
        if selection_mode == "normal" and all_roles_have_required_candidates(role_results):
            break
    return finalize_results(inventory, role_results, model_run_records, state_dir, selection_mode=selection_mode, composite_top_n=composite_top_n)


def finalize_results(inventory: Dict[str, Any], role_results: Dict[str, Any], model_run_records: List[Dict[str, Any]], state_dir: str, *, selection_mode: str = "normal", composite_top_n: int = -1) -> Dict[str, Any]:
    shortlists_dir = os.path.join(state_dir, "role-shortlists")
    os.makedirs(shortlists_dir, exist_ok=True)
    health_registry = _load_model_health_registry(state_dir)
    excluded_models = {mid for mid, rec in (health_registry.get("models") or {}).items() if rec.get("exclude_from_selection")}
    role_candidate_map: Dict[str, Any] = {"apiVersion": "noemaforge.roles/v1", "kind": "RoleCandidateMap", "updated_at": now(), "roles": {}, "unique_selected_model_ids": [], "health_registry": os.path.join(state_dir, "model-health-registry.json"), "excluded_model_count": len(excluded_models), "selection_diagnostics": {"no_candidates_reason": None}}
    unique: List[str] = []
    for role_key, rec in role_results.items():
        results = sorted(rec.get("results") or [], key=lambda x: (-float(x.get("score") or 0.0), float(x.get("avg_latency_ms") or 1e12), str(x.get("model_id") or "")))
        measured = [x for x in results if x.get("selection_status") == "valid_measured" and float(x.get("score") or 0.0) > 0.0 and str(x.get("model_id") or "") not in excluded_models]
        ranking_pool = measured if measured else []
        top_k = int(rec.get("top_k") or 8)
        selected = ranking_pool[:top_k]
        selected_ids = set(str(x.get("model_id") or "") for x in selected)
        not_selected = [x for x in results if str(x.get("model_id") or "") not in selected_ids]
        rec["selection_pool"] = "valid_measured_only" if measured else "none_valid_measured_candidates"
        rec["selected"] = selected
        rec["not_selected"] = not_selected
        rec["selected_count"] = len(selected)
        for x in selected:
            mid = str(x.get("model_id") or "")
            if mid and mid not in unique:
                unique.append(mid)
        role_candidate_map["roles"][role_key] = {"selected": selected, "chosen": selected[0] if selected else None, "top_k": top_k, "selected_count": len(selected), "selection_pool": rec.get("selection_pool")}
        write_json(os.path.join(shortlists_dir, f"{role_file_id(role_key)}.json"), role_candidate_map["roles"][role_key])
    role_candidate_map["unique_selected_model_ids"] = unique
    if not unique:
        infra_failure_path = os.path.join(state_dir, "runtime-infrastructure-failure.json")
        if os.path.exists(infra_failure_path):
            role_candidate_map["selection_diagnostics"]["no_candidates_reason"] = "runtime_infrastructure_failed"
        elif excluded_models:
            role_candidate_map["selection_diagnostics"]["no_candidates_reason"] = "no_candidates_after_failed_model_filter"
        else:
            role_candidate_map["selection_diagnostics"]["no_candidates_reason"] = "no_candidates_after_thresholds"
    composite_plan = None
    if selection_mode == "full_composite":
        n = int(composite_top_n) if int(composite_top_n) >= 0 else 0
        max_enum = int(os.environ.get("NOEMAFORGE_COMPOSITE_MAX_ENUM", "100000"))
        composite_plan = build_composition_plan(role_candidate_map, top_n=n, max_enum=max_enum)
        write_json(os.path.join(state_dir, "composite-selection-plan.json"), composite_plan)
    result_doc = {
        "apiVersion": "noemaforge.tournament/v1",
        "kind": "RoleTournamentResults",
        "updated_at": now(),
        "principle": "top_k is per role, never global",
        "selection_mode": selection_mode,
        "mode_contract": {
            "fast": "first valid measured candidate per role; no composite test",
            "normal": "at least two valid candidates per role when available; best is chosen; no composite test",
            "full": "evaluate all runnable models; best per role is chosen; no composite test",
            "full_composite": "evaluate all runnable models and produce composition plan from top N candidates",
        },
        "inventory_summary": inventory.get("summary") or {},
        "runtime_mode": "run" if model_run_records else "probe",
        "model_run_records": model_run_records,
        "roles": role_results,
        "role_shortlists_dir": shortlists_dir,
        "role_candidate_map": os.path.join(state_dir, "role-candidate-map.json"),
        "composite_selection_plan": os.path.join(state_dir, "composite-selection-plan.json") if composite_plan else None,
    }
    write_json(os.path.join(state_dir, "role-candidate-map.json"), role_candidate_map)
    write_json(os.path.join(state_dir, "role-candidate-map.filtered.json"), role_candidate_map)
    emit_progress(state_dir, phase="candidate_map_filtered", excluded_model_count=len(excluded_models), selected_models=len(unique), score="n/a")
    write_json(os.path.join(state_dir, "model-run-records.json"), model_run_records)
    write_json(os.path.join(state_dir, "role-tournament-results.json"), result_doc)
    emit_progress(state_dir, phase="complete", selected_models=len(unique), roles=len(role_results), selection_mode=selection_mode)
    # Compatibility union list: not authoritative, but useful for old scripts.
    with open(os.path.join(state_dir, "noemaforge-firstboot-shortlist.role-aware.txt"), "w", encoding="utf-8") as f:
        f.write("# Union of role-aware selected ModelStore IDs. Authoritative data is role-candidate-map.json.\n")
        for mid in unique:
            f.write(mid + "\n")
    return result_doc


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="NoemaForge role-aware first-start tournament")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("eligibility")
    p.add_argument("--inventory", default=DEFAULT_INVENTORY)
    p.add_argument("--role-catalog", default=DEFAULT_ROLE_CATALOG)
    p.add_argument("--json-out", default=os.path.join(DEFAULT_STATE_DIR, "role-eligibility-matrix.json"))
    p = sub.add_parser("run")
    p.add_argument("--inventory", default=DEFAULT_INVENTORY)
    p.add_argument("--role-catalog", default=DEFAULT_ROLE_CATALOG)
    p.add_argument("--pack-root", default=DEFAULT_PACK_ROOT)
    p.add_argument("--state-dir", default=DEFAULT_STATE_DIR)
    p.add_argument("--modelstore-root", default=DEFAULT_MODELSTORE)
    p.add_argument("--scorecards-dir", default=DEFAULT_SCORECARDS)
    p.add_argument("--runtime-mode", choices=["probe", "run"], default="probe")
    p.add_argument("--role", default="")
    p.add_argument("--selection-mode", choices=["fast", "normal", "full", "full_composite"], default="normal")
    p.add_argument("--composite-top-n", type=int, default=-1)
    p.add_argument("--per-model-timeout", type=int, default=0, help="Override NOEMAFORGE_TOURNAMENT_PER_MODEL_TIMEOUT for this run")
    p.add_argument("--total-timeout", type=int, default=0, help="Override NOEMAFORGE_TOURNAMENT_TOTAL_TIMEOUT for this run")
    p.add_argument("--include-unverified", action="store_true", help="Include models blocked by default name-based safety filter")
    p.add_argument("--retry-failed-models", action="store_true", help="Retry models previously marked failed in model-health-registry.json")
    p.add_argument("--clear-model-health", action="store_true", help="Clear persisted failed-model registry before this run")
    p.add_argument("--strict-any-fail", action="store_true", help="Treat any negative role result as a global model disqualification")
    p.add_argument("--exclude-failed-from-selection", action="store_true", default=True, help="Default: exclude failed/disqualified models from selected candidates")
    p.add_argument("--allow-failed-selection", action="store_true", help="Compatibility escape hatch; do not exclude failed models from selected pool")
    args = ap.parse_args(argv)
    if getattr(args, "per_model_timeout", 0):
        os.environ["NOEMAFORGE_TOURNAMENT_PER_MODEL_TIMEOUT"] = str(args.per_model_timeout)
    if getattr(args, "total_timeout", 0):
        os.environ["NOEMAFORGE_TOURNAMENT_TOTAL_TIMEOUT"] = str(args.total_timeout)
    if getattr(args, "include_unverified", False):
        os.environ["NOEMAFORGE_TOURNAMENT_INCLUDE_UNVERIFIED"] = "1"
    if getattr(args, "retry_failed_models", False):
        os.environ["NOEMAFORGE_TOURNAMENT_RETRY_FAILED_MODELS"] = "1"
    if getattr(args, "clear_model_health", False):
        os.environ["NOEMAFORGE_TOURNAMENT_CLEAR_MODEL_HEALTH"] = "1"
    if getattr(args, "strict_any_fail", False):
        os.environ["NOEMAFORGE_TOURNAMENT_STRICT_ANY_FAIL"] = "1"
    if getattr(args, "allow_failed_selection", False):
        os.environ["NOEMAFORGE_TOURNAMENT_EXCLUDE_FAILED_FROM_SELECTION"] = "0"
    inv = load_json(args.inventory)
    catalog = load_yaml(args.role_catalog)
    if args.cmd == "eligibility":
        matrix = build_eligibility(inv, role_defs(catalog))
        write_json(args.json_out, matrix)
        print(json.dumps({"ok": True, "eligibility": args.json_out, "roles": len(matrix.get("roles") or {})}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "run":
        doc = run_tournament(inv, catalog, pack_root=args.pack_root, state_dir=args.state_dir, modelstore_root=args.modelstore_root, scorecards_dir=args.scorecards_dir, runtime_mode=args.runtime_mode, role_filter=args.role, selection_mode=args.selection_mode, composite_top_n=args.composite_top_n)
        print(json.dumps({"ok": True, "results": os.path.join(args.state_dir, "role-tournament-results.json"), "roles": len(doc.get("roles") or {})}, ensure_ascii=False, indent=2))
        # In actual run mode fail early when no role got any selected model. Specialized runtime-missing roles can remain empty;
        # the critical check is at least one LLM/admin/dev role selected.
        if args.runtime_mode == "run":
            selected_total = sum(len((r.get("selected") or [])) for r in (doc.get("roles") or {}).values())
            return 0 if selected_total > 0 else 73
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
