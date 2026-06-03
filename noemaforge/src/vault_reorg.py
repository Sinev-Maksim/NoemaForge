#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/vault_reorg.py
# Zone: vault/reorg
# Purpose: Variant-B safe Vault reorganization: dry-run plan, audit, and explicit apply with canonical-preserving quarantine.
# Callers: noemaforge vault plan/show-plan/audit/apply.
# Safety notes: never deletes model files; never overwrites or renames canonical destinations. Colliding incoming dirs are moved to Vault/duplicates/reorg-*/...
# === End NoemaForge File Header ===

import argparse
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from platform_paths import DEFAULT_PATHS as _pp

try:
    import vault_inventory
except Exception:  # pragma: no cover
    sys.path.insert(0, "/opt/noemaforge/src")
    import vault_inventory  # type: ignore

DEFAULT_PLAN = str(_pp.data_root / "bootstrap/vault-reorg-plan.json")
DEFAULT_AUDIT = str(_pp.data_root / "bootstrap/vault-reorg-audit.json")
APPLY_REPORT = str(_pp.data_root / "bootstrap/vault-reorg-apply-report.json")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


def real(path: str) -> str:
    return os.path.realpath(path)


def exists(path: str) -> bool:
    try:
        return os.path.exists(path)
    except Exception:
        return False


def unique_target(path: str) -> str:
    """Return a unique target without touching the original path.

    Kept for metadata-copy cases. Model/data collisions are handled by quarantine,
    not by creating foo.dup2 next to canonical foo.
    """
    if not exists(path):
        return path
    base = path
    i = 2
    while exists(f"{base}.dup{i}"):
        i += 1
    return f"{base}.dup{i}"


def safe_rel(path: str) -> str:
    rel = path.replace("\\", "/").strip("/")
    # Collapse all weird path chars; this is only for quarantine labels.
    parts = [p for p in rel.split("/") if p and p not in {".", ".."}]
    return "/".join(parts) or "unknown"


def quarantine_root(vault_root: str, rid: str) -> str:
    return os.path.join(vault_root, "duplicates", f"reorg-{rid}")


def quarantine_target(vault_root: str, group: str, src: str, rid: str) -> str:
    group = group or "unknown"
    name = os.path.basename(src.rstrip("/")) or "item"
    return os.path.join(quarantine_root(vault_root, rid), group, name)


def shallow_tree_stats(path: str) -> Dict[str, Any]:
    """Cheap, non-cryptographic tree stats for operator visibility.

    We intentionally avoid hashing huge model files during GUI prep. The stats are
    only used for reports, not for destructive decisions.
    """
    out = {"exists": exists(path), "files": 0, "dirs": 0, "bytes": 0, "gguf_files": 0}
    if not out["exists"]:
        return out
    try:
        if os.path.isfile(path) or os.path.islink(path):
            out["files"] = 1
            out["bytes"] = int(os.path.getsize(path))
            out["gguf_files"] = 1 if path.lower().endswith(".gguf") else 0
            return out
        for root, dirs, files in os.walk(path):
            out["dirs"] += len(dirs)
            out["files"] += len(files)
            for fn in files:
                fp = os.path.join(root, fn)
                try:
                    out["bytes"] += int(os.path.getsize(fp))
                except Exception:
                    pass
                if fn.lower().endswith(".gguf"):
                    out["gguf_files"] += 1
    except Exception:
        pass
    return out


