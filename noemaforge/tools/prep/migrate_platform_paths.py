#!/usr/bin/env python3
"""
migrate_platform_paths.py — batch-migrate hardcoded path constants to platform_paths.

Replaces patterns like:
    DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
    DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_XYZ_STATE", "/var/lib/noemaforge/xyz"))

With:
    from platform_paths import DEFAULT_PATHS as _pp
    DEFAULT_ROOT  = _pp.root
    DEFAULT_STATE = _pp.<mapped_property>

Usage:
    python migrate_platform_paths.py --dry-run     # show what would change
    python migrate_platform_paths.py               # apply changes
    python migrate_platform_paths.py --file src/xyz.py  # single file
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Mapping: env var name → platform_paths property name
ENV_TO_PROP: Dict[str, str] = {
    "NOEMAFORGE_ROOT":                    "root",
    "NOEMAFORGE_DATA_ROOT":               "data_root",
    "NOEMAFORGE_PIPELINE_STATE":          "pipelines_dir",
    "NOEMAFORGE_PIPELINE_REGISTRY":       "pipelines_dir",
    "NOEMAFORGE_MODEL_SELECTION_STATE":   "model_selection_state_dir",
    "NOEMAFORGE_MODEL_EVOLUTION_STATE":   "model_evolution_state_dir",
    "NOEMAFORGE_DEV_TEAM_STATE":          "dev_team_state_dir",
    "NOEMAFORGE_CODE_EVOLUTION_STATE":    "code_evolution_state_dir",
    "NOEMAFORGE_SESSION_STATE":           "session_state_dir",
    "NOEMAFORGE_EVENT_STATE":             "event_log_dir",
    "NOEMAFORGE_EPOCH_STATE":             "epoch_dir",
    "NOEMAFORGE_VAULT_DIR":               "vault_dir",
    "NOEMAFORGE_PERSONA_STATE":           "persona_state_dir",
    "NOEMAFORGE_GUI_STATE_DIR":           "gui_state_dir",
    "NOEMAFORGE_JOBS_DIR":                "jobs_dir",
    "NOEMAFORGE_LOG_DIR":                 "log_dir",
}

# Pattern: DEFAULT_XYZ = Path(os.environ.get("NOEMAFORGE_...", "/..."))
_PATTERN = re.compile(
    r"""^(?P<indent>[ \t]*)(?P<name>[A-Z_]+)\s*=\s*"""
    r"""Path\(os\.environ\.get\(\s*"(?P<env_key>NOEMAFORGE_[A-Z_]+)"\s*,\s*"""
    r""""[^"]*"\)\)[ \t]*$""",
    re.MULTILINE,
)

# Import line to inject (only once per file)
_IMPORT_LINE = "from platform_paths import DEFAULT_PATHS as _pp\n"


def _migrate_source(source: str) -> Tuple[str, List[str]]:
    """Return (migrated_source, list_of_changes). If no changes, returns original."""
    changes: List[str] = []
    needs_import = False
    lines = source.splitlines(keepends=True)
    new_lines = []
    import_injected = False
    import_present = "from platform_paths import DEFAULT_PATHS" in source

    for line in lines:
        m = _PATTERN.match(line.rstrip("\n"))
        if m:
            env_key = m.group("env_key")
            prop = ENV_TO_PROP.get(env_key)
            if prop:
                name = m.group("name")
                indent = m.group("indent")
                new_line = f"{indent}{name} = _pp.{prop}\n"
                changes.append(f"  {name}: {env_key!r} -> _pp.{prop}")
                new_lines.append(new_line)
                needs_import = True
                continue
        new_lines.append(line)

    if not changes:
        return source, []

    if needs_import and not import_present:
        # Inject import after the last stdlib/third-party import block
        # (heuristic: find last line starting with "from " or "import " or
        #  "NOEMAFORGE_VERSION" or "__future__")
        insert_at = 0
        for i, ln in enumerate(new_lines):
            stripped = ln.strip()
            if stripped.startswith(("from ", "import ")) or "noemaforge_version" in stripped.lower():
                insert_at = i + 1
        new_lines.insert(insert_at, _IMPORT_LINE)

    return "".join(new_lines), changes


def migrate_file(path: Path, dry_run: bool = False) -> List[str]:
    """Migrate a single Python file. Returns list of change descriptions."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"  [skip] {path}: {exc}", file=sys.stderr)
        return []

    new_source, changes = _migrate_source(source)
    if not changes:
        return []

    if not dry_run:
        path.write_text(new_source, encoding="utf-8")

    return changes


def migrate_directory(src_dir: Path, dry_run: bool = False,
                       skip_patterns: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """Migrate all .py files in src_dir. Returns {filename: [changes]}."""
    skip = skip_patterns or ["__pycache__", "platform_paths.py", "install_config.py",
                              "migrate_platform_paths.py"]
    results: Dict[str, List[str]] = {}
    for py_file in sorted(src_dir.rglob("*.py")):
        if any(s in str(py_file) for s in skip):
            continue
        changes = migrate_file(py_file, dry_run=dry_run)
        if changes:
            results[py_file.name] = changes
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show changes without writing files")
    parser.add_argument("--file", help="Migrate a single file instead of the whole src dir")
    parser.add_argument("--src-dir",
                        default=str(Path(__file__).resolve().parents[2] / "src"),
                        help="Source directory to scan (default: noemaforge/src)")
    args = parser.parse_args()

    mode = "DRY RUN" if args.dry_run else "APPLY"
    print(f"=== migrate_platform_paths.py [{mode}] ===")

    if args.file:
        changes = migrate_file(Path(args.file), dry_run=args.dry_run)
        if changes:
            print(f"\n{args.file}:")
            for c in changes: print(c)
        else:
            print("No changes needed.")
        return

    results = migrate_directory(Path(args.src_dir), dry_run=args.dry_run)
    if results:
        total = sum(len(v) for v in results.values())
        print(f"\nFound {len(results)} files with {total} replacements:\n")
        for fname, changes in results.items():
            print(f"  {fname}:")
            for c in changes:
                print(f"    {c}")
    else:
        print("No files needed migration.")

    if args.dry_run and results:
        print(f"\nRun without --dry-run to apply {sum(len(v) for v in results.values())} changes.")


if __name__ == "__main__":
    main()
