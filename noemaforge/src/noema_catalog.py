#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/noema_catalog.py
Zone: runtime/cli
Version: 0.33.0
Created: 2026-06-08
Modified: 2026-06-08
Purpose: Knowledge projection — generate a capability catalog of the system's *declared* contracts
  (runtime version, published JSON schemas, ToolProxy/release policies, and the `noema` CLI
  surface) into one legible JSON/Markdown view. Following the project's graph-projection
  convention, the catalog is a projection (NOT the source of truth) and carries source refs, a
  content digest, generated_at, and an explicit not-source-of-truth notice.
Inputs: package root (default: this install).
Outputs: a catalog dict / JSON / Markdown projection.
Side effects: read-only filesystem scan; writes a file only when --out is given.
Tests: python3 -m unittest noemaforge/tests/test_noema_catalog.py
Notes: Code comments are English-only. Display-safe: read-only, no GPU/model/display actions.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_PKG_ROOT = Path(__file__).resolve().parents[1]  # noemaforge/
PROJECTION_TYPE = "capability-catalog/v1"
NOT_SOURCE_OF_TRUTH = (
    "This catalog is a GENERATED PROJECTION of declared contracts. The canonical sources are the "
    "files under noemaforge/{schemas,policies,src}; do not treat this catalog as authoritative."
)
_PACKAGE_RE = re.compile(r"^\s*package\s+([A-Za-z0-9_.]+)", re.MULTILINE)


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _runtime_version(root: Path) -> str:
    for candidate in (root / "VERSION", root.parent / "VERSION"):
        try:
            v = candidate.read_text(encoding="utf-8").strip()
            if v:
                return v
        except OSError:
            continue
    try:
        import sys
        sys.path.insert(0, str(root / "src"))
        from noemaforge_version import RUNTIME_VERSION
        return str(RUNTIME_VERSION)
    except Exception:
        return "unknown"


def _schemas(root: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    sdir = root / "schemas"
    if not sdir.is_dir():
        return out
    for p in sorted(sdir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        out.append({
            "file": f"schemas/{p.name}",
            "id": d.get("$id"),
            "title": d.get("title"),
            "required": d.get("required", []),
        })
    return out


def _policies(root: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    pdir = root / "policies"
    if not pdir.is_dir():
        return out
    for p in sorted(pdir.glob("*.rego")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        m = _PACKAGE_RE.search(text)
        out.append({"file": f"policies/{p.name}", "package": m.group(1) if m else None})
    return out


def _cli_commands(root: Path) -> List[str]:
    """Discover the `noema` subcommand surface from the source modules (noema_<cmd>.py with a
    top-level main()), so the catalog reflects what is actually wired, without importing them."""
    src = root / "src"
    cmds: List[str] = []
    if not src.is_dir():
        return cmds
    for p in sorted(src.glob("noema_*.py")):
        stem = p.stem  # noema_<cmd>
        cmd = stem[len("noema_"):]
        if cmd in ("cli", "version"):
            continue
        try:
            if re.search(r"(?m)^def main\(", p.read_text(encoding="utf-8")):
                cmds.append(cmd)
        except OSError:
            continue
    return cmds


def _digest(catalog: Dict[str, Any]) -> str:
    """Stable sha256 over the catalog content, excluding the volatile/derived fields."""
    stable = {k: v for k, v in catalog.items() if k not in ("generated_at", "digest")}
    blob = json.dumps(stable, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def build_catalog(root: Optional[Path] = None) -> Dict[str, Any]:
    """Build the capability catalog by scanning declared contracts under *root* (read-only)."""
    root = Path(root) if root else _PKG_ROOT
    catalog: Dict[str, Any] = {
        "projection_type": PROJECTION_TYPE,
        "not_source_of_truth": NOT_SOURCE_OF_TRUTH,
        "version": _runtime_version(root),
        "source_refs": ["schemas/", "policies/", "src/noema_*.py", "VERSION"],
        "schemas": _schemas(root),
        "policies": _policies(root),
        "cli_commands": _cli_commands(root),
    }
    catalog["digest"] = _digest(catalog)
    catalog["generated_at"] = _nowz()
    return catalog


def format_markdown(catalog: Dict[str, Any]) -> str:
    lines = [
        f"# NoemaForge capability catalog (v{catalog.get('version', 'unknown')})",
        "",
        f"> {catalog['not_source_of_truth']}",
        "",
        f"_Projection `{catalog['projection_type']}` · digest `{catalog['digest'][:12]}…` · "
        f"generated {catalog['generated_at']}_",
        "",
        f"## CLI surface ({len(catalog['cli_commands'])})",
        "",
        "".join(f"- `noema {c}`\n" for c in catalog["cli_commands"]) or "- (none)\n",
        f"## Published schemas ({len(catalog['schemas'])})",
        "",
    ]
    for s in catalog["schemas"]:
        lines.append(f"- **{s.get('title') or s['file']}** (`{s['file']}`) — required: "
                     f"{', '.join(s.get('required') or []) or '—'}")
    lines += ["", f"## Policies ({len(catalog['policies'])})", ""]
    for p in catalog["policies"]:
        lines.append(f"- `{p['file']}` — package `{p.get('package') or '—'}`")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="noema catalog",
        description="Project the system's declared contracts (version, schemas, policies, CLI) "
                    "into a capability catalog. Read-only; display-safe.",
    )
    parser.add_argument("--root", default=None, help="package root (default: this install)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", default=None, help="write the catalog here (default: stdout)")
    args = parser.parse_args(argv)

    catalog = build_catalog(Path(args.root) if args.root else None)
    text = (json.dumps(catalog, indent=2, ensure_ascii=False) + "\n") if args.json \
        else format_markdown(catalog)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(catalog['cli_commands'])} commands, "
              f"{len(catalog['schemas'])} schemas, {len(catalog['policies'])} policies)")
    else:
        import sys
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
