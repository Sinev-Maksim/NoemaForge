#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/platform_paths.py
Zone: runtime/platform
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Single source of truth for platform-aware default paths.
         Reads installer-written noemaforge.conf (INI), env vars,
         and platform defaults. Eliminates hardcoded /opt/noemaforge
         strings across 123+ source files.
Inputs: noemaforge.conf (written by installer), environment variables,
        sys.platform.
Outputs: Path objects for install root, data root, config dir, log dir,
         state dirs, runtime socket, GUI address, etc.
Side effects: None (pure query). Config file is read at import time.
Tests: python3 -m unittest noemaforge/tests/test_platform_paths.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===

Cross-platform path resolution for NoemaForge.

Priority order (highest → lowest) for every resolved path
----------------------------------------------------------
  1. Explicit constructor argument  (tests / programmatic override)
  2. Environment variable           (NOEMAFORGE_ROOT, etc.)
  3. noemaforge.conf [paths] key    (written by installer)
  4. Platform-appropriate default   (auto-detected OS)

Config file location (searched in order, first found wins)
----------------------------------------------------------
  NOEMAFORGE_CONFIG_FILE env var  (explicit override)
  <install_root>/noemaforge.conf  (preferred; installer writes here)
  /etc/noemaforge/noemaforge.conf (Linux system-wide fallback)
  C:\\ProgramData\\noemaforge\\noemaforge.conf  (Windows fallback)
  /Library/Application Support/noemaforge/noemaforge.conf  (macOS)
  <script_dir>/../noemaforge.conf (development / portable installs)

noemaforge.conf format (INI, written by installer)
--------------------------------------------------
  [noemaforge]
  install_root = /opt/noemaforge
  data_root    = /var/lib/noemaforge

  [paths]
  gui_state_dir            = /var/lib/noemaforge/gui
  sessions_dir             = /var/lib/noemaforge/gui/sessions
  jobs_dir                 = /var/lib/noemaforge/gui/jobs
  event_log_dir            = /var/lib/noemaforge/gui/events
  pipelines_dir            = /var/lib/noemaforge/pipelines
  model_selection_state_dir= /var/lib/noemaforge/model-selection
  model_evolution_state_dir= /var/lib/noemaforge/model-evolution
  dev_team_state_dir       = /var/lib/noemaforge/dev-team
  code_evolution_state_dir = /var/lib/noemaforge/code-evolution
  log_dir                  = /var/log/noemaforge
  vault_dir                = /var/lib/noemaforge/vault
  epoch_dir                = /var/lib/noemaforge/epochs
  persona_state_dir        = /var/lib/noemaforge/personas

  [gui]
  host = 127.0.0.1
  port = 8765

Supported platforms
-------------------
  linux   → /opt/noemaforge install,  /var/lib/noemaforge data
  windows → C:\\ProgramData\\noemaforge (install + data)
  macos   → /Library/Application Support/noemaforge
  other   → /opt/noemaforge fallback

Usage
-----
  from platform_paths import NoemaForgePaths, DEFAULT_PATHS

  # module-level singleton (reads config + env at import time)
  paths = DEFAULT_PATHS
  paths.root                      # install root
  paths.data_root                 # mutable data
  paths.session_state_dir         # sessions JSONL
  paths.jobs_dir                  # jobs.json store
  paths.gui_listen_address        # (host, port) for Admin GUI

  # inspect resolved config
  print(paths.config_file_used)   # Path or None
  print(paths.as_dict())          # all resolved paths as str dict
