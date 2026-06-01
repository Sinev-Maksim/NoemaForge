#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/platform_paths.py
Zone: runtime/platform
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Single source of truth for platform-aware default paths.
         Eliminates hardcoded /opt/noemaforge and /var/lib/noemaforge
         strings spread across 123 source files.
Inputs: Environment variables (NOEMAFORGE_ROOT, NOEMAFORGE_DATA_ROOT),
        sys.platform, os.name.
Outputs: Path objects for install root, data root, config dir, log dir,
         state dirs, runtime socket, etc.
Side effects: None (pure query).
Tests: python3 -m unittest noemaforge/tests/test_platform_paths.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===

Cross-platform path resolution for NoemaForge.

Priority order for every path:
  1. Explicit environment variable (NOEMAFORGE_ROOT, etc.)
  2. Platform-appropriate default
  3. XDG / appdirs convention where applicable

Supported platforms:
  linux   → /opt/noemaforge install, /var/lib/noemaforge data
  windows → C:/ProgramData/noemaforge  (both install and data)
  darwin  → /Library/Application Support/noemaforge  (or ~/Library for user installs)
  other   → /opt/noemaforge fallback (embedded, BSD, etc.)

Usage
-----
from platform_paths import NoemaForgePaths

paths = NoemaForgePaths()          # reads env vars, auto-detects platform
paths.root                         # install root
paths.data_root                    # mutable data (sessions, jobs, logs…)
paths.session_state_dir            # sessions JSONL
paths.jobs_dir                     # jobs.json store
paths.event_log_dir                # event log JSONL
paths.gui_state_dir                # Admin GUI runtime state
paths.model_selection_state_dir    # model-selection state
paths.dev_team_state_dir           # dev-team / code-evolution state
paths.model_evolution_state_dir    # model-evolution state
paths.pipelines_dir                # pipeline state
paths.gui_listen_address           # (host, port) tuple for Admin GUI

Platform detection
------------------
Call NoemaForgePaths.detect_platform() for a dict with all relevant info.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Supported platform tokens
# ---------------------------------------------------------------------------
PLATFORM_LINUX = "linux"
PLATFORM_WINDOWS = "windows"
PLATFORM_MACOS = "macos"
PLATFORM_OTHER = "other"


def current_platform() -> str:
    """Return one of the PLATFORM_* constants for the running OS."""
    p = sys.platform
    if p.startswith("linux"):
        return PLATFORM_LINUX
    if p == "win32" or p == "cygwin":
        return PLATFORM_WINDOWS
    if p == "darwin":
        return PLATFORM_MACOS
    return PLATFORM_OTHER


# ---------------------------------------------------------------------------
# Platform-default root directories
# ---------------------------------------------------------------------------

def _default_install_root(platform: str) -> Path:
    """Canonical install directory for the NoemaForge package."""
    if platform == PLATFORM_WINDOWS:
        base = os.environ.get("ProgramData", r"C:\ProgramData")
        return Path(base) / "noemaforge"
    if platform == PLATFORM_MACOS:
        return Path("/Library/Application Support/noemaforge")
    # linux + other
    return Path("/opt/noemaforge")


def _default_data_root(platform: str) -> Path:
    """Canonical mutable data directory (sessions, jobs, logs, state)."""
    if platform == PLATFORM_WINDOWS:
        base = os.environ.get("ProgramData", r"C:\ProgramData")
        return Path(base) / "noemaforge" / "data"
    if platform == PLATFORM_MACOS:
        return Path("/Library/Application Support/noemaforge/data")
    # linux + other
    return Path("/var/lib/noemaforge")


def _default_config_dir(platform: str, install_root: Path) -> Path:
    if platform == PLATFORM_WINDOWS:
        return install_root / "config"
    if platform == PLATFORM_MACOS:
        return install_root / "config"
    return Path("/etc/noemaforge")


def _default_log_dir(platform: str, data_root: Path) -> Path:
    if platform == PLATFORM_WINDOWS:
        return data_root / "logs"
    if platform == PLATFORM_MACOS:
        return data_root / "logs"
    return Path("/var/log/noemaforge")


# ---------------------------------------------------------------------------
# NoemaForgePaths — the main interface
# ---------------------------------------------------------------------------