def action_kind_for(src: str, dst: str, group: str, vault: str, rid: str, requested_kind: str = "move") -> Dict[str, Any]:
    """Build one safe plan action.

    If dst does not exist, action is normal move/copy. If dst exists, preserve it
    and quarantine the incoming source. This is the core 0.28.6 fix.
    """
    src_r = real(src)
    if not exists(src_r):
        return {}
    dst_r = dst
    dst_exists = exists(dst_r)
    if requested_kind == "copy":
        # Legacy metadata copies may collide; copy to unique import path rather than quarantine.
        if dst_exists:
            final_dst = unique_target(dst_r)
            return {
                "action": "copy",
                "src": src_r,
                "dst": final_dst,
                "requested_dst": dst_r,
                "reason": "copy metadata; destination existed so a unique import target was chosen",
                "group": group,
                "collision_policy": "copy_to_unique_import_target",
                "dst_exists": True,
                "src_stats": shallow_tree_stats(src_r),
                "dst_stats": shallow_tree_stats(dst_r),
            }
        return {
            "action": "copy",
            "src": src_r,
            "dst": dst_r,
            "reason": "copy metadata from legacy Vault",
            "group": group,
            "collision_policy": "no_collision",
            "dst_exists": False,
            "src_stats": shallow_tree_stats(src_r),
        }
    if dst_exists:
        qdst = quarantine_target(vault, group, src_r, rid)
        return {
            "action": "quarantine_duplicate",
            "src": src_r,
            "dst": qdst,
            "canonical_dst": dst_r,
            "reason": "destination already exists; preserve canonical target and move incoming item to duplicates quarantine",
            "group": group,
            "collision_policy": "preserve_canonical_quarantine_incoming",
            "dst_exists": True,
            "src_stats": shallow_tree_stats(src_r),
            "dst_stats": shallow_tree_stats(dst_r),
        }
    return {
        "action": requested_kind,
        "src": src_r,
        "dst": dst_r,
        "reason": "normalization move without destination collision",
        "group": group,
        "collision_policy": "no_collision",
        "dst_exists": False,
        "src_stats": shallow_tree_stats(src_r),
    }


def add_action(plan: Dict[str, Any], src: str, dst: str, reason: str, group: str = "", requested_kind: str = "move") -> None:
    action = action_kind_for(src, dst, group, plan["canonical_vault_root"], plan["run_id"], requested_kind=requested_kind)
    if not action:
        return
    action["reason_requested"] = reason
    plan["actions"].append(action)


def build_plan(share_root: str = "/mnt/noemaforge-share", vault_root: str = "") -> Dict[str, Any]:
    vault = vault_inventory.choose_vault_root(share_root, vault_root)
    legacy = os.path.join(share_root, "Vault")
    rid = run_id()
    plan: Dict[str, Any] = {
        "apiVersion": "noemaforge.vault-reorg/v1",
        "kind": "VaultReorgPlan",
        "created_at": now(),
        "run_id": rid,
        "share_root": real(share_root),
        "canonical_vault_root": vault,
        "legacy_vault_root": real(legacy) if os.path.isdir(legacy) else "",
        "mode": "dry_run_until_apply",
        "safety_policy": {
            "overwrite_existing_destinations": False,
            "rename_existing_canonical_destinations": False,
            "delete_duplicates": False,
            "collision_action": "quarantine incoming item under Vault/duplicates/reorg-<run_id>/...",
        },
        "actions": [],
        "keeps": [],
        "warnings": [],
    }
    os.makedirs(os.path.join(vault, "models-gguf"), exist_ok=True)
    os.makedirs(os.path.join(vault, "models-full"), exist_ok=True)
    os.makedirs(os.path.join(vault, "models", "hub"), exist_ok=True)
    os.makedirs(os.path.join(vault, "manifests"), exist_ok=True)
    os.makedirs(os.path.join(vault, "duplicates"), exist_ok=True)

    legacy_man = os.path.join(legacy, "manifests")
    if os.path.isdir(legacy_man) and real(legacy) != real(vault):
        add_action(plan, legacy_man, os.path.join(vault, "manifests", "imported-legacy-root", "manifests"), "import metadata from legacy /mnt/noemaforge-share/Vault", "legacy_metadata", requested_kind="copy")
        plan["warnings"].append({"code": "legacy_vault_not_canonical", "message": "Using noemaforge-lab/data/Vault as canonical; legacy Vault kept as metadata source."})

    inbox_gguf = os.path.join(vault, "inbox", "models-gguf")
    if os.path.isdir(inbox_gguf):
        for child in sorted(Path(inbox_gguf).iterdir(), key=lambda p: p.name.lower()):
            add_action(plan, str(child), os.path.join(vault, "models-gguf", child.name), "promote inbox GGUF drop to canonical models-gguf", "inbox_models_gguf")

    inbox_full = os.path.join(vault, "inbox", "models-full")
    if os.path.isdir(inbox_full):
        for child in sorted(Path(inbox_full).iterdir(), key=lambda p: p.name.lower()):
            add_action(plan, str(child), os.path.join(vault, "models-full", child.name), "promote inbox full-model drop to canonical models-full", "inbox_models_full")

    nested_gguf = os.path.join(vault, "models", "models-gguf")
    if os.path.isdir(nested_gguf):
        for child in sorted(Path(nested_gguf).iterdir(), key=lambda p: p.name.lower()):
            add_action(plan, str(child), os.path.join(vault, "models-gguf", child.name), "flatten nested models/models-gguf to top-level models-gguf", "flatten_models_gguf")

    hub = os.path.join(vault, "models", "hub")
    if os.path.isdir(hub):
        plan["keeps"].append({"path": real(hub), "reason": "HuggingFace cache; keep repo dirs intact, do not split blobs/refs/snapshots"})

    collisions = [a for a in plan["actions"] if a.get("dst_exists")]
    if collisions:
        plan["warnings"].append({
            "code": "incoming_items_quarantined",
            "count": len(collisions),
            "message": "Destination directories already exist; apply will preserve canonical targets and move incoming copies to Vault/duplicates/.",
        })

    try:
        inv = vault_inventory.scan_inventory(share_root, vault)
        dups = inv.get("gguf", {}).get("duplicates") or []
        if dups:
            plan["warnings"].append({"code": "duplicates_not_removed", "count": len(dups), "message": "Duplicate GGUF files were detected but will not be deleted during this reorg."})
    except Exception as e:
        plan["warnings"].append({"code": "inventory_scan_failed", "message": repr(e)})

    return plan


