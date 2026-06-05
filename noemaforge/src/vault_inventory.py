#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/vault_inventory.py
# Zone: vault/index
# Purpose: Build a canonical, role-aware inventory of heterogeneous Vault models/datasets without moving files; preserve logical HF snapshot paths.
# Callers: noemaforge inventory/vault commands, prepare-gui, firstboot_orchestrator, role_tournament.
# Outputs: /var/lib/noemaforge/bootstrap/model-inventory.json and Vault/manifests/model-inventory.json.
# Safety notes: scan is read-only. Physical moves are delegated to vault_reorg.py plan/apply.
# === End NoemaForge File Header ===

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from platform_paths import DEFAULT_PATHS as _pp

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

try:
    import model_capabilities
except Exception:  # pragma: no cover
    sys.path.insert(0, "/opt/noemaforge/src")
    import model_capabilities  # type: ignore

DEFAULT_STATE = str(_pp.data_root / "bootstrap/model-inventory.json")
DEFAULT_SHARE = "/mnt/noemaforge-share"

SHARD_RE = re.compile(r"^(?P<prefix>.+?)(?:[-_. ]+)(?P<idx>\d{3,6})(?:[-_. ]*of[-_. ]*)(?P<total>\d{3,6})\.gguf$", re.IGNORECASE)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def safe_id(raw: str) -> str:
    s = raw.lower()
    s = re.sub(r"\.gguf$", "", s)
    s = re.sub(r"models--", "", s)
    s = s.replace("--", "-")
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = re.sub(r"[-_.]+", "-", s).strip("-_.")
    return s[:120] or "model"


def stat_size(path: str) -> int:
    try:
        return int(os.path.getsize(path))
    except Exception:
        return 0


def parse_shard(path: str) -> Optional[Dict[str, Any]]:
    base = os.path.basename(path)
    m = SHARD_RE.match(base)
    if not m:
        return None
    idx = int(m.group("idx"))
    total = int(m.group("total"))
    prefix = m.group("prefix")
    return {
        "index": idx,
        "total": total,
        "prefix": prefix,
        "logical_key": safe_id(prefix),
        "basename": base,
    }


def canonical_priority(path: str) -> Tuple[int, str]:
    p = path.replace("\\", "/")
    # Keep inbox as a source of incoming drops, never as canonical when curated
    # directories already exist. Check it before /models-gguf/ because
    # /inbox/models-gguf/... also contains that substring.
    if "/inbox/" in p:
        return (7, p)
    # Preferred curated operator-facing GGUF layout:
    #   Vault/models-gguf/qwen25-7b/model.gguf
    if "/models-gguf/" in p:
        # HF-cache-shaped directories accidentally placed under models-gguf are
        # less canonical than curated short-name directories, but still better
        # than nested legacy mirrors.
        if "/models-gguf/models--" in p or "/snapshots/" in p:
            return (1, p)
        return (0, p)
    if "/models/models-gguf/" in p:
        return (2, p)
    if "/models/llm/" in p:
        return (3, p)
    if "/models/hub/" in p and "/snapshots/" in p:
        return (4, p)
    if "/models/hub/" in p and "/blobs/" in p:
        return (9, p)
    return (8, p)


def choose_vault_root(share_root: str = DEFAULT_SHARE, explicit: str = "") -> str:
    if explicit:
        if not os.path.isdir(explicit):
            raise FileNotFoundError(explicit)
        return os.path.realpath(explicit)
    rich = os.path.join(share_root, "noemaforge-lab", "data", "Vault")
    legacy = os.path.join(share_root, "Vault")
    # Prefer the rich Vault when it has data-bearing subtrees. This fixes the old
    # metadata-only /mnt/noemaforge-share/Vault auto-selection bug.
    if os.path.isdir(rich) and any(os.path.isdir(os.path.join(rich, x)) for x in ["models-full", "models-gguf", "models", "datasets"]):
        return os.path.realpath(rich)
    if os.path.isdir(legacy):
        return os.path.realpath(legacy)
    if os.path.isdir(rich):
        return os.path.realpath(rich)
    raise RuntimeError(f"Could not locate Vault under {share_root}")


