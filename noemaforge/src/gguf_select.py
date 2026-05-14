#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/gguf_select.py
# Zone: prep/spinal
# Purpose: Discover, validate, shortlist, and stage GGUF model artifacts safely for first launch.
# Callers: firstboot_orchestrator.py, model_registry.py, llama_start.py, noemaforge-first-launch.sh.
# Inputs: Vault/model directories, optional shortlist text, ModelStore path.
# Outputs: JSON discovery reports, ModelStore manifests/symlinks, validation summaries.
# Safety notes:
#   - Multi-part GGUF sets are represented by the first shard only.
#   - Non-head shards such as 00003-of-00005.gguf are rejected, never promoted to main.
#   - Incomplete shard sets fail early in strict mode.
# === End NoemaForge File Header ===


import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

# Accept both common llama.cpp names and the human-written variant that caused the issue:
#   model-00001-of-00005.gguf
#   model-0001_of_0005.gguf
#   model 0003 of 0005.gguf
_SHARD_RE = re.compile(
    r"^(?P<prefix>.*?)(?:[-_.\s])?(?P<idx>\d{1,5})\s*(?:[-_\s])?of\s*(?:[-_\s])?(?P<total>\d{1,5})(?P<suffix>.*?)\.gguf$",
    re.IGNORECASE,
)
_SAFE_ID_RE = re.compile(r"[^a-z0-9._-]+")


@dataclass(frozen=True)
class ShardInfo:
    index: int
    total: int
    group_key: str
    canonical_prefix: str
    suffix: str


@dataclass(frozen=True)
class Candidate:
    path: str
    basename: str
    model_id_hint: str
    sharded: bool
    shard_index: int
    shard_count: int
    shard_paths: List[str]
    size_bytes: int
    effective_size_bytes: int
    source_root: str


def _json_dump(obj: Any, path: str = "") -> None:
    data = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)
    if path:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data + "\n")
    else:
        print(data)


def _safe_id(raw: str) -> str:
    s = str(raw or "").strip()
    s = s[:-5] if s.lower().endswith(".gguf") else s
    s = s.lower().replace(" ", "_")
    s = _SAFE_ID_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("._-")
    return s[:80].strip("._-") or "model"


def shard_info(path_or_name: str) -> Optional[ShardInfo]:
    """Return multi-part GGUF shard metadata, or None for a normal single GGUF."""
    name = os.path.basename(str(path_or_name))
    m = _SHARD_RE.match(name)
    if not m:
        return None
    try:
        idx = int(m.group("idx"))
        total = int(m.group("total"))
    except Exception:
        return None
    if idx <= 0 or total <= 1 or idx > total:
        return None
    prefix = str(m.group("prefix") or "").strip(" ._-")
    suffix = str(m.group("suffix") or "").strip(" ._-")
    # Group inside the same real directory. This prevents merging unrelated downloads.
    parent = os.path.realpath(os.path.dirname(str(path_or_name)))
    group_key = f"{parent}|{prefix.lower()}|{suffix.lower()}|{total}"
    return ShardInfo(index=idx, total=total, group_key=group_key, canonical_prefix=prefix, suffix=suffix)


def model_id_hint_for_path(path: str) -> str:
    base = os.path.basename(path)
    si = shard_info(path)
    if si:
        raw = si.canonical_prefix or base
        if si.suffix:
            raw = f"{raw}-{si.suffix}"
        return _safe_id(raw)
    return _safe_id(base)


def _load_shortlist(path: str) -> List[str]:
    if not path or not os.path.isfile(path):
        return []
    out: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s)
    return out


def _shortlist_match(path: str, shortlist: Sequence[str]) -> bool:
    if not shortlist:
        return True
    p = str(path)
    b = os.path.basename(p)
    hay = f"{p}\n{b}".lower()
    return any(str(item).lower() in hay for item in shortlist)


_PRUNE_DIR_NAMES = {
    "$RECYCLE.BIN", "System Volume Information", ".git", ".svn", ".hg",
    "node_modules", "__pycache__", ".cache", "cache", "tmp", "temp",
}