"""
from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Platform tokens
# ---------------------------------------------------------------------------
PLATFORM_LINUX   = "linux"
PLATFORM_WINDOWS = "windows"
PLATFORM_MACOS   = "macos"
PLATFORM_OTHER   = "other"

# Config file name
CONF_FILENAME = "noemaforge.conf"


def current_platform() -> str:
    p = sys.platform
    if p.startswith("linux"):   return PLATFORM_LINUX
    if p in ("win32", "cygwin"): return PLATFORM_WINDOWS
    if p == "darwin":           return PLATFORM_MACOS
    return PLATFORM_OTHER


# ---------------------------------------------------------------------------
# Platform-default directories (used only when config + env vars are absent)
# ---------------------------------------------------------------------------

def _default_install_root(platform: str) -> Path:
    if platform == PLATFORM_WINDOWS:
        return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "noemaforge"
    if platform == PLATFORM_MACOS:
        return Path("/Library/Application Support/noemaforge")
    return Path("/opt/noemaforge")


def _default_data_root(platform: str) -> Path:
    if platform == PLATFORM_WINDOWS:
        return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "noemaforge" / "data"
    if platform == PLATFORM_MACOS:
        return Path("/Library/Application Support/noemaforge/data")
    return Path("/var/lib/noemaforge")


def _default_config_dir(platform: str) -> Path:
    if platform == PLATFORM_WINDOWS:
        return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "noemaforge"
    if platform == PLATFORM_MACOS:
        return Path("/Library/Application Support/noemaforge")
    return Path("/etc/noemaforge")


def _default_log_dir(platform: str, data_root: Path) -> Path:
    if platform in (PLATFORM_WINDOWS, PLATFORM_MACOS):
        return data_root / "logs"
    return Path("/var/log/noemaforge")


# ---------------------------------------------------------------------------
# Config file discovery + parsing
# ---------------------------------------------------------------------------

def _candidate_config_paths(platform: str, install_root: Optional[Path] = None) -> list:
    """Return candidate paths for noemaforge.conf, highest priority first."""
    candidates = []
    # 1. Explicit env override
    explicit = os.environ.get("NOEMAFORGE_CONFIG_FILE")
    if explicit:
        candidates.append(Path(explicit))
    # 2. install_root (if already resolved without config)
    if install_root:
        candidates.append(install_root / CONF_FILENAME)
    # 3. Standard system locations per platform
    if platform == PLATFORM_WINDOWS:
        pd = os.environ.get("ProgramData", r"C:\ProgramData")
        candidates.append(Path(pd) / "noemaforge" / CONF_FILENAME)
    elif platform == PLATFORM_MACOS:
        candidates.append(Path("/Library/Application Support/noemaforge") / CONF_FILENAME)
    else:
        candidates.append(Path("/etc/noemaforge") / CONF_FILENAME)
        candidates.append(Path("/opt/noemaforge") / CONF_FILENAME)
    # 4. Relative to this source file (development / portable installs)
    candidates.append(Path(__file__).resolve().parents[2] / CONF_FILENAME)
    return candidates


def _load_config(platform: str, install_root: Optional[Path] = None) -> Tuple[Optional[configparser.ConfigParser], Optional[Path]]:
    """Read the first noemaforge.conf found. Returns (parser_or_None, path_or_None)."""
    for candidate in _candidate_config_paths(platform, install_root):
        if candidate.is_file():
            cfg = configparser.ConfigParser(
                interpolation=None,       # don't interpret % signs
                inline_comment_prefixes=("#", ";"),
            )
            try:
                cfg.read(candidate, encoding="utf-8")
                return cfg, candidate
            except (configparser.Error, OSError):
                continue
    return None, None


def _cfg_get(cfg: Optional[configparser.ConfigParser], section: str, key: str) -> Optional[str]:
    """Safe read from config parser; returns None if section/key missing."""
    if cfg is None:
        return None
    try:
        val = cfg.get(section, key).strip()
        return val if val else None
    except (configparser.NoSectionError, configparser.NoOptionError):
        return None


# ---------------------------------------------------------------------------
# Config file writer (called by installer)
# ---------------------------------------------------------------------------

def write_config(
    dest: Path,
    install_root: Path,
    data_root: Path,
    *,
    gui_host: str = "127.0.0.1",
    gui_port: int = 8765,
    extra_paths: Optional[Dict[str, str]] = None,
) -> Path:
    """Write a noemaforge.conf to *dest*.

    Called by the installer after the operator confirms install/data paths.
    Returns the path written.

    Parameters
    ----------
    dest :
        Target path for noemaforge.conf (usually inside install_root).
    install_root :
        Chosen install directory (operator-confirmed).
    data_root :
        Chosen mutable data directory (operator-confirmed).
    gui_host :
        Admin GUI listen host (default 127.0.0.1).
    gui_port :
        Admin GUI listen port (default 8765).
    extra_paths :
        Optional mapping of additional [paths] keys to override defaults.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Derive sub-paths from data_root
    derived = {
        "gui_state_dir":             str(data_root / "gui"),
        "sessions_dir":              str(data_root / "gui" / "sessions"),
        "jobs_dir":                  str(data_root / "gui" / "jobs"),
        "event_log_dir":             str(data_root / "gui" / "events"),
        "pipelines_dir":             str(data_root / "pipelines"),
        "model_selection_state_dir": str(data_root / "model-selection"),
        "model_evolution_state_dir": str(data_root / "model-evolution"),
        "dev_team_state_dir":        str(data_root / "dev-team"),
        "code_evolution_state_dir":  str(data_root / "code-evolution"),
        "vault_dir":                 str(data_root / "vault"),
        "epoch_dir":                 str(data_root / "epochs"),
        "persona_state_dir":         str(data_root / "personas"),
    }
    # Linux log dir lives outside data_root
    plat = current_platform()
    derived["log_dir"] = str(_default_log_dir(plat, data_root))

    if extra_paths:
        derived.update(extra_paths)

    cfg = configparser.ConfigParser(interpolation=None)
    cfg["noemaforge"] = {
        "install_root": str(install_root),
        "data_root":    str(data_root),
        "version":      "0.32.2",
    }
    cfg["paths"] = derived
    cfg["gui"] = {
        "host": gui_host,
        "port": str(gui_port),
    }

    with dest.open("w", encoding="utf-8") as fh:
        fh.write(
            "# NoemaForge installation configuration\n"
            "# Generated by platform_paths.write_config().\n"
            "# Edit paths here to relocate the runtime without rebuilding.\n"
            "# After editing, restart the Admin GUI service.\n\n"
        )
        cfg.write(fh)

    return dest


