#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/firstboot_orchestrator.py
# Zone: spinal/first-start
# Purpose: Role-aware first-boot orchestration: inventory all models, build datasets/eval packs, run per-role light tournaments, stage winners, and create first epoch policy.
# Callers: tools/prep/noemaforge-firstboot-from-share.sh, sudo noemaforge first-start.
# Inputs: share/Vault roots, role-catalog.yaml, local ModelStore, NoemaForge configs.
# Outputs: model-inventory.json, role-tournament-results.json, role-candidate-map.json, prestart request, optional epoch switch.
# Safety notes:
#   - Top-K is per role, not global.
#   - Tournament starts at most one GGUF backend at a time.
#   - Size is only a runtime safety gate, never a ranking metric.
# === End NoemaForge File Header ===

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

import firstboot_status
import model_installer_plan
import model_registry
import prestart
import vault_inventory
import dataset_inventory
import role_tournament
import runtime_safety
import model_inventory_normalize
import model_profiles
import pre_release_uat_fix_runtime
from noemaforge_version import RUNTIME_VERSION
from platform_paths import DEFAULT_PATHS as _pp

NOEMAFORGE_ROOT = str(_pp.root)
DEFAULT_POLICY = str(_pp.root / "configs/firstboot-policy.yaml")
DEFAULT_ROLE_CATALOG = str(_pp.root / "configs/role-catalog.yaml")
DEFAULT_STATUS = str(_pp.data_root / "bootstrap/firstboot-status.json")
DEFAULT_EVENTS = str(_pp.data_root / "bootstrap/firstboot-events.jsonl")
STATE_DIR = str(_pp.data_root / "bootstrap")
_MAIN_ALIAS_LOCK_STALE_GRACE_SECONDS = 300


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    return obj if isinstance(obj, dict) else {}


def _write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _nowz() -> str:
    return firstboot_status._nowz()