def _append_root(roots: List[Path], path: Path) -> None:
    try:
        if not path.is_dir():
            return
        real = Path(os.path.realpath(str(path)))
    except Exception:
        return
    if real not in roots:
        roots.append(real)


def _limited_modelish_dirs(root: Path, *, max_depth: int = 5) -> List[Path]:
    """Find likely GGUF/model directories without doing an expensive full share scan."""
    out: List[Path] = []
    try:
        root_real = Path(os.path.realpath(str(root)))
    except Exception:
        return out
    if not root_real.is_dir():
        return out
    root_parts = len(root_real.parts)
    for dirpath, dirnames, _filenames in os.walk(str(root_real), followlinks=False, onerror=lambda _e: None):
        dp = Path(dirpath)
        depth = len(dp.parts) - root_parts
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIR_NAMES and not d.startswith('.')]
        if depth >= max_depth:
            dirnames[:] = []
        name = dp.name.lower()
        if depth > 0 and ("model" in name or "gguf" in name or "llm" in name):
            out.append(dp)
    return out


def _candidate_roots(
    vault_root: str,
    *,
    include_download_mirror: bool = False,
    share_root: str = "",
    extra_roots: Sequence[str] = (),
    full_share_scan: bool = False,
) -> List[Path]:
    roots: List[Path] = []
    vr = Path(vault_root)

    # First preference: explicit Vault model directories.
    for name in ["models-gguf", "models", "gguf", "GGUF"]:
        _append_root(roots, vr / name)
    if vr.is_dir():
        for p in sorted(vr.glob("models*")):
            _append_root(roots, p)
        # If operators placed GGUF files directly under Vault, include it too.
        try:
            if any(x.name.lower().endswith(".gguf") for x in vr.iterdir() if x.is_file() or x.is_symlink()):
                _append_root(roots, vr)
        except Exception:
            pass
    if include_download_mirror:
        dm = vr / "download-mirror"
        if dm.is_dir():
            for p in _limited_modelish_dirs(dm, max_depth=6):
                _append_root(roots, p)

    # Second preference: common model locations anywhere on NOEMAFORGE_SHARE.
    sr = Path(share_root) if share_root else None
    if sr and sr.is_dir():
        common = [
            sr / "models", sr / "models-gguf", sr / "GGUF", sr / "gguf", sr / "llm",
            sr / "Vault" / "models", sr / "Vault" / "models-gguf",
            sr / "noemaforge-lab" / "data" / "Vault" / "models",
            sr / "noemaforge-lab" / "data" / "Vault" / "models-gguf",
        ]
        for p in common:
            _append_root(roots, p)
        for p in _limited_modelish_dirs(sr, max_depth=5):
            _append_root(roots, p)
        if full_share_scan:
            _append_root(roots, sr)

    for raw in extra_roots:
        if raw:
            _append_root(roots, Path(raw))
    return roots


def _iter_gguf_files(root: Path) -> Iterable[Path]:
    """Robust GGUF iterator for NTFS/share trees; ignores unreadable folders."""
    try:
        root_real = Path(os.path.realpath(str(root)))
    except Exception:
        return
    if root_real.is_file() or root_real.is_symlink():
        if root_real.name.lower().endswith(".gguf"):
            yield root_real
        return
    if not root_real.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(str(root_real), followlinks=False, onerror=lambda _e: None):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIR_NAMES and not d.startswith('.')]
        for name in sorted(filenames):
            if name.lower().endswith(".gguf"):
                yield Path(dirpath) / name


def _stat_size(path: str) -> int:
    try:
        return int(os.stat(path).st_size)
    except Exception:
        return 0


def _group_shards(files: Sequence[str]) -> Dict[str, List[Tuple[int, str]]]:
    groups: Dict[str, List[Tuple[int, str]]] = {}
    for p in files:
        si = shard_info(p)
        if not si:
            continue
        groups.setdefault(si.group_key, []).append((si.index, p))
    for key in list(groups.keys()):
        groups[key] = sorted(groups[key], key=lambda x: (x[0], x[1]))
    return groups


