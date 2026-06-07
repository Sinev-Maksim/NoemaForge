#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/noema_upgrade.py
Zone: runtime/upgrade
Version: 0.33.0
Created: 2026-06-07
Modified: 2026-06-07
Purpose: Plan and apply an in-place NoemaForge version upgrade by replacing install-tree files
  from an extracted incoming release, while GUARANTEEING that user/machine state is never lost.
  Safety invariants: (1) nothing is ever deleted; (2) protected paths (context.md, and anything
  under data/memory/sessions/secrets/vault/state/logs, plus token/secret/key files) are never
  overwritten; (3) only managed code/doc extensions are replaced; (4) dry-run is the default.
Inputs: a current install root; an extracted incoming-release root; optional extra preserve globs.
Outputs: a structured upgrade plan (replace/add/preserve/skip) and, with --apply, the actions taken.
Side effects: read-only in plan/dry-run; copies incoming files into the install root only on --apply.
Tests: python3 -m unittest noemaforge/tests/test_noema_upgrade.py
Notes: Code comments are English-only. This module performs NO GPU/model/display actions and never
  removes files, so it is display-safe and data-safe by construction.
=== End NoemaForge File Header ===

Design: NoemaForge separates the install root (code/docs — upgraded here) from the data root
(machine state — never part of an upgrade, resolved separately by platform_paths). This planner
additionally protects named state that may live inside the install tree.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Managed extensions: the only files an upgrade is allowed to overwrite in place.
REPLACE_SUFFIXES = {
    ".py", ".sh", ".md", ".yaml", ".yml", ".json", ".html", ".css", ".js",
    ".txt", ".service", ".cfg", ".ini", ".toml", ".rego",
}

# Directory components whose entire subtree is user/machine state — never touched.
PRESERVE_DIR_PARTS = {
    ".git", "data", "memory", "sessions", "secrets", "tokens", "vault", "state",
    "logs", "var", "__pycache__",
}
# Exact protected basenames (machine state / secrets that may sit in the install tree).
PRESERVE_NAMES = {"context.md", "token", "secret", "credentials", "id_rsa", ".env"}
# Protected suffixes (local overrides, keys, env, token/secret material).
# NOTE: matched on the full suffix only — a release file such as
# ``capability-token.schema.json`` is NOT a secret and stays upgradable.
PRESERVE_SUFFIXES = {".local", ".key", ".pem", ".env", ".token", ".secret", ".credentials"}


def _is_protected(rel_parts: Sequence[str]) -> bool:
    """True if a path (given as relative parts) is user/machine state that must never be
    overwritten or deleted by an upgrade. Protection is by directory subtree, exact basename,
    or sensitive suffix — never by loose substring, so normal code/schema files are upgradable."""
    if any(part in PRESERVE_DIR_PARTS for part in rel_parts):
        return True
    name = rel_parts[-1] if rel_parts else ""
    if name in PRESERVE_NAMES:
        return True
    if Path(name).suffix in PRESERVE_SUFFIXES:
        return True
    return False


def _rel_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file():
            yield p.relative_to(root)


