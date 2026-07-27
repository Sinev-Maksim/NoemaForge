#!/usr/bin/env bash
# NoemaForge 0.33.0 — read-only night_watch co-integration evidence
set -euo pipefail
umask 077

REPO_ROOT=""
EXPECTED_HEAD=""
STATE_ROOT=""
OUT=""

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --repo-root)
            REPO_ROOT="${2:-}"
            shift 2
            ;;
        --expected-head)
            EXPECTED_HEAD="${2:-}"
            shift 2
            ;;
        --state-root)
            STATE_ROOT="${2:-}"
            shift 2
            ;;
        --out)
            OUT="${2:-}"
            shift 2
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
done

[[ -n "$REPO_ROOT" ]] || fail "--repo-root is required"
[[ -n "$EXPECTED_HEAD" ]] || fail "--expected-head is required"
[[ -n "$OUT" ]] || fail "--out is required"
[[ "$EXPECTED_HEAD" =~ ^[0-9a-f]{40}$ ]] || fail "expected head must be a full SHA"

REPO_ROOT="$(realpath "$REPO_ROOT")"
mkdir -p "$OUT"
OUT="$(realpath "$OUT")"

git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
    fail "not a Git worktree: $REPO_ROOT"

ACTUAL_HEAD="$(git -C "$REPO_ROOT" rev-parse HEAD)"
[[ "$ACTUAL_HEAD" = "$EXPECTED_HEAD" ]] ||
    fail "exact head mismatch: expected=$EXPECTED_HEAD actual=$ACTUAL_HEAD"

python3 - "$REPO_ROOT" "$OUT" <<'PY'
import os
import sys

repo = os.path.realpath(sys.argv[1])
out = os.path.realpath(sys.argv[2])
try:
    inside = os.path.commonpath([repo, out]) == repo
except ValueError:
    inside = False
if inside:
    raise SystemExit("FAIL: evidence output must be outside repository")
PY

STATUS_BEFORE="$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all)"
[[ -z "$STATUS_BEFORE" ]] || {
    echo "FAIL: repository must be clean before co-integration:" >&2
    printf '%s\n' "$STATUS_BEFORE" >&2
    exit 3
}

export PYTHONPATH="$REPO_ROOT/noemaforge/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1

PROBE_ARGS=(probe)
SNAPSHOT_ARGS=(snapshot)
if [[ -n "$STATE_ROOT" ]]; then
    PROBE_ARGS+=(--state-root "$STATE_ROOT")
    SNAPSHOT_ARGS+=(--state-root "$STATE_ROOT")
fi

python3 -m evolution_adapters.night_watch_readonly "${PROBE_ARGS[@]}" \
    > "$OUT/probe.json"

SELECTED_STATE_ROOT="$(
    python3 - "$OUT/probe.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
if doc.get("available") is not True:
    raise SystemExit("FAIL: live night_watch state was not detected")
root = str(doc.get("selected_state_root") or "")
if not root:
    raise SystemExit("FAIL: selected state root is empty")
print(root)
PY
)"
SELECTED_STATE_ROOT="$(realpath "$SELECTED_STATE_ROOT")"

python3 - "$REPO_ROOT" "$SELECTED_STATE_ROOT" "$OUT" <<'PY'
import os
import sys

repo = os.path.realpath(sys.argv[1])
state = os.path.realpath(sys.argv[2])
out = os.path.realpath(sys.argv[3])
for label, protected in (("repository", repo), ("state root", state)):
    try:
        inside = os.path.commonpath([protected, out]) == protected
    except ValueError:
        inside = False
    if inside:
        raise SystemExit(f"FAIL: evidence output must be outside {label}")
PY

