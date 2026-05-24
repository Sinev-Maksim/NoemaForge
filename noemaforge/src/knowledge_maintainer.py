#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge_maintainer.py
Zone: release/package
Version: 0.31.13.alpha-patched1
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
# File: src/knowledge_maintainer.py
# Purpose: Provide the module 'knowledge_maintainer'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - run
#   - main
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/kg/kg.sqlite, /var/lib/noemaforge/kg/maintainer_state.json
#   - Imports: __future__, json, os, time, typing, epoch, toolvault, knowledge.store
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - SQLite databases
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""knowledge_maintainer.py (v0.17.0)

"Planned" stream module: keep the hypergraph healthy.

This is the spine-side maintenance loop for the knowledge vault:
  1) optional ingest from a queue directory (offline)
  2) run gatekeeper invariant checks (publication gates)
  3) (re)build embeddings index for passages (CPU-friendly hashing by default)

This module is designed to be safe to run when the system is idle.
"""


import json
import os
import time
from typing import Any, Dict, List

from epoch import current_epoch_dir
from toolvault import load_yaml, sha256_file

from knowledge.store import KnowledgeStore
from knowledge.ingest import ingest_text_file
from knowledge.gatekeeper import run_gatekeeper
from knowledge.embedding_worker import embed_passages, embed_claims, embed_concepts


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/caps.py
#   - src/casebase.py
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
# Calls:
#   - strftime, gmtime
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# === NoemaForge Autodoc Function Header ===
# Function: _load_state(path: str)
# Purpose: Implement the routine ' load state'.
# Inputs:
#   - path: str
# Called by:
#   - src/localgateway.py
#   - src/nids_lite.py
# Calls:
#   - isinstance, open, load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, obj
# === End NoemaForge Autodoc Function Header ===
def _load_state(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f) or {}
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {"processed": {}}


# === NoemaForge Autodoc Function Header ===
# Function: _save_state(path: str, obj: Dict[str, Any])
# Purpose: Implement the routine ' save state'.
# Inputs:
#   - path: str
#   - obj: Dict[str, Any]
# Called by:
#   - src/localgateway.py
#   - src/maintenance.py
#   - src/nids_lite.py
# Calls:
#   - makedirs, replace, dirname, open, dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, tmp
# === End NoemaForge Autodoc Function Header ===
def _save_state(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# === NoemaForge Autodoc Function Header ===
# Function: _iter_queue_files(queue_dir: str)
# Purpose: Implement the routine ' iter queue files'.
# Inputs:
#   - queue_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - walk, sorted, isdir, lower, endswith, append, join
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - fn, lf, out
# === End NoemaForge Autodoc Function Header ===
def _iter_queue_files(queue_dir: str) -> List[str]:
    out: List[str] = []
    if not queue_dir or not os.path.isdir(queue_dir):
        return out
    for root, _, files in os.walk(queue_dir):
        for fn in files:
            lf = fn.lower()
            if lf.endswith(".md") or lf.endswith(".txt"):
                out.append(os.path.join(root, fn))
    return sorted(out)


# === NoemaForge Autodoc Function Header ===
# Function: run()
# Purpose: Implement the routine 'run'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/hwscan.py
#   - src/lan_discovery.py
#   - src/localgateway.py
#   - src/localgw_connectors/ipp.py
#   - src/lsm.py
# Calls:
#   - load_yaml, str, KnowledgeStore, _load_state, run_gatekeeper, embed_passages, embed_claims, embed_concepts, current_epoch_dir, join, isinstance, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - db_path, emb_cfg, emb_claim, emb_concept, emb_pass, epoch_dir, fp, gates, h, ingest_cfg, ingest_report, knowledge_policy
# === End NoemaForge Autodoc Function Header ===
def run() -> Dict[str, Any]:
    epoch_dir = current_epoch_dir() or ""
    if not epoch_dir:
        return {"ok": False, "reason": "missing_epoch_dir"}
    knowledge_policy = load_yaml(os.path.join(epoch_dir, "knowledge-policy.yaml"))

    db_path = str((knowledge_policy.get("store") or {}).get("db_path") or "/var/lib/noemaforge/kg/kg.sqlite")
    store = KnowledgeStore(db_path=db_path, store_full_text=bool(knowledge_policy.get("store_full_text", True)))

    # ingest (optional)
    ingest_cfg = (knowledge_policy.get("ingest") or {}) if isinstance(knowledge_policy.get("ingest"), dict) else {}
    queue_dir = str(ingest_cfg.get("queue_dir") or "")
    state_path = str(ingest_cfg.get("state_path") or "/var/lib/noemaforge/kg/maintainer_state.json")
    st = _load_state(state_path)
    processed = st.get("processed") if isinstance(st.get("processed"), dict) else {}

    ingest_report = {"ok": True, "queue_dir": queue_dir, "added_sources": 0, "added_passages": 0, "skipped": 0, "errors": 0}
    if queue_dir:
        for fp in _iter_queue_files(queue_dir):
            try:
                h = sha256_file(fp)
                if processed.get(h):
                    ingest_report["skipped"] += 1
                    continue
                rep = ingest_text_file(store, filepath=fp)
                if rep.get("ok"):
                    ingest_report["added_sources"] += int(rep.get("added_sources") or 0)
                    ingest_report["added_passages"] += int(rep.get("added_passages") or 0)
                    processed[h] = {"path": fp, "ts": _nowz(), "source_id": rep.get("source_ids")}
                else:
                    ingest_report["errors"] += 1
            except Exception:
                ingest_report["errors"] += 1
        st["processed"] = processed
        _save_state(state_path, st)

    # gatekeeper
    gates = run_gatekeeper(store, limit_each=int((knowledge_policy.get("gatekeeper") or {}).get("limit_each") or 500))

    # embeddings
    emb_cfg = (knowledge_policy.get("embeddings") or {}) if isinstance(knowledge_policy.get("embeddings"), dict) else {}
    emb_pass = embed_passages(epoch_dir=epoch_dir, store=store, limit=int(emb_cfg.get("passage_limit") or 500))
    emb_claim = embed_claims(epoch_dir=epoch_dir, store=store, limit=int(emb_cfg.get("claim_limit") or 500))
    emb_concept = embed_concepts(epoch_dir=epoch_dir, store=store, limit=int(emb_cfg.get("concept_limit") or 500))

    return {
        "ok": True,
        "ts": _nowz(),
        "ingest": ingest_report,
        "gates": gates,
        "embeddings": {
            "passages": emb_pass,
            "claims": emb_claim,
            "concepts": emb_concept,
        },
    }


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
#   - run, print, dumps
# Returns / emits: None
# Side effects:
#   - serializes structured data
#   - spawns subprocesses or workers
# Key locals:
#   - rep
# === End NoemaForge Autodoc Function Header ===
def main() -> None:
    rep = run()
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
