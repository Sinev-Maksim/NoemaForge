#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/event_log.py
Zone: runtime/orchestration
Version: 0.32.2
Created: 2026-05-25
Modified: 2026-05-25
Purpose: Provide a minimal append-only event log for GUI progress, Admin routing and release evidence.
Inputs: Event dictionaries from runtime modules and Admin GUI handlers.
Outputs: JSONL event records under /var/lib/noemaforge/events by default.
Side effects: Appends JSONL rows only.
Tests: python3 -m py_compile noemaforge/src/event_log.py; event append/read smoke.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from noemaforge_version import RUNTIME_VERSION
from orchestration_state import nowz

DEFAULT_EVENT_STATE = Path(os.environ.get("NOEMAFORGE_EVENT_STATE", "/var/lib/noemaforge/events"))


class EventLog:
    """Append-only JSONL event log with bounded readback."""

    def __init__(self, root: Path | str = DEFAULT_EVENT_STATE):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "events.jsonl"

    def append(self, event_type: str, data: Dict[str, Any] | None = None, *, actor: str = "system", trace_id: str = "") -> Dict[str, Any]:
        row = {
            "ts": nowz(),
            "type": str(event_type or "event"),
            "actor": str(actor or "system"),
            "trace_id": str(trace_id or ""),
            "version": RUNTIME_VERSION,
            "data": data or {},
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row

    def read(self, after_index: int = 0, limit: int = 200) -> list[Dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[Dict[str, Any]] = []
        for idx, line in enumerate(self.path.read_text(encoding="utf-8", errors="replace").splitlines()):
            if idx < after_index or not line.strip():
                continue
            try:
                row = json.loads(line)
                row["index"] = idx
                rows.append(row)
            except Exception:
                continue
            if len(rows) >= limit:
                break
        return rows


__all__ = ["EventLog", "DEFAULT_EVENT_STATE"]