class NoemaForgePaths:
    """Platform-aware path resolver for NoemaForge.

    All paths can be overridden via environment variables (listed in the
    __init__ docstring). Environment variables take precedence over platform
    defaults so that dev setups, containers, and test harnesses can redirect
    everything to a scratch directory.
    """

    def __init__(
        self,
        *,
        platform: Optional[str] = None,
        root: Optional[Path] = None,
        data_root: Optional[Path] = None,
    ) -> None:
        """Construct paths.

        Parameters
        ----------
        platform:
            Override platform detection (one of PLATFORM_* constants).
            Useful in tests.
        root:
            Override install root directly (skips env var lookup).
        data_root:
            Override data root directly (skips env var lookup).

        Environment variables (all optional):
            NOEMAFORGE_ROOT              install root
            NOEMAFORGE_DATA_ROOT         mutable data root
            NOEMAFORGE_CONFIG_DIR        config directory
            NOEMAFORGE_LOG_DIR           log directory
            NOEMAFORGE_GUI_HOST          admin GUI listen host (default 127.0.0.1)
            NOEMAFORGE_GUI_PORT          admin GUI listen port (default 8765)
        """
        self._platform = platform or current_platform()

        # ---- install root --------------------------------------------------
        if root is not None:
            self._root = Path(root)
        elif "NOEMAFORGE_ROOT" in os.environ:
            self._root = Path(os.environ["NOEMAFORGE_ROOT"])
        else:
            self._root = _default_install_root(self._platform)

        # ---- data root -----------------------------------------------------
        if data_root is not None:
            self._data_root = Path(data_root)
        elif "NOEMAFORGE_DATA_ROOT" in os.environ:
            self._data_root = Path(os.environ["NOEMAFORGE_DATA_ROOT"])
        else:
            # Many env vars in the legacy code point at sub-paths of data_root.
            # Honour them to stay backward-compatible while the codebase migrates.
            self._data_root = _default_data_root(self._platform)

    # ---- properties --------------------------------------------------------

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def root(self) -> Path:
        """NoemaForge install root (package source, configs, scripts)."""
        return self._root

    @property
    def data_root(self) -> Path:
        """Mutable runtime data root."""
        return self._data_root

    @property
    def config_dir(self) -> Path:
        override = os.environ.get("NOEMAFORGE_CONFIG_DIR")
        if override:
            return Path(override)
        return _default_config_dir(self._platform, self._root)

    @property
    def log_dir(self) -> Path:
        override = os.environ.get("NOEMAFORGE_LOG_DIR")
        if override:
            return Path(override)
        return _default_log_dir(self._platform, self._data_root)

    # ---- GUI state ---------------------------------------------------------

    @property
    def gui_state_dir(self) -> Path:
        """Admin GUI runtime state: conversations, sessions, jobs, events."""
        override = os.environ.get("NOEMAFORGE_GUI_STATE_DIR")
        if override:
            return Path(override)
        return self._data_root / "gui"

    @property
    def session_state_dir(self) -> Path:
        override = os.environ.get("NOEMAFORGE_SESSION_STATE")
        if override:
            return Path(override)
        return self.gui_state_dir / "sessions"

    @property
    def event_log_dir(self) -> Path:
        override = os.environ.get("NOEMAFORGE_EVENT_LOG_DIR")
        if override:
            return Path(override)
        return self.gui_state_dir / "events"

    @property
    def jobs_dir(self) -> Path:
        override = os.environ.get("NOEMAFORGE_JOBS_DIR")
        if override:
            return Path(override)
        return self.gui_state_dir / "jobs"

    # ---- pipeline / evolution state ----------------------------------------

    @property
    def pipelines_dir(self) -> Path:
        override = os.environ.get("NOEMAFORGE_PIPELINE_STATE")
        if override:
            return Path(override)
        return self._data_root / "pipelines"

    @property
    def model_selection_state_dir(self) -> Path:
        override = os.environ.get("NOEMAFORGE_MODEL_SELECTION_STATE")
        if override:
            return Path(override)
        return self._data_root / "model-selection"

    @property
    def model_evolution_state_dir(self) -> Path:
        override = os.environ.get("NOEMAFORGE_MODEL_EVOLUTION_STATE")
        if override:
            return Path(override)
        return self._data_root / "model-evolution"

    @property
    def dev_team_state_dir(self) -> Path:
        override = os.environ.get("NOEMAFORGE_DEV_TEAM_STATE")
        if override:
            return Path(override)
        return self._data_root / "dev-team"

    @property
    def code_evolution_state_dir(self) -> Path:
        """State directory for the autonomous code-evolution loop."""
        override = os.environ.get("NOEMAFORGE_CODE_EVOLUTION_STATE")
        if override:
            return Path(override)
        return self._data_root / "code-evolution"

    @property
    def epoch_dir(self) -> Path:
        override = os.environ.get("NOEMAFORGE_EPOCH_STATE")
        if override:
            return Path(override)
        return self._data_root / "epochs"

    @property
    def vault_dir(self) -> Path:
        override = os.environ.get("NOEMAFORGE_VAULT_DIR")
        if override:
            return Path(override)
        return self._data_root / "vault"

    @property
    def persona_state_dir(self) -> Path:
        override = os.environ.get("NOEMAFORGE_PERSONA_STATE")
        if override:
            return Path(override)
        return self._data_root / "personas"

    # ---- network -----------------------------------------------------------

    @property
    def gui_listen_address(self) -> Tuple[str, int]:
        """(host, port) for the Admin GUI HTTP server."""
        host = os.environ.get("NOEMAFORGE_GUI_HOST", "127.0.0.1")
        try:
            port = int(os.environ.get("NOEMAFORGE_GUI_PORT", "8765"))
        except ValueError:
            port = 8765
        return (host, port)

    @property
    def gui_unix_socket(self) -> Optional[Path]:
        """Unix domain socket for Admin GUI (Linux/macOS only).

        Returns None on Windows or when NOEMAFORGE_GUI_SOCKET is unset.
        """
        if self._platform == PLATFORM_WINDOWS:
            return None
        sock = os.environ.get("NOEMAFORGE_GUI_SOCKET")
        if sock:
            return Path(sock)
        return self._data_root / "run" / "admin-gui.sock"

    # ---- helpers -----------------------------------------------------------

    def as_dict(self) -> Dict[str, Any]:
        """Serialisable snapshot of all resolved paths (for diagnostics/logging)."""
        return {
            "platform": self.platform,
            "root": str(self.root),
            "data_root": str(self.data_root),
            "config_dir": str(self.config_dir),
            "log_dir": str(self.log_dir),
            "gui_state_dir": str(self.gui_state_dir),
            "session_state_dir": str(self.session_state_dir),
            "event_log_dir": str(self.event_log_dir),
            "jobs_dir": str(self.jobs_dir),
            "pipelines_dir": str(self.pipelines_dir),
            "model_selection_state_dir": str(self.model_selection_state_dir),
            "model_evolution_state_dir": str(self.model_evolution_state_dir),
            "dev_team_state_dir": str(self.dev_team_state_dir),
            "code_evolution_state_dir": str(self.code_evolution_state_dir),
            "epoch_dir": str(self.epoch_dir),
            "vault_dir": str(self.vault_dir),
            "persona_state_dir": str(self.persona_state_dir),
            "gui_listen_address": list(self.gui_listen_address),
            "gui_unix_socket": str(self.gui_unix_socket) if self.gui_unix_socket else None,
        }

    @staticmethod
    def detect_platform() -> Dict[str, Any]:
        """Return a dict with OS detection details for diagnostics."""
        p = current_platform()
        return {
            "platform": p,
            "sys_platform": sys.platform,
            "os_name": os.name,
            "python_version": sys.version,
            "is_linux": p == PLATFORM_LINUX,
            "is_windows": p == PLATFORM_WINDOWS,
            "is_macos": p == PLATFORM_MACOS,
        }