def plan_upgrade(
    current_root: Path,
    incoming_root: Path,
    *,
    preserve_globs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Classify every incoming file into replace / add / preserve / skip_unmanaged.

    Never schedules a delete. Protected paths are reported under ``preserve`` and are never
    overwritten even when the incoming release ships a different version of them.
    """
    current_root = Path(current_root)
    incoming_root = Path(incoming_root)
    preserve_globs = list(preserve_globs or [])

    replace: List[str] = []
    add: List[str] = []
    preserve: List[str] = []
    skip_unmanaged: List[str] = []

    for rel in _rel_files(incoming_root):
        rel_posix = rel.as_posix()
        parts = rel.parts
        protected = _is_protected(parts) or any(rel.match(g) for g in preserve_globs)
        exists = (current_root / rel).is_file()

        if protected:
            # Never overwrite protected state, whether or not it exists in current.
            preserve.append(rel_posix)
            continue
        if exists:
            if rel.suffix in REPLACE_SUFFIXES:
                replace.append(rel_posix)
            else:
                skip_unmanaged.append(rel_posix)
        else:
            add.append(rel_posix)

    # Files that exist only in the current install are KEPT (upgrade never deletes).
    current_only = sorted(
        rel.as_posix() for rel in _rel_files(current_root)
        if not (incoming_root / rel).exists()
    )

    return {
        "current_root": str(current_root),
        "incoming_root": str(incoming_root),
        "replace": sorted(replace),
        "add": sorted(add),
        "preserve": sorted(preserve),
        "skip_unmanaged": sorted(skip_unmanaged),
        "kept_current_only": current_only,
        "summary": {
            "replace": len(replace),
            "add": len(add),
            "preserve": len(preserve),
            "skip_unmanaged": len(skip_unmanaged),
            "kept_current_only": len(current_only),
        },
    }


def apply_plan(plan: Dict[str, Any], *, dry_run: bool = True) -> Dict[str, Any]:
    """Apply replace + add actions from a plan. Dry-run by default: pass dry_run=False to write.

    Only copies incoming → current for the ``replace`` and ``add`` lists. Never touches the
    ``preserve`` / ``skip_unmanaged`` / ``kept_current_only`` sets, and never deletes anything.
    """
    current_root = Path(plan["current_root"])
    incoming_root = Path(plan["incoming_root"])
    applied: List[str] = []
    for rel in list(plan["replace"]) + list(plan["add"]):
        src = incoming_root / rel
        dst = current_root / rel
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        applied.append(rel)
    return {
        "dry_run": dry_run,
        "applied": sorted(applied),
        "applied_count": len(applied),
        "preserved_count": len(plan["preserve"]),
    }


def format_plan(plan: Dict[str, Any]) -> str:
    s = plan["summary"]
    lines = [
        f"NoemaForge upgrade plan: {plan['incoming_root']} -> {plan['current_root']}",
        f"  replace={s['replace']} add={s['add']} preserve={s['preserve']} "
        f"skip_unmanaged={s['skip_unmanaged']} kept_current_only={s['kept_current_only']}",
        "  (upgrade never deletes; protected user/machine state is never overwritten)",
    ]
    for rel in plan["preserve"][:10]:
        lines.append(f"  [preserve] {rel}")
    if len(plan["preserve"]) > 10:
        lines.append(f"  [preserve] … +{len(plan['preserve']) - 10} more")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="noema upgrade",
        description="Plan/apply an in-place upgrade, preserving user/machine state. "
                    "Display-safe: performs no GPU/model/display actions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply"):
        sp = sub.add_parser(name, help=f"{name} an upgrade")
        sp.add_argument("--current", required=True, help="current install root")
        sp.add_argument("--incoming", required=True, help="extracted incoming-release root")
        sp.add_argument("--preserve", action="append", default=[],
                        help="extra glob (relative) to protect; repeatable")
        sp.add_argument("--json", action="store_true")
        if name == "apply":
            sp.add_argument("--apply", action="store_true",
                            help="actually write changes (default is dry-run)")

    args = parser.parse_args(argv)
    import json
    plan = plan_upgrade(Path(args.current), Path(args.incoming), preserve_globs=args.preserve)

    if args.command == "plan":
        print(json.dumps(plan, indent=2, ensure_ascii=False) if args.json else format_plan(plan))
        return 0

    # apply
    result = apply_plan(plan, dry_run=not args.apply)
    if args.json:
        print(json.dumps({"plan": plan["summary"], "result": result}, indent=2, ensure_ascii=False))
    else:
        print(format_plan(plan))
        mode = "APPLIED" if not result["dry_run"] else "DRY-RUN (no changes written; pass --apply)"
        print(f"  {mode}: {result['applied_count']} files, {result['preserved_count']} preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
