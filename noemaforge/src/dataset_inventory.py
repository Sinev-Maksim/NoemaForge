#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/dataset_inventory.py
# Zone: eval/datasets
# Purpose: Inventory Vault datasets and generate tiny role-specific first-start eval packs.
# Callers: noemaforge datasets, prepare-gui, role_tournament, firstboot_orchestrator.
# Safety notes: read-only scan; generated packs are small JSONL files under /var/lib/noemaforge/eval-packs.
# === End NoemaForge File Header ===

import argparse
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

try:
    import vault_inventory
except Exception:  # pragma: no cover
    sys.path.insert(0, "/opt/noemaforge/src")
    import vault_inventory  # type: ignore

DEFAULT_STATE = "/var/lib/noemaforge/bootstrap/dataset-inventory.json"
DEFAULT_PACK_ROOT = "/var/lib/noemaforge/eval-packs/first-start-light"
DEFAULT_ROLE_CATALOG = "/opt/noemaforge/configs/role-catalog.yaml"
DEFAULT_ROLE_EVAL_DATASET_ROOT = os.environ.get("NOEMAFORGE_ROLE_EVAL_DATASET", "/opt/noemaforge/datasets/role_eval_cases")
PACKAGE_ROLE_EVAL_DATASET_ROOT = str(Path(__file__).resolve().parents[1] / "datasets" / "role_eval_cases")
REQUIRED_ROLE_EVAL_FILES = [
    "administrator_smoke.jsonl",
    "dev_work_smoke.jsonl",
    "system_guard_smoke.jsonl",
    "writing_story_smoke.jsonl",
]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def role_safe(role_key: str) -> str:
    return role_key.replace("/", "__").replace(".", "_")


def load_yaml(path: str) -> Dict[str, Any]:
    if yaml is None or not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        obj = yaml.safe_load(f) or {}
    return obj if isinstance(obj, dict) else {}


def scan_datasets(share_root: str = "/mnt/noemaforge-share", vault_root: str = "") -> Dict[str, Any]:
    vault = vault_inventory.choose_vault_root(share_root, vault_root)
    datasets = vault_inventory.discover_datasets(vault)
    by_cap: Dict[str, int] = {}
    by_role: Dict[str, int] = {}
    for d in datasets:
        for cap in d.get("capability_hints") or []:
            by_cap[str(cap)] = by_cap.get(str(cap), 0) + 1
        for role in d.get("role_hints") or []:
            by_role[str(role)] = by_role.get(str(role), 0) + 1
    return {
        "apiVersion": "noemaforge.datasets/v1",
        "kind": "DatasetInventory",
        "updated_at": now(),
        "share_root": os.path.realpath(share_root),
        "vault_root": vault,
        "summary": {"datasets": len(datasets), "by_capability_hint": by_cap, "by_role_hint": by_role},
        "datasets": datasets,
    }


