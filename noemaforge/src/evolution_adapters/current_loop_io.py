"""Bounded read-only IO helpers for the current-loop adapter."""
from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

ADAPTER_ID = "evolution.code.current-loop"
ADAPTER_VERSION = "noemaforge.evolution.current-loop-adapter/v1"
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_ARTIFACTS = 250
SHA40 = re.compile(r"^[0-9a-f]{40}$")
STATUS_LINE = re.compile(r"^- ([a-zA-Z0-9_]+):\s*(.*)$")
ARTIFACT_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("status.md", "coordinator_status"),
    ("ledger.md", "coordinator_ledger"),
    ("coordinator-lock-v51.json", "coordinator_lock"),
    ("last-staged-paths.txt", "staged_paths"),
    ("scheduler/open-pr-snapshot.json", "github_snapshot"),
    ("scheduler/pr-creation-epochs.json", "pr_creation_ledger"),
    ("scheduler/pr-*.json", "scheduler_pr_state"),
    ("scheduler-v51/pr-*.json", "scheduler_pr_state_legacy"),
    ("scheduler-v47/pr-*.json", "scheduler_pr_state_legacy"),
    ("work-items-v51/issue-*.json", "issue_work_item"),
    ("work-items-v51/recovery/*", "issue_recovery"),
    ("review-threads-v46/parked-prs/pr-*.json", "parked_review"),
    ("issues-v39/manual-pending/*", "manual_evidence_pending"),
    ("security-v36/last-branch-gate.txt", "security_gate"),
    ("evolution-v43/**/*.json", "evolution_evidence"),
    ("evolution-v43/**/*.md", "evolution_evidence"),
    ("visual-v44/**/*.json", "visual_evidence"),
    ("visual-v44/**/*.md", "visual_evidence"),
    ("semantic-loops/**/*.quarantined", "quarantine_marker"),
    ("*-pause-until.txt", "provider_pause_marker"),
    ("*-write-blocked-until.txt", "provider_write_block_marker"),
    ("logs/*.log", "loop_log"),
)


