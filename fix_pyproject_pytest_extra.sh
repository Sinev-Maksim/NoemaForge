#!/usr/bin/env bash
set -Eeuo pipefail

# Add pytest as the NoemaForge project test extra in pyproject.toml.
#
# Usage:
#   cd ~/src/NoemaForge
#   bash ./fix_pyproject_pytest_extra.sh
#
# Optional:
#   INSTALL=1 bash ./fix_pyproject_pytest_extra.sh
#   INSTALL=1 RUN_TESTS=1 bash ./fix_pyproject_pytest_extra.sh
#
# What it does:
#   - creates a timestamped pyproject.toml backup;
#   - ensures [project.optional-dependencies] exists;
#   - ensures test = ["pytest>=8,<9"] exists;
#   - if test extra already exists, adds pytest only if missing;
#   - validates TOML syntax with Python tomllib;
#   - optionally installs the test extra into .venv;
#   - optionally runs focused pytest checks.

PYPROJECT="${PYPROJECT:-pyproject.toml}"
PYTEST_SPEC="${PYTEST_SPEC:-pytest>=8,<9}"
INSTALL="${INSTALL:-0}"
RUN_TESTS="${RUN_TESTS:-0}"
VENV_DIR="${VENV_DIR:-.venv}"

if [[ ! -f "$PYPROJECT" ]]; then
  echo "[fix-pytest-extra][ERROR] $PYPROJECT not found. Run from repo root." >&2
  exit 2
fi

python3 - "$PYPROJECT" "$PYTEST_SPEC" <<'PY'
from __future__ import annotations

import re
import shutil
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
pytest_spec = sys.argv[2]

text = path.read_text(encoding="utf-8")

# Validate current TOML before editing. If this fails, do not touch the file.
try:
    tomllib.loads(text)
except Exception as exc:
    raise SystemExit(f"[fix-pytest-extra][ERROR] existing pyproject.toml is not valid TOML: {exc}")

timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = path.with_name(f"{path.name}.bak.{timestamp}")
shutil.copy2(path, backup)

header_re = re.compile(r"(?m)^\[project\.optional-dependencies\]\s*$")
next_header_re = re.compile(r"(?m)^\[")

def find_table_bounds(src: str, table_header_re: re.Pattern[str]) -> tuple[int, int, int, int] | None:
    match = table_header_re.search(src)
    if not match:
        return None

    table_start = match.start()
    table_body_start = match.end()

    next_match = next_header_re.search(src, table_body_start)
    table_end = next_match.start() if next_match else len(src)
    return table_start, table_body_start, table_end, match.end()

def find_key_assignment(src: str, key: str, start: int, end: int) -> tuple[int, int] | None:
    # Finds a TOML key assignment inside the table and returns the full assignment span.
    # Supports one-line values and multiline arrays.
    line_re = re.compile(rf"(?m)^(\s*){re.escape(key)}\s*=\s*")
    match = line_re.search(src, start, end)
    if not match:
        return None

    assign_start = match.start()
    cursor = match.end()

    # If this is a multiline array, scan until bracket balance returns to zero.
    remainder = src[cursor:end]
    first_line_end = src.find("\n", cursor, end)
    if first_line_end == -1:
        first_line_end = end

    value_prefix = src[cursor:first_line_end]
    if "[" in value_prefix:
        depth = 0
        in_str = False
        escaped = False
        i = cursor
        while i < end:
            ch = src[i]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth <= 0:
                        line_end = src.find("\n", i, end)
                        assign_end = end if line_end == -1 else line_end + 1
                        return assign_start, assign_end
            i += 1

    # Fallback: single-line assignment.
    return assign_start, first_line_end + (1 if first_line_end < len(src) and src[first_line_end:first_line_end+1] == "\n" else 0)

def add_pytest_to_existing_test_extra(src: str, start: int, end: int) -> str:
    assignment = src[start:end]
    if re.search(r'["\']pytest(?:[<>=!~,\d\.\s]*)?["\']', assignment):
        return src

    # Multiline array: insert before closing bracket.
    close_idx = assignment.rfind("]")
    if close_idx != -1:
        indent_match = re.search(r"(?m)^(\s*)\]", assignment)
        item_indent = "  "
        if indent_match:
            item_indent = indent_match.group(1)
        else:
            key_indent = re.match(r"(\s*)", assignment).group(1)
            item_indent = key_indent + "  "

        insert = f'{item_indent}"{pytest_spec}",\n'
        new_assignment = assignment[:close_idx] + insert + assignment[close_idx:]
        return src[:start] + new_assignment + src[end:]

    # Non-array or unusual value: replace test extra with explicit multiline array.
    line_indent = re.match(r"(\s*)", assignment).group(1)
    new_assignment = (
        f'{line_indent}test = [\n'
        f'{line_indent}  "{pytest_spec}",\n'
        f'{line_indent}]\n'
    )
    return src[:start] + new_assignment + src[end:]

table = find_table_bounds(text, header_re)

if table is None:
    suffix = "" if text.endswith("\n") else "\n"
    text = (
        text
        + suffix
        + "\n[project.optional-dependencies]\n"
        + "test = [\n"
        + f'  "{pytest_spec}",\n'
        + "]\n"
    )
else:
    table_start, table_body_start, table_end, header_end = table
    existing = find_key_assignment(text, "test", table_body_start, table_end)
    if existing:
        text = add_pytest_to_existing_test_extra(text, existing[0], existing[1])
    else:
        insert = (
            "\ntest = [\n"
            f'  "{pytest_spec}",\n'
            "]\n"
        )
        text = text[:header_end] + insert + text[header_end:]

# Validate resulting TOML.
try:
    parsed = tomllib.loads(text)
except Exception as exc:
    path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    raise SystemExit(f"[fix-pytest-extra][ERROR] edited TOML invalid; restored backup: {exc}")

extras = parsed.get("project", {}).get("optional-dependencies", {})
test_extra = extras.get("test")
if not isinstance(test_extra, list) or not any(str(item).startswith("pytest") for item in test_extra):
    path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    raise SystemExit("[fix-pytest-extra][ERROR] test extra was not created correctly; restored backup")

if text != path.read_text(encoding="utf-8"):
    path.write_text(text, encoding="utf-8")
    print(f"[fix-pytest-extra] updated {path}")
else:
    print(f"[fix-pytest-extra] no change needed; pytest already present in test extra")

print(f"[fix-pytest-extra] backup: {backup}")
print(f"[fix-pytest-extra] test extra: {test_extra}")
PY

python3 - <<'PY'
import tomllib
from pathlib import Path
data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
print("[fix-pytest-extra] TOML validation: OK")
print("[fix-pytest-extra] project.optional-dependencies.test =", data.get("project", {}).get("optional-dependencies", {}).get("test"))
PY

if [[ "$INSTALL" == "1" ]]; then
  if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
  fi

  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"

  python -m pip install -U pip
  python -m pip install -e '.[test]'

  python - <<'PY'
import pytest
print(f"[fix-pytest-extra] pytest import: OK {pytest.__version__}")
PY
fi

if [[ "$RUN_TESTS" == "1" ]]; then
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    "$VENV_DIR/bin/python" -m pytest \
      noemaforge/tests/test_033_prod_ready_install_reentry.py \
      noemaforge/tests/test_pipeline_runtime_public_mwp.py \
      -q
  else
    python3 -m pytest \
      noemaforge/tests/test_033_prod_ready_install_reentry.py \
      noemaforge/tests/test_pipeline_runtime_public_mwp.py \
      -q
  fi
fi

echo "[fix-pytest-extra] done"