# ---------------------------------------------------------------------------
# Module-level singleton — import and use directly
# ---------------------------------------------------------------------------

#: Pre-built instance using environment variables and auto-detected platform.
#: Import this in production code:  ``from platform_paths import DEFAULT_PATHS``
DEFAULT_PATHS = NoemaForgePaths()


# ---------------------------------------------------------------------------
# Backward-compatibility shims — drop-in for the most common env-var patterns
# ---------------------------------------------------------------------------

def get_root() -> Path:
    """Equivalent of Path(os.environ.get('NOEMAFORGE_ROOT', '/opt/noemaforge'))."""
    return DEFAULT_PATHS.root


def get_data_root() -> Path:
    """Equivalent of Path(os.environ.get('NOEMAFORGE_DATA_ROOT', '/var/lib/noemaforge'))."""
    return DEFAULT_PATHS.data_root


def get_gui_state_dir() -> Path:
    return DEFAULT_PATHS.gui_state_dir


def get_session_state_dir() -> Path:
    return DEFAULT_PATHS.session_state_dir


def get_jobs_dir() -> Path:
    return DEFAULT_PATHS.jobs_dir


def get_pipelines_dir() -> Path:
    return DEFAULT_PATHS.pipelines_dir


def get_model_evolution_state_dir() -> Path:
    return DEFAULT_PATHS.model_evolution_state_dir


def get_dev_team_state_dir() -> Path:
    return DEFAULT_PATHS.dev_team_state_dir


def get_code_evolution_state_dir() -> Path:
    return DEFAULT_PATHS.code_evolution_state_dir


# ---------------------------------------------------------------------------
# CLI entry point — useful for debugging on any platform
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json as _json

    paths = NoemaForgePaths()
    info = {
        "detection": NoemaForgePaths.detect_platform(),
        "paths": paths.as_dict(),
    }
    print(_json.dumps(info, indent=2))
