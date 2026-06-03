#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/runtime_safety.py
# Zone: spinal/runtime-safety
# Purpose: Shared guards for ModelStore/runtime launch safety: block non-head GGUF shards, validate backend ids, repair unsafe ModelStore dirs, and smoke-check main backend.
# Callers: llm_backends_manager.py, model_registry.py, role_tournament.py, firstboot_eval.py, firstboot_orchestrator.py, noemaforge CLI.
# Safety notes:
#   - A sharded GGUF model may only be launched through shard 00001-of-N.
#   - Non-head shards (00002/00003/.../000NN-of-N) are never valid backend ids or runtime artifacts.
#   - The module is conservative: uncertain ModelStore entries are skipped/quarantined rather than started.
# === End NoemaForge File Header ===

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from platform_paths import DEFAULT_PATHS as _pp

MODELSTORE_ROOT = os.environ.get("NOEMAFORGE_MODELSTORE_ROOT", str(_pp.data_root.parent / "modelstore"))
STATE_DIR = str(_pp.data_root / "bootstrap")
INVENTORY_PATH = os.path.join(STATE_DIR, "model-inventory.json")
LEGACY_SHARE_ROOT = "/mnt/brainos-share"
CANONICAL_SHARE_ROOT = "/mnt/noemaforge-share"
LEGACY_LAB_ROOT = "/mnt/brainos-share/brainos-lab"
CANONICAL_LAB_ROOT = "/mnt/noemaforge-share/noemaforge-lab"

# Matches common shard naming variants:
#   model-00001-of-00005.gguf
#   model.00001.of.00005.gguf
#   model 00001 of 00005.gguf
#   model_00001-of-00005.gguf
SHARD_RE = re.compile(r"(?:^|[^0-9])0*([0-9]{1,5})\s*(?:[-_. ]+|)of(?:[-_. ]+|)0*([0-9]{1,5})(?=[^0-9]|$)", re.IGNORECASE)
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,180}$")


def shard_match(text: str) -> Optional[Tuple[int, int]]:
    s = str(text or "")
    # Prefer basename to avoid false positives in parent dirs; callers can pass full path too.
    for m in SHARD_RE.finditer(s):
        try:
            idx = int(m.group(1))
            total = int(m.group(2))
        except Exception:
            continue
        if total > 1 and 1 <= idx <= total:
            return idx, total
    return None


def is_sharded_head(text: str) -> bool:
    sm = shard_match(text)
    return bool(sm and sm[0] == 1)


def is_non_head_shard(text: str) -> bool:
    sm = shard_match(text)
    return bool(sm and sm[0] > 1)


def safe_backend_id(model_id: str) -> bool:
    s = str(model_id or "").strip()
    return bool(SAFE_ID_RE.match(s)) and not is_non_head_shard(s)


def _realpath(path: str) -> str:
    try:
        return os.path.realpath(path)
    except Exception:
        return str(path)


def canonicalize_noemaforge_path(path: str, *, require_existing: bool = False) -> str:
    """Map legacy share paths to canonical NoemaForge paths.

    After the BrainOS -> NoemaForge rename, ModelStore entries and older
    Vault indexes can still resolve through /mnt/brainos-share. Launcher paths
    should always normalize to the NoemaForge mount; artifact validation can ask
    for existence-gated normalization to avoid masking a missing legacy target.
    """
    s = str(path or "")
    mappings = [
        (LEGACY_LAB_ROOT, CANONICAL_LAB_ROOT),
        (LEGACY_SHARE_ROOT, CANONICAL_SHARE_ROOT),
    ]
    for old_root, new_root in mappings:
        if s == old_root or s.startswith(old_root + "/"):
            candidate = new_root + s[len(old_root):]
            if not require_existing:
                return candidate
            try:
                return candidate if os.path.exists(candidate) else s
            except Exception:
                return s
    return s


def normalize_launcher_paths(*, share_root: str, vault_root: str = "", shortlist_file: str = "") -> Dict[str, Any]:
    share_in = str(share_root or CANONICAL_SHARE_ROOT).strip() or CANONICAL_SHARE_ROOT
    vault_in = str(vault_root or "").strip()
    shortlist_in = str(shortlist_file or "").strip()
    share_out = canonicalize_noemaforge_path(share_in)
    vault_out = canonicalize_noemaforge_path(vault_in) if vault_in else ""
    shortlist_out = canonicalize_noemaforge_path(shortlist_in) if shortlist_in else ""
    return {
        "share_root_input": share_in,
        "vault_root_input": vault_in,
        "shortlist_file_input": shortlist_in,
        "share_root": share_out,
        "vault_root": vault_out,
        "shortlist_file": shortlist_out,
        "changed": share_in != share_out or vault_in != vault_out or shortlist_in != shortlist_out,
        "canonical_share_root": CANONICAL_SHARE_ROOT,
    }