def iter_files(root: str, pattern: str) -> Iterable[str]:
    r = Path(root)
    if not r.is_dir():
        return
    for p in r.rglob(pattern):
        try:
            if not p.is_file():
                continue
            # Preserve the logical path that matched the glob. HuggingFace
            # snapshots often contain symlinks into blobs/; using realpath() here
            # turns qwen.gguf into a hash-like blob filename and breaks model IDs,
            # duplicate grouping, and capability classification. os.path.getsize()
            # still follows symlinks later, so size checks keep working.
            logical = os.path.abspath(str(p))
            lp = logical.replace("\\", "/")
            if "/models/hub/" in lp and "/blobs/" in lp:
                # Direct blob paths are cache implementation details. Snapshot
                # symlinks are the operator-facing artifacts.
                continue
            yield logical
        except Exception:
            continue


def list_dir_names(path: str, limit: int = 500) -> List[str]:
    p = Path(path)
    if not p.is_dir():
        return []
    out: List[str] = []
    try:
        for child in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            out.append(child.name)
            if len(out) >= limit:
                break
    except Exception:
        pass
    return out


def shallow_files(path: str, limit: int = 80) -> List[str]:
    p = Path(path)
    if not p.is_dir():
        return []
    out: List[str] = []
    try:
        for child in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            if child.is_file() or child.is_symlink():
                out.append(child.name)
            if len(out) >= limit:
                break
    except Exception:
        pass
    return out


def read_config(path: str) -> Dict[str, Any]:
    p = Path(path) / "config.json"
    if not p.is_file():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def discover_gguf(vault_root: str, *, strict_shards: bool = True) -> Dict[str, Any]:
    files = sorted(iter_files(vault_root, "*.gguf"))
    by_key: Dict[str, Dict[str, Any]] = {}
    excluded_shards: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []
    duplicates: List[Dict[str, Any]] = []

    # Build raw groups keyed by normalized model prefix/basename.
    raw_groups: Dict[str, List[str]] = {}
    for path in files:
        si = parse_shard(path)
        key = si["logical_key"] if si else safe_id(os.path.basename(path))
        raw_groups.setdefault(key, []).append(path)

    for key, paths in sorted(raw_groups.items()):
        # Separate sharded paths and singletons.
        sharded = [p for p in paths if parse_shard(p)]
        singles = [p for p in paths if not parse_shard(p)]
        if sharded:
            # There can be duplicate complete shard sets in curated and hub dirs. Split by parent dir.
            sets: Dict[str, List[str]] = {}
            for p in sharded:
                sets.setdefault(os.path.dirname(p), []).append(p)
            valid_sets: List[Dict[str, Any]] = []
            for parent, members in sets.items():
                infos = [parse_shard(p) for p in members]
                infos = [x for x in infos if x]
                total = int(infos[0]["total"]) if infos else 0
                present = sorted({int(x["index"]) for x in infos})
                expected = list(range(1, total + 1)) if total else []
                head = next((p for p in members if (parse_shard(p) or {}).get("index") == 1), "")
                for p in members:
                    si = parse_shard(p) or {}
                    if int(si.get("index") or 0) != 1:
                        excluded_shards.append({"path": p, "reason": "non_head_shard", "shard_index": si.get("index"), "shard_count": si.get("total"), "canonical_first_shard": head})
                if not head:
                    invalid.append({"logical_key": key, "reason": "sharded_set_missing_head", "present_indices": present, "expected_indices": expected, "paths": members})
                    continue
                if strict_shards and present != expected:
                    invalid.append({"logical_key": key, "reason": "incomplete_shard_set", "present_indices": present, "expected_indices": expected, "head": head, "paths": members})
                    continue
                valid_sets.append({
                    "head": head,
                    "members": sorted(members),
                    "present_indices": present,
                    "expected_indices": expected,
                    "shard_count": total,
                    "effective_size_bytes": sum(stat_size(x) for x in members),
                    "priority": canonical_priority(head),
                })
            if valid_sets:
                valid_sets.sort(key=lambda x: x["priority"])
                chosen = valid_sets[0]
                for dup in valid_sets[1:]:
                    duplicates.append({"logical_key": key, "canonical": chosen["head"], "duplicate_head": dup["head"], "reason": "duplicate_sharded_gguf"})
                name = Path(chosen["head"]).stem
                meta = model_capabilities.summarize_model(name, chosen["head"], [os.path.basename(x) for x in chosen["members"]])
                rec = {
                    **meta,
                    "model_id": key,
                    "display_name": name,
                    "artifact_format": "gguf",
                    "source_path": chosen["head"],
                    "canonical_path": chosen["head"],
                    "all_artifacts": chosen["members"],
                    "sharded": True,
                    "shard_count": chosen["shard_count"],
                    "artifact_valid": True,
                    "effective_size_bytes": chosen["effective_size_bytes"],
                }
                by_key[key] = rec
        for p in singles:
            if stat_size(p) <= 0:
                invalid.append({"path": p, "logical_key": safe_id(os.path.basename(p)), "reason": "zero_or_unreadable_size"})
                continue
            skey = safe_id(os.path.basename(p))
            meta = model_capabilities.summarize_model(Path(p).stem, p, [os.path.basename(p)])
            rec = {
                **meta,
                "model_id": skey,
                "display_name": Path(p).stem,
                "artifact_format": "gguf",
                "source_path": p,
                "canonical_path": p,
                "all_artifacts": [p],
                "sharded": False,
                "shard_count": 0,
                "artifact_valid": True,
                "effective_size_bytes": stat_size(p),
            }
            if skey in by_key:
                old = by_key[skey]
                if canonical_priority(p) < canonical_priority(str(old.get("canonical_path") or "")):
                    duplicates.append({"logical_key": skey, "canonical": p, "duplicate": old.get("canonical_path"), "reason": "duplicate_single_gguf_replaced"})
                    by_key[skey] = rec
                else:
                    duplicates.append({"logical_key": skey, "canonical": old.get("canonical_path"), "duplicate": p, "reason": "duplicate_single_gguf"})
            else:
                by_key[skey] = rec

    models = sorted(by_key.values(), key=lambda r: (canonical_priority(str(r.get("canonical_path") or "")), str(r.get("model_id") or "")))
    return {
        "logical_count": len(models),
        "file_count": len(files),
        "models": models,
        "excluded_shards": excluded_shards,
        "invalid": invalid,
        "duplicates": duplicates,
    }


