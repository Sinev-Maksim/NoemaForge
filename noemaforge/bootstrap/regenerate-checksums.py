#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/bootstrap/regenerate-checksums.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: Cross-platform SHA256SUMS regeneration (replaces make-checksums.sh on Windows/CI).
Inputs: noemaforge/ package root directory.
Outputs: noemaforge/checksums/SHA256SUMS (sorted, deterministic).
Side effects: Overwrites checksums/SHA256SUMS inside the package root.
Tests: python3 noemaforge/bootstrap/regenerate-checksums.py noemaforge/ --dry-run
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

EXCLUDE_PATHS = {
    "checksums/SHA256SUMS",
    "checksums\\SHA256SUMS",
}
EXCLUDE_SUFFIXES = {".pyc"}
EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_NAMES = {"noemaforge-llm-gateway", "noemaforge-llm-gateway.exe"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect(root: Path) -> list[tuple[str, str]]:
    """Return sorted list of (hash, rel_path) pairs."""
    rows: list[tuple[str, str]] = []
    for abs_path in root.rglob("*"):
        if not abs_path.is_file():
            continue
        rel = abs_path.relative_to(root).as_posix()
        # Apply exclusions
        if rel in EXCLUDE_PATHS:
            continue
        if abs_path.suffix in EXCLUDE_SUFFIXES:
            continue
        if any(part in EXCLUDE_DIRS for part in abs_path.parts):
            continue
        if abs_path.name in EXCLUDE_NAMES:
            continue
        rows.append((sha256_file(abs_path), rel))
    rows.sort(key=lambda x: x[1])
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate SHA256SUMS for the NoemaForge package.")
    parser.add_argument("root", nargs="?", default=".", help="Package root directory (default: .)")
    parser.add_argument("--dry-run", action="store_true", help="Print checksums without writing")
    parser.add_argument("--out", default=None, help="Output path (default: <root>/checksums/SHA256SUMS)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"ERROR: root not found: {root}", file=sys.stderr)
        return 1

    rows = collect(root)
    content = "".join(f"{h}  {rel}\n" for h, rel in rows)

    if args.dry_run:
        print(content, end="")
        print(f"\n# {len(rows)} files hashed (dry-run, not written)", file=sys.stderr)
        return 0

    out = Path(args.out) if args.out else (root / "checksums" / "SHA256SUMS")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"Wrote {out} ({len(rows)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
