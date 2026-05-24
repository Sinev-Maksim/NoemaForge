#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/pipelines/photos_diary.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Manage NoemaForge pipeline catalog, runs, gates, artifacts and state.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/pipelines/photos_diary.py
# Purpose: Implement the deterministic pipeline 'photos_diary'.
# Invoked by / imported from:
#   - src/noemaforge_core.py
# Public API / entry functions:
#   - build_facts
#   - render_diary_md
#   - write_manifest
#   - run
#   - main
# Inputs:
#   - --in-dir
#   - --out-dir
#   - --day
#   - --cfg
#   - Common path inputs: /opt/noemaforge/configs/photos-diary.yaml
#   - Imports: __future__, datetime, hashlib, json, os, re, typing, yaml
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""photos_diary.py (v0.11.0)

Deterministic photo -> diary pipeline.

Input:
- A directory tree with photo files (jpg/jpeg/png/heic best-effort)
- No network access

Output (per day):
  /var/lib/noemaforge/routines/diary/YYYY-MM-DD/
    facts.json         # structured episodes
    diary.md           # human-readable diary (template)
    manifest.json      # inputs + outputs pointers

Notes:
- Image understanding (captioning, dog/sunrise detection) is NOT done here.
  That's brain-zone work and should be done via role execution with ToolProxy,
  producing additional artifacts (e.g., diary_story.md).