def _canonical_noemaforge_path(path: str) -> str:
    p = os.path.realpath(str(path))
    if p.startswith("/mnt/brainos-share/brainos-lab/"):
        cand = "/mnt/noemaforge-share/noemaforge-lab/" + p[len("/mnt/brainos-share/brainos-lab/"):]
        if os.path.exists(cand):
            return cand
    return p


def validate_artifact_path(path: str, *, require_complete: bool = True) -> Tuple[bool, str, Dict[str, Any]]:
    """Validate a GGUF artifact path.

    Returns (ok, reason, sharding_meta). Normal single-file GGUF returns ok and empty meta.
    For sharded GGUF, only shard 1 is usable, and all shards must be present when strict.
    """
    p = _canonical_noemaforge_path(str(path))
    if not os.path.isfile(p):
        return False, "artifact_missing", {"path": p}
    if not p.lower().endswith(".gguf"):
        return False, "not_gguf", {"path": p}
    si = shard_info(p)
    if not si:
        return True, "single_file", {}
    parent = Path(os.path.dirname(p))
    siblings = [str(x) for x in parent.glob("*.gguf")]
    group = _group_shards(siblings).get(si.group_key, [])
    present = sorted({idx for idx, _ in group})
    expected = list(range(1, si.total + 1))
    meta = {
        "sharded": True,
        "shard_index": si.index,
        "shard_count": si.total,
        "shard_paths": [x for _, x in group],
        "present_indices": present,
        "expected_indices": expected,
        "canonical_first_shard": next((x for idx, x in group if idx == 1), ""),
    }
    if si.index != 1:
        return False, "not_first_shard", meta
    if require_complete and present != expected:
        return False, "incomplete_shard_set", meta
    return True, "sharded_head", meta


def discover_gguf_candidates(
    vault_root: str,
    *,
    include_download_mirror: bool = False,
    shortlist: Optional[Sequence[str]] = None,
    shortlist_file: str = "",
    candidate_limit: int = 0,
    strict_shards: bool = True,
    share_root: str = "",
    extra_roots: Optional[Sequence[str]] = None,
    fallback_share_scan: bool = True,
) -> Dict[str, Any]:
    shortlist_items = list(shortlist or []) or _load_shortlist(shortlist_file)
    roots = _candidate_roots(
        vault_root,
        include_download_mirror=include_download_mirror,
        share_root=share_root,
        extra_roots=extra_roots or (),
        full_share_scan=False,
    )
    all_files: List[str] = []
    seen_real: set[str] = set()

    def collect(from_roots: Sequence[Path]) -> None:
        for root in from_roots:
            for fp in sorted(_iter_gguf_files(root), key=lambda x: str(x)):
                p = os.path.realpath(str(fp))
                if p in seen_real:
                    continue
                seen_real.add(p)
                if not _shortlist_match(p, shortlist_items):
                    continue
                all_files.append(p)

    collect(roots)
    full_scan_used = False
    if not all_files and share_root and fallback_share_scan:
        # Last resort: operators often leave downloaded models outside Vault/models*.
        # Do this only if modelish-root discovery found nothing, because the share may be large.
        sr = Path(share_root)
        if sr.is_dir():
            print(f"[gguf_select] no GGUF found in model roots; falling back to full share scan: {sr}", file=sys.stderr)
            full_scan_used = True
            collect([sr])

    groups = _group_shards(all_files)
    accepted: List[Candidate] = []
    rejected: List[Dict[str, Any]] = []

    for p in sorted(all_files):
        base = os.path.basename(p)
        size = _stat_size(p)
        if size <= 0:
            rejected.append({"path": p, "basename": base, "reason": "zero_or_unreadable_size"})
            continue
        si = shard_info(p)
        if si:
            group = groups.get(si.group_key, [])
            present = sorted({idx for idx, _ in group})
            expected = list(range(1, si.total + 1))
            shard_paths = [x for _, x in group]
            if si.index != 1:
                rejected.append({
                    "path": p,
                    "basename": base,
                    "reason": "not_first_shard",
                    "shard_index": si.index,
                    "shard_count": si.total,
                    "canonical_first_shard": next((x for idx, x in group if idx == 1), ""),
                })
                continue
            if strict_shards and present != expected:
                rejected.append({
                    "path": p,
                    "basename": base,
                    "reason": "incomplete_shard_set",
                    "present_indices": present,
                    "expected_indices": expected,
                })
                continue
            effective = sum(_stat_size(x) for x in shard_paths) or size
            accepted.append(Candidate(
                path=p,
                basename=base,
                model_id_hint=model_id_hint_for_path(p),
                sharded=True,
                shard_index=1,
                shard_count=si.total,
                shard_paths=shard_paths,
                size_bytes=size,
                effective_size_bytes=effective,
                source_root=os.path.realpath(os.path.dirname(p)),
            ))
            continue
        accepted.append(Candidate(
            path=p,
            basename=base,
            model_id_hint=model_id_hint_for_path(p),
            sharded=False,
            shard_index=0,
            shard_count=0,
            shard_paths=[],
            size_bytes=size,
            effective_size_bytes=size,
            source_root=os.path.realpath(os.path.dirname(p)),
        ))

    # Deterministic, first-launch-friendly ordering: smallest usable model first for main,
    # then stable by name. For sharded sets this uses total shard size, not one shard size.
    accepted.sort(key=lambda c: (int(c.effective_size_bytes), c.model_id_hint, c.path))
    if candidate_limit and candidate_limit > 0:
        accepted = accepted[:candidate_limit]

    return {
        "ok": bool(accepted),
        "vault_root": os.path.realpath(vault_root),
        "roots": [str(x) for x in roots],
        "share_root": os.path.realpath(share_root) if share_root else "",
        "full_share_scan_used": bool(full_scan_used),
        "strict_shards": bool(strict_shards),
        "shortlist": list(shortlist_items),
        "candidate_count": len(accepted),
        "rejected_count": len(rejected),
        "candidates": [asdict(c) for c in accepted],
        "rejected": rejected,
    }


