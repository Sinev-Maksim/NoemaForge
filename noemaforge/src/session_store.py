#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/session_store.py
Zone: runtime/orchestration
Version: 0.32.2
Created: 2026-05-25
Modified: 2026-05-25
Purpose: Persist Admin GUI session state so browser refresh does not lose messages, mode selection or active jobs.
Inputs: Session updates from Admin GUI/API and runtime orchestration state.
Outputs: JSON session records under /var/lib/noemaforge/gui/sessions by default.
Side effects: Writes session JSON files and an append-only session event log.
Tests: python3 -m py_compile noemaforge/src/session_store.py; GUI refresh replay.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from noemaforge_version import RUNTIME_VERSION
from orchestration_state import nowz, normalize_session_record

DEFAULT_SESSION_STATE = Path(os.environ.get("NOEMAFORGE_SESSION_STATE", "/var/lib/noemaforge/gui/sessions"))


class SessionStore:
    """Small file-backed session store for the local Admin GUI.

    Thread-safety: all write paths are serialised under self._lock (RLock so
    that methods which call each other — e.g. update() → load() → save() —
    can re-enter without deadlock).  The events() read path does not hold the
    lock (consistent with EventLog.read() semantics).
    """

    def __init__(self, root: Path | str = DEFAULT_SESSION_STATE):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.events_path = self.root / "session-events.jsonl"
        # Reentrant lock: same thread may acquire multiple times (update→load→save).
        self._lock = threading.RLock()

    def _session_path(self, session_id: str) -> Path:
        clean = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in str(session_id or "default"))[:96] or "default"
        return self.root / f"{clean}.json"

    def _write_atomic(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)

    def _append_event(self, event_type: str, session: Dict[str, Any], data: Optional[Dict[str, Any]] = None) -> None:
        """Append a structured event row to session-events.jsonl.  Caller must hold self._lock."""
        row = {
            "ts": nowz(),
            "type": event_type,
            "session_id": session.get("session_id", "default"),
            "version": RUNTIME_VERSION,
            "data": data or {},
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def load(self, session_id: str = "default") -> Dict[str, Any]:
        """Load or create a session record."""
        with self._lock:
            path = self._session_path(session_id)
            if path.exists():
                try:
                    return normalize_session_record(json.loads(path.read_text(encoding="utf-8")))
                except Exception:
                    pass
            session = normalize_session_record({"session_id": session_id})
            self._write_atomic(path, session)
            self._append_event("session.created", session)
            return session

    def save(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and persist a session record."""
        with self._lock:
            normalized = normalize_session_record(session)
            self._write_atomic(self._session_path(normalized["session_id"]), normalized)
            self._append_event("session.saved", normalized)
            return normalized

    def update(self, session_id: str = "default", **changes: Any) -> Dict[str, Any]:
        """Patch a session record and persist it atomically under self._lock."""
        with self._lock:
            session = self.load(session_id)   # re-entrant: same thread, RLock allows
            session.update(changes)
            saved = self.save(session)         # re-entrant
            self._append_event("session.updated", saved, changes)
            return saved

    def append_message(self, session_id: str, message: Dict[str, Any], max_messages: int = 500) -> Dict[str, Any]:
        """Append a GUI message while keeping bounded history."""
        with self._lock:
            session = self.load(session_id)   # re-entrant
            messages = list(session.get("messages") or [])
            row = dict(message)
            row.setdefault("ts", nowz())
            row.setdefault("version", RUNTIME_VERSION)
            messages.append(row)
            session["messages"] = messages[-max_messages:]
            saved = self.save(session)         # re-entrant
            self._append_event("session.message", saved, {"message": row})
            return saved

    def set_mode(self, session_id: str, mode: str, composite_top_n: int = 0) -> Dict[str, Any]:
        """Persist a selected model-selection mode for subsequent GUI actions."""
        allowed = {"fast", "normal", "full", "full_composite"}
        clean_mode = mode if mode in allowed else "normal"
        return self.update(session_id, selected_mode=clean_mode, selected_composite_top_n=int(composite_top_n or 0))

    def attach_active_jobs(self, session_id: str, jobs: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        """Persist a list of active jobs visible to the GUI after refresh."""
        active = [dict(job) for job in jobs if isinstance(job, dict)]
        return self.update(session_id, active_jobs=active)

    def events(self, after_index: int = 0, limit: int = 200) -> list[Dict[str, Any]]:
        """Return append-only session events for polling or SSE."""
        if not self.events_path.exists():
            return []
        rows: list[Dict[str, Any]] = []
        for idx, line in enumerate(self.events_path.read_text(encoding="utf-8", errors="replace").splitlines()):
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


__all__ = ["SessionStore", "DEFAULT_SESSION_STATE"]