- This pipeline focuses on reliable metadata and episode grouping.
"""


import datetime as dt
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except Exception:
    yaml = None

try:
    from PIL import Image, ExifTags  # type: ignore
except Exception:
    Image = None  # type: ignore
    ExifTags = None  # type: ignore


SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/caps.py
#   - src/casebase.py
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
# Calls:
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _load_yaml(path: str)
# Purpose: Implement the routine ' load yaml'.
# Inputs:
#   - path: str
# Called by:
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/canary_runner.py
#   - src/daily_scheduler.py
#   - src/fixture_bundle.py
#   - src/flow_metrics.py
#   - src/incidents.py
#   - src/knowledge/policy.py
# Calls:
#   - open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_yaml(path: str) -> Dict[str, Any]:
    if yaml is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _ensure_dir(p: str)
# Purpose: Implement the routine ' ensure dir'.
# Inputs:
#   - p: str
# Called by:
#   - src/casebase.py
#   - src/memory_system.py
#   - src/pipelines/finance_budget.py
#   - src/vstore.py
# Calls:
#   - makedirs
# Returns / emits: None
# Side effects:
#   - creates directories
# === End NoemaForge Autodoc Function Header ===
def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_text(s: str)
# Purpose: Implement the routine ' sha256 text'.
# Inputs:
#   - s: str
# Called by:
#   - src/team_memory_sync.py
#   - src/telemetry.py
# Calls:
#   - sha256, update, hexdigest, encode
# Returns / emits: str
# Key locals:
#   - h
# === End NoemaForge Autodoc Function Header ===
def _sha256_text(s: str) -> str:
    h = hashlib.sha256()
    h.update(s.encode("utf-8"))
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _parse_date(s: str)
# Purpose: Implement the routine ' parse date'.
# Inputs:
#   - s: str
# Called by:
#   - src/pipelines/finance_budget.py
# Calls:
#   - date, strptime
# Returns / emits: dt.date
# === End NoemaForge Autodoc Function Header ===
def _parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


# === NoemaForge Autodoc Function Header ===
# Function: _list_photo_files(root: str)
# Purpose: Implement the routine ' list photo files'.
# Inputs:
#   - root: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - walk, sort, lower, append, join, splitext
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - ext, fn, out
# === End NoemaForge Autodoc Function Header ===
def _list_photo_files(root: str) -> List[str]:
    out: List[str] = []
    for base, _dirs, files in os.walk(root):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in SUPPORTED_EXT:
                out.append(os.path.join(base, fn))
    out.sort()
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _parse_exif_dt(v)
# Purpose: Implement the routine ' parse exif dt'.
# Inputs:
#   - v
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, strip, match, datetime, decode, str, int, group
# Returns / emits: Optional[dt.datetime]
# Key locals:
#   - m, s, v
# === End NoemaForge Autodoc Function Header ===
def _parse_exif_dt(v: Any) -> Optional[dt.datetime]:
    if not v:
        return None
    if isinstance(v, bytes):
        try:
            v = v.decode("utf-8", "replace")
        except Exception:
            return None
    s = str(v).strip()
    # common EXIF: "YYYY:MM:DD HH:MM:SS"
    m = re.match(r"^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", s)
    if not m:
        return None
    try:
        return dt.datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6))
        )
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: _gps_to_deg(gps)
# Purpose: Implement the routine ' gps to deg'.
# Inputs:
#   - gps
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - float
# Returns / emits: Optional[float]
# Key locals:
#   - deg, minute, sec
# === End NoemaForge Autodoc Function Header ===
def _gps_to_deg(gps: Any) -> Optional[float]:
    # gps can be a tuple of rationals, e.g. ((deg_num,deg_den),(min_num,min_den),(sec_num,sec_den))
    try:
        d, m, s = gps
        deg = float(d[0]) / float(d[1])
        minute = float(m[0]) / float(m[1])
        sec = float(s[0]) / float(s[1])
        return deg + (minute / 60.0) + (sec / 3600.0)
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: _extract_exif(path: str)
# Purpose: Implement the routine ' extract exif'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - items, get, isinstance, open, _gps_to_deg, _getexif, str, _parse_exif_dt
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - dtv, exif, gps, img, key, lat, lat_ref, lon, lon_ref, name, named, out
# === End NoemaForge Autodoc Function Header ===
def _extract_exif(path: str) -> Dict[str, Any]:
    if Image is None:
        return {}
    try:
        img = Image.open(path)
        exif = img._getexif() or {}
    except Exception:
        return {}

    # Map tag ids -> names
    tagmap = {}
    try:
        tagmap = {k: v for k, v in ExifTags.TAGS.items()}  # type: ignore
    except Exception:
        tagmap = {}

    named: Dict[str, Any] = {}
    for k, v in (exif or {}).items():
        name = tagmap.get(k, str(k))
        named[name] = v

    out: Dict[str, Any] = {}

    # datetime
    for key in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
        if key in named:
            dtv = _parse_exif_dt(named.get(key))
            if dtv:
                out["datetime"] = dtv
                out["datetime_src"] = key
                break

    # GPS
    gps = named.get("GPSInfo")
    if isinstance(gps, dict):
        lat = _gps_to_deg(gps.get(2))
        lat_ref = gps.get(1)
        lon = _gps_to_deg(gps.get(4))
        lon_ref = gps.get(3)
        if lat is not None and lat_ref in ("S", b"S"):
            lat = -lat
        if lon is not None and lon_ref in ("W", b"W"):
            lon = -lon
        if lat is not None and lon is not None:
            out["gps"] = {"lat": lat, "lon": lon}

    return out


# === NoemaForge Autodoc Function Header ===
# Function: _time_of_day_label(t: dt.time)
# Purpose: Implement the routine ' time of day label'.
# Inputs:
#   - t: dt.time
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Returns / emits: str
# Key locals:
#   - h
# === End NoemaForge Autodoc Function Header ===
def _time_of_day_label(t: dt.time) -> str:
    h = t.hour
    if 5 <= h < 9:
        return "утро"
    if 9 <= h < 12:
        return "позднее утро"
    if 12 <= h < 17:
        return "день"
    if 17 <= h < 21:
        return "вечер"
    return "ночь"


# === NoemaForge Autodoc Function Header ===
# Function: _tags_from_path(path: str, rules: List[Dict[str, Any]])
# Purpose: Implement the routine ' tags from path'.
# Inputs:
#   - path: str
#   - rules: List[Dict[str, Any]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, set, strip, get, add, append, str
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - kw, low, out, r, seen, t, tag, tags
# === End NoemaForge Autodoc Function Header ===
def _tags_from_path(path: str, rules: List[Dict[str, Any]]) -> List[str]:
    low = path.lower()
    tags: List[str] = []
    for r in rules:
        tag = str(r.get("tag") or "").strip()
        if not tag:
            continue
        for kw in (r.get("keywords") or []):
            if str(kw).lower() in low:
                tags.append(tag)
                break
    # dedup
    seen = set()
    out = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: build_facts(in_dir: str, day: dt.date, cfg: Dict[str, Any])
# Purpose: Implement the routine 'build facts'.
# Inputs:
#   - in_dir: str
#   - day: dt.date
#   - cfg: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _list_photo_files, sort, int, timedelta, flush, isinstance, _extract_exif, get, stat, _tags_from_path, append, fromisoformat
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - cur, end, episodes, ex, facts, files, gap, gap_min, gps, it, items, label
# === End NoemaForge Autodoc Function Header ===
def build_facts(
    *,
    in_dir: str,
    day: dt.date,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    files = _list_photo_files(in_dir)

    items: List[Dict[str, Any]] = []
    tag_rules = (cfg.get("tag_rules") or []) if isinstance(cfg.get("tag_rules"), list) else []

    for p in files:
        ex = _extract_exif(p)
        ts = ex.get("datetime")
        ts_src = ex.get("datetime_src") or "exif"
        if not isinstance(ts, dt.datetime):
            st = os.stat(p)
            ts = dt.datetime.fromtimestamp(st.st_mtime)
            ts_src = "mtime"

        if ts.date() != day:
            continue

        st = os.stat(p)
        gps = ex.get("gps") or {}
        tags = _tags_from_path(p, tag_rules)

        items.append(
            {
                "path": p,
                "ts": ts.isoformat(),
                "ts_src": ts_src,
                "size": int(st.st_size),
                "mtime": int(st.st_mtime),
                "gps": gps if gps else None,
                "tags": tags,
            }
        )

    items.sort(key=lambda x: x["ts"])

    gap_min = int(cfg.get("event_gap_minutes") or 45)
    gap = dt.timedelta(minutes=max(5, gap_min))

    episodes: List[Dict[str, Any]] = []
    cur: List[Dict[str, Any]] = []
    last_ts: Optional[dt.datetime] = None

    # === NoemaForge Autodoc Function Header ===
    # Function: flush()
    # Purpose: Implement the routine 'flush'.
    # Inputs:
    #   - No explicit parameters.
    # Called by:
    #   - src/seclog.py
    # Calls:
    #   - fromisoformat, set, _time_of_day_label, append, time, get, join, isoformat, len, add
    # Returns / emits: None
    # Side effects:
    #   - appends to logs or files
    # Key locals:
    #   - cur, end, it, label, seen, start, t, tagset
    # === End NoemaForge Autodoc Function Header ===
    def flush() -> None:
        nonlocal cur
        if not cur:
            return
        start = dt.datetime.fromisoformat(cur[0]["ts"])
        end = dt.datetime.fromisoformat(cur[-1]["ts"])
        # aggregate tags
        tagset: List[str] = []
        seen = set()
        for it in cur:
            for t in (it.get("tags") or []):
                if t not in seen:
                    seen.add(t)
                    tagset.append(t)

        label = _time_of_day_label(start.time())
        if tagset:
            label = label + ": " + ", ".join(tagset[:4])

        episodes.append(
            {
                "episode_id": f"E{len(episodes)+1}",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "time_of_day": _time_of_day_label(start.time()),
                "photo_count": len(cur),
                "tags": tagset,
                "label": label,
                "items": cur,
            }
        )
        cur = []

    for it in items:
        ts = dt.datetime.fromisoformat(it["ts"])
        if last_ts is None:
            cur = [it]
            last_ts = ts
            continue
        if (ts - last_ts) > gap:
            flush()
            cur = [it]
            last_ts = ts
            continue
        cur.append(it)
        last_ts = ts

    flush()

    facts = {
        "kind": "photos.diary.facts",
        "day": day.strftime("%Y-%m-%d"),
        "generated_at": _nowz(),
        "in_dir": in_dir,
        "photo_count": len(items),
        "episode_count": len(episodes),
        "episodes": episodes,
    }
    return facts


# === NoemaForge Autodoc Function Header ===
# Function: render_diary_md(facts: Dict[str, Any])
# Purpose: Implement the routine 'render diary md'.
# Inputs:
#   - facts: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, append, join, get, int, fromisoformat, strftime
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - day, e, edt, end, episodes, label, lines, n, sdt, span, start, tag_line
# === End NoemaForge Autodoc Function Header ===
def render_diary_md(facts: Dict[str, Any]) -> str:
    day = str(facts.get("day") or "")
    episodes = facts.get("episodes") or []

    lines: List[str] = []
    lines.append(f"# Дневник: {day}\n")
    lines.append(f"\nФото: {facts.get('photo_count', 0)} | Эпизоды: {facts.get('episode_count', 0)}\n")

    if not episodes:
        lines.append("\nСегодня фотографий не найдено (или не удалось извлечь даты).\n")
        lines.append("\nПроверка: убедись, что фото лежат в /workspace/inbox/photos и имеют EXIF дату или корректные mtime.\n")
        return "".join(lines)

    lines.append("\n## Эпизоды\n")
    for e in episodes:
        start = str(e.get("start") or "")
        end = str(e.get("end") or "")
        try:
            sdt = dt.datetime.fromisoformat(start)
            edt = dt.datetime.fromisoformat(end)
            span = f"{sdt.strftime('%H:%M')}–{edt.strftime('%H:%M')}"
        except Exception:
            span = f"{start}–{end}"

        label = str(e.get("label") or "")
        n = int(e.get("photo_count") or 0)
        tags = e.get("tags") or []
        tag_line = ""
        if tags:
            tag_line = " | теги: " + ", ".join([str(t) for t in tags[:8]])

        lines.append(f"- **{span}** — {label} — {n} фото{tag_line}\n")

    lines.append("\n## Заметки для улучшения\n")
    lines.append("- Этот MVP не анализирует содержимое фото. Для 'гуляли с собакой на рассвете' нужен отдельный vision-этап (опционально GPU) и/или ручные подсказки.\n")
    lines.append("- Если хочешь, можно добавить sidecar-метки (например, папки 'dog', 'hike'), и они попадут в теги.\n")

    return "".join(lines)


# === NoemaForge Autodoc Function Header ===
# Function: write_manifest(out_dir: str, inputs: List[str], outputs: List[str], facts: Dict[str, Any])
# Purpose: Implement the routine 'write manifest'.
# Inputs:
#   - out_dir: str
#   - inputs: List[str]
#   - outputs: List[str]
#   - facts: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _sha256_text, join, _nowz, str, open, dump, stat, append, get, int
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - appends to logs or files
# Key locals:
#   - f, fp, man, p, st, stats
# === End NoemaForge Autodoc Function Header ===
def write_manifest(out_dir: str, *, inputs: List[str], outputs: List[str], facts: Dict[str, Any]) -> Dict[str, Any]:
    # fast fingerprint: path|size|mtime
    stats: List[Dict[str, Any]] = []
    for p in inputs:
        try:
            st = os.stat(p)
            stats.append({"path": p, "size": int(st.st_size), "mtime": int(st.st_mtime)})
        except Exception:
            continue

    fp = _sha256_text("\n".join([f"{x['path']}|{x['size']}|{x['mtime']}" for x in stats]))

    man = {
        "kind": "photos.diary.manifest",
        "generated_at": _nowz(),
        "day": str(facts.get("day") or ""),
        "inputs_fingerprint": fp,
        "inputs": stats,
        "outputs": [{"path": p} for p in outputs],
    }

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)

    return man


# === NoemaForge Autodoc Function Header ===
# Function: run(in_dir: str, out_dir: str, day: str, cfg_path: str = '/opt/noemaforge/configs/photos-diary.yaml')
# Purpose: Implement the routine 'run'.
# Inputs:
#   - in_dir: str
#   - out_dir: str
#   - day: str
#   - cfg_path: str = '/opt/noemaforge/configs/photos-diary.yaml'
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/hwscan.py
#   - src/knowledge_maintainer.py
#   - src/lan_discovery.py
#   - src/localgateway.py
#   - src/localgw_connectors/ipp.py
# Calls:
#   - _load_yaml, _parse_date, _ensure_dir, build_facts, join, render_diary_md, write_manifest, open, dump, write, str, get
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - cfg, day_dt, diary_md, diary_path, f, facts, facts_path, inputs, man, outputs, summary
# === End NoemaForge Autodoc Function Header ===
def run(
    *,
    in_dir: str,
    out_dir: str,
    day: str,
    cfg_path: str = "/opt/noemaforge/configs/photos-diary.yaml",
) -> Dict[str, Any]:
    cfg = _load_yaml(cfg_path)

    day_dt = _parse_date(day)
    _ensure_dir(out_dir)

    facts = build_facts(in_dir=in_dir, day=day_dt, cfg=cfg)

    facts_path = os.path.join(out_dir, "facts.json")
    with open(facts_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)

    diary_md = render_diary_md(facts)
    diary_path = os.path.join(out_dir, "diary.md")
    with open(diary_path, "w", encoding="utf-8") as f:
        f.write(diary_md)

    inputs = [it["path"] for ep in (facts.get("episodes") or []) for it in (ep.get("items") or [])]
    outputs = [facts_path, diary_path, os.path.join(out_dir, "manifest.json")]

    man = write_manifest(out_dir, inputs=inputs, outputs=outputs, facts=facts)

    # short summary for casebase
    summary = f"Фото-дневник за {day}: {facts.get('episode_count',0)} эпизодов, {facts.get('photo_count',0)} фото."

    return {
        "ok": True,
        "day": day,
        "in_dir": in_dir,
        "out_dir": out_dir,
        "facts_path": facts_path,
        "diary_path": diary_path,
        "manifest_path": os.path.join(out_dir, "manifest.json"),
        "inputs_fingerprint": str(man.get("inputs_fingerprint") or ""),
        "summary": summary,
    }


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: List[str])
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: List[str]
# Called by:
#   - bootstrap/microvm/noemaforge-microvm-run.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/brainui.py
#   - src/canary_runner.py
#   - src/doctor.py
#   - src/dream_cycle.py
# Calls:
#   - ArgumentParser, add_argument, parse_args, run, print, dumps, get
# Returns / emits: int
# Side effects:
#   - serializes structured data
#   - spawns subprocesses or workers
# Key locals:
#   - ap, args, res
# === End NoemaForge Autodoc Function Header ===
def main(argv: List[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--day", required=True)
    ap.add_argument("--cfg", default="/opt/noemaforge/configs/photos-diary.yaml")
    args = ap.parse_args(argv)

    res = run(in_dir=args.in_dir, out_dir=args.out_dir, day=args.day, cfg_path=args.cfg)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(os.sys.argv[1:]))
