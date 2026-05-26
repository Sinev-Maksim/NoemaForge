#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/prep/apply-runtime-version-centralization.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-25
Modified: 2026-05-25
Purpose: Apply the 0.32.2 centralized runtime-version migration across Python runtime files in a local checkout.
Inputs: Repository root, Python runtime files, canonical VERSION files.
Outputs: Modified files with centralized RUNTIME_VERSION imports and 0.32.2 headers.
Side effects: Rewrites targeted source files in-place; creates no network calls.
Tests: python3 noemaforge/tools/prep/apply-runtime-version-centralization.py --check; python3 -m py_compile noemaforge/src/*.py.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

This helper exists because some runtime files are large and should be rewritten
locally in one deterministic pass before the final release archive is created.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VERSION = "0.32.2"
MODIFIED = "2026-05-25"

TARGETS = [
    "noemaforge/src/admin_gui_server.py",
    "noemaforge/src/admin_runtime.py",
    "noemaforge/src/code_qa_runtime.py",
    "noemaforge/src/dev_team_runtime.py",
    "noemaforge/src/first_start_summary.py",
    "noemaforge/src/intent_router_eval.py",
    "noemaforge/src/model_evolution_runtime.py",
    "noemaforge/src/model_selection_runtime.py",
    "noemaforge/src/pipeline_runtime.py",
    "noemaforge/src/selftest_runtime.py",
    "noemaforge/src/team_member_runtime.py",
    "noemaforge/src/wiki_patch_runtime.py",
]

RUNTIME_ASSIGNMENT_RE = re.compile(r"(?m)^\s*RUNTIME_VERSION\s*=\s*['\"][^'\"]+['\"]\s*$")
IMPORT_LINE = "from noemaforge_version import RUNTIME_VERSION"


def patch_text(text: str, rel_path: str) -> str:
    text = re.sub(r"(?m)^Version: .*$", f"Version: {VERSION}", text, count=1)
    text = re.sub(r"(?m)^Modified: .*$", f"Modified: {MODIFIED}", text, count=1)
    text = re.sub(r"0\.32\.1", VERSION, text)
    text = re.sub(r"0\.31\.13\.alpha", VERSION, text)

    if rel_path.endswith("noemaforge_version.py"):
        return text

    if RUNTIME_ASSIGNMENT_RE.search(text):
        return RUNTIME_ASSIGNMENT_RE.sub(IMPORT_LINE, text, count=1)

    if IMPORT_LINE in text:
        return text

    # Insert after the last import/from line in the first import block.
    lines = text.splitlines(keepends=True)
    insert_at = None
    for idx, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            insert_at = idx + 1
        elif insert_at is not None and line.strip() and not (line.startswith("import ") or line.startswith("from ")):
            break
    if insert_at is None:
        return text
    lines.insert(insert_at, IMPORT_LINE + "\n")
    return "".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true", help="Report pending changes without writing files.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    changed: list[str] = []
    missing: list[str] = []

    for rel in TARGETS:
        path = root / rel
        if not path.exists():
            missing.append(rel)
            continue
        before = path.read_text(encoding="utf-8")
        after = patch_text(before, rel)
        if after != before:
            changed.append(rel)
            if not args.check:
                path.write_text(after, encoding="utf-8")

    for rel in ["VERSION", "noemaforge/VERSION", "docs/VERSION"]:
        path = root / rel
        if path.exists():
            before = path.read_text(encoding="utf-8")
            after = VERSION + "\n"
            if before != after:
                changed.append(rel)
                if not args.check:
                    path.write_text(after, encoding="utf-8")

    hardcoded: list[str] = []
    for py in (root / "noemaforge" / "src").glob("*.py"):
        if py.name == "noemaforge_version.py":
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        if RUNTIME_ASSIGNMENT_RE.search(text):
            hardcoded.append(str(py.relative_to(root)))

    print("NoemaForge runtime version centralization")
    print(f"root={root}")
    print(f"check={args.check}")
    print(f"changed_count={len(changed)}")
    for rel in changed:
        print(f"changed: {rel}")
    for rel in missing:
        print(f"missing: {rel}")
    if hardcoded:
        print("remaining hardcoded RUNTIME_VERSION assignments:", file=sys.stderr)
        for rel in hardcoded:
            print(f" - {rel}", file=sys.stderr)
        return 1
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