def _jsonl_report(root: str) -> Dict[str, Any]:
    path = Path(root)
    files = sorted(path.glob("*.jsonl")) if path.is_dir() else []
    errors: List[Dict[str, Any]] = []
    records = 0
    for file_path in files:
        try:
            with file_path.open("r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    text = line.strip()
                    if not text:
                        continue
                    records += 1
                    obj = json.loads(text)
                    if not isinstance(obj, dict) or not str(obj.get("id") or "").strip():
                        errors.append({"file": str(file_path), "line": line_no, "reason": "missing_id"})
        except Exception as exc:
            errors.append({"file": str(file_path), "reason": repr(exc)})
    missing = [name for name in REQUIRED_ROLE_EVAL_FILES if not (path / name).is_file()]
    return {
        "root": str(path),
        "exists": path.is_dir(),
        "file_count": len(files),
        "record_count": records,
        "required_files": REQUIRED_ROLE_EVAL_FILES,
        "missing_required_files": missing,
        "errors": errors,
        "ok": path.is_dir() and len(files) > 0 and not missing and not errors,
    }


def _copy_seed_datasets(source_root: str, target_root: str) -> List[Dict[str, str]]:
    source = Path(source_root)
    target = Path(target_root)
    copied: List[Dict[str, str]] = []
    if not source.is_dir():
        return copied
    target.mkdir(parents=True, exist_ok=True)
    for src in sorted(source.glob("*.jsonl")):
        dst = target / src.name
        if dst.exists():
            continue
        shutil.copy2(src, dst)
        copied.append({"source": str(src), "target": str(dst)})
    return copied


def _write_builtin_seed(target_root: str) -> List[Dict[str, str]]:
    target = Path(target_root)
    target.mkdir(parents=True, exist_ok=True)
    mapping = {
        "administrator_smoke.jsonl": BASE_TASKS["admin_ops_light_10"],
        "dev_work_smoke.jsonl": BASE_TASKS["dev_code_light_10"],
        "system_guard_smoke.jsonl": BASE_TASKS["admin_ops_light_10"],
        "writing_story_smoke.jsonl": BASE_TASKS["writing_light_10"],
    }
    written: List[Dict[str, str]] = []
    for filename, tasks in mapping.items():
        dst = target / filename
        if dst.exists():
            continue
        with dst.open("w", encoding="utf-8") as f:
            for index, task in enumerate(tasks[:10], 1):
                rec = dict(task)
                rec.setdefault("ordinal", index)
                rec.setdefault("source", "noemaforge_builtin_dataset_assurance")
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        written.append({"target": str(dst), "source": "builtin"})
    return written


def assure_role_eval_dataset(
    target_root: str = DEFAULT_ROLE_EVAL_DATASET_ROOT,
    *,
    source_root: str = PACKAGE_ROLE_EVAL_DATASET_ROOT,
    allow_builtin_seed: bool = True,
) -> Dict[str, Any]:
    """Ensure firstboot role-eval JSONL datasets exist before scoring."""
    before = _jsonl_report(target_root)
    copied: List[Dict[str, str]] = []
    written: List[Dict[str, str]] = []
    if not before["ok"]:
        try:
            if os.path.realpath(source_root) != os.path.realpath(target_root):
                copied = _copy_seed_datasets(source_root, target_root)
            if allow_builtin_seed:
                after_copy = _jsonl_report(target_root)
                if not after_copy["ok"]:
                    written = _write_builtin_seed(target_root)
        except Exception as exc:
            after_error = _jsonl_report(target_root)
            return {
                "apiVersion": "noemaforge.datasetassurance/v1",
                "kind": "RoleEvalDatasetAssurance",
                "updated_at": now(),
                "ok": False,
                "target_root": target_root,
                "source_root": source_root,
                "before": before,
                "after": after_error,
                "copied": copied,
                "written": written,
                "error": repr(exc),
            }
    after = _jsonl_report(target_root)
    return {
        "apiVersion": "noemaforge.datasetassurance/v1",
        "kind": "RoleEvalDatasetAssurance",
        "updated_at": now(),
        "ok": bool(after["ok"]),
        "target_root": target_root,
        "source_root": source_root,
        "before": before,
        "after": after,
        "copied": copied,
        "written": written,
    }


BASE_TASKS: Dict[str, List[Dict[str, Any]]] = {
    "admin_ops_light_10": [
        {"id": "admin-01", "prompt": "Given a failing systemd service, produce a safe three-step read-only diagnostic plan as JSON with keys commands and risks.", "expect_json": True, "contains_any": ["systemctl", "journalctl"]},
        {"id": "admin-02", "prompt": "Classify this command as read-only or destructive: sudo rm -rf /var/lib/modelstore/models. Return JSON {classification, reason}.", "expect_json": True, "contains_any": ["destructive", "опас"]},
        {"id": "admin-03", "prompt": "Write a safe command block to check whether /mnt/noemaforge-share is mounted. Do not modify files.", "contains_any": ["findmnt", "lsblk"]},
        {"id": "admin-04", "prompt": "A GUI first-start may be killed when display-manager stops. Explain the safer systemd-run approach in 3 bullets.", "contains_any": ["systemd", "journalctl"]},
        {"id": "admin-05", "prompt": "Create a rollback plan for a patch that changes /etc/systemd/system/noemaforge-llama@.service.d/*.conf.", "contains_any": ["backup", "daemon-reload"]},
        {"id": "admin-06", "prompt": "Given MemAvailable=3GiB and a 9GB GGUF model, should we start it? Return JSON {start:boolean, reason}.", "expect_json": True, "contains_any": ["false", "memory", "RAM"]},
        {"id": "admin-07", "prompt": "Summarize the difference between inventory, candidate shortlist, and runtime staged models.", "contains_any": ["inventory", "shortlist", "staged"]},
        {"id": "admin-08", "prompt": "Explain why non-head GGUF shard 0003-of-0005 must not be launched directly.", "contains_any": ["0001", "shard"]},
        {"id": "admin-09", "prompt": "Return JSON status for a prepared but not first-started NoemaForge host.", "expect_json": True},
        {"id": "admin-10", "prompt": "Write a concise runbook to stop llama-server and stale sockets safely.", "contains_any": ["systemctl", "pkill", "sock"]},
    ],
    "dev_code_light_10": [
        {"id": "dev-01", "prompt": "Fix this bash bug: if [ $x -lt 6 ]; then echo low; fi. Make it safe when x is empty.", "contains_any": ["${x", "-z", "set -u"]},
        {"id": "dev-02", "prompt": "Write Python that groups filenames model-00001-of-00003.gguf by shard set and rejects missing shards.", "contains_any": ["regex", "00001", "missing"]},
        {"id": "dev-03", "prompt": "Explain a race condition when deleting a Unix socket before restarting a service.", "contains_any": ["socket", "service"]},
        {"id": "dev-04", "prompt": "Return JSON with a minimal test plan for a CLI subcommand named noemaforge vault plan.", "expect_json": True},
        {"id": "dev-05", "prompt": "Write a jq command that prints .summary.gguf_logical_models from model-inventory.json.", "contains_any": ["jq", "gguf_logical_models"]},
        {"id": "dev-06", "prompt": "Given a traceback FileNotFoundError('/x'), explain the likely cause and one guard.", "contains_any": ["exists", "path"]},
        {"id": "dev-07", "prompt": "Design an idempotent move plan that never overwrites an existing directory.", "contains_any": ["dry", "exists", "suffix"]},
        {"id": "dev-08", "prompt": "Show a Python function signature for scoring 10 role-specific tasks per model.", "contains_any": ["role", "model"]},
        {"id": "dev-09", "prompt": "Explain why global top-8 models is wrong when roles need separate candidate pools.", "contains_any": ["role", "top"]},
        {"id": "dev-10", "prompt": "Return JSON {bug, fix} for: discovery sorted by size before evaluation.", "expect_json": True, "contains_any": ["evaluate", "role"]},
    ],
    "writing_light_10": [
        {"id": "write-01", "prompt": "Compress this requirement into one clear sentence: first-start should prepare system, stop GUI softly, evaluate candidates by role.", "contains_any": ["role", "GUI"]},
        {"id": "write-02", "prompt": "Write a four-line scene where a server is treated like a sleeping giant, without purple prose.", "contains_any": ["server"]},
        {"id": "write-03", "prompt": "Create a concise outline for a technical post about safe model inventory.", "contains_any": ["inventory"]},
        {"id": "write-04", "prompt": "Rewrite: 'it crashed because models are bad' into a careful diagnostic statement.", "contains_any": ["diagnostic", "uncertain"]},
        {"id": "write-05", "prompt": "Return JSON with keys title and bullets for a quick operator note.", "expect_json": True},
        {"id": "write-06", "prompt": "Find the contradiction: 'Do not move files. Apply the move plan now.'", "contains_any": ["contradiction", "move"]},
        {"id": "write-07", "prompt": "Produce a neutral warning that first-start may close GNOME but does not uninstall it.", "contains_any": ["GNOME", "not uninstall"]},
        {"id": "write-08", "prompt": "Summarize a dataset inventory in two bullets.", "contains_any": ["dataset"]},
        {"id": "write-09", "prompt": "Explain top-8-per-role in plain Russian in one paragraph.", "contains_any": ["роль"]},
        {"id": "write-10", "prompt": "Write a tiny changelog entry for version 0.32.2.", "contains_any": ["0.32.2"]},
    ],
    "factcheck_light_10": [
        {"id": "fact-01", "prompt": "A user claims 74 GGUF files means 74 models. Explain why this may be false.", "contains_any": ["shard", "duplicate"]},
        {"id": "fact-02", "prompt": "Return JSON with confidence and caveat for a fact you cannot verify offline.", "expect_json": True},
        {"id": "fact-03", "prompt": "Identify what evidence is needed to prove datasets are used in evaluation.", "contains_any": ["eval", "dataset"]},
        {"id": "fact-04", "prompt": "Explain why screenshots of folders are suggestive but not a complete inventory.", "contains_any": ["inventory", "scan"]},
        {"id": "fact-05", "prompt": "Given two Vault roots, state the safer conclusion before moving files.", "contains_any": ["canonical", "plan"]},
        {"id": "fact-06", "prompt": "List two reasons not to delete duplicate model files during first reorg.", "contains_any": ["duplicate", "delete"]},
        {"id": "fact-07", "prompt": "Return JSON {claim, evidence_needed} for model count 25.", "expect_json": True},
        {"id": "fact-08", "prompt": "Explain how to distinguish a model from a shard file.", "contains_any": ["00001", "of"]},
        {"id": "fact-09", "prompt": "Summarize risks of moving HuggingFace blobs independently.", "contains_any": ["snapshot", "blobs"]},
        {"id": "fact-10", "prompt": "Explain why size should be a safety gate, not a ranking metric.", "contains_any": ["safety", "rank"]},
    ],
    "retrieval_light_10": [
        {"id": "ret-01", "query": "NoemaForge model inventory", "positive": "Inventory lists every logical model, artifact format, capabilities, and runtime status.", "negative": "The weather today is rainy."},
        {"id": "ret-02", "query": "non-head shard danger", "positive": "A GGUF 0003-of-0005 shard cannot be launched directly; use 0001 and complete set.", "negative": "Voice cloning requires a sample speaker."},
        {"id": "ret-03", "query": "dataset role tests", "positive": "Each role should have its own small evaluation pack of ten tasks.", "negative": "Docker Compose starts containers."},
        {"id": "ret-04", "query": "Vault reorg dry run", "positive": "Plan/apply separates proposed file moves from execution.", "negative": "A TTS model generates audio."},
        {"id": "ret-05", "query": "first start headless", "positive": "First-start may stop the display manager after early checks pass.", "negative": "Embedding vectors are normalized."},
        {"id": "ret-06", "query": "capability vector", "positive": "A model can support multiple capabilities and roles at the same time.", "negative": "NTFS supports Windows filenames."},
        {"id": "ret-07", "query": "HuggingFace cache", "positive": "Move model repo directories intact; do not split blobs from snapshots.", "negative": "Swap is a disk-backed memory area."},
        {"id": "ret-08", "query": "top candidates per role", "positive": "Eight candidates are selected for each role, not globally.", "negative": "Piper is an ONNX TTS runtime."},
        {"id": "ret-09", "query": "runtime missing", "positive": "Valid artifacts may be deferred when their runtime is absent.", "negative": "Firefox profiles can limit memory."},
        {"id": "ret-10", "query": "safe launch", "positive": "Start one model at a time and clean sockets/processes between candidates.", "negative": "Vision segmentation outputs masks."},
    ],
    "asr_light_10": [
        {"id": f"asr-{i:02d}", "prompt": "ASR smoke placeholder: runtime must transcribe a short sample if available.", "expect_runtime": "asr"} for i in range(1, 11)
    ],
    "tts_light_10": [
        {"id": f"tts-{i:02d}", "prompt": "TTS smoke placeholder: runtime must generate a non-empty wav if available.", "expect_runtime": "tts"} for i in range(1, 11)
    ],
    "vision_light_10": [
        {"id": f"vision-{i:02d}", "prompt": "Vision smoke placeholder: runtime must process a tiny image if available.", "expect_runtime": "vision"} for i in range(1, 11)
    ],
    "video_light_10": [
        {"id": f"video-{i:02d}", "prompt": "Video smoke placeholder: heavy generation is deferred during first-start.", "expect_runtime": "video", "deferred": True} for i in range(1, 11)
    ],
}


def eval_profile_for_role(role_key: str, role_def: Dict[str, Any]) -> str:
    if role_def.get("eval_pack"):
        return str(role_def["eval_pack"])
    caps = set(role_def.get("required_capabilities") or []) | set(role_def.get("optional_capabilities") or [])
    rk = role_key.lower()
    if "code" in caps or "/dev" in rk or "coder" in rk or "python" in rk or "qa" in rk:
        return "dev_code_light_10"
    if "embedding" in caps or "retrieval" in caps or "researcher" in rk:
        return "retrieval_light_10"
    if "asr" in caps or "transcriber" in rk:
        return "asr_light_10"
    if "tts" in caps or "speaker" in rk:
        return "tts_light_10"
    if "vision" in caps or "segment" in rk or "photo" in rk:
        return "vision_light_10"
    if "video_generation" in caps or "video" in rk:
        return "video_light_10"
    if "writing" in caps or "writer" in rk or "editor" in rk or "story" in rk:
        return "writing_light_10"
    if "fact" in rk or "checker" in rk:
        return "factcheck_light_10"
    return "admin_ops_light_10" if "admin" in rk or "operator" in rk or "surgeon" in rk else "dev_code_light_10"


def build_eval_packs(role_catalog_path: str = DEFAULT_ROLE_CATALOG, out_root: str = DEFAULT_PACK_ROOT, dataset_inventory_path: str = DEFAULT_STATE) -> Dict[str, Any]:
    catalog = load_yaml(role_catalog_path)
    roles = (catalog.get("roles") or {}) if isinstance(catalog, dict) else {}
    os.makedirs(out_root, exist_ok=True)
    written: List[Dict[str, Any]] = []
    for role_key, role_def in sorted(roles.items()):
        if not isinstance(role_def, dict):
            role_def = {}
        profile = eval_profile_for_role(str(role_key), role_def)
        tasks = BASE_TASKS.get(profile, BASE_TASKS["dev_code_light_10"])
        out_path = os.path.join(out_root, f"{role_safe(str(role_key))}.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for idx, task in enumerate(tasks[:10], 1):
                rec = dict(task)
                rec.setdefault("role_key", role_key)
                rec.setdefault("eval_profile", profile)
                rec.setdefault("ordinal", idx)
                rec.setdefault("source", "noemaforge_builtin_light_pack_v0.32.2")
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        written.append({"role_key": role_key, "eval_profile": profile, "path": out_path, "tasks": min(10, len(tasks))})
    index = {"apiVersion": "noemaforge.evalpacks/v1", "kind": "FirstStartEvalPacks", "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "out_root": out_root, "packs": written, "dataset_inventory": dataset_inventory_path}
    with open(os.path.join(out_root, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return index


def write_dataset_inventory(doc: Dict[str, Any], path: str = DEFAULT_STATE) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_dataset_assurance(doc: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="NoemaForge dataset inventory and first-start light eval-pack builder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("--share-root", default="/mnt/noemaforge-share")
    p.add_argument("--vault-root", default="")
    p.add_argument("--json-out", default=DEFAULT_STATE)
    p = sub.add_parser("build-packs")
    p.add_argument("--role-catalog", default=DEFAULT_ROLE_CATALOG)
    p.add_argument("--out-root", default=DEFAULT_PACK_ROOT)
    p.add_argument("--dataset-inventory", default=DEFAULT_STATE)
    p = sub.add_parser("assure")
    p.add_argument("--target-root", default=DEFAULT_ROLE_EVAL_DATASET_ROOT)
    p.add_argument("--source-root", default=PACKAGE_ROLE_EVAL_DATASET_ROOT)
    p.add_argument("--json-out", default="")
    p.add_argument("--no-builtin-seed", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "scan":
        doc = scan_datasets(args.share_root, args.vault_root)
        write_dataset_inventory(doc, args.json_out)
        print(json.dumps({"ok": True, "dataset_inventory": args.json_out, "summary": doc.get("summary")}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "build-packs":
        index = build_eval_packs(args.role_catalog, args.out_root, args.dataset_inventory)
        print(json.dumps({"ok": True, "eval_pack_index": os.path.join(args.out_root, "index.json"), "packs": len(index.get("packs") or [])}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "assure":
        doc = assure_role_eval_dataset(args.target_root, source_root=args.source_root, allow_builtin_seed=not bool(args.no_builtin_seed))
        if args.json_out:
            write_dataset_assurance(doc, args.json_out)
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0 if doc.get("ok") else 74
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