def write_json(path: str, obj: Dict[str, Any]) -> bool:
    """Write JSON when possible.

    Read-only operator commands such as `noemaforge vault audit` may be run
    without sudo. In that case the audit is still printed to stdout and this
    function returns False instead of crashing on /var/lib/noemaforge permissions.
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return True
    except PermissionError:
        return False


def write_plan(plan: Dict[str, Any], path: str = DEFAULT_PLAN) -> None:
    write_json(path, plan)


def audit_plan(plan_path: str = DEFAULT_PLAN, out_path: str = DEFAULT_AUDIT) -> Dict[str, Any]:
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    actions = plan.get("actions") or []
    missing_src: List[Dict[str, Any]] = []
    existing_dst: List[Dict[str, Any]] = []
    cross_device: List[Dict[str, Any]] = []
    by_group: Dict[str, int] = {}
    by_action: Dict[str, int] = {}

    for idx, action in enumerate(actions, 1):
        src = str(action.get("src") or "")
        dst = str(action.get("dst") or "")
        canonical_dst = str(action.get("canonical_dst") or action.get("requested_dst") or "")
        group = str(action.get("group") or "unknown")
        kind = str(action.get("action") or "unknown")
        by_group[group] = by_group.get(group, 0) + 1
        by_action[kind] = by_action.get(kind, 0) + 1
        if not src or not exists(src):
            missing_src.append({"index": idx, "action": kind, "group": group, "src": src, "dst": dst})
            continue
        # For quarantine actions, canonical_dst is expected to exist; it is not a dangerous collision.
        dangerous_dst = dst if kind != "quarantine_duplicate" else ""
        if dangerous_dst and exists(dangerous_dst):
            existing_dst.append({"index": idx, "action": kind, "group": group, "src": src, "dst": dst})
        dst_parent = os.path.dirname(dst)
        if exists(dst_parent):
            try:
                if os.stat(src).st_dev != os.stat(dst_parent).st_dev:
                    cross_device.append({"index": idx, "action": kind, "group": group, "src": src, "dst": dst})
            except OSError:
                pass
    audit = {
        "apiVersion": "noemaforge.vault-reorg/v1",
        "kind": "VaultReorgAudit",
        "updated_at": now(),
        "plan": plan_path,
        "summary": {
            "actions": len(actions),
            "by_group": by_group,
            "by_action": by_action,
            "missing_src": len(missing_src),
            "dangerous_existing_dst_collisions": len(existing_dst),
            "cross_device_moves": len(cross_device),
            "quarantine_actions": by_action.get("quarantine_duplicate", 0),
            "safe_to_apply": len(missing_src) == 0 and len(existing_dst) == 0 and len(cross_device) == 0,
        },
        "missing_src": missing_src[:200],
        "dangerous_existing_dst_collisions": existing_dst[:200],
        "cross_device_moves": cross_device[:200],
        "warnings": plan.get("warnings") or [],
    }
    wrote = write_json(out_path, audit)
    if not wrote:
        audit.setdefault("warnings", []).append({
            "code": "audit_report_not_written_permission",
            "message": f"Could not write audit report to {out_path}; stdout audit is still valid. Run with sudo or pass --json-out to a writable path to persist it.",
        })
    return audit


def apply_plan(plan_path: str = DEFAULT_PLAN, yes: bool = False) -> Dict[str, Any]:
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    if not yes:
        raise RuntimeError("Refusing to apply without --yes. Review with: noemaforge vault show-plan")

    audit = audit_plan(plan_path)
    if not (audit.get("summary") or {}).get("safe_to_apply"):
        raise RuntimeError("Plan audit is not safe_to_apply. Run: noemaforge vault audit")

    applied: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for action in plan.get("actions") or []:
        src = str(action.get("src") or "")
        dst = str(action.get("dst") or "")
        kind = str(action.get("action") or "")
        if not src or not dst or not exists(src):
            skipped.append({**action, "status": "missing_src"})
            continue
        final_dst = dst
        # Backward compatibility: if an old 0.32.2 plan is applied with this
        # hotfix and dst already exists, do NOT create foo.dup2 next to canonical.
        # Quarantine incoming instead.
        if kind in {"move", "copy"} and exists(dst):
            vault = str(plan.get("canonical_vault_root") or os.path.dirname(os.path.dirname(dst)))
            final_dst = quarantine_target(vault, str(action.get("group") or "legacy_plan_collision"), src, str(plan.get("run_id") or run_id()))
            action = {**action, "canonical_dst": dst, "collision_policy": "preserve_canonical_quarantine_incoming", "action": "quarantine_duplicate" if kind == "move" else "copy_quarantine_duplicate"}
            kind = str(action.get("action"))
        os.makedirs(os.path.dirname(final_dst), exist_ok=True)
        if exists(final_dst):
            final_dst = unique_target(final_dst)
        try:
            if kind in {"move", "quarantine_duplicate"}:
                shutil.move(src, final_dst)
            elif kind in {"copy", "copy_quarantine_duplicate"}:
                if os.path.isdir(src):
                    shutil.copytree(src, final_dst)
                else:
                    shutil.copy2(src, final_dst)
            else:
                skipped.append({**action, "status": "unknown_action"})
                continue
            applied.append({**action, "final_dst": final_dst, "status": "applied"})
        except Exception as e:
            skipped.append({**action, "status": "failed", "error": repr(e)})
    report = {
        "apiVersion": "noemaforge.vault-reorg/v1",
        "kind": "VaultReorgApplyReport",
        "applied_at": now(),
        "plan": plan_path,
        "safety_policy": plan.get("safety_policy") or {},
        "applied": applied,
        "skipped": skipped,
        "ok": len([x for x in skipped if x.get("status") == "failed"]) == 0,
    }
    write_json(APPLY_REPORT, report)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="NoemaForge safe Vault reorganization plan/audit/apply")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--share-root", default="/mnt/noemaforge-share")
    p.add_argument("--vault-root", default="")
    p.add_argument("--json-out", default=DEFAULT_PLAN)
    p = sub.add_parser("show-plan")
    p.add_argument("--plan", default=DEFAULT_PLAN)
    p = sub.add_parser("audit")
    p.add_argument("--plan", default=DEFAULT_PLAN)
    p.add_argument("--json-out", default=DEFAULT_AUDIT)
    p = sub.add_parser("apply")
    p.add_argument("--plan", default=DEFAULT_PLAN)
    p.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "plan":
        plan = build_plan(args.share_root, args.vault_root)
        write_plan(plan, args.json_out)
        audit = audit_plan(args.json_out)
        print(json.dumps({
            "ok": True,
            "plan": args.json_out,
            "audit": DEFAULT_AUDIT,
            "actions": len(plan.get("actions") or []),
            "by_action": (audit.get("summary") or {}).get("by_action"),
            "safe_to_apply": (audit.get("summary") or {}).get("safe_to_apply"),
            "warnings": plan.get("warnings") or [],
        }, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "show-plan":
        with open(args.plan, "r", encoding="utf-8") as f:
            plan = json.load(f)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "audit":
        audit = audit_plan(args.plan, args.json_out)
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return 0 if (audit.get("summary") or {}).get("safe_to_apply") else 1
    if args.cmd == "apply":
        try:
            rep = apply_plan(args.plan, yes=bool(args.yes))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e), "hint": "Use: sudo noemaforge vault plan && noemaforge vault audit && sudo noemaforge vault apply --yes"}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        print(json.dumps({"ok": rep.get("ok"), "report": APPLY_REPORT, "applied": len(rep.get("applied") or []), "skipped": len(rep.get("skipped") or [])}, ensure_ascii=False, indent=2))
        return 0 if rep.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