def _canonical_noemaforge_path(path: str) -> str:
    """Existence-gated canonicalization for artifact validation."""
    return canonicalize_noemaforge_path(path, require_existing=True)


def validate_artifact_path(path: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Return (ok, reason, meta) for a runtime artifact path."""
    p = str(path or "").strip()
    if not p:
        return False, "missing_artifact_path", {}
    base = os.path.basename(p)
    rp = _realpath(p)
    rbase = os.path.basename(rp)
    sm = shard_match(base) or shard_match(rbase)
    canon = _canonical_noemaforge_path(rp)
    if canon != rp:
        rp = canon
    meta: Dict[str, Any] = {"path": p, "realpath": rp}
    if sm:
        meta.update({"sharded": True, "shard_index": sm[0], "shard_count": sm[1]})
    else:
        meta.update({"sharded": False})
    if is_non_head_shard(base) or is_non_head_shard(rbase):
        return False, "non_head_shard", meta
    if p and not os.path.exists(p) and not os.path.exists(rp):
        return False, "artifact_missing", meta
    return True, "ok", meta


def read_manifest(mdir: Path) -> Dict[str, Any]:
    path = mdir / "manifest.yaml"
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore
        obj = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def artifact_for_model_dir(model_dir: Path) -> str:
    man = read_manifest(model_dir)
    ap = str(man.get("artifact_path") or man.get("source_path") or "").strip()
    if ap:
        return ap if ap.startswith("/") else str(model_dir / ap)
    legacy = model_dir / "model.gguf"
    if legacy.exists() or legacy.is_symlink():
        return str(legacy)
    return ""


def validate_modelstore_backend(modelstore_root: str, backend_id: str) -> Tuple[bool, str, Dict[str, Any]]:
    bid = str(backend_id or "").strip()
    meta: Dict[str, Any] = {"backend_id": bid, "modelstore_root": modelstore_root}
    if not safe_backend_id(bid):
        return False, "unsafe_backend_id_non_head_or_invalid", meta
    mdir = Path(modelstore_root) / "models" / bid
    meta["model_dir"] = str(mdir)
    if not mdir.is_dir():
        return False, "model_dir_missing", meta
    ap = artifact_for_model_dir(mdir)
    meta["artifact_path"] = ap
    ok, reason, ameta = validate_artifact_path(ap)
    meta["artifact_validation"] = ameta
    if not ok:
        return False, reason, meta
    return True, "ok", meta


def iter_model_dirs(modelstore_root: str = MODELSTORE_ROOT) -> Iterable[Path]:
    models = Path(modelstore_root) / "models"
    if not models.exists():
        return []
    return [p for p in sorted(models.iterdir()) if p.is_dir() and not p.name.startswith(".")]


def scan_modelstore_safety(modelstore_root: str = MODELSTORE_ROOT) -> Dict[str, Any]:
    safe: List[Dict[str, Any]] = []
    unsafe: List[Dict[str, Any]] = []
    for d in iter_model_dirs(modelstore_root):
        ok, reason, meta = validate_modelstore_backend(modelstore_root, d.name)
        rec = {"model_id": d.name, "ok": ok, "reason": reason, **meta}
        (safe if ok else unsafe).append(rec)
    return {
        "ok": len(unsafe) == 0,
        "modelstore_root": modelstore_root,
        "safe_count": len(safe),
        "unsafe_count": len(unsafe),
        "safe": safe,
        "unsafe": unsafe,
    }


def safe_move(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    final = dst
    n = 1
    while final.exists():
        final = Path(str(dst) + f".dup{n}")
        n += 1
    shutil.move(str(src), str(final))
    return final


def choose_safe_single_from_inventory(inventory_path: str = INVENTORY_PATH) -> Optional[Dict[str, Any]]:
    if not os.path.exists(inventory_path):
        return None
    try:
        doc = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
    except Exception:
        return None
    models = doc.get("models") or []
    candidates: List[Dict[str, Any]] = []
    for m in models:
        if str(m.get("artifact_format") or "") != "gguf":
            continue
        if m.get("sharded"):
            continue
        p = str(m.get("source_path") or m.get("canonical_path") or m.get("path") or "")
        ok, reason, _ = validate_artifact_path(p)
        if ok and os.path.exists(p):
            candidates.append(m)
    if not candidates:
        # Older inventories have .gguf.models.
        for m in (doc.get("gguf", {}) or {}).get("models", []) or []:
            if m.get("sharded"):
                continue
            p = str(m.get("canonical_path") or m.get("source_path") or m.get("path") or "")
            ok, reason, _ = validate_artifact_path(p)
            if ok and os.path.exists(p):
                candidates.append(m)
    if not candidates:
        return None
    prefs = [
        "qwen2-5-coder-3b", "qwen2.5-coder-3b", "qwen2-5-3b", "qwen2.5-3b",
        "microsoft-phi-4-mini", "phi-4-mini", "granite-3-3-2b", "granite-2b",
        "phi-3-mini", "qwen2-5-coder-0-5b", "qwen2-5-1-5b", "falcon3", "smollm2",
    ]
    def score(m: Dict[str, Any]) -> Tuple[int, int]:
        mid = (str(m.get("model_id") or "") + " " + str(m.get("display_name") or "")).lower()
        size = int(m.get("effective_size_bytes") or m.get("size_bytes") or 0)
        rank = 999
        for i, p in enumerate(prefs):
            if p in mid:
                rank = i
                break
        if size > 6 * 1024 ** 3:
            rank += 200
        return rank, size
    return sorted(candidates, key=score)[0]


def repair_modelstore(modelstore_root: str = MODELSTORE_ROOT, inventory_path: str = INVENTORY_PATH, ensure_main: bool = True) -> Dict[str, Any]:
    run_id = time.strftime("%Y%m%d-%H%M%S")
    quarantine = Path(modelstore_root) / "quarantine" / f"runtime-unsafe-{run_id}"
    moved: List[Dict[str, str]] = []
    before = scan_modelstore_safety(modelstore_root)
    for rec in before.get("unsafe") or []:
        d = Path(str(rec.get("model_dir") or ""))
        if d.is_dir():
            dst = safe_move(d, quarantine / d.name)
            moved.append({"model_id": d.name, "src": str(d), "dst": str(dst), "reason": str(rec.get("reason") or "")})
    main_info: Dict[str, Any] = {}
    if ensure_main:
        ok, reason, meta = validate_modelstore_backend(modelstore_root, "main")
        if not ok:
            chosen = choose_safe_single_from_inventory(inventory_path)
            if chosen:
                p = str(chosen.get("source_path") or chosen.get("canonical_path") or chosen.get("path") or "")
                main_dir = Path(modelstore_root) / "models" / "main"
                if main_dir.exists():
                    safe_move(main_dir, quarantine / "main-before-repair")
                main_dir.mkdir(parents=True, exist_ok=True)
                link = main_dir / "model.gguf"
                if link.exists() or link.is_symlink():
                    link.unlink()
                os.symlink(p, str(link))
                (main_dir / "noemaforge-model.json").write_text(json.dumps({
                    "model_id": chosen.get("model_id"),
                    "display_name": chosen.get("display_name"),
                    "source": p,
                    "repair_run_id": run_id,
                    "reason": "safe single-file fallback for main",
                }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                main_info = {"repaired": True, "model_id": chosen.get("model_id"), "source": p}
            else:
                main_info = {"repaired": False, "reason": "no_safe_single_model_found"}
        else:
            main_info = {"repaired": False, "reason": "main_already_safe", "meta": meta}
    after = scan_modelstore_safety(modelstore_root)
    return {"ok": after.get("unsafe_count", 0) == 0, "run_id": run_id, "moved": moved, "main": main_info, "before": {"safe_count": before.get("safe_count"), "unsafe_count": before.get("unsafe_count")}, "after": {"safe_count": after.get("safe_count"), "unsafe_count": after.get("unsafe_count")}, "unsafe_after": after.get("unsafe") or []}


def smoke_backend_health(sock: str = "/run/noemaforge/llm/backends/main.sock", timeout: int = 10) -> Tuple[bool, str]:
    if not os.path.exists(sock):
        return False, "socket_missing"
    try:
        out = subprocess.check_output(["curl", "-fsS", "--max-time", str(timeout), "--unix-socket", sock, "http://localhost:8080/health"], stderr=subprocess.STDOUT)
        return True, out.decode("utf-8", errors="replace").strip()
    except subprocess.CalledProcessError as e:
        return False, (e.output or b"").decode("utf-8", errors="replace")[:4000]
    except Exception as e:
        return False, repr(e)


STRUCTURED_RUNTIME_KEYS = {
    "artifact", "artifact_path", "artifact_realpath", "artifact_validation",
    "backend", "backend_id", "canonical_path", "canonical_first_shard",
    "file", "filename", "gguf", "main", "model", "model_dir", "model_id",
    "model_path", "path", "realpath", "runtime_artifact", "source",
    "source_path", "staged_models", "selected", "selected_model_ids",
}

FREE_TEXT_RUNTIME_KEYS = {
    "answer", "completion", "content", "description", "explanation", "message",
    "negative", "notes", "positive", "prompt", "query", "reply", "response",
    "stderr", "stdout", "text", "transcript",
}


def _structured_runtime_key(key: str) -> bool:
    k = str(key or "").lower().replace("-", "_")
    if k in FREE_TEXT_RUNTIME_KEYS:
        return False
    if k in STRUCTURED_RUNTIME_KEYS:
        return True
    return any(tok in k for tok in ("artifact", "backend", "canonical", "gguf", "model", "path", "realpath", "source"))


def _free_text_runtime_key(key: str) -> bool:
    k = str(key or "").lower().replace("-", "_")
    return k in FREE_TEXT_RUNTIME_KEYS or any(tok in k for tok in ("answer", "completion", "explanation", "prompt", "reply", "response", "stdout", "stderr"))


def assert_candidate_doc_safe(doc: Any) -> Tuple[bool, List[str]]:
    """Validate runtime-safety using structured runtime fields only.

    This intentionally does *not* scan free-form model answers/prompts.  The
    first-start eval set can ask models to explain why a non-head shard such as
    0003-of-0005 must not be launched.  Those answer strings are evidence of
    correct safety reasoning, not unsafe runtime artifacts.  Only structured
    fields that can represent runtime paths, model ids, backend ids or selected
    artifacts are considered blocking.
    """
    bad: List[str] = []

    def walk(x: Any, key: str = "", structured_context: bool = False) -> None:
        if isinstance(x, dict):
            reason = str(x.get("reason") or "")
            allow_excluded = reason == "non_head_shard" and ("canonical_first_shard" in x)
            for kk, vv in x.items():
                sk = _structured_runtime_key(str(kk))
                fk = _free_text_runtime_key(str(kk))
                if isinstance(vv, str):
                    if sk and not fk and is_non_head_shard(vv) and not allow_excluded:
                        bad.append(vv)
                    continue
                walk(vv, str(kk), structured_context=(structured_context or sk) and not fk)
        elif isinstance(x, list):
            for v in x:
                if isinstance(v, str):
                    if structured_context and is_non_head_shard(v):
                        bad.append(v)
                else:
                    walk(v, key, structured_context=structured_context)
        elif isinstance(x, str):
            if structured_context and is_non_head_shard(x):
                bad.append(x)

    walk(doc)
    return len(bad) == 0, bad


def collect_text_non_head_mentions(doc: Any, limit: int = 20) -> List[str]:
    """Return non-blocking warnings where free text mentions non-head shards."""
    out: List[str] = []

    def walk(x: Any, key: str = "") -> None:
        if len(out) >= limit:
            return
        if isinstance(x, dict):
            for kk, vv in x.items():
                if _free_text_runtime_key(str(kk)):
                    if isinstance(vv, str) and is_non_head_shard(vv):
                        out.append(vv[:400])
                    elif isinstance(vv, (dict, list)):
                        walk(vv, str(kk))
                else:
                    walk(vv, str(kk))
        elif isinstance(x, list):
            for v in x:
                walk(v, key)
        elif isinstance(x, str) and _free_text_runtime_key(key) and is_non_head_shard(x):
            out.append(x[:400])

    walk(doc)
    return out



def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="NoemaForge runtime safety guard")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--modelstore-root", default=MODELSTORE_ROOT)
    p.add_argument("--json-out", default="")
    p = sub.add_parser("repair")
    p.add_argument("--modelstore-root", default=MODELSTORE_ROOT)
    p.add_argument("--inventory", default=INVENTORY_PATH)
    p.add_argument("--no-main", action="store_true")
    p.add_argument("--json-out", default=os.path.join(STATE_DIR, "runtime-safety-repair.json"))
    p = sub.add_parser("smoke-main")
    p.add_argument("--sock", default="/run/noemaforge/llm/backends/main.sock")
    p.add_argument("--timeout", type=int, default=10)
    args = ap.parse_args(argv)
    if args.cmd == "check":
        doc = scan_modelstore_safety(args.modelstore_root)
        if args.json_out:
            Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.json_out).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0 if doc.get("ok") else 70
    if args.cmd == "repair":
        doc = repair_modelstore(args.modelstore_root, args.inventory, ensure_main=not args.no_main)
        if args.json_out:
            Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.json_out).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0 if doc.get("ok") else 71
    if args.cmd == "smoke-main":
        ok, msg = smoke_backend_health(args.sock, args.timeout)
        print(json.dumps({"ok": ok, "message": msg, "sock": args.sock}, ensure_ascii=False, indent=2))
        return 0 if ok else 72
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
