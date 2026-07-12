#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-version-audit.sh
# Zone: release/package
# Version: 0.32.2
# Created: 2026-05-14
# Modified: 2026-05-25
# Purpose: Audit NoemaForge release/version consistency against the canonical VERSION file.
# Inputs: --root, --expected, release metadata, Python runtime modules, shell helpers, JSON/YAML configs.
# Outputs: Human or JSON audit report and non-zero exit code on version drift.
# Side effects: None; this script is read-only.
# Tests: bash -n, noemaforge-version-audit.sh --strict-all --expected 0.32.2.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
set -euo pipefail

ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
EXPECTED=""
FORMAT="human"
VERBOSE=0
STRICT_ALL=0

usage(){ cat <<'USAGE'
Usage: noemaforge-version-audit.sh [--root ROOT] [--expected VERSION] [--json] [--verbose] [--strict-all]

Checks:
  - canonical VERSION files
  - release.json and release YAML metadata
  - JSON/YAML top-level version fields
  - Python centralized noemaforge_version import behavior
  - hardcoded Python RUNTIME_VERSION assignments outside noemaforge_version.py
  - shell VERSION assignments and stale command fallbacks

With --strict-all, any active old version literal in runtime/config/tooling files is a failure.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --expected) EXPECTED="$2"; shift 2 ;;
    --json) FORMAT="json"; shift ;;
    --verbose|--full) VERBOSE=1; shift ;;
    --strict-all) STRICT_ALL=1; shift ;;
    -h|--help|help|\?) usage; exit 0 ;;
    *) echo "[version-audit][ERROR] unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$EXPECTED" ]]; then
  if [[ -f "$ROOT/VERSION" ]]; then EXPECTED="$(tr -d '[:space:]' < "$ROOT/VERSION")"; else EXPECTED="unknown"; fi
fi

python3 - "$ROOT" "$EXPECTED" "$FORMAT" "$VERBOSE" "$STRICT_ALL" <<'PY'
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
expected = sys.argv[2]
fmt = sys.argv[3]
verbose = sys.argv[4] == "1"
strict_all = sys.argv[5] == "1"

old_version_re = re.compile(r"(?<![A-Za-z0-9_.-])(?:0\.31\.13\.alpha|0\.31\.13\.pre-alpha(?:-patched\d+)?|0\.31\.\d+(?:\.alpha(?:-patched\d+)?|\.pre-alpha(?:-patched\d+)?)?|0\.29\.10|0\.29\.11|0\.29\.06|0\.28\.5)(?![A-Za-z0-9_.-])")
hardcoded_runtime_re = re.compile(r"(?m)^\s*RUNTIME_VERSION\s*=\s*[\"'][^\"']+[\"']")

problems: list[dict] = []
warnings: list[dict] = []
checks: list[dict] = []
seen: list[dict] = []
warning_keys: set[tuple] = set()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root))
    except Exception:
        return str(path)


def add_problem(problem_id: str, path: Path | str, found, expected_value: str, message: str = "") -> None:
    if not isinstance(found, list):
        found = [found]
    problems.append({"id": problem_id, "path": str(path), "found": found, "expected": expected_value, "message": message})


def add_warning(warning_id: str, path: Path | str, found=None, message: str = "") -> None:
    if found is None:
        found = []
    if not isinstance(found, list):
        found = [found]
    key = (warning_id, str(path), tuple(map(str, found)), message)
    if key in warning_keys:
        return
    warning_keys.add(key)
    warnings.append({"id": warning_id, "path": str(path), "found": found, "message": message})


def check(check_id: str, ok: bool, message: str, **extra) -> None:
    row = {"id": check_id, "ok": bool(ok), "message": message}
    row.update(extra)
    checks.append(row)


def read_text(path: Path) -> str | None:
    try:
        size = path.stat().st_size
        if size > 2_000_000 and path.suffix not in {".json", ".py", ".sh", ".yaml", ".yml"}:
            runtime_bins = {"llama-server-cpu", "llama-server-cuda", "noemaforge-llm-gateway"}
            if path.parent.name == "bin" and ".bak." in path.name:
                add_warning("backup_binary_in_active_bin", path, [], "Move backup binaries to /var/backups/noemaforge/bin before release packaging.")
            elif verbose or path.name not in runtime_bins:
                add_warning("large_binary_skipped", path, [], f"skipped {size} byte non-text file")
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        add_warning("unreadable", path, [], str(exc))
        return None


