#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/prep/process_inbox.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: tools/prep/process_inbox.py
# Purpose: Prepare or ingest external assets for 'process_inbox'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - process_library
#   - process_vault
#   - main
# Inputs:
#   - --library-root
#   - --vault-root
#   - --workspace-root
#   - --out
#   - Common path inputs: noemaforge.inbox/v1
#   - Imports: __future__, argparse, os, shutil, typing, prep_common
# Output formats / side effects:
#   - copied filesystem artifacts
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""Process (ingest) inbox folders into canonical stores.

This is a *pre-start* helper meant to run on Windows without WSL.

Goals
-----
- Make it easy to drop new files into a known "inbox" folder.
- Move them into canonical locations (Library/Vault) deterministically.
- Keep a small receipt trail for audit/debugging.
- Never block the whole lab run just because one file is weird.

What it does today
------------------
- Library inbox:   <Library>/inbox/**   -> <Library>/sources/inbox/**
- Vault inbox:     <Vault>/inbox/**     -> <Vault>/(models|adapters|bundles)/...

It does *not* parse PDFs, GGUF metadata, Telegram exports, etc.
Those are handled by later streams (or future prep tools).

Exit code
---------
Always 0 unless arguments are invalid.
"""


import argparse
import os
import shutil
from typing import Any, Dict, List, Optional, Tuple

from prep_common import (
    ensure_dir,
    nowz,
    quick_fingerprint,
    safe_relpath,
    stable_id,
    write_json,
)


# === NoemaForge Autodoc Function Header ===
# Function: _is_hidden_or_tmp(name: str)
# Purpose: Implement the routine ' is hidden or tmp'.
# Inputs:
#   - name: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, startswith, endswith
# Returns / emits: bool
# Key locals:
#   - n
# === End NoemaForge Autodoc Function Header ===
def _is_hidden_or_tmp(name: str) -> bool:
    n = name.lower()
    return n.startswith("~") or n.endswith(".tmp") or n.endswith(".part")


# === NoemaForge Autodoc Function Header ===
# Function: _unique_path(path: str)
# Purpose: If path exists, add a .dup-N suffix (before extension).
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - splitext, range, exists, nowz
# Returns / emits: str
# Key locals:
#   - cand, i
# === End NoemaForge Autodoc Function Header ===
def _unique_path(path: str) -> str:
    """If path exists, add a .dup-N suffix (before extension)."""
    if not os.path.exists(path):
        return path

    base, ext = os.path.splitext(path)
    for i in range(1, 10000):
        cand = f"{base}.dup-{i}{ext}"
        if not os.path.exists(cand):
            return cand
    # Fallback: timestamp
    return f"{base}.dup-{nowz()}{ext}"


# === NoemaForge Autodoc Function Header ===
# Function: _move_file(src: str, dst: str)
# Purpose: Move src to dst, making dst unique if needed.
# Inputs:
#   - src: str
#   - dst: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_dir, _unique_path, move, dirname, copy2, remove
# Returns / emits: Tuple[bool, str]
# Side effects:
#   - copies filesystem artifacts
# Key locals:
#   - final
# === End NoemaForge Autodoc Function Header ===
def _move_file(src: str, dst: str) -> Tuple[bool, str]:
    """Move src to dst, making dst unique if needed.

    Returns (moved, final_dst).
    """
    ensure_dir(os.path.dirname(dst) or ".")
    final = _unique_path(dst)
    try:
        shutil.move(src, final)
        return True, final
    except Exception:
        # On Windows, cross-device moves can fail; try copy+delete.
        try:
            shutil.copy2(src, final)
            os.remove(src)
            return True, final
        except Exception:
            return False, final


# === NoemaForge Autodoc Function Header ===
# Function: _write_receipt(receipt_dir: str, kind: str, src_abs: str, src_root: str, dst_abs: str, dst_root: str)
# Purpose: Implement the routine ' write receipt'.
# Inputs:
#   - receipt_dir: str
#   - kind: str
#   - src_abs: str
#   - src_root: str
#   - dst_abs: str
#   - dst_root: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ensure_dir, stat, safe_relpath, stable_id, join, write_json, quick_fingerprint, nowz, replace, int, getattr
# Returns / emits: None
# Key locals:
#   - obj, out, qfp, rel_dst, rel_src, rid, st
# === End NoemaForge Autodoc Function Header ===
def _write_receipt(receipt_dir: str, kind: str, src_abs: str, src_root: str, dst_abs: str, dst_root: str) -> None:
    ensure_dir(receipt_dir)
    st = os.stat(dst_abs)
    rel_src = safe_relpath(src_abs, src_root)
    rel_dst = safe_relpath(dst_abs, dst_root)
    qfp = ""
    try:
        qfp = quick_fingerprint(dst_abs)
    except Exception:
        qfp = ""

    rid = stable_id("rcpt", f"{kind}:{rel_src}->{rel_dst}:{int(st.st_size)}")
    obj: Dict[str, Any] = {
        "apiVersion": "noemaforge.inbox/v1",
        "kind": "IngestReceipt",
        "receipt_id": rid,
        "created_at": nowz(),
        "ingest_kind": kind,
        "src": {"root": src_root.replace("\\", "/"), "rel": rel_src, "abs": src_abs},
        "dst": {"root": dst_root.replace("\\", "/"), "rel": rel_dst, "abs": dst_abs},
        "file": {
            "size": int(st.st_size),
            "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))),
            "quick_fp": qfp,
        },
    }

    out = os.path.join(receipt_dir, f"{nowz()}_{rid}.json")
    write_json(out, obj)


# === NoemaForge Autodoc Function Header ===
# Function: process_library(library_root: str)
# Purpose: Implement the routine 'process library'.
# Inputs:
#   - library_root: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, walk, isdir, _is_hidden_or_tmp, relpath, startswith, _move_file, _write_receipt, append, replace, safe_relpath
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - dst_abs, dst_base, fn, inbox, receipts, rel_in, result, src_abs
# === End NoemaForge Autodoc Function Header ===
def process_library(library_root: str) -> Dict[str, Any]:
    inbox = os.path.join(library_root, "inbox")
    dst_base = os.path.join(library_root, "sources", "inbox")
    receipts = os.path.join(library_root, "_queue", "ingest_receipts")

    result: Dict[str, Any] = {"kind": "library", "moved": 0, "skipped": 0, "errors": 0, "items": []}
    if not os.path.isdir(inbox):
        return result

    for dp, _, fns in os.walk(inbox):
        for fn in fns:
            if _is_hidden_or_tmp(fn):
                result["skipped"] += 1
                continue
            src_abs = os.path.join(dp, fn)
            # Skip if already inside a processed directory.
            rel_in = os.path.relpath(src_abs, inbox)
            if rel_in.replace("\\", "/").startswith("_processed/"):
                result["skipped"] += 1
                continue

            dst_abs = os.path.join(dst_base, rel_in)
            ok, final = _move_file(src_abs, dst_abs)
            if ok:
                result["moved"] += 1
                _write_receipt(receipts, "library", src_abs, inbox, final, library_root)
                result["items"].append({"src": rel_in.replace("\\", "/"), "dst": safe_relpath(final, library_root)})
            else:
                result["errors"] += 1
                result["items"].append({"src": rel_in.replace("\\", "/"), "dst": safe_relpath(final, library_root), "error": "move_failed"})

    return result


# === NoemaForge Autodoc Function Header ===
# Function: _vault_dest_for(vault_root: str, rel_in: str)
# Purpose: Compute destination inside Vault for an inbox entry.
# Inputs:
#   - vault_root: str
#   - rel_in: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - replace, splitext, lower, startswith, isdir, join, split, basename
# Returns / emits: str
# Key locals:
#   - p, top
# === End NoemaForge Autodoc Function Header ===
def _vault_dest_for(vault_root: str, rel_in: str) -> str:
    """Compute destination inside Vault for an inbox entry.

    Project requirement: models may live in N+1 folders (models*, N>=0).
    - If the user pre-classifies by placing files under Vault/inbox/models-gguf/...
      we preserve that bucket.
    - Otherwise, we route by extension, preferring models-gguf for .gguf when present.
    """

    p = rel_in.replace("\\", "/")

    # Allow user to pre-classify by folder (including models-* buckets).
    top = p.split("/", 1)[0].lower() if p else ""
    if top.startswith("models") or top.startswith("adapters") or top.startswith("bundles") or top in {"datasets", "manifests"}:
        return p

    _, ext = os.path.splitext(p.lower())
    if ext == ".gguf":
        if os.path.isdir(os.path.join(vault_root, "models-gguf")):
            return f"models-gguf/inbox/{p}"
        return f"models/inbox/{p}"
    if ext in (".safetensors", ".bin", ".pt", ".pth", ".onnx"):
        return f"models/inbox/{p}"
    if ext in (".zip", ".tar", ".tgz", ".gz"):
        return f"bundles/inbox/{p}"
    if ext in (".json", ".yml", ".yaml") and "manifest" in os.path.basename(p).lower():
        return f"manifests/inbox/{p}"
    return f"misc/inbox/{p}"


# === NoemaForge Autodoc Function Header ===
# Function: process_vault(vault_root: str)
# Purpose: Implement the routine 'process vault'.
# Inputs:
#   - vault_root: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, walk, isdir, _is_hidden_or_tmp, relpath, startswith, _vault_dest_for, _move_file, replace, _write_receipt, append, safe_relpath
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - dest_rel, dst_abs, fn, inbox, receipts, rel_in, result, src_abs
# === End NoemaForge Autodoc Function Header ===
def process_vault(vault_root: str) -> Dict[str, Any]:
    inbox = os.path.join(vault_root, "inbox")
    receipts = os.path.join(vault_root, "_queue", "ingest_receipts")

    result: Dict[str, Any] = {"kind": "vault", "moved": 0, "skipped": 0, "errors": 0, "items": []}
    if not os.path.isdir(inbox):
        return result

    for dp, _, fns in os.walk(inbox):
        for fn in fns:
            if _is_hidden_or_tmp(fn):
                result["skipped"] += 1
                continue
            src_abs = os.path.join(dp, fn)
            rel_in = os.path.relpath(src_abs, inbox)
            if rel_in.replace("\\", "/").startswith("_processed/"):
                result["skipped"] += 1
                continue

            dest_rel = _vault_dest_for(vault_root, rel_in)
            dst_abs = os.path.join(vault_root, dest_rel.replace("/", os.sep))
            ok, final = _move_file(src_abs, dst_abs)
            if ok:
                result["moved"] += 1
                _write_receipt(receipts, "vault", src_abs, inbox, final, vault_root)
                result["items"].append({"src": rel_in.replace("\\", "/"), "dst": safe_relpath(final, vault_root)})
            else:
                result["errors"] += 1
                result["items"].append({"src": rel_in.replace("\\", "/"), "dst": safe_relpath(final, vault_root), "error": "move_failed"})

    return result


# === NoemaForge Autodoc Function Header ===
# Function: main()
# Purpose: Implement the routine 'main'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - bootstrap/microvm/noemaforge-microvm-run.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/brainui.py
#   - src/canary_runner.py
#   - src/doctor.py
#   - src/dream_cycle.py
# Calls:
#   - ArgumentParser, add_argument, parse_args, print, nowz, append, write_json, process_library, process_vault, abspath
# Returns / emits: int
# Side effects:
#   - appends to logs or files
# Key locals:
#   - ap, args, r, summary
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library-root", default="", help="Path to LabRoot/data/Library")
    ap.add_argument("--vault-root", default="", help="Path to LabRoot/data/Vault")
    ap.add_argument("--workspace-root", default="", help="Path to LabRoot/data/Workspace (currently unused)")
    ap.add_argument("--out", default="", help="Optional path to write a JSON summary")
    args = ap.parse_args()

    if not args.library_root and not args.vault_root:
        print("No roots provided; nothing to do.")
        return 0

    summary: Dict[str, Any] = {
        "apiVersion": "noemaforge.inbox/v1",
        "kind": "InboxProcessSummary",
        "created_at": nowz(),
        "results": [],
    }

    if args.library_root:
        summary["results"].append(process_library(os.path.abspath(args.library_root)))

    if args.vault_root:
        summary["results"].append(process_vault(os.path.abspath(args.vault_root)))

    if args.out:
        write_json(os.path.abspath(args.out), summary)

    # Print a short human summary.
    for r in summary["results"]:
        print(f"{r['kind']}: moved={r['moved']} skipped={r['skipped']} errors={r['errors']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
