#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/wiki_patch_runtime.py
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

Existing module notes:
NoemaForge wiki incremental patch runtime.

Creates auditable patch bundles for a project wiki repository. Each patch bundle
contains:
- copied wiki payload files;
- functional_delta.md supplied by operator/task/request;
- metrics_delta.json comparing before/after summaries;
- patch.diff with concrete textual changes;
- manifest and apply.sh.

No network access and no git push are performed by this runtime.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_WIKI_PATCH_STATE", "/var/lib/noemaforge/wiki_patches"))
SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
RUNTIME_VERSION = "0.32.1"


def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_id(value: str) -> str:
    value = SAFE_ID_RE.sub("_", (value or "").strip()).strip("_")
    return value or "wiki_patch"


def json_dumps(data: Any, *, pretty: bool = True) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2 if pretty else None, sort_keys=False)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
        return loaded if isinstance(loaded, dict) else {"value": loaded}
    except Exception:
        return {}


def copy_optional_json_artifact(src_path: Optional[str], out_dir: Path, filename: str) -> Dict[str, Any]:
    if not src_path:
        return {"present": False, "path": ""}
    src = Path(src_path).resolve()
    if not src.exists() or src.is_dir():
        return {"present": False, "path": str(src), "error": "missing_or_directory"}
    payload = load_json(str(src))
    dst = out_dir / filename
    atomic_write_text(dst, json_dumps(payload) + "\n")
    return {"present": True, "path": str(dst), "source": str(src), "keys": sorted(payload.keys())}


def flatten_numeric(data: Any, prefix: str = "") -> Dict[str, float]:
    out: Dict[str, float] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            out.update(flatten_numeric(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            out.update(flatten_numeric(v, f"{prefix}.{i}"))
    elif isinstance(data, (int, float)) and not isinstance(data, bool):
        out[prefix] = float(data)
    return out


def metrics_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    b = flatten_numeric(before)
    a = flatten_numeric(after)
    rows: Dict[str, Dict[str, Any]] = {}
    for key in sorted(set(b) | set(a)):
        bv = b.get(key)
        av = a.get(key)
        if bv is None or av is None:
            rows[key] = {"before": bv, "after": av, "delta": None, "pct": None}
            continue
        delta = av - bv
        pct = (delta / bv * 100.0) if bv else 0.0
        rows[key] = {"before": bv, "after": av, "delta": delta, "pct": pct}
    return {"metric_count": len(rows), "metrics": rows}


def copy_payload(includes: Iterable[str], source_root: Path, payload_dir: Path) -> List[Dict[str, str]]:
    copied: List[Dict[str, str]] = []
    for raw in includes:
        src = Path(raw)
        if not src.is_absolute():
            src = (source_root / src).resolve()
        if not src.exists() or src.is_dir():
            copied.append({"source": str(src), "status": "missing_or_directory"})
            continue
        try:
            rel = src.relative_to(source_root.resolve())
        except Exception:
            rel = Path("imports") / src.name
        dst = payload_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append({"source": str(src), "relative_path": str(rel), "payload_path": str(dst), "status": "copied"})
    return copied


def make_unified_diff(repo: Path, payload_dir: Path, copied: List[Dict[str, str]]) -> str:
    chunks: List[str] = []
    for item in copied:
        if item.get("status") != "copied":
            continue
        rel = Path(item["relative_path"])
        new_path = payload_dir / rel
        old_path = repo / rel
        old_lines = old_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if old_path.exists() else []
        new_lines = new_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        chunks.extend(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm=""))
        if chunks and not chunks[-1].endswith("\n"):
            chunks[-1] += "\n"
    return "".join(chunks) if chunks else "# No textual payload diff generated.\n"


def create_cmd(args: argparse.Namespace) -> None:
    root = Path(args.root or DEFAULT_ROOT).resolve()
    state = Path(args.state or DEFAULT_STATE).resolve()
    wiki_repo = Path(args.wiki_repo).resolve()
    source_root = Path(args.source_root).resolve() if args.source_root else root.resolve()
    title = args.title or "NoemaForge wiki patch"
    patch_id = safe_id(args.patch_id or f"patch_{nowz().replace(':','').replace('-','').replace('Z','Z')}_{title}")[:180]
    out_dir = Path(args.out_dir).resolve() if args.out_dir else state / patch_id
    payload_dir = out_dir / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)
    includes = list(args.include or [])
    if not includes:
        includes = ["docs/wiki/README.md"]
    copied = copy_payload(includes, source_root, payload_dir)
    before = load_json(args.metrics_before)
    after = load_json(args.metrics_after)
    mdelta = metrics_delta(before, after)
    media_delta = copy_optional_json_artifact(getattr(args, "media_capability_report", None), out_dir, "media_capability_delta.json")
    generated_artifacts = copy_optional_json_artifact(getattr(args, "artifact_manifest", None), out_dir, "generated_artifacts.json")
    description = args.description or os.environ.get("NOEMAFORGE_TASK_DESCRIPTION") or "No functional description supplied."
    functional = f"""# Functional Delta — {title}

- patch_id: `{patch_id}`
- created_at: `{nowz()}`
- source_task: `{args.source_task or ''}`
- run_id: `{args.run_id or ''}`

## Operator / task description

{description}

## Included wiki payload

"""
    for item in copied:
        functional += f"- `{item.get('relative_path', item.get('source'))}` — {item.get('status')}\n"
    functional += "\n## Metrics delta summary\n\n"
    important = [k for k in mdelta.get("metrics", {}) if any(token in k for token in ["duration", "failed", "passed", "maxrss", "memory", "latency", "active_llms"])]
    if important:
        for key in important[:40]:
            row = mdelta["metrics"][key]
            functional += f"- `{key}`: {row.get('before')} → {row.get('after')} (delta={row.get('delta')}, pct={row.get('pct')})\n"
    else:
        functional += "No comparable numeric metrics supplied.\n"
    if media_delta.get("present"):
        functional += "\n## Media capability delta\n\n"
        functional += f"- `media_capability_delta.json` copied from `{media_delta.get('source')}`.\n"
    if generated_artifacts.get("present"):
        functional += "\n## Generated artifacts\n\n"
        functional += f"- `generated_artifacts.json` copied from `{generated_artifacts.get('source')}`.\n"
    atomic_write_text(out_dir / "functional_delta.md", functional)
    atomic_write_text(out_dir / "metrics_delta.json", json_dumps(mdelta) + "\n")
    diff = make_unified_diff(wiki_repo, payload_dir, copied)
    atomic_write_text(out_dir / "patch.diff", diff)
    manifest = {
        "apiVersion": "noemaforge.wiki.patch/v1",
        "version": RUNTIME_VERSION,
        "patch_id": patch_id,
        "title": title,
        "description": description,
        "created_at": nowz(),
        "wiki_repo": str(wiki_repo),
        "source_root": str(source_root),
        "source_task": args.source_task,
        "run_id": args.run_id,
        "payload": copied,
        "metrics_before": args.metrics_before,
        "metrics_after": args.metrics_after,
        "metric_count": mdelta.get("metric_count", 0),
        "media_capability_delta": media_delta,
        "generated_artifacts": generated_artifacts,
        "apply": "./apply.sh /path/to/wiki-repo",
    }
    atomic_write_text(out_dir / "wiki_patch_manifest.json", json_dumps(manifest) + "\n")
    apply_sh = """#!/usr/bin/env bash
set -euo pipefail
WIKI_REPO="${1:-}"
if [[ -z "$WIKI_REPO" ]]; then
  echo "Usage: ./apply.sh /path/to/wiki-repo" >&2
  exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rsync -a "$SCRIPT_DIR/payload/" "$WIKI_REPO/"
echo "Applied NoemaForge wiki patch payload to $WIKI_REPO"
"""
    atomic_write_text(out_dir / "apply.sh", apply_sh)
    os.chmod(out_dir / "apply.sh", 0o755)
    commit_msg = f"NoemaForge wiki patch: {title}\n\n{description[:500]}\n\nPatch: {patch_id}\n"
    atomic_write_text(out_dir / "commit_message.txt", commit_msg)
    atomic_write_text(out_dir / "README.md", f"# {patch_id}\n\nApply with:\n\n```bash\n./apply.sh {wiki_repo}\n```\n\nReview `functional_delta.md`, `metrics_delta.json` and `patch.diff` first.\n")
    doc = {"ok": True, "patch_id": patch_id, "patch_dir": str(out_dir), "payload_files": len([x for x in copied if x.get("status") == "copied"]), "metric_count": mdelta.get("metric_count", 0)}
    print(json_dumps(doc) if args.json else f"ok=true patch_dir={out_dir} patch_id={patch_id}")