def json_version(path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        add_warning("json_parse_warning", path, [], str(exc))
        return
    if isinstance(data, dict) and "version" in data:
        found = str(data.get("version"))
        seen.append({"path": rel(path), "version": found})
        if found != expected:
            add_problem("json_top_level_version_mismatch", path, found, expected)


def simple_yaml_version(path: Path) -> None:
    text = read_text(path)
    if text is None:
        return
    for line in text.splitlines():
        if re.match(r"^\s*version\s*:", line):
            found = line.split(":", 1)[1].strip().strip("'\"")
            seen.append({"path": rel(path), "version": found})
            if found and found != expected:
                add_problem("yaml_top_level_version_mismatch", path, found, expected)
            return


def check_version_file(path: Path, label: str) -> None:
    if not path.exists():
        add_problem("version_file_missing", path, "<missing>", expected, label)
        return
    found = path.read_text(encoding="utf-8", errors="replace").strip()
    seen.append({"path": rel(path), "version_file": found})
    if found != expected:
        add_problem("version_file_mismatch", path, found or "<empty>", expected, label)


def check_optional_version_file(path: Path, label: str) -> None:
    if path.exists():
        check_version_file(path, label)


source_checkout = (root / "noemaforge" / "src").is_dir()
installed_payload = (root / "src").is_dir()


# Canonical version files. Source checkouts have root/VERSION and
# noemaforge/VERSION; installed /opt payloads have VERSION at the payload root.
check_version_file(root / "VERSION", "root VERSION")
if source_checkout:
    check_version_file(root / "noemaforge" / "VERSION", "package VERSION")
elif installed_payload:
    check_optional_version_file(root / "noemaforge" / "VERSION", "legacy nested package VERSION")
else:
    check_version_file(root / "noemaforge" / "VERSION", "package VERSION")
check_version_file(root / "docs" / "VERSION", "docs VERSION")

# Release metadata.
for release_json in [root / "release.json", root / "docs" / "release.json"]:
    if release_json.exists():
        json_version(release_json)
for release_dir in [root / "noemaforge" / "release", root / "release"]:
    if not release_dir.exists():
        continue
    for release_yaml in sorted(release_dir.glob(f"release-v{expected}.yaml")):
        simple_yaml_version(release_yaml)

# Active config files are policy/schema metadata, not release identity. Keep
# release version enforcement to canonical package metadata above; strict-all
# still reports old active literals when operators request the broader scan.

# Centralized runtime version import check.
module_path = root / "noemaforge" / "src" / "noemaforge_version.py"
if not module_path.exists() and (root / "src" / "noemaforge_version.py").exists():
    module_path = root / "src" / "noemaforge_version.py"
if not module_path.exists():
    add_problem("central_version_module_missing", module_path, "<missing>", expected)
else:
    env = os.environ.copy()
    env["NOEMAFORGE_ROOT"] = str(root)
    code = "import sys; sys.path.insert(0, r'%s'); import noemaforge_version; print(noemaforge_version.RUNTIME_VERSION)" % str(module_path.parent)
    proc = subprocess.run([sys.executable, "-c", code], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    imported = proc.stdout.strip()
    check("central_version_import", proc.returncode == 0 and imported == expected, f"imported={imported!r}, expected={expected!r}", stderr=proc.stderr.strip())
    if proc.returncode != 0 or imported != expected:
        add_problem("central_version_import_mismatch", module_path, imported or f"rc={proc.returncode}", expected, proc.stderr.strip())

# Python runtime hardcoded assignments are forbidden outside noemaforge_version.py.
for src_dir in [root / "noemaforge" / "src", root / "src"]:
    if not src_dir.exists():
        continue
    for path in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = read_text(path)
        if text is None:
            continue
        if path.name != "noemaforge_version.py" and hardcoded_runtime_re.search(text):
            add_problem("hardcoded_runtime_version_assignment", path, hardcoded_runtime_re.findall(text), "from noemaforge_version import RUNTIME_VERSION")

# Shell VERSION assignments should not pin stale release versions.
for sub in ["helpers", "noemaforge/bin", "noemaforge/tools", "tools", "bin"]:
    d = root / sub
    if not d.exists():
        continue
    for path in sorted(d.rglob("*")):
        if not path.is_file():
            continue
        text = read_text(path)
        if text is None:
            continue
        for match in re.finditer(r"(?m)^VERSION=[\"']([^\"']+)[\"']", text):
            found = match.group(1)
            if not re.match(r"^\d+\.\d+\.\d+(?:[-.][A-Za-z0-9]+)?$", found):
                continue
            seen.append({"path": rel(path), "shell_version": found})
            if found != expected:
                add_problem("shell_version_assignment_mismatch", path, found, expected)

# Strict stale version scan for active release-bearing files.
scan_roots = ["helpers", "noemaforge/bin", "noemaforge/src", "noemaforge/configs", "noemaforge/tools", "noemaforge/systemd", "setup.sh"]
for sub in scan_roots:
    path = root / sub
    paths: list[Path]
    if path.is_file():
        paths = [path]
    elif path.exists():
        paths = [p for p in path.rglob("*") if p.is_file()]
    else:
        continue
    for item in sorted(paths):
        if "__pycache__" in item.parts or item.suffix == ".pyc":
            continue
        text = read_text(item)
        if text is None:
            continue
        bad = sorted(set(old_version_re.findall(text)))
        bad = [v for v in bad if v != expected]
        if not bad:
            continue
        if strict_all:
            add_problem("strict_stale_version_reference", item, bad, expected)
        else:
            if not any(p["path"] == str(item) for p in problems):
                add_warning("historical_or_fixture_version_reference", item, bad, "Use --strict-all to fail on every active older version string.")

check("version_files", not any(p["id"].startswith("version_file") for p in problems), "canonical VERSION files checked")
check("metadata_versions", not any("version_mismatch" in p["id"] for p in problems), "metadata versions checked")
check("hardcoded_runtime_versions", not any(p["id"] == "hardcoded_runtime_version_assignment" for p in problems), "Python runtime version assignments checked")

report = {
    "ok": not problems,
    "root": str(root),
    "expected": expected,
    "checks": checks,
    "problems": problems,
    "warnings": warnings,
}
if verbose:
    report["seen_versions"] = seen

if fmt == "json":
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
else:
    print(f"NoemaForge version audit: expected={expected} root={root}")
    print("overall: OK" if not problems else f"overall: FAIL ({len(problems)} problems)")
    for problem in problems:
        print(f"- {problem['id']}: {problem['path']} found={problem['found']} expected={problem['expected']} {problem.get('message','')}")
    if warnings:
        print(f"warnings: {len(warnings)}; run --json --verbose for details")

sys.exit(0 if not problems else 1)
PY