def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def date_time(value: Any, fallback: str, warnings: List[str], field: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return text
    except ValueError:
        warnings.append(f"{field}:invalid_date_time")
        return fallback


def exact_head(value: Any) -> Optional[str]:
    text = str(value or "").lower()
    return text if SHA40.fullmatch(text) else None


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    seen: set[str] = set()
    result: List[Path] = []
    for path in paths:
        key = str(path.expanduser().absolute())
        if key not in seen:
            seen.add(key)
            result.append(Path(key))
    return result


def candidate_state_roots(
    explicit: Optional[Path | str] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
    home: Optional[Path | str] = None,
) -> List[Path]:
    env = dict(os.environ if environ is None else environ)
    home_path = Path(home or env.get("HOME") or Path.home())
    candidates: List[Path] = [Path(explicit)] if explicit is not None else []
    candidates.extend(Path(env[key]) for key in ("STATE_ROOT", "NF_V46_STATE_DIR") if env.get(key))
    candidates.extend([
        home_path / ".local/share/noemaforge-agent-runs/token-aware-0330-v46",
        home_path / ".local/share/noemaforge-agent-runs/token-aware-0330-v3",
    ])
    return _dedupe_paths(candidates)


def _root_score(root: Path) -> Tuple[int, List[str]]:
    weights = {
        "status.md": 6,
        "coordinator-lock-v51.json": 5,
        "scheduler": 4,
        "work-items-v51": 3,
        "logs": 2,
        "ledger.md": 1,
    }
    indicators = [relative for relative in weights if (root / relative).exists()]
    return sum(weights[item] for item in indicators), indicators


def probe(
    state_root: Optional[Path | str] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
    home: Optional[Path | str] = None,
) -> Dict[str, Any]:
    records = []
    for index, root in enumerate(candidate_state_roots(state_root, environ=environ, home=home)):
        score, indicators = _root_score(root)
        records.append({
            "path": str(root),
            "exists": root.exists(),
            "score": score,
            "indicators": indicators,
            "order": index,
        })
    selected = records[0] if state_root is not None else max(records, key=lambda item: (item["score"], -item["order"]))
    active = [item for item in records if item["score"] > 0]
    warnings: List[str] = []
    if len(active) > 1:
        warnings.append("multiple_current_loop_state_roots_detected")
    if any("token-aware-0330-v46" in item["path"] for item in active) and any("token-aware-0330-v3" in item["path"] for item in active):
        warnings.append("v46_wrapper_and_v3_base_state_layout_both_present")
    if selected["score"] == 0:
        warnings.append("current_loop_state_not_detected")
    return {
        "apiVersion": ADAPTER_VERSION,
        "kind": "CurrentLoopAdapterProbe",
        "adapter_id": ADAPTER_ID,
        "mode": "read_only",
        "available": selected["score"] > 0,
        "selected_state_root": selected["path"],
        "candidates": records,
        "operations": ["probe", "snapshot", "artifacts", "blockers"],
        "mutating_operations": [],
        "warnings": warnings,
    }


def contained_file(root: Path, relative: str, max_bytes: int = MAX_FILE_BYTES) -> Tuple[Optional[Path], Optional[str]]:
    base = root.resolve()
    try:
        resolved = (root / relative).resolve(strict=True)
    except (OSError, RuntimeError):
        return None, "missing_or_unresolvable"
    try:
        if os.path.commonpath([str(base), str(resolved)]) != str(base):
            return None, "path_escape"
    except ValueError:
        return None, "path_escape"
    try:
        if not resolved.is_file():
            return None, "not_file"
        if resolved.stat().st_size > max_bytes:
            return None, "oversized"
    except OSError:
        return None, "stat_failed"
    return resolved, None


def read_text(root: Path, relative: str, warnings: List[str]) -> Optional[str]:
    path, error = contained_file(root, relative)
    if path is None:
        if error not in {"missing_or_unresolvable", "not_file"}:
            warnings.append(f"{relative}:{error}")
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        warnings.append(f"{relative}:read_failed")
        return None


def read_json(root: Path, relative: str, warnings: List[str]) -> Optional[Dict[str, Any]]:
    text = read_text(root, relative, warnings)
    if text is None:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        warnings.append(f"{relative}:malformed_json")
        return None
    return payload if isinstance(payload, dict) else None


def parse_status(text: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    in_fence = False
    for line in str(text or "").splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        match = None if in_fence else STATUS_LINE.match(line.strip())
        if match:
            result[match.group(1)] = match.group(2).strip()
    return result


def artifacts(state_root: Path | str, *, max_artifacts: int = MAX_ARTIFACTS) -> Dict[str, Any]:
    root = Path(state_root)
    warnings: List[str] = []
    records: Dict[str, Dict[str, Any]] = {}
    for pattern, kind in ARTIFACT_PATTERNS:
        for path in sorted(root.glob(pattern)):
            if len(records) >= max_artifacts:
                warnings.append("artifact_limit_reached")
                break
            relative = str(path.relative_to(root))
            resolved, error = contained_file(root, relative)
            if resolved is None:
                if error not in {"missing_or_unresolvable", "not_file"}:
                    warnings.append(f"{relative}:{error}")
                continue
            try:
                data, stat = resolved.read_bytes(), resolved.stat()
            except OSError:
                warnings.append(f"{relative}:read_failed")
                continue
            digest = hashlib.sha256(data).hexdigest()
            modified = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            records[relative] = {
                "artifact_id": f"sha256:{digest}",
                "relative_path": relative,
                "kind": kind,
                "size_bytes": stat.st_size,
                "modified_at": modified,
                "sha256": digest,
                "source": "current-loop-readonly",
            }
    return {"artifacts": [records[key] for key in sorted(records)], "warnings": sorted(set(warnings))}