def discover_model_dirs(vault_root: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"models_full": [], "models_hub": [], "models_other": []}
    roots = {
        "models_full": os.path.join(vault_root, "models-full"),
        "models_hub": os.path.join(vault_root, "models", "hub"),
        "models_other": os.path.join(vault_root, "models"),
    }
    for bucket, root in roots.items():
        rp = Path(root)
        if not rp.is_dir():
            continue
        try:
            children = sorted([x for x in rp.iterdir() if x.is_dir()], key=lambda x: x.name.lower())
        except Exception:
            children = []
        for child in children:
            # Avoid double-counting hub/models-gguf as generic "other".
            if bucket == "models_other" and child.name in {"hub", "models-gguf"}:
                continue
            files = shallow_files(str(child), limit=120)
            cfg = read_config(str(child))
            meta = model_capabilities.summarize_model(child.name, str(child), files, cfg)
            rec = {
                **meta,
                "model_id": safe_id(child.name),
                "display_name": child.name,
                "source_path": os.path.realpath(str(child)),
                "artifact_valid": bool(files or list_dir_names(str(child), limit=1)),
                "bucket": bucket,
                "files_sample": files[:30],
            }
            out[bucket].append(rec)
    return out


def discover_datasets(vault_root: str) -> List[Dict[str, Any]]:
    root = Path(vault_root) / "datasets"
    if not root.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    try:
        children = sorted(root.iterdir(), key=lambda x: x.name.lower())
    except Exception:
        children = []
    for child in children:
        name_l = child.name.lower()
        caps: List[str] = []
        roles: List[str] = []
        if any(x in name_l for x in ["mbpp", "humaneval", "swe-bench"]):
            caps = ["code", "debugging"]
            roles = ["dev.work/dev", "dev.work/qa", "dev.work/python_dev"]
        elif any(x in name_l for x in ["squad", "hotpot", "truthful", "longbench", "govreport"]):
            caps = ["chat", "reasoning", "fact_check", "summarization"]
            roles = ["tg.channel/fact_checker", "browser.readinglist/researcher", "writing.story/fact_checker"]
        elif any(x in name_l for x in ["beir", "ms-marco", "retrieval"]):
            caps = ["retrieval", "embedding", "reranking"]
            roles = ["knowledge.vault/researcher", "browser.readinglist/researcher"]
        elif any(x in name_l for x in ["speech", "voice", "golos", "audio"]):
            caps = ["asr", "tts", "audio"]
            roles = ["voice.transcriber", "voice.speaker"]
        elif any(x in name_l for x in ["coco", "davis", "sora", "video"]):
            caps = ["vision", "segmentation", "video_generation"]
            roles = ["vision.segmenter", "video.generator"]
        else:
            caps = ["generic_eval"]
            roles = []
        out.append({
            "dataset_id": safe_id(child.name),
            "name": child.name,
            "path": os.path.realpath(str(child)),
            "kind": "directory" if child.is_dir() else "archive_or_file",
            "capability_hints": caps,
            "role_hints": roles,
        })
    return out


