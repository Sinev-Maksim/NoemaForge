#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-version-audit.sh
# Zone: release/package
# Version: 0.32.1
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Provide NoemaForge release functionality for the packaged local runtime.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
# NoemaForge release/version consistency audit.
set -euo pipefail

ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
EXPECTED=""
FORMAT="human"
VERBOSE=0
STRICT_ALL=0

usage(){ cat <<'USAGE'
Usage: noemaforge version-audit [--root ROOT] [--expected VERSION] [--json] [--verbose] [--strict-all]

Default mode checks release-bearing metadata only:
  - ROOT/VERSION
  - release.json version
  - top-level JSON config "version" fields
  - RUNTIME_VERSION constants
  - shell VERSION assignments and cmd_version fallback lines

Historical references inside tests/catalog descriptions are reported only with --strict-all.
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
import ast, json, re, sys
from pathlib import Path
root = Path(sys.argv[1])
expected = sys.argv[2]
fmt = sys.argv[3]
verbose = sys.argv[4] == "1"
strict_all = sys.argv[5] == "1"
version_re = re.compile(r"(?<![A-Za-z0-9_.-])0\.31\.\d+(?:\.pre-alpha(?:-patched\d*)?|\.alpha(?:-patched\d+)?)?(?![A-Za-z0-9_.-])")
problems=[]
warnings=[]
warning_keys=set()
checks=[]
seen=[]

def add_problem(id, path, found, expected, message=""):
    problems.append({"id":id, "path":str(path), "found":found if isinstance(found,list) else [found], "expected":expected, "message":message})

def add_warning(id, path, found, message=""):
    key=(id, str(path), tuple(found if isinstance(found,list) else [found]), message)
    if key in warning_keys:
        return
    warning_keys.add(key)
    warnings.append({"id":id, "path":str(path), "found":found if isinstance(found,list) else [found], "message":message})

def check_id(id, ok, message, **extra):
    d={"id":id,"ok":bool(ok),"message":message}; d.update(extra); checks.append(d)

def read(p):
    try:
        size = p.stat().st_size
        if size > 2_000_000 and p.suffix not in {'.json', '.py', '.sh'} and p.name != 'noemaforge':
            known_runtime_bins = {'llama-server-cpu', 'llama-server-cuda', 'noemaforge-llm-gateway'}
            if p.parent.name == 'bin' and '.bak.' in p.name:
                add_warning('backup_binary_in_active_bin', p, [], 'backup binary should be moved to /var/backups/noemaforge/bin')
            elif verbose or p.name not in known_runtime_bins:
                add_warning('large_binary_skipped', p, [], f'skipped {size} byte non-text file')
            return ''
        return p.read_text(errors='replace')
    except Exception as e:
        add_warning('unreadable', p, [], str(e)); return None

# Canonical VERSION.
vfile=root/'VERSION'
actual=vfile.read_text().strip() if vfile.exists() else None
if actual != expected:
    add_problem('version_file_mismatch', vfile, actual or '<missing>', expected)

# release.json.
rj=root/'release.json'
if rj.exists():
    try:
        data=json.loads(rj.read_text())
        rv=data.get('version')
        if rv != expected: add_problem('release_json_version_mismatch', rj, rv or '<missing>', expected)
    except Exception as e:
        add_problem('release_json_invalid', rj, '<invalid>', expected, str(e))

# Top-level JSON config versions.
for cfgdir in [root/'configs']:
    if not cfgdir.exists(): continue
    for p in sorted(cfgdir.glob('*.json')):
        try:
            data=json.loads(p.read_text())
        except Exception as e:
            add_warning('json_parse_warning', p, [], str(e)); continue
        if isinstance(data, dict) and 'version' in data:
            v=data.get('version')
            if v != expected: add_problem('json_top_level_version_mismatch', p, v or '<missing>', expected)
            seen.append({'path':str(p),'metadata_version':v})

# Runtime constants in Python.
for srcdir in [root/'src']:
    if not srcdir.exists(): continue
    for p in sorted(srcdir.rglob('*.py')):
        text=read(p)
        if text is None: continue
        for m in re.finditer(r'RUNTIME_VERSION\s*=\s*["\']([^"\']+)["\']', text):
            v=m.group(1)
            if v != expected: add_problem('runtime_version_mismatch', p, v, expected)
            seen.append({'path':str(p),'runtime_version':v})

# Shell VERSION= assignments and cmd_version fallback in active scripts.
for sub in ['bin','tools/prep','tools/ops','helpers']:
    d=root/sub
    if not d.exists(): continue
    for p in sorted(d.rglob('*')):
        if not p.is_file(): continue
        text=read(p)
        if text is None: continue
        for m in re.finditer(r'(?m)^VERSION=["\']([^"\']+)["\']', text):
            v=m.group(1)
            if v != expected: add_problem('shell_version_assignment_mismatch', p, v, expected)
            seen.append({'path':str(p),'shell_version':v})
        # cmd_version fallback, only for noemaforge CLI.
        if p.name == 'noemaforge':
            for m in re.finditer(r'echo\s+["\'](0\.31\.\d+(?:\.pre-alpha(?:-patched\d*)?|\.alpha(?:-patched\d+)?)?)["\']', text):
                v=m.group(1)
                if v != expected: add_problem('cmd_version_fallback_mismatch', p, v, expected)
                seen.append({'path':str(p),'cmd_version_fallback':v})

# Strict grep of all active versions is opt-in, because catalogs may include historical names/test cases.
if strict_all:
    for sub in ['bin','src','configs','tools','helpers','systemd']:
        d=root/sub
        if not d.exists(): continue
        for p in sorted(d.rglob('*')):
            if not p.is_file(): continue
            if '__pycache__' in p.parts or p.suffix == '.pyc': continue
            text=read(p)
            if text is None: continue
            found=sorted(set(version_re.findall(text)))
            bad=[v for v in found if v != expected]
            if bad: add_problem('strict_stale_version_reference', p, bad, expected)
            elif found: seen.append({'path':str(p),'versions':found})
else:
    # Non-fatal warnings for active files containing older versions in comments/descriptions.
    for sub in ['bin','src','configs','tools','helpers','systemd']:
        d=root/sub
        if not d.exists(): continue
        for p in sorted(d.rglob('*')):
            if not p.is_file(): continue
            if '__pycache__' in p.parts or p.suffix == '.pyc': continue
            text=read(p)
            if text is None: continue
            found=sorted(set(version_re.findall(text)))
            bad=[v for v in found if v != expected]
            if bad:
                # Already captured metadata mismatches should be problems; remaining are warnings.
                if not any(pr['path']==str(p) for pr in problems):
                    add_warning('historical_or_fixture_version_reference', p, bad, 'Use --strict-all to fail on every active older version string.')

check_id('version_file', actual == expected, f"VERSION={actual!r}, expected={expected!r}")
check_id('active_release_metadata_versions', not problems, f"metadata/runtime mismatches={len(problems)}")
report={"ok": not problems, "root":str(root), "expected":expected, "checks":checks, "problems":problems, "warnings":warnings}
if verbose: report['seen_versions']=seen
if fmt == 'json':
    print(json.dumps(report, indent=2, ensure_ascii=False))
else:
    print(f"NoemaForge version audit: expected={expected} root={root}")
    if not problems: print('overall: OK')
    else:
        print(f"overall: FAIL ({len(problems)} metadata/runtime mismatches)")
        for p in problems: print(f"- {p['path']}: found={','.join(map(str,p['found']))} expected={expected} {p.get('message','')}")
    if warnings: print(f"warnings: {len(warnings)} audit warnings; run --verbose or --strict-all for details")
sys.exit(0 if not problems else 1)
PY