# ---------------------------------------------------------------------------
# NoemaForgePaths — main interface
# ---------------------------------------------------------------------------

class NoemaForgePaths:
    """Platform-aware, config-file-aware path resolver for NoemaForge.

    Resolution priority (highest → lowest) for every path:
      1. Constructor argument
      2. Environment variable  (NOEMAFORGE_ROOT, NOEMAFORGE_DATA_ROOT, …)
      3. noemaforge.conf       (written by installer, read at construction)
      4. Platform default      (auto-detected OS convention)
    """

    def __init__(
        self,
        *,
        platform: Optional[str] = None,
        root: Optional[Path] = None,
        data_root: Optional[Path] = None,
        config_file: Optional[Path] = None,
    ) -> None:
        """
        Parameters
        ----------
        platform :
            Override platform detection (PLATFORM_* constant). Useful in tests.
        root :
            Override install root directly.
        data_root :
            Override data root directly.
        config_file :
            Override config file path directly (also disables env-var discovery).
        """
        self._platform = platform or current_platform()

        # ---- Load config file ---------------------------------------------
        if config_file is not None:
            cfg = configparser.ConfigParser(interpolation=None,
                                            inline_comment_prefixes=("#", ";"))
            try:
                cfg.read(Path(config_file), encoding="utf-8")
                self._cfg: Optional[configparser.ConfigParser] = cfg
                self._cfg_path: Optional[Path] = Path(config_file)
            except (configparser.Error, OSError):
                self._cfg = None
                self._cfg_path = None
        else:
            # Two-phase: discover install root first (needed for config search),
            # then load config, then finalize install root from config.
            _early_root = (
                Path(root) if root is not None
                else (Path(os.environ["NOEMAFORGE_ROOT"]) if "NOEMAFORGE_ROOT" in os.environ else None)
            )
            self._cfg, self._cfg_path = _load_config(self._platform, _early_root)

        # ---- Resolve install root -----------------------------------------
        if root is not None:
            self._root = Path(root)
        elif "NOEMAFORGE_ROOT" in os.environ:
            self._root = Path(os.environ["NOEMAFORGE_ROOT"])
        else:
            cfg_val = _cfg_get(self._cfg, "noemaforge", "install_root")
            self._root = Path(cfg_val) if cfg_val else _default_install_root(self._platform)

        # ---- Resolve data root --------------------------------------------
        if data_root is not None:
            self._data_root = Path(data_root)
        elif "NOEMAFORGE_DATA_ROOT" in os.environ:
            self._data_root = Path(os.environ["NOEMAFORGE_DATA_ROOT"])
        else:
            cfg_val = _cfg_get(self._cfg, "noemaforge", "data_root")
            self._data_root = Path(cfg_val) if cfg_val else _default_data_root(self._platform)

    # ---- properties -------------------------------------------------------

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def config_file_used(self) -> Optional[Path]:
        """Path to the noemaforge.conf that was loaded, or None."""
        return self._cfg_path

    @property
    def root(self) -> Path:
        return self._root

    @property
    def data_root(self) -> Path:
        return self._data_root

    def _resolve(self, env_key: str, cfg_section: str, cfg_key: str, default: Path) -> Path:
        """Three-level resolution: env var → config file → default."""
        if env_key and env_key in os.environ:
            return Path(os.environ[env_key])
        cfg_val = _cfg_get(self._cfg, cfg_section, cfg_key)
        return Path(cfg_val) if cfg_val else default

    @property
    def config_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_CONFIG_DIR", "paths", "config_dir",
                             _default_config_dir(self._platform))

    @property
    def log_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_LOG_DIR", "paths", "log_dir",
                             _default_log_dir(self._platform, self._data_root))

    @property
    def gui_state_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_GUI_STATE_DIR", "paths", "gui_state_dir",
                             self._data_root / "gui")

    @property
    def session_state_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_SESSION_STATE", "paths", "sessions_dir",
                             self.gui_state_dir / "sessions")

    @property
    def event_log_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_EVENT_LOG_DIR", "paths", "event_log_dir",
                             self.gui_state_dir / "events")

    @property
    def jobs_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_JOBS_DIR", "paths", "jobs_dir",
                             self.gui_state_dir / "jobs")

    @property
    def pipelines_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_PIPELINE_STATE", "paths", "pipelines_dir",
                             self._data_root / "pipelines")

    @property
    def model_selection_state_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_MODEL_SELECTION_STATE", "paths",
                             "model_selection_state_dir",
                             self._data_root / "model-selection")

    @property
    def model_evolution_state_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_MODEL_EVOLUTION_STATE", "paths",
                             "model_evolution_state_dir",
                             self._data_root / "model-evolution")

    @property
    def dev_team_state_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_DEV_TEAM_STATE", "paths", "dev_team_state_dir",
                             self._data_root / "dev-team")

    @property
    def code_evolution_state_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_CODE_EVOLUTION_STATE", "paths",
                             "code_evolution_state_dir",
                             self._data_root / "code-evolution")

    @property
    def epoch_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_EPOCH_STATE", "paths", "epoch_dir",
                             self._data_root / "epochs")

    @property
    def vault_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_VAULT_DIR", "paths", "vault_dir",
                             self._data_root / "vault")

    @property
    def persona_state_dir(self) -> Path:
        return self._resolve("NOEMAFORGE_PERSONA_STATE", "paths", "persona_state_dir",
                             self._data_root / "personas")

    @property
    def gui_listen_address(self) -> Tuple[str, int]:
        host = os.environ.get("NOEMAFORGE_GUI_HOST") or _cfg_get(self._cfg, "gui", "host") or "127.0.0.1"
        port_str = os.environ.get("NOEMAFORGE_GUI_PORT") or _cfg_get(self._cfg, "gui", "port") or "8765"
        try:
            port = int(port_str)
        except (ValueError, TypeError):
            port = 8765
        return (host, port)

    @property
    def gui_unix_socket(self) -> Optional[Path]:
        if self._platform == PLATFORM_WINDOWS:
            return None
        sock = os.environ.get("NOEMAFORGE_GUI_SOCKET")
        if sock:
            return Path(sock)
        return self._data_root / "run" / "admin-gui.sock"

    # ---- helpers ----------------------------------------------------------

    def as_dict(self) -> Dict[str, Any]:
        return {
            "platform":                   self.platform,
            "config_file_used":           str(self.config_file_used) if self.config_file_used else None,
            "root":                       str(self.root),
            "data_root":                  str(self.data_root),
            "config_dir":                 str(self.config_dir),
            "log_dir":                    str(self.log_dir),
            "gui_state_dir":              str(self.gui_state_dir),
            "session_state_dir":          str(self.session_state_dir),
            "event_log_dir":              str(self.event_log_dir),
            "jobs_dir":                   str(self.jobs_dir),
            "pipelines_dir":              str(self.pipelines_dir),
            "model_selection_state_dir":  str(self.model_selection_state_dir),
            "model_evolution_state_dir":  str(self.model_evolution_state_dir),
            "dev_team_state_dir":         str(self.dev_team_state_dir),
            "code_evolution_state_dir":   str(self.code_evolution_state_dir),
            "epoch_dir":                  str(self.epoch_dir),
            "vault_dir":                  str(self.vault_dir),
            "persona_state_dir":          str(self.persona_state_dir),
            "gui_listen_address":         list(self.gui_listen_address),
            "gui_unix_socket":            str(self.gui_unix_socket) if self.gui_unix_socket else None,
        }

    @staticmethod
    def detect_platform() -> Dict[str, Any]:
        p = current_platform()
        return {
            "platform":        p,
            "sys_platform":    sys.platform,
            "os_name":         os.name,
            "python_version":  sys.version,
            "is_linux":        p == PLATFORM_LINUX,
            "is_windows":      p == PLATFORM_WINDOWS,
            "is_macos":        p == PLATFORM_MACOS,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

DEFAULT_PATHS = NoemaForgePaths()


# ---------------------------------------------------------------------------
# Backward-compatibility shims
# ---------------------------------------------------------------------------

def get_root()                    -> Path: return DEFAULT_PATHS.root
def get_data_root()               -> Path: return DEFAULT_PATHS.data_root
def get_gui_state_dir()           -> Path: return DEFAULT_PATHS.gui_state_dir
def get_session_state_dir()       -> Path: return DEFAULT_PATHS.session_state_dir
def get_jobs_dir()                -> Path: return DEFAULT_PATHS.jobs_dir
def get_pipelines_dir()           -> Path: return DEFAULT_PATHS.pipelines_dir
def get_model_evolution_state_dir() -> Path: return DEFAULT_PATHS.model_evolution_state_dir
def get_dev_team_state_dir()      -> Path: return DEFAULT_PATHS.dev_team_state_dir
def get_code_evolution_state_dir() -> Path: return DEFAULT_PATHS.code_evolution_state_dir


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json as _json
    paths = NoemaForgePaths()
    info = {"detection": NoemaForgePaths.detect_platform(), "paths": paths.as_dict()}
    print(_json.dumps(info, indent=2))
