#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_inventory_normalize.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Existing module notes:
Canonical model inventory normalization for public MWP launcher flows.

The normalizer is deliberately small and dependency-free. It takes discovered
GGUF paths or a model-inventory report and returns runtime-safe candidates:
full GGUF files and first shards only. Non-head shard tails are explicit rejects.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

SHARD_RE = re.compile(r"^(?P<prefix>.+?)(?:[-_. ]+)(?P<idx>\d{3,6})(?:[-_. ]*of[-_. ]*)(?P<total>\d{3,6})\.gguf$", re.IGNORECASE)


def safe_id(raw: str) -> str:
    s = raw.lower()
    s = re.sub(r"\.gguf$", "", s)
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = re.sub(r"[-_.]+", "-", s).strip("-_.")
    return s[:140] or "model"


def parse_shard(path: str) -> dict[str, Any] | None:
    base = os.path.basename(path)
    m = SHARD_RE.match(base)
    if not m:
        return None
    return {"index": int(m.group("idx")), "total": int(m.group("total")), "prefix": m.group("prefix"), "basename": base}


def normalize_paths(paths: list[str], *, require_complete: bool = False) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[str]] = {}
    singles: list[str] = []
    for p in sorted(set(paths)):
        if not p.lower().endswith(".gguf"):
            continue
        si = parse_shard(p)
        if not si:
            singles.append(p)
            continue
        groups.setdefault((str(Path(p).parent), si["prefix"]), []).append(p)

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for p in singles:
        accepted.append({"model_id": safe_id(Path(p).stem), "path": p, "sharded": False, "reason": "single_file"})

    for (_parent, prefix), members in sorted(groups.items()):
        metas = [(p, parse_shard(p) or {}) for p in members]
        totals = {m.get("total") for _, m in metas if m}
        total = int(next(iter(totals))) if len(totals) == 1 and next(iter(totals)) else 0
        present = sorted(int(m.get("index", 0)) for _, m in metas if m.get("index"))
        head = next((p for p, m in metas if int(m.get("index", 0)) == 1), "")
        complete = bool(total and present == list(range(1, total + 1)))
        for p, m in metas:
            idx = int(m.get("index", 0))
            if idx != 1:
                rejected.append({"path": p, "reason": "non_head_shard", "shard_index": idx, "shard_count": total, "canonical_first_shard": head})
        if not head:
            rejected.append({"path": members[0], "reason": "sharded_set_missing_head", "present_indices": present, "shard_count": total})
            continue
        if require_complete and not complete:
            rejected.append({"path": head, "reason": "incomplete_shard_set", "present_indices": present, "shard_count": total})
            continue
        accepted.append({"model_id": safe_id(prefix), "path": head, "sharded": True, "shard_index": 1, "shard_count": total, "complete_shard_set": complete, "reason": "head_shard"})

    return {"ok": True, "candidate_count": len(accepted), "rejected_count": len(rejected), "candidates": accepted, "rejected": rejected}


def paths_from_report(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for key in ("paths", "files"):
            if isinstance(obj.get(key), list):
                out.extend(str(x) for x in obj[key])
        for key in ("candidates", "models", "items"):
            vals = obj.get(key)
            if isinstance(vals, list):
                for item in vals:
                    if isinstance(item, str):
                        out.append(item)
                    elif isinstance(item, dict):
                        for k in ("path", "artifact_path", "source_path", "head", "canonical"):
                            if item.get(k):
                                out.append(str(item[k])); break
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and item.get("path"):
                out.append(str(item["path"]))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normalize GGUF candidates; reject non-head shards.")
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--from-json", help="Read existing inventory/report JSON.")
    ap.add_argument("--require-complete", action="store_true")
    ap.add_argument("--out")
    ns = ap.parse_args(argv)
    paths = list(ns.paths)
    if ns.from_json:
        obj = json.loads(Path(ns.from_json).read_text(encoding="utf-8"))
        paths.extend(paths_from_report(obj))
    if not paths and not sys.stdin.isatty():
        paths.extend(line.strip() for line in sys.stdin if line.strip())
    doc = normalize_paths(paths, require_complete=ns.require_complete)
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if ns.out:
        Path(ns.out).parent.mkdir(parents=True, exist_ok=True)
        Path(ns.out).write_text(text + "\n", encoding="utf-8")
        print(ns.out)
    else:
        print(text)
    return 0 if doc["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