def apply_cmd(args: argparse.Namespace) -> None:
    patch_dir = Path(args.patch_dir).resolve()
    wiki_repo = Path(args.wiki_repo).resolve()
    payload = patch_dir / "payload"
    if not payload.exists():
        raise SystemExit(f"payload not found: {payload}")
    actions = []
    for src in payload.rglob("*"):
        if src.is_file():
            rel = src.relative_to(payload)
            dst = wiki_repo / rel
            actions.append({"source": str(src), "target": str(dst)})
            if not args.dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    print(json_dumps({"ok": True, "dry_run": bool(args.dry_run), "actions": actions}))


def list_cmd(args: argparse.Namespace) -> None:
    state = Path(args.state or DEFAULT_STATE).resolve()
    rows = []
    for manifest in sorted(state.glob("*/wiki_patch_manifest.json"), reverse=True):
        rows.append(load_json(str(manifest)))
    if args.json:
        print(json_dumps({"ok": True, "patches": rows[:args.limit]}))
    else:
        for row in rows[:args.limit]:
            print(f"{row.get('patch_id')}\t{row.get('title')}\t{row.get('created_at')}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="noemaforge wiki-patch")
    p.add_argument("--root")
    p.add_argument("--state")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--wiki-repo", required=True)
    c.add_argument("--source-root")
    c.add_argument("--title", required=True)
    c.add_argument("--description")
    c.add_argument("--source-task")
    c.add_argument("--run-id")
    c.add_argument("--metrics-before")
    c.add_argument("--metrics-after")
    c.add_argument("--media-capability-report")
    c.add_argument("--artifact-manifest")
    c.add_argument("--include", action="append")
    c.add_argument("--out-dir")
    c.add_argument("--patch-id")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=create_cmd)
    a = sub.add_parser("apply")
    a.add_argument("--patch-dir", required=True)
    a.add_argument("--wiki-repo", required=True)
    a.add_argument("--dry-run", action="store_true")
    a.set_defaults(func=apply_cmd)
    l = sub.add_parser("list")
    l.add_argument("--limit", type=int, default=20)
    l.add_argument("--json", action="store_true")
    l.set_defaults(func=list_cmd)
    return p


def normalize_global_argv(argv: Optional[List[str]]) -> List[str]:
    import sys
    items = list(sys.argv[1:] if argv is None else argv)
    global_opts: List[str] = []
    rest: List[str] = []
    i = 0
    while i < len(items):
        item = items[i]
        if item in {"--root", "--state"} and i + 1 < len(items):
            global_opts.extend([item, items[i + 1]])
            i += 2
        else:
            rest.append(item)
            i += 1
    return global_opts + rest


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_global_argv(argv))
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