def _pid_is_active(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "posix":
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _main_alias_lock_status(lock_dir: Path) -> Dict[str, Any]:
    if not lock_dir.exists():
        return {"stale": True, "reason": "lock_missing"}
    if not lock_dir.is_dir():
        return {"stale": False, "reason": "lock_path_not_directory", "lock_dir": str(lock_dir)}

    owner_path = lock_dir / "owner.json"
    try:
        lock_age = max(0.0, time.time() - lock_dir.stat().st_mtime)
    except OSError:
        lock_age = 0.0

    owner: Dict[str, Any] = {}
    if owner_path.is_file():
        try:
            parsed = json.loads(owner_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                owner = parsed
        except Exception as exc:
            return {
                "stale": lock_age > _MAIN_ALIAS_LOCK_STALE_GRACE_SECONDS,
                "reason": "owner_metadata_unreadable",
                "error": str(exc),
                "lock_age_seconds": lock_age,
            }
    else:
        return {
            "stale": lock_age > _MAIN_ALIAS_LOCK_STALE_GRACE_SECONDS,
            "reason": "owner_metadata_missing",
            "lock_age_seconds": lock_age,
        }

    hostname = str(owner.get("hostname") or "")
    current_hostname = socket.gethostname()
    if hostname and hostname != current_hostname:
        return {"stale": False, "reason": "owner_host_unverifiable", "owner": owner}

    try:
        pid = int(owner.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if _pid_is_active(pid):
        return {"stale": False, "reason": "owner_pid_active", "owner": owner}
    return {"stale": True, "reason": "owner_pid_inactive", "owner": owner}


def _acquire_main_alias_lock(lock_dir: Path) -> Tuple[bool, Dict[str, Any]]:
    owner = {"pid": os.getpid(), "hostname": socket.gethostname(), "created_at": _nowz()}
    for _attempt in range(2):
        try:
            lock_dir.mkdir()
            try:
                (lock_dir / "owner.json").write_text(
                    json.dumps(owner, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            except Exception as exc:
                shutil.rmtree(str(lock_dir), ignore_errors=True)
                return False, {"reason": "owner_metadata_write_failed", "error": str(exc)}
            return True, {"owner": owner}
        except FileExistsError:
            status = _main_alias_lock_status(lock_dir)
            if not status.get("stale"):
                return False, status
            try:
                stale_dir = lock_dir.with_name(f"{lock_dir.name}.stale.{os.getpid()}")
                shutil.rmtree(str(stale_dir), ignore_errors=True)
                os.rename(str(lock_dir), str(stale_dir))
                shutil.rmtree(str(stale_dir), ignore_errors=True)
            except FileNotFoundError:
                pass
            except Exception as exc:
                status["cleanup_error"] = str(exc)
                return False, status
    return False, {"reason": "lock_reacquire_race", "stale": False}


def _normalize_selection_mode(value: str) -> str:
    value = str(value or "normal").strip().lower().replace("-", "_")
    aliases = {"composite": "full_composite", "fullcomposite": "full_composite"}
    value = aliases.get(value, value)
    return value if value in {"fast", "normal", "full", "full_composite"} else "normal"


def normalize_launcher_paths(*, share_root: str, vault_root: str = "", shortlist_file: str = "") -> Dict[str, Any]:
    return runtime_safety.normalize_launcher_paths(share_root=share_root, vault_root=vault_root, shortlist_file=shortlist_file)


def _selection_mode_contract(mode: str, composite_top_n: int) -> Dict[str, Any]:
    return {
        "mode": mode,
        "fast": "first valid measured candidate per role is accepted; QA != Developer; no composite testing",
        "normal": "at least two valid candidates are retained per role when available; best measured candidate is chosen; QA != Developer; no composite testing",
        "full": "all runnable models are evaluated; best measured candidate is chosen per role; QA != Developer; no composite testing",
        "full_composite": "all runnable models are evaluated, then role composition plan is built from top N candidates; N=0 means no top-limit before safety materialization cap",
        "composite_top_n": int(composite_top_n),
        "hard_constraints": ["QA != Developer", "single_active_llm_runtime", "no_invalid_backend_calls", "no_non_head_gguf_shards"],
    }


def _write_selection_artifacts(*, state_dir: str, mode: str, composite_top_n: int, candidate_map: Dict[str, Any], tournament_doc: Dict[str, Any], staffing_summary: Dict[str, Any], dry_run: bool) -> Dict[str, str]:
    paths = {
        "candidate_selection_plan": os.path.join(state_dir, "candidate-selection-plan.json"),
        "model_selection_decision": os.path.join(state_dir, "model-selection-decision.json"),
        "rollback_plan": os.path.join(state_dir, "rollback_plan.json"),
        "model_run_records": os.path.join(state_dir, "model-run-records.json"),
        "model_run_summary": os.path.join(state_dir, "model-run-summary.json"),
    }
    roles = candidate_map.get("roles") or {}
    chosen = {}
    for role_key, rec in roles.items():
        selected = rec.get("selected") or []
        chosen[role_key] = selected[0] if selected else None
    plan = {
        "apiVersion": "noemaforge.model-selection/v1",
        "kind": "CandidateSelectionPlan",
        "created_at": _nowz(),
        "version": RUNTIME_VERSION,
        "selection": _selection_mode_contract(mode, composite_top_n),
        "dry_run": bool(dry_run),
        "artifacts": {
            "role_candidate_map": os.path.join(state_dir, "role-candidate-map.json"),
            "role_tournament_results": os.path.join(state_dir, "role-tournament-results.json"),
            "staffing_summary": os.path.join(state_dir, "firstboot-staffing-summary.json"),
            "composite_selection_plan": os.path.join(state_dir, "composite-selection-plan.json") if mode == "full_composite" else None,
        },
        "next": [
            "review model-selection-decision.json",
            "apply with sudo noemaforge first-start --%s" % ("full_composite %s" % composite_top_n if mode == "full_composite" else mode),
            "rollback is described in rollback_plan.json",
        ],
    }
    decision = {
        "apiVersion": "noemaforge.model-selection/v1",
        "kind": "ModelSelectionDecision",
        "created_at": _nowz(),
        "version": RUNTIME_VERSION,
        "mode": mode,
        "dry_run": bool(dry_run),
        "staffing_state": staffing_summary.get("staffing_state"),
        "selected_roles": staffing_summary.get("selected_roles"),
        "target_met_roles": staffing_summary.get("target_met_roles"),
        "missing_mandatory_core_roles": staffing_summary.get("missing_mandatory_core_roles") or [],
        "chosen_by_role": chosen,
        "ready_to_apply": bool(chosen) and not staffing_summary.get("missing_mandatory_core_roles"),
        "requires_confirmation_before_epoch_switch": True,
    }
    rollback = {
        "apiVersion": "noemaforge.model-selection/v1",
        "kind": "ModelSelectionRollbackPlan",
        "created_at": _nowz(),
        "version": RUNTIME_VERSION,
        "mode": mode,
        "steps": [
            "Do not delete previous epoch contracts.",
            "Before switching epoch, keep the previous current-epoch symlink target.",
            "If smoke/canary fails, switch current epoch back to the previous epoch id.",
            "Keep role-candidate-map.json and model-run-records.json for audit.",
        ],
    }
    _write_json(paths["candidate_selection_plan"], plan)
    _write_json(paths["model_selection_decision"], decision)
    _write_json(paths["rollback_plan"], rollback)
    model_run_records = tournament_doc.get("model_run_records") or []
    _write_json(paths["model_run_records"], {"created_at": _nowz(), "records": model_run_records})
    _write_json(
        paths["model_run_summary"],
        {
            "created_at": _nowz(),
            **pre_release_uat_fix_runtime.summarize_model_run_records(
                pre_release_uat_fix_runtime.normalize_model_run_records(model_run_records)
            ),
        },
    )
    return paths


def _safe_reboot(no_reboot: bool) -> bool:
    if no_reboot:
        return False
    try:
        subprocess.Popen(["systemctl", "--no-block", "reboot"])
        return True
    except Exception:
        return False


def _run_optional(cmd: List[str]) -> None:
    try:
        subprocess.check_call(cmd)
    except FileNotFoundError:
        return
    except subprocess.CalledProcessError:
        raise


def _normalize_vault(vault_root: str) -> None:
    inbox_script = os.path.join(NOEMAFORGE_ROOT, "tools", "prep", "process_inbox.py")
    scan_script = os.path.join(NOEMAFORGE_ROOT, "tools", "prep", "scan_vault.py")
    if os.path.isdir(os.path.join(vault_root, "inbox")) and os.path.isfile(inbox_script):
        _run_optional([sys.executable, inbox_script, "--vault-root", vault_root, "--out", os.path.join(STATE_DIR, "inbox_process_summary.json")])
    if os.path.isfile(scan_script):
        _run_optional([sys.executable, scan_script, "--vault-root", vault_root, "--auto-manifest"])


def _threshold_pass(scorecard: Dict[str, Any], thresholds: Dict[str, Any]) -> bool:
    """Return True when a scorecard meets all supplied numeric thresholds.

    Kept as a small pure helper because older smoke/unit tests and operator
    checks call it directly. Missing metrics are treated as zero.
    """
    for key, min_value in (thresholds or {}).items():
        try:
            if float(scorecard.get(key) or 0.0) < float(min_value):
                return False
        except Exception:
            return False
    return True


def _profile_available(profile_id: str, profiles: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
    """Check whether a model/profile is available on this machine.

    Supports the compact `available_when` contract used by historical tests and
    profile manifests. Unknown kinds are considered unavailable instead of being
    silently accepted.
    """
    profile = profiles.get(profile_id) or {}
    missing: List[Dict[str, Any]] = []
    for cond in profile.get("available_when") or []:
        path = str(cond.get("path") or "")
        kind = str(cond.get("kind") or "file")
        ok = False
        if kind == "file":
            ok = os.path.isfile(path)
        elif kind == "dir":
            ok = os.path.isdir(path)
        elif kind in {"path", "exists"}:
            ok = os.path.exists(path)
        if not ok:
            missing.append({"path": path, "kind": kind})
    return len(missing) == 0, missing


def _discover_gguf(vault_root: str, *, include_download_mirror: bool = False, shortlist: List[str] | None = None, candidate_limit: int = 0) -> List[str]:
    """Compatibility GGUF discovery helper used by smoke tests.

    The production inventory path is `vault_inventory.scan_inventory`; this
    helper intentionally remains small and deterministic.
    """
    root = Path(vault_root)
    dirs = [root / "models-gguf", root / "Models" / "gguf"]
    if include_download_mirror:
        dirs.extend([root / "download-mirror", root / "downloads"])
    needles = [str(x).lower() for x in (shortlist or []) if str(x).strip()]
    out: List[str] = []
    discovered: List[str] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for path in sorted(d.rglob("*.gguf")):
            sp = str(path)
            if needles and not any(n in sp.lower() for n in needles):
                continue
            discovered.append(sp)

    # Firstboot must never pass shard tails to scoring/runtime.  Use the
    # same normalizer exposed by `noemaforge normalize-models` so direct tests,
    # CLI discovery and launcher paths share one safety rule.
    normalized = model_inventory_normalize.normalize_paths(discovered)
    for item in normalized.get("candidates", []):
        sp = str(item.get("path") or "")
        if not sp:
            continue
        out.append(sp)
        if candidate_limit and len(out) >= candidate_limit:
            return out
    return out


MANDATORY_CORE_ROLES = [
    "operator.admin/administrator",
    "system.guard/surgeon",
    "dev.work/solution_architect",
    "writing.story/writer",
]


def _best_selected(role_rec: Dict[str, Any]) -> Dict[str, Any]:
    selected = role_rec.get("selected") or []
    return selected[0] if selected and isinstance(selected[0], dict) else {}


def _build_staffing_summary(tournament_doc: Dict[str, Any], thresholds: Dict[str, Any], mandatory_roles: List[str] | None = None) -> Dict[str, Any]:
    """Summarize firstboot role staffing and encode degraded semantics.

    The accepted NoemaForge bootstrap proved that viable below-target roles must
    be treated as `degraded_selected`, not collapsed to N/A. Reboot/apply is
    allowed only when all mandatory core roles have at least one selected model.
    """
    roles = tournament_doc.get("roles") or {}
    mandatory = list(mandatory_roles or MANDATORY_CORE_ROLES)
    total_roles = len(roles)
    selected_roles = 0
    target_met_roles = 0
    degraded_roles: List[str] = []
    unstaffed_roles: List[str] = []
    missing_mandatory: List[str] = []
    selected_model_ids: List[str] = []
    scores: List[float] = []

    for role_key, rec in roles.items():
        best = _best_selected(rec if isinstance(rec, dict) else {})
        if best:
            selected_roles += 1
            mid = str(best.get("model_id") or "").strip()
            if mid and mid not in selected_model_ids:
                selected_model_ids.append(mid)
            try:
                scores.append(float(best.get("score") or 0.0))
            except Exception:
                scores.append(0.0)
            if _threshold_pass(best, thresholds):
                target_met_roles += 1
            else:
                degraded_roles.append(str(role_key))
        else:
            unstaffed_roles.append(str(role_key))

    for role_key in mandatory:
        rec = roles.get(role_key) or {}
        if not _best_selected(rec if isinstance(rec, dict) else {}):
            missing_mandatory.append(role_key)

    if selected_roles <= 0 or missing_mandatory:
        staffing_state = "unstaffed"
    elif selected_roles == total_roles and target_met_roles == total_roles:
        staffing_state = "meets_target"
    else:
        staffing_state = "degraded_selected"

    warnings: List[str] = []
    if staffing_state == "degraded_selected":
        warnings.append("Some selected roles are below minimal thresholds; continuing only because mandatory core roles are staffed.")
    if missing_mandatory:
        warnings.append("One or more mandatory core roles are unstaffed; epoch apply/reboot must be blocked.")

    return {
        "apiVersion": "noemaforge.firstbootstaffing/v1",
        "kind": "FirstbootStaffingSummary",
        "staffing_state": staffing_state,
        "warnings": warnings,
        "total_roles": total_roles,
        "selected_roles": selected_roles,
        "target_met_roles": target_met_roles,
        "degraded_roles": degraded_roles,
        "unstaffed_roles": unstaffed_roles,
        "mandatory_core_roles": mandatory,
        "missing_mandatory_core_roles": missing_mandatory,
        "selected_model_ids": selected_model_ids,
        "selected_model_count": len(selected_model_ids),
        "all_scorecards_zero": bool(scores) and all(x <= 0.0 for x in scores),
        "thresholds": thresholds,
    }


def _role_keys_with_selected(tournament_doc: Dict[str, Any]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for role_key, rec in (tournament_doc.get("roles") or {}).items():
        if not rec.get("selected"):
            continue
        if "/" not in str(role_key):
            continue
        stream, role = str(role_key).split("/", 1)
        out.append((stream, role))
    return out


def _choose_main_model(candidate_map: Dict[str, Any]) -> str:
    roles = candidate_map.get("roles") or {}
    preferred = ["operator.admin/administrator", "system.guard/surgeon", "dev.work/dev"]
    for role_key in preferred + sorted(roles.keys()):
        selected = (roles.get(role_key) or {}).get("selected") or []
        if selected:
            mid = str(selected[0].get("model_id") or "").strip()
            if mid:
                return mid
    for mid in candidate_map.get("unique_selected_model_ids") or []:
        if str(mid).strip():
            return str(mid).strip()
    return ""




def _smoke_main_backend(timeout_sec: int = 30) -> Dict[str, Any]:
    ok, msg = runtime_safety.smoke_backend_health("/run/noemaforge/llm/backends/main.sock", timeout=min(timeout_sec, 30))
    return {"ok": ok, "message": msg, "sock": "/run/noemaforge/llm/backends/main.sock"}

def _runtime_safety_gate(modelstore_root: str, candidate_map: Dict[str, Any], tournament_doc: Dict[str, Any]) -> Dict[str, Any]:
    cm_ok, cm_bad = runtime_safety.assert_candidate_doc_safe(candidate_map)
    rt_ok, rt_bad = runtime_safety.assert_candidate_doc_safe(tournament_doc)
    cm_text_mentions = runtime_safety.collect_text_non_head_mentions(candidate_map)
    rt_text_mentions = runtime_safety.collect_text_non_head_mentions(tournament_doc)
    ms = runtime_safety.scan_modelstore_safety(modelstore_root)
    ok = cm_ok and rt_ok and (ms.get("unsafe_count", 0) == 0)
    return {
        "ok": ok,
        "candidate_map_ok": cm_ok,
        "candidate_map_bad": cm_bad,
        "tournament_ok": rt_ok,
        "tournament_bad": rt_bad,
        "text_mentions_warning_only": {
            "candidate_map": cm_text_mentions,
            "tournament": rt_text_mentions,
        },
        "modelstore": {
            "safe_count": ms.get("safe_count"),
            "unsafe_count": ms.get("unsafe_count"),
            "unsafe": ms.get("unsafe"),
        },
    }

def _ensure_main_alias(modelstore_root: str, selected_model_id: str) -> Dict[str, Any]:
    if not selected_model_id or selected_model_id == "main":
        return {"main_model_id": selected_model_id, "aliased": False}
    models_dir = Path(modelstore_root) / "models"
    src = models_dir / selected_model_id
    dst = models_dir / "main"
    if not src.is_dir():
        return {"main_model_id": selected_model_id, "aliased": False, "reason": "selected_model_dir_missing"}
    ok_safe, reason, meta = runtime_safety.validate_modelstore_backend(modelstore_root, selected_model_id)
    if not ok_safe:
        return {"main_model_id": selected_model_id, "aliased": False, "reason": f"runtime_safety_blocked:{reason}", "meta": meta}
    link = src / "model.gguf"
    target = os.path.realpath(str(link)) if link.exists() or link.is_symlink() else ""
    if not target or not Path(target).is_file():
        return {
            "main_model_id": selected_model_id,
            "aliased": False,
            "reason": "selected_model_artifact_missing",
            "source_model": str(link),
            "source_realpath": target,
        }
    dst.mkdir(parents=True, exist_ok=True)
    lock_dir = dst / ".materialize-main.lock"
    lock_acquired, lock_status = _acquire_main_alias_lock(lock_dir)
    if not lock_acquired:
        return {
            "main_model_id": selected_model_id,
            "aliased": False,
            "reason": "main_alias_materialization_locked",
            "lock": lock_status,
        }
    active_files = [dst / "model.gguf", dst / "manifest.yaml", dst / "noemaforge-model.json", dst / "brainos-model.json"]
    staging_dir = None
    try:
        man = src / "manifest.yaml"
        manifest_obj: Dict[str, Any] = {}
        if man.is_file():
            try:
                manifest_obj = yaml.safe_load(man.read_text(encoding="utf-8")) or {}
                if not isinstance(manifest_obj, dict):
                    manifest_obj = {}
            except Exception:
                manifest_obj = {}
        display_name = str(
            manifest_obj.get("display_name")
            or manifest_obj.get("name")
            or manifest_obj.get("model_id")
            or selected_model_id
        )
        source = str(target or manifest_obj.get("source") or link)
        active_manifest = {
            **manifest_obj,
            "model_id": selected_model_id,
            "display_name": display_name,
            "source": source,
            "alias": "main",
            "alias_of": selected_model_id,
            "selection_provenance": {
                "reason": "firstboot_selected_main_model",
                "selected_model_id": selected_model_id,
                "source_model_dir": str(src),
                "materialized_main_dir": str(dst),
            },
        }
        if target:
            active_manifest["source_realpath"] = target

        stamp = _nowz().replace(":", "").replace("-", "")
        rollback_dir = None
        existing_files = [f for f in active_files if f.exists() or f.is_symlink()]
        if existing_files:
            rollback_dir = dst / ".rollback" / f"alias-materialization-{stamp}"
            rollback_dir.mkdir(parents=True, exist_ok=True)
            for f in existing_files:
                backup = rollback_dir / f.name
                if f.is_symlink():
                    os.symlink(os.readlink(f), str(backup))
                elif f.is_file():
                    shutil.copy2(str(f), str(backup))

        staging_dir = dst / ".staging" / f"alias-materialization-{stamp}-{os.getpid()}"
        staging_dir.mkdir(parents=True, exist_ok=False)
        replacements: List[Tuple[Path, Path]] = []
        tmp_link = staging_dir / "model.gguf"
        os.symlink(target, str(tmp_link))
        replacements.append((tmp_link, dst / "model.gguf"))
        tmp_yaml = staging_dir / "manifest.yaml"
        tmp_yaml.write_text(yaml.safe_dump(active_manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
        replacements.append((tmp_yaml, dst / "manifest.yaml"))
        for name in ["noemaforge-model.json", "brainos-model.json"]:
            tmp = staging_dir / name
            tmp.write_text(json.dumps(active_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            replacements.append((tmp, dst / name))
        replaced_targets: List[Path] = []
        try:
            for tmp, final in replacements:
                os.replace(tmp, final)
                replaced_targets.append(final)
        except Exception:
            rollback_names = {f.name for f in existing_files}
            for final in replaced_targets:
                backup = rollback_dir / final.name if rollback_dir else None
                if backup and (backup.exists() or backup.is_symlink()):
                    os.replace(backup, final)
                elif final.name not in rollback_names and (final.exists() or final.is_symlink()):
                    final.unlink()
            raise
        return {"main_model_id": selected_model_id, "aliased": True, "main_dir": str(dst), "manifest": str(dst / "noemaforge-model.json"), "rollback_dir": str(rollback_dir) if rollback_dir else ""}
    except Exception as exc:
        return {
            "main_model_id": selected_model_id,
            "aliased": False,
            "reason": "main_alias_materialization_failed",
            "error": str(exc),
        }
    finally:
        if staging_dir is not None and staging_dir.exists():
            shutil.rmtree(str(staging_dir), ignore_errors=True)
        shutil.rmtree(str(lock_dir), ignore_errors=True)


def orchestrate(
    *,
    share_root: str,
    vault_root: str = "",
    shortlist_file: str = "",
    model_profile: str = "minimal",
    candidate_limit: int = 0,
    top_k: int = 0,
    no_reboot: bool = False,
    force: bool = False,
    include_download_mirror: bool = False,
    allow_incomplete_shards: bool = False,
    selection_mode: str = "normal",
    composite_top_n: int = -1,
    dry_run: bool = False,
    show_candidates: bool = False,
    show_compositions: bool = False,
    per_model_timeout: int = 0,
    total_timeout: int = 0,
    include_unverified: bool = False,
    retry_failed_models: bool = False,
    clear_model_health: bool = False,
    strict_any_fail: bool = False,
    allow_failed_selection: bool = False,
) -> Dict[str, Any]:
    path_normalization = normalize_launcher_paths(share_root=share_root, vault_root=vault_root, shortlist_file=shortlist_file)
    share_root = str(path_normalization["share_root"])
    vault_root = str(path_normalization["vault_root"])
    shortlist_file = str(path_normalization["shortlist_file"])
    policy = _load_yaml(DEFAULT_POLICY)
    profile_catalog = model_profiles.load_profiles(Path(NOEMAFORGE_ROOT))
    profile_report = model_profiles.validate_profiles(profile_catalog)
    if not profile_report.get("ok"):
        raise ValueError(f"model_profile_config_invalid:{profile_report.get('failures')}")
    if model_profile not in profile_catalog:
        raise ValueError(f"unknown_model_profile:{model_profile}")
    profile_manifest = model_profiles.build_profile_manifest(profile_catalog, model_profile)
    status_path = str(policy.get("status_path") or DEFAULT_STATUS)
    events_path = str(policy.get("events_path") or DEFAULT_EVENTS)
    modelstore_root = str(policy.get("modelstore_root") or _pp.modelstore_dir)
    scorecards_dir = str(policy.get("scorecards_dir") or _pp.data_root / "model_scorecards")
    requests_dir = str(policy.get("requests_dir") or _pp.data_root / "requests/prestart")
    selection_mode = _normalize_selection_mode(selection_mode)
    top_k_per_role = int(top_k or policy.get("top_k_per_role") or policy.get("top_k") or 8)
    if selection_mode == "fast":
        top_k_per_role = 1
    elif selection_mode == "normal":
        top_k_per_role = max(2, top_k_per_role if top_k else 2)
    elif selection_mode in {"full", "full_composite"}:
        # Evaluation is full because role_tournament iterates every runnable model.
        # top_k_per_role controls how many measured candidates are retained for review/composition.
        top_k_per_role = max(1, top_k_per_role)
    # 0.32.1: preserve effective tournament options for
    # direct and systemd-rehomed first-start runs. role_tournament reads these
    # from the environment, so CLI flags must be materialized before calling it.
    default_per_model, default_total = role_tournament._selection_timeout_defaults(selection_mode)
    effective_per_model_timeout = int(per_model_timeout or os.environ.get("NOEMAFORGE_TOURNAMENT_PER_MODEL_TIMEOUT", "0") or default_per_model)
    effective_total_timeout = int(total_timeout or os.environ.get("NOEMAFORGE_TOURNAMENT_TOTAL_TIMEOUT", "0") or default_total)
    os.environ["NOEMAFORGE_TOURNAMENT_PER_MODEL_TIMEOUT"] = str(effective_per_model_timeout)
    os.environ["NOEMAFORGE_TOURNAMENT_TOTAL_TIMEOUT"] = str(effective_total_timeout)
    if include_unverified:
        os.environ["NOEMAFORGE_TOURNAMENT_INCLUDE_UNVERIFIED"] = "1"
    if retry_failed_models:
        os.environ["NOEMAFORGE_TOURNAMENT_RETRY_FAILED_MODELS"] = "1"
    if clear_model_health:
        os.environ["NOEMAFORGE_TOURNAMENT_CLEAR_MODEL_HEALTH"] = "1"
    if strict_any_fail:
        os.environ["NOEMAFORGE_TOURNAMENT_STRICT_ANY_FAIL"] = "1"
    if allow_failed_selection:
        os.environ["NOEMAFORGE_TOURNAMENT_EXCLUDE_FAILED_FROM_SELECTION"] = "0"
    vault = vault_inventory.choose_vault_root(share_root, vault_root)
    effective_options = {
        "selection_mode": selection_mode,
        "model_profile": model_profile,
        "composite_top_n": composite_top_n,
        "dry_run": bool(dry_run),
        "show_candidates": bool(show_candidates),
        "show_compositions": bool(show_compositions),
        "per_model_timeout": effective_per_model_timeout,
        "total_timeout": effective_total_timeout,
        "include_unverified": bool(include_unverified),
        "retry_failed_models": bool(retry_failed_models),
        "clear_model_health": bool(clear_model_health),
        "strict_any_fail": bool(strict_any_fail),
        "exclude_failed_from_selection": not bool(allow_failed_selection),
        "top_k_per_role": top_k_per_role,
        "share_root": share_root,
        "vault_root": vault,
        "path_normalization": path_normalization,
    }
    run_lease = firstboot_status.acquire_run_lease(status_path, events_path, state_dir=STATE_DIR, force=force)
    if not run_lease.get("ok"):
        return {"ok": False, "reason": "firstboot_already_running", "lease": run_lease}
    firstboot_status.mark_started(status_path, events_path, share_root=share_root, vault_root=vault)
    effective_options["run_lease"] = run_lease.get("lock_path")
    _write_json(os.path.join(STATE_DIR, "effective-first-start-options.json"), effective_options)
    _write_json(os.path.join(STATE_DIR, "model-profile-manifest.json"), profile_manifest)

    firstboot_status.mark_step(status_path, events_path, step="vault", state="running", message="Normalizing and scanning canonical Vault.")
    _normalize_vault(vault)

    firstboot_status.mark_step(status_path, events_path, step="dataset_assurance", state="running", message="Ensuring firstboot role-eval datasets exist before scoring.")
    dataset_assurance_path = os.path.join(STATE_DIR, "dataset-assurance.json")
    dataset_assurance = dataset_inventory.assure_role_eval_dataset()
    dataset_inventory.write_dataset_assurance(dataset_assurance, dataset_assurance_path)
    effective_options["dataset_assurance"] = dataset_assurance_path
    _write_json(os.path.join(STATE_DIR, "effective-first-start-options.json"), effective_options)
    if not dataset_assurance.get("ok"):
        firstboot_status.mark_finished(status_path, events_path, state="blocked_dataset_assurance", message="Firstboot role-eval datasets are missing or invalid; scoring was not started.", extra={"dataset_assurance": dataset_assurance_path, "report": dataset_assurance})
        return {"ok": False, "reason": "dataset_assurance_failed", "dataset_assurance": dataset_assurance}

    firstboot_status.mark_step(status_path, events_path, step="inventory", state="running", message="Inventorying all model artifacts and datasets.")
    inventory = vault_inventory.scan_inventory(share_root, vault, strict_shards=not allow_incomplete_shards)
    inventory_path = os.path.join(STATE_DIR, "model-inventory.json")
    vault_inventory.write_inventory(inventory, inventory_path, write_vault_manifest=True)

    ds = dataset_inventory.scan_datasets(share_root, vault)
    dataset_path = os.path.join(STATE_DIR, "dataset-inventory.json")
    dataset_inventory.write_dataset_inventory(ds, dataset_path)
    eval_index = dataset_inventory.build_eval_packs(DEFAULT_ROLE_CATALOG, str(_pp.data_root / "eval-packs/first-start-light"), dataset_path)

    firstboot_status.mark_step(status_path, events_path, step="role_tournament", state="running", message=f"Running role-specific tournaments in {selection_mode} mode; retaining top {top_k_per_role} per role.", extra={"inventory": inventory_path, "top_k_per_role": top_k_per_role, "selection_mode": selection_mode, "composite_top_n": composite_top_n, "per_model_timeout": effective_per_model_timeout, "total_timeout": effective_total_timeout, "include_unverified": bool(include_unverified), "effective_options": os.path.join(STATE_DIR, "effective-first-start-options.json")})
    catalog = _load_yaml(DEFAULT_ROLE_CATALOG)
    # Force catalog default top_k when old CLI passes --top-k.
    catalog.setdefault("selection", {})["top_k_per_role"] = top_k_per_role
    for rec in (catalog.get("roles") or {}).values():
        if isinstance(rec, dict):
            # patched7: normal/top-k must not silently keep old catalog top_k=8.
            rec["top_k"] = top_k_per_role
    tournament_doc = role_tournament.run_tournament(
        inventory,
        catalog,
        pack_root=str(_pp.data_root / "eval-packs/first-start-light"),
        state_dir=STATE_DIR,
        modelstore_root=modelstore_root,
        scorecards_dir=scorecards_dir,
        runtime_mode="run",
        selection_mode=selection_mode,
        composite_top_n=composite_top_n,
    )
    candidate_map_path = os.path.join(STATE_DIR, "role-candidate-map.json")
    candidate_map = _read_json(candidate_map_path)
    selected_total = sum(len((r.get("selected") or [])) for r in (tournament_doc.get("roles") or {}).values())
    staffing_summary = _build_staffing_summary(
        tournament_doc,
        thresholds=dict(policy.get("minimal_thresholds") or {}),
        mandatory_roles=list(policy.get("mandatory_core_roles") or MANDATORY_CORE_ROLES),
    )
    staffing_summary_path = os.path.join(STATE_DIR, "firstboot-staffing-summary.json")
    _write_json(staffing_summary_path, staffing_summary)
    selection_artifacts = _write_selection_artifacts(state_dir=STATE_DIR, mode=selection_mode, composite_top_n=composite_top_n, candidate_map=candidate_map, tournament_doc=tournament_doc, staffing_summary=staffing_summary, dry_run=dry_run)
    staffing_gate_state = "warning" if staffing_summary.get("staffing_state") == "degraded_selected" else "running"
    staffing_gate_msg = "Firstboot staffing is degraded_selected; mandatory core roles are staffed, so continuing with warning." if staffing_gate_state == "warning" else "Evaluating firstboot staffing quality gate."
    firstboot_status.mark_step(status_path, events_path, step="staffing_gate", state=staffing_gate_state, message=staffing_gate_msg, extra={"staffing_summary": staffing_summary_path, "staffing_state": staffing_summary.get("staffing_state"), "warnings": staffing_summary.get("warnings") or []})
    if selected_total <= 0:
        diagnostics = (candidate_map.get("selection_diagnostics") or {}) if isinstance(candidate_map, dict) else {}
        reason = str(diagnostics.get("no_candidates_reason") or "no_role_candidates")
        firstboot_status.mark_finished(status_path, events_path, state="blocked_no_role_candidates", message=f"No model candidates selected: {reason}.", extra={"inventory": inventory_path, "tournament": os.path.join(STATE_DIR, "role-tournament-results.json"), "staffing": staffing_summary, "selection_diagnostics": diagnostics, "model_profile": model_profile, "model_profile_manifest": os.path.join(STATE_DIR, "model-profile-manifest.json")})
        return {"ok": False, "reason": reason, "inventory": inventory_path, "tournament": os.path.join(STATE_DIR, "role-tournament-results.json"), "staffing": staffing_summary, "selection_diagnostics": diagnostics}
    if staffing_summary.get("all_scorecards_zero"):
        firstboot_status.mark_finished(status_path, events_path, state="blocked_all_zero_scorecards", message="All selected firstboot scorecards are zero; refusing epoch apply/reboot.", extra={"staffing": staffing_summary, "tournament": os.path.join(STATE_DIR, "role-tournament-results.json")})
        return {"ok": False, "reason": "all_zero_scorecards", "staffing": staffing_summary}
    if staffing_summary.get("missing_mandatory_core_roles"):
        firstboot_status.mark_finished(status_path, events_path, state="blocked_mandatory_core_roles_unstaffed", message="Mandatory core roles are unstaffed; refusing epoch apply/reboot.", extra={"staffing": staffing_summary, "tournament": os.path.join(STATE_DIR, "role-tournament-results.json"), "selection_artifacts": selection_artifacts})
        return {"ok": False, "reason": "mandatory_core_roles_unstaffed", "staffing": staffing_summary, "selection_artifacts": selection_artifacts}

    if dry_run:
        final = {"ok": True, "dry_run": True, "reason": "selection_ready_no_apply", "selection_mode": selection_mode, "model_profile": model_profile, "model_profile_manifest": os.path.join(STATE_DIR, "model-profile-manifest.json"), "composite_top_n": composite_top_n, "inventory": inventory_path, "dataset_inventory": dataset_path, "role_candidate_map": candidate_map_path, "tournament_results": os.path.join(STATE_DIR, "role-tournament-results.json"), "staffing_summary": staffing_summary_path, "selection_artifacts": selection_artifacts, "staffing_state": staffing_summary.get("staffing_state"), "show_candidates": bool(show_candidates), "show_compositions": bool(show_compositions)}
        firstboot_status.mark_finished(status_path, events_path, state="selection_ready_no_apply", message="Model selection completed in dry-run mode; no services, epoch switch or reboot were performed.", extra=final)
        return final

    gate = _runtime_safety_gate(modelstore_root, candidate_map, tournament_doc)
    if not gate.get("ok"):
        # Try one conservative repair pass: quarantine unsafe ModelStore dirs and rebuild main if needed.
        repair = runtime_safety.repair_modelstore(modelstore_root=modelstore_root, inventory_path=inventory_path, ensure_main=True)
        gate = _runtime_safety_gate(modelstore_root, candidate_map, tournament_doc)
        if not gate.get("ok"):
            firstboot_status.mark_finished(status_path, events_path, state="blocked_runtime_safety", message="Runtime safety gate blocked first-start before service launch.", extra={"gate": gate, "repair": repair})
            return {"ok": False, "reason": "runtime_safety_blocked", "gate": gate, "repair": repair}

    main_selected = _choose_main_model(candidate_map)
    main_alias = _ensure_main_alias(modelstore_root, main_selected)
    if str(main_alias.get("reason") or "").startswith("runtime_safety_blocked"):
        repair = runtime_safety.repair_modelstore(modelstore_root=modelstore_root, inventory_path=inventory_path, ensure_main=True)
        main_alias = {"main_model_id": main_selected, "aliased": False, "reason": "main_repaired_by_runtime_safety", "repair": repair}
    elif main_alias.get("reason") in {"main_alias_materialization_locked", "main_alias_materialization_failed", "selected_model_artifact_missing"}:
        firstboot_status.mark_finished(status_path, events_path, state="blocked_main_alias_materialization", message="Selected main model could not be materialized safely.", extra={"main_alias": main_alias})
        return {"ok": False, "reason": "main_alias_materialization_failed", "main_alias": main_alias}
    model_registry.update_registry(registry_path=os.path.join(modelstore_root, "model_registry.json"), emit_sel=True)

    firstboot_status.mark_step(status_path, events_path, step="services", state="running", message="Starting baseline NoemaForge services after role-aware tournament.", extra={"main_alias": main_alias, "runtime_safety": gate})
    for unit in ["noemaforge-llm-gateway.service", "noemaforge-toolproxy.service", "noemaforge-llama@main.service"]:
        subprocess.call(["systemctl", "start", unit])
    smoke = _smoke_main_backend(timeout_sec=30)
    if not smoke.get("ok"):
        firstboot_status.mark_finished(status_path, events_path, state="blocked_main_backend_smoke_failed", message="Main backend failed health smoke after first-start service launch.", extra={"smoke": smoke, "main_alias": main_alias})
        return {"ok": False, "reason": "main_backend_smoke_failed", "smoke": smoke, "main_alias": main_alias}

    picked_roles = _role_keys_with_selected(tournament_doc)
    if not picked_roles:
        picked_roles = [("operator.admin", "administrator")]

    firstboot_status.mark_step(status_path, events_path, step="prestart_request", state="running", message="Building approved first-epoch request from role candidate map.")
    epoch_dir = prestart.epoch_path(prestart.ensure_epoch_initialized(config_dir=str(_pp.root / "configs"), contracts_root=str(_pp.data_root / "contracts")), str(_pp.data_root / "contracts"))
    patches = model_installer_plan.propose_policy_patches(
        role_model_policy_path=os.path.join(epoch_dir, "role-model-policy.yaml"),
        llm_backends_policy_path=os.path.join(epoch_dir, "llm-backends-policy.yaml"),
        registry_path=os.path.join(modelstore_root, "model_registry.json"),
        scorecards_dir=scorecards_dir,
        roles_to_consider=picked_roles,
        top_k=top_k_per_role,
    )
    rid = "firstboot-roleaware-" + firstboot_status._nowz().replace(":", "").replace("-", "")
    req = model_installer_plan.make_prestart_request(
        request_id=rid,
        created_by={"actor_type": "system", "actor_id": "firstboot_orchestrator", "role": "surgeon"},
        track="policy",
        patches=patches,
        user_comment=f"Auto-generated role-aware first-boot model staffing request: mode={selection_mode}, top_k={top_k_per_role}, composite_top_n={composite_top_n}.",
    )
    req["status"] = "approved"
    req["firstboot"] = {"auto_apply": True, "auto_reboot": not no_reboot, "role_candidate_map": candidate_map_path, "tournament_results": os.path.join(STATE_DIR, "role-tournament-results.json"), "top_k_per_role": top_k_per_role, "selection_mode": selection_mode, "model_profile": model_profile, "model_profile_manifest": os.path.join(STATE_DIR, "model-profile-manifest.json"), "composite_top_n": composite_top_n, "selection_artifacts": selection_artifacts, "staffing_summary": staffing_summary_path, "staffing_state": staffing_summary.get("staffing_state")}
    os.makedirs(requests_dir, exist_ok=True)
    req_path = os.path.join(requests_dir, f"{rid}.prestart_request.yaml")
    with open(req_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(req, f, sort_keys=False, allow_unicode=True)

    applied_epoch = ""
    reboot_scheduled = False
    if bool(policy.get("auto_apply_first_epoch", True)):
        firstboot_status.mark_step(status_path, events_path, step="build_epoch", state="running", message="Building candidate epoch from approved role-aware firstboot request.", extra={"request_id": rid})
        reqs = prestart.select_requests_for_build(prestart.load_requests(requests_dir))
        eid = prestart.build_candidate_epoch(
            desired_epoch_id=prestart.next_epoch_id(str(_pp.data_root / "contracts")),
            contracts_root=str(_pp.data_root / "contracts"),
            requests=reqs,
            created_by={"actor_type": "system", "channel": "firstboot_orchestrator"},
            description="Role-aware first-boot staffed epoch",
            user_comment="Automatic role-aware first-boot staffing",
        )
        ep_dir = prestart.epoch_path(eid, str(_pp.data_root / "contracts"))
        report = _read_json(os.path.join(ep_dir, "prestart_build_report.json"))
        if str(report.get("overall_decision") or "").lower() != "pass":
            firstboot_status.mark_finished(status_path, events_path, state="blocked_apply_failed", message="Candidate epoch did not pass build/canary checks.", extra={"epoch_id": eid, "request_id": rid, "tournament": os.path.join(STATE_DIR, "role-tournament-results.json")})
            return {"ok": False, "reason": "build_not_pass", "epoch_id": eid, "request_id": rid}
        prestart.switch_current_epoch(eid, str(_pp.data_root / "contracts"))
        prestart.mark_requests_applied(prestart.load_requests(requests_dir), applied_epoch_id=eid, only_request_ids=[rid])
        applied_epoch = eid
        if bool(policy.get("auto_reboot_after_apply", True)):
            reboot_scheduled = _safe_reboot(no_reboot=no_reboot)

    final_state = "reboot_pending" if reboot_scheduled else "applied_no_reboot"
    msg = "Role-aware first-boot staffing finished; reboot scheduled." if reboot_scheduled else "Role-aware first-boot staffing finished; no reboot scheduled."
    final = {"ok": True, "request_id": rid, "applied_epoch_id": applied_epoch, "reboot_scheduled": reboot_scheduled, "inventory": inventory_path, "dataset_inventory": dataset_path, "eval_pack_index": eval_index.get("out_root"), "role_candidate_map": candidate_map_path, "tournament_results": os.path.join(STATE_DIR, "role-tournament-results.json"), "staffing_summary": staffing_summary_path, "staffing_state": staffing_summary.get("staffing_state"), "main_alias": main_alias, "main_backend_smoke": smoke, "runtime_safety": gate, "picked_models": patches.get("picked_models"), "selection_mode": selection_mode, "model_profile": model_profile, "model_profile_manifest": os.path.join(STATE_DIR, "model-profile-manifest.json"), "composite_top_n": composite_top_n, "selection_artifacts": selection_artifacts}
    firstboot_status.mark_finished(status_path, events_path, state=final_state, message=msg, extra=final)
    return final


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--share-root", default="/mnt/noemaforge-share")
    ap.add_argument("--vault-root", default="")
    ap.add_argument("--shortlist-file", default="")
    ap.add_argument("--model-profile", default="minimal", choices=["minimal", "balanced", "writer", "research", "gpu-heavy"])
    ap.add_argument("--candidate-limit", type=int, default=0, help="compatibility only; role-aware selection uses top-k-per-role after eval")
    ap.add_argument("--top-k", type=int, default=0, help="top K per role; default 8")
    ap.add_argument("--include-download-mirror", action="store_true")
    ap.add_argument("--allow-incomplete-shards", action="store_true")
    ap.add_argument("--no-reboot", action="store_true")
    ap.add_argument("--force", action="store_true")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--fast", dest="selection_mode", action="store_const", const="fast")
    mode.add_argument("--normal", dest="selection_mode", action="store_const", const="normal")
    mode.add_argument("--full", dest="selection_mode", action="store_const", const="full")
    mode.add_argument("--full_composite", dest="full_composite_n", type=int, nargs="?", const=0)
    ap.add_argument("--selection-mode", choices=["fast", "normal", "full", "full_composite"], default="normal")
    ap.add_argument("--composite-top-n", type=int, default=-1)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show-candidates", action="store_true")
    ap.add_argument("--show-compositions", action="store_true")
    ap.add_argument("--per-model-timeout", type=int, default=0)
    ap.add_argument("--total-timeout", type=int, default=0)
    ap.add_argument("--include-unverified", action="store_true")
    ap.add_argument("--yes-i-understand-unverified-risk", action="store_true")
    ap.add_argument("--retry-failed-models", action="store_true")
    ap.add_argument("--clear-model-health", action="store_true")
    ap.add_argument("--strict-any-fail", action="store_true")
    ap.add_argument("--allow-failed-selection", action="store_true")
    args = ap.parse_args()
    if args.include_unverified and not args.dry_run and not args.yes_i_understand_unverified_risk:
        print("ERROR: real first-start with --include-unverified requires --yes-i-understand-unverified-risk; run --dry-run first.", file=sys.stderr)
        return 64
    if getattr(args, "full_composite_n", None) is not None:
        args.selection_mode = "full_composite"
        args.composite_top_n = int(args.full_composite_n)
    res = orchestrate(
        share_root=args.share_root,
        vault_root=args.vault_root,
        shortlist_file=args.shortlist_file,
        model_profile=args.model_profile,
        candidate_limit=args.candidate_limit,
        top_k=args.top_k,
        no_reboot=bool(args.no_reboot),
        force=bool(args.force),
        include_download_mirror=bool(args.include_download_mirror),
        allow_incomplete_shards=bool(args.allow_incomplete_shards),
        selection_mode=str(args.selection_mode),
        composite_top_n=int(args.composite_top_n),
        dry_run=bool(args.dry_run),
        show_candidates=bool(args.show_candidates),
        show_compositions=bool(args.show_compositions),
        per_model_timeout=int(args.per_model_timeout or 0),
        total_timeout=int(args.total_timeout or 0),
        include_unverified=bool(args.include_unverified),
        retry_failed_models=bool(args.retry_failed_models),
        clear_model_health=bool(args.clear_model_health),
        strict_any_fail=bool(args.strict_any_fail),
        allow_failed_selection=bool(args.allow_failed_selection),
    )
    print(yaml.safe_dump(res, sort_keys=False, allow_unicode=True))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