def scan_inventory(share_root: str = DEFAULT_SHARE, vault_root: str = "", strict_shards: bool = True) -> Dict[str, Any]:
    vault = choose_vault_root(share_root, vault_root)
    gguf = discover_gguf(vault, strict_shards=strict_shards)
    dirs = discover_model_dirs(vault)
    datasets = discover_datasets(vault)
    all_models: List[Dict[str, Any]] = []
    for m in gguf["models"]:
        x = dict(m)
        x["bucket"] = "models_gguf"
        all_models.append(x)
    for bucket, items in dirs.items():
        all_models.extend(items)

    by_format: Dict[str, int] = {}
    by_capability: Dict[str, int] = {}
    for m in all_models:
        by_format[str(m.get("artifact_format") or "unknown")] = by_format.get(str(m.get("artifact_format") or "unknown"), 0) + 1
        for cap in m.get("capabilities") or []:
            by_capability[str(cap)] = by_capability.get(str(cap), 0) + 1

    return {
        "apiVersion": "noemaforge.inventory/v1",
        "kind": "ModelInventory",
        "updated_at": now(),
        "share_root": os.path.realpath(share_root),
        "vault_root": vault,
        "legacy_vault_root": os.path.realpath(os.path.join(share_root, "Vault")) if os.path.isdir(os.path.join(share_root, "Vault")) else "",
        "summary": {
            "logical_models_total": len(all_models),
            "gguf_logical_models": gguf["logical_count"],
            "gguf_files": gguf["file_count"],
            "models_full_dirs": len(dirs.get("models_full") or []),
            "models_hub_dirs": len(dirs.get("models_hub") or []),
            "models_other_dirs": len(dirs.get("models_other") or []),
            "datasets": len(datasets),
            "by_artifact_format": by_format,
            "by_capability": by_capability,
            "excluded_non_head_shards": len(gguf.get("excluded_shards") or []),
            "invalid_artifacts": len(gguf.get("invalid") or []),
            "duplicates": len(gguf.get("duplicates") or []),
        },
        "models": all_models,
        "gguf": gguf,
        "datasets": datasets,
        "warnings": build_warnings(share_root, vault, gguf),
    }


def build_warnings(share_root: str, vault: str, gguf: Dict[str, Any]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    legacy = os.path.join(share_root, "Vault")
    if os.path.isdir(legacy) and os.path.realpath(legacy) != os.path.realpath(vault):
        warnings.append({"code": "split_vault_roots", "message": "metadata-only legacy Vault exists beside rich noemaforge-lab/data/Vault", "legacy_vault": os.path.realpath(legacy), "canonical_vault": vault})
    if gguf.get("invalid"):
        warnings.append({"code": "invalid_gguf_artifacts", "count": len(gguf.get("invalid") or [])})
    if gguf.get("duplicates"):
        warnings.append({"code": "duplicate_gguf_copies", "count": len(gguf.get("duplicates") or [])})
    return warnings


def write_inventory(doc: Dict[str, Any], state_path: str = DEFAULT_STATE, write_vault_manifest: bool = True) -> None:
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if write_vault_manifest:
        manifest_dir = os.path.join(str(doc.get("vault_root") or ""), "manifests")
        if manifest_dir and os.path.isdir(os.path.dirname(manifest_dir)):
            try:
                os.makedirs(manifest_dir, exist_ok=True)
                with open(os.path.join(manifest_dir, "model-inventory.json"), "w", encoding="utf-8") as f:
                    json.dump(doc, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            except Exception:
                pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="NoemaForge Vault model/dataset inventory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--share-root", default=DEFAULT_SHARE)
    p.add_argument("--vault-root", default="")
    p.add_argument("--json-out", default=DEFAULT_STATE)
    p.add_argument("--allow-incomplete-shards", action="store_true")
    p.add_argument("--no-vault-manifest", action="store_true")
    p = sub.add_parser("summary")
    p.add_argument("--json", default=DEFAULT_STATE)
    args = ap.parse_args(argv)
    if args.cmd == "scan":
        doc = scan_inventory(args.share_root, args.vault_root, strict_shards=not bool(args.allow_incomplete_shards))
        write_inventory(doc, args.json_out, write_vault_manifest=not bool(args.no_vault_manifest))
        print(json.dumps({"ok": True, "inventory": args.json_out, "vault_root": doc.get("vault_root"), "summary": doc.get("summary")}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "summary":
        with open(args.json, "r", encoding="utf-8") as f:
            doc = json.load(f)
        print(json.dumps(doc.get("summary") or {}, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