manifest() {
    local root="$1"
    local destination="$2"
    python3 - "$root" "$destination" <<'PY'
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
destination = Path(sys.argv[2])
records = []

for path in sorted(root.rglob("*")):
    try:
        relative = path.relative_to(root)
    except ValueError:
        continue
    if relative.parts and relative.parts[0] == ".git":
        continue
    try:
        info = path.lstat()
    except OSError as exc:
        records.append({
            "path": str(relative),
            "type": "stat_error",
            "error": type(exc).__name__,
        })
        continue

    record = {
        "path": str(relative),
        "mode": stat.S_IMODE(info.st_mode),
        "mtime_ns": info.st_mtime_ns,
        "size": info.st_size,
    }
    if stat.S_ISLNK(info.st_mode):
        record["type"] = "symlink"
        record["target"] = os.readlink(path)
    elif stat.S_ISREG(info.st_mode):
        record["type"] = "file"
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            record["sha256"] = digest.hexdigest()
        except OSError as exc:
            record["read_error"] = type(exc).__name__
    elif stat.S_ISDIR(info.st_mode):
        record["type"] = "directory"
    else:
        record["type"] = "special"
    records.append(record)

payload = json.dumps(
    records,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
destination.write_bytes(payload)
print(hashlib.sha256(payload).hexdigest())
PY
}

echo "UAT_STAGE=manifests_before"
REPO_MANIFEST_BEFORE="$(manifest "$REPO_ROOT" "$OUT/repository-before.json")"
STATE_MANIFEST_BEFORE="$(manifest "$SELECTED_STATE_ROOT" "$OUT/state-before.json")"

echo "UAT_STAGE=snapshot_first"
python3 -m evolution_adapters.night_watch_readonly "${SNAPSHOT_ARGS[@]}" \
    > "$OUT/snapshot-first.json"

echo "UAT_STAGE=snapshot_second"
python3 -m evolution_adapters.night_watch_readonly "${SNAPSHOT_ARGS[@]}" \
    > "$OUT/snapshot-second.json"

cmp -s "$OUT/snapshot-first.json" "$OUT/snapshot-second.json" ||
    fail "repeated imports are not byte-identical"

echo "UAT_STAGE=canonical_validation"
python3 - "$OUT/snapshot-first.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
failures = []

if doc.get("available") is not True:
    failures.append("snapshot_not_available")
if doc.get("mode") != "read_only":
    failures.append("mode_not_read_only")
if doc.get("mutating_operations") != []:
    failures.append("mutating_operations_not_empty")
if doc.get("operations") != ["probe", "snapshot", "artifacts", "blockers"]:
    failures.append("unexpected_operation_surface")

validation = doc.get("canonical_validation") or {}
if validation.get("ok") is not True:
    failures.extend(validation.get("failures") or ["canonical_validation_failed"])

run = doc.get("evolution_run") or {}
if run.get("apiVersion") != "noemaforge.evolution-execution/v1":
    failures.append("run_api_version_invalid")
if run.get("runtime_neutral") is not True:
    failures.append("run_not_runtime_neutral")
policy = run.get("external_reference_policy") or {}
if policy.get("source_samples_local_only") is not True:
    failures.append("source_samples_not_local_only")
if policy.get("reference_runtime_shipped") is not False:
    failures.append("reference_runtime_marked_shipped")

usage = doc.get("resource_usage") or {}
for field in ("token_usage", "cpu_usage", "ram_usage", "vram_usage"):
    if usage.get(field) is not None:
        failures.append(f"{field}_must_be_unknown")

if failures:
    raise SystemExit("FAIL: " + ", ".join(sorted(set(failures))))
PY

echo "UAT_STAGE=manifests_after"
REPO_MANIFEST_AFTER="$(manifest "$REPO_ROOT" "$OUT/repository-after.json")"
STATE_MANIFEST_AFTER="$(manifest "$SELECTED_STATE_ROOT" "$OUT/state-after.json")"

[[ "$REPO_MANIFEST_BEFORE" = "$REPO_MANIFEST_AFTER" ]] ||
    fail "repository filesystem changed during adapter execution"
[[ "$STATE_MANIFEST_BEFORE" = "$STATE_MANIFEST_AFTER" ]] ||
    fail "observed night_watch state changed during adapter execution"

cmp -s "$OUT/repository-before.json" "$OUT/repository-after.json" ||
    fail "repository manifest changed"
cmp -s "$OUT/state-before.json" "$OUT/state-after.json" ||
    fail "state-root manifest changed"

STATUS_AFTER="$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all)"
[[ -z "$STATUS_AFTER" ]] || {
    echo "FAIL: repository is dirty after co-integration:" >&2
    printf '%s\n' "$STATUS_AFTER" >&2
    exit 4
}

SNAPSHOT_SHA="$(
    sha256sum "$OUT/snapshot-first.json" | awk '{print $1}'
)"

python3 - \
    "$OUT" \
    "$EXPECTED_HEAD" \
    "$SELECTED_STATE_ROOT" \
    "$SNAPSHOT_SHA" \
    "$REPO_MANIFEST_BEFORE" \
    "$STATE_MANIFEST_BEFORE" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
snapshot = json.loads((out / "snapshot-first.json").read_text(encoding="utf-8"))
summary = {
    "apiVersion": "noemaforge.evolution.night-watch-co-integration/v1",
    "kind": "NightWatchReadOnlyCoIntegrationSummary",
    "ok": True,
    "classification": "UAT request findings resolution",
    "exact_head": sys.argv[2],
    "selected_state_root": sys.argv[3],
    "source_fingerprint": snapshot.get("source_fingerprint"),
    "snapshot_sha256": sys.argv[4],
    "idempotent_reimport": True,
    "repository_zero_write": True,
    "state_root_zero_write": True,
    "repository_manifest_sha256": sys.argv[5],
    "state_manifest_sha256": sys.argv[6],
    "canonical_validation": snapshot.get("canonical_validation"),
    "mutating_operations": snapshot.get("mutating_operations"),
    "reference_source_policy": (
        snapshot.get("evolution_run", {}).get("external_reference_policy")
    ),
}
(out / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
PY

echo "PASS: night_watch read-only canonical co-integration"
echo "evidence: $OUT"
