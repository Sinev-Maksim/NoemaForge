#!/usr/bin/env python3
"""
migrate_platform_paths.py — batch-migrate hardcoded path constants to platform_paths.

Migrates two module-level constant patterns to platform_paths.DEFAULT_PATHS:

  Pattern 1 (env-get Path default):
      DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
    ->
      DEFAULT_ROOT = _pp.root

  Pattern 2 (bare top-level string constant):
      BASE        = "/var/lib/noemaforge"
      CONFIG_DIR  = "/opt/noemaforge/configs"
    ->
      BASE        = str(_pp.data_root)
      CONFIG_DIR  = str(_pp.root / "configs")

Only column-0 (top-level) UPPERCASE constants are rewritten, so paths embedded
in function bodies, docstrings or systemd unit templates (e.g. brainctl.py's
"ExecStart=/opt/noemaforge/...") are left untouched. Pattern 2 emits str(...) to
preserve the original str type (callers use os.path.join / string concatenation).

The "from platform_paths import DEFAULT_PATHS as _pp" import is injected exactly
once, at the END of the file's top-of-module import block — never inside a
function (this is the bug the previous version had: it scanned the whole file and
landed the import on the last import-looking line anywhere).

Usage:
    python migrate_platform_paths.py --dry-run         # show what would change
    python migrate_platform_paths.py                   # apply changes
    python migrate_platform_paths.py --file src/xyz.py # single file
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Mapping: env var name -> platform_paths property name (Pattern 1).
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

# Pattern 1: DEFAULT_XYZ = Path(os.environ.get("NOEMAFORGE_...", "/..."))
_PATTERN = re.compile(
    r"""^(?P<name>[A-Z_]+)\s*=\s*"""
    r"""Path\(os\.environ\.get\(\s*"(?P<env_key>NOEMAFORGE_[A-Z_]+)"\s*,\s*"""
    r""""[^"]*"\)\)[ \t]*$""",
)

# Pattern 2: top-level bare string constant pointing at a hardcoded NoemaForge
# path. Anchored at column 0 and ending the line, so only module-level constants
# are matched (never indented/in-function strings, never trailing-comment lines).
_STRING_CONST_PATTERN = re.compile(
    r"""^(?P<name>[A-Z_][A-Z0-9_]*)\s*=\s*"""
    r'''"(?P<path>/(?:var/lib|opt)/noemaforge[^"]*)"[ \t]*$''',
)

_IMPORT_LINE = "from platform_paths import DEFAULT_PATHS as _pp\n"


def _path_to_expr(raw: str) -> Optional[str]:
    """Map a hardcoded NoemaForge path to a platform_paths expression that yields
    a str (preserving the original literal's type)."""
    raw = raw.rstrip("/")
    if raw == "/var/lib/noemaforge":
        return "str(_pp.data_root)"
    if raw.startswith("/var/lib/noemaforge/"):
        suffix = raw[len("/var/lib/noemaforge/"):]
        return f'str(_pp.data_root / "{suffix}")'
    if raw == "/opt/noemaforge":
        return "str(_pp.root)"
    if raw.startswith("/opt/noemaforge/"):
        suffix = raw[len("/opt/noemaforge/"):]
        return f'str(_pp.root / "{suffix}")'
    return None


def _insert_import(lines: List[str]) -> List[str]:
    """Insert _IMPORT_LINE after the top-of-module import block.

    Scans only the file header: shebang/comments, the module docstring, blank
    lines and the contiguous top-level import block (including multi-line
    parenthesized or backslash-continued imports). Stops at the first real code
    statement, so the import is never placed inside a function/class or inside a
    multi-line import's parentheses.
    """
    insert_at = 0
    in_docstring = False
    quote = ""
    depth = 0      # unclosed "(" carried across the lines of a multi-line import
    cont = False   # previous line ended with a backslash continuation
    for i, ln in enumerate(lines):
        raw = ln.rstrip("\n")
        stripped = raw.strip()
        # Inside a multi-line import statement: consume until it closes.
        if depth > 0 or cont:
            depth += raw.count("(") - raw.count(")")
            cont = raw.endswith("\\")
            if depth <= 0 and not cont:
                depth = 0
                insert_at = i + 1
            continue
        if in_docstring:
            if quote in stripped:
                in_docstring = False
                insert_at = i + 1
            continue
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"""^[rbRB]{0,2}("{3}|'{3})""", stripped)
        if m:
            quote = m.group(1)
            # single-line docstring (opening and closing quote on one line)?
            if stripped.count(quote) >= 2:
                insert_at = i + 1
                continue
            in_docstring = True
            continue
        if stripped.startswith(("import ", "from ")):
            depth = raw.count("(") - raw.count(")")
            cont = raw.endswith("\\")
            if depth <= 0 and not cont:
                depth = 0
                insert_at = i + 1
            # else: multi-line import; insert_at is set when it closes
            continue
        # First real statement — header is over; stop scanning.
        break
    out = list(lines)
    out.insert(insert_at, _IMPORT_LINE)
    return out


def _migrate_source(source: str) -> Tuple[str, List[str]]:
    """Return (migrated_source, list_of_changes). If no changes, returns original."""
    changes: List[str] = []
    needs_import = False
    import_present = "from platform_paths import DEFAULT_PATHS" in source
    lines = source.splitlines(keepends=True)
    new_lines: List[str] = []

    for line in lines:
        body = line.rstrip("\n")

        # Pattern 1: Path(os.environ.get("NOEMAFORGE_X", "/..."))
        m = _PATTERN.match(body)
        if m:
            prop = ENV_TO_PROP.get(m.group("env_key"))
            if prop:
                name = m.group("name")
                new_lines.append(f"{name} = _pp.{prop}\n")
                changes.append(f"  {name}: env {m.group('env_key')} -> _pp.{prop}")
                needs_import = True
                continue

        # Pattern 2: top-level bare string constant
        m2 = _STRING_CONST_PATTERN.match(body)
        if m2:
            expr = _path_to_expr(m2.group("path"))
            if expr:
                name = m2.group("name")
                new_lines.append(f"{name} = {expr}\n")
                changes.append(f'  {name}: "{m2.group("path")}" -> {expr}')
                needs_import = True
                continue

        new_lines.append(line)

    if not changes:
        return source, []

    if needs_import and not import_present:
        new_lines = _insert_import(new_lines)

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
    """Migrate all .py files in src_dir. Returns {relative_path: [changes]}."""
    skip = skip_patterns or ["__pycache__", "platform_paths.py", "install_config.py",
                             "migrate_platform_paths.py"]
    results: Dict[str, List[str]] = {}
    for py_file in sorted(src_dir.rglob("*.py")):
        if any(s in str(py_file) for s in skip):
            continue
        changes = migrate_file(py_file, dry_run=dry_run)
        if changes:
            results[py_file.relative_to(src_dir).as_posix()] = changes
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
            for c in changes:
                print(c)
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