def _unique_model_id(wanted: str, used: set[str]) -> str:
    base = _safe_id(wanted)
    mid = base
    i = 2
    while mid in used:
        mid = f"{base}_{i}"
        i += 1
    used.add(mid)
    return mid


def _write_yaml(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if yaml is None:
        # Tiny fallback for simple manifest usage.
        with open(path, "w", encoding="utf-8") as f:
            for k, v in obj.items():
                if isinstance(v, (str, int, float, bool)):
                    f.write(f"{k}: {json.dumps(v, ensure_ascii=False)}\n")
                else:
                    f.write(f"{k}: {json.dumps(v, ensure_ascii=False)}\n")
        return
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)


def stage_candidates(modelstore_root: str, candidates: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stage safe candidates in ModelStore.

    The first accepted candidate becomes model_id=main. Multi-part models keep manifest
    artifact_path pointing to the real first shard; the legacy model.gguf symlink is only a
    compatibility pointer. The runtime wrapper reads manifest.yaml and passes the real path
    to llama-server, avoiding shard-name loss via symlink.
    """
    models_dir = Path(modelstore_root) / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    out: List[Dict[str, Any]] = []
    for idx, cand in enumerate(candidates):
        path = os.path.realpath(str(cand.get("path") or ""))
        ok, reason, meta = validate_artifact_path(path, require_complete=True)
        if not ok:
            raise RuntimeError(f"refusing to stage invalid GGUF artifact: {reason}: {path}")
        mid = "main" if idx == 0 else _unique_model_id(str(cand.get("model_id_hint") or os.path.basename(path)), used)
        used.add(mid)
        target_dir = models_dir / mid
        target_dir.mkdir(parents=True, exist_ok=True)
        for stale in [target_dir / "model.gguf", target_dir / "manifest.yaml"]:
            if stale.exists() or stale.is_symlink():
                stale.unlink()
        os.symlink(path, str(target_dir / "model.gguf"))
        manifest = {
            "apiVersion": "noemaforge.model/v1",
            "kind": "ModelArtifact",
            "model_id": mid,
            "format": "gguf",
            "artifact_path": path,
            "source_path": path,
            "trust": "unknown",
            "family": "",
            "variant": os.path.basename(path),
            "notes": "staged by first-launch GGUF selector",
            "firstboot": {
                "bootstrap": mid == "main",
                "effective_size_bytes": int(cand.get("effective_size_bytes") or 0),
                "size_bytes": int(cand.get("size_bytes") or 0),
            },
        }
        if meta:
            manifest["sharding"] = meta
        _write_yaml(str(target_dir / "manifest.yaml"), manifest)
        out.append({
            "model_id": mid,
            "source": path,
            "manifest": str(target_dir / "manifest.yaml"),
            "bootstrap": mid == "main",
            "sharded": bool(meta),
            "shard_count": int((meta or {}).get("shard_count") or 0),
            "effective_size_bytes": int(cand.get("effective_size_bytes") or _stat_size(path)),
        })
    return out


def validate_modelstore(modelstore_root: str) -> Dict[str, Any]:
    models_dir = Path(modelstore_root) / "models"
    checked: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    if not models_dir.is_dir():
        return {"ok": False, "reason": "models_dir_missing", "models_dir": str(models_dir), "checked": [], "failed": []}
    for mdir in sorted(models_dir.iterdir()):
        if not mdir.is_dir() or mdir.name.startswith("."):
            continue
        artifact = str(mdir / "model.gguf")
        manifest = mdir / "manifest.yaml"
        if manifest.is_file() and yaml is not None:
            try:
                obj = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
                ap = str(obj.get("artifact_path") or "").strip()
                if ap:
                    artifact = ap if ap.startswith("/") else str(mdir / ap)
            except Exception:
                pass
        ok, reason, meta = validate_artifact_path(artifact, require_complete=True)
        rec = {"model_id": mdir.name, "artifact_path": os.path.realpath(artifact), "ok": ok, "reason": reason}
        if meta:
            rec["sharding"] = meta
        checked.append(rec)
        if not ok:
            failed.append(rec)
    return {"ok": len(failed) == 0, "models_dir": str(models_dir), "checked": checked, "failed": failed}


def write_shortlist(report: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# NoemaForge safe firstboot model shortlist\n")
        f.write("# Auto-generated by gguf_select.py; each line is a canonical GGUF candidate.\n")
        f.write("# Multi-part models list only shard 00001-of-N. Non-head shards are intentionally omitted.\n")
        for cand in report.get("candidates") or []:
            f.write(str(cand.get("path") or "") + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="NoemaForge safe GGUF model discovery/staging helper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_disc = sub.add_parser("discover")
    p_disc.add_argument("--vault-root", required=True)
    p_disc.add_argument("--shortlist-file", default="")
    p_disc.add_argument("--candidate-limit", type=int, default=0)
    p_disc.add_argument("--include-download-mirror", action="store_true")
    p_disc.add_argument("--allow-incomplete-shards", action="store_true")
    p_disc.add_argument("--share-root", default="")
    p_disc.add_argument("--extra-root", action="append", default=[])
    p_disc.add_argument("--no-fallback-share-scan", action="store_true")
    p_disc.add_argument("--json-out", default="")
    p_disc.add_argument("--shortlist-out", default="")

    p_val = sub.add_parser("validate-modelstore")
    p_val.add_argument("--root", default="/var/lib/modelstore")
    p_val.add_argument("--json-out", default="")

    args = ap.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "discover":
        report = discover_gguf_candidates(
            args.vault_root,
            include_download_mirror=bool(args.include_download_mirror),
            shortlist_file=str(args.shortlist_file or ""),
            candidate_limit=int(args.candidate_limit or 0),
            strict_shards=not bool(args.allow_incomplete_shards),
            share_root=str(args.share_root or ""),
            extra_roots=list(args.extra_root or []),
            fallback_share_scan=not bool(args.no_fallback_share_scan),
        )
        if args.shortlist_out:
            write_shortlist(report, args.shortlist_out)
        _json_dump(report, args.json_out)
        return 0 if report.get("ok") else 1
    if args.cmd == "validate-modelstore":
        report = validate_modelstore(str(args.root))
        _json_dump(report, args.json_out)
        return 0 if report.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
