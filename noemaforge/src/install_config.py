#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/install_config.py
Zone: runtime/platform
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Cross-platform installer configuration writer.
         Generates noemaforge.conf with operator-chosen install/data paths.
         Called by the installer scripts (setup.sh, setup.ps1, brainctl install).
Inputs: CLI arguments (--install-root, --data-root, --gui-host, --gui-port,
        --dry-run), or imported as a library.
Outputs: noemaforge.conf written to <install-root>/noemaforge.conf.
Side effects: Creates directories, writes config file.
Tests: python3 -m unittest noemaforge/tests/test_install_config.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===

Cross-platform installation configuration writer
================================================

This module is the single place where the installer persists chosen paths.
It is intentionally small and dependency-free (stdlib only, no YAML required).

Usage from the installer (any platform)
----------------------------------------
  # Python
  from install_config import run_install_config
  run_install_config(install_root="/opt/noemaforge", data_root="/var/lib/noemaforge")

  # CLI (called by setup.sh / setup.ps1)
  python install_config.py \\
      --install-root /opt/noemaforge \\
      --data-root    /var/lib/noemaforge

  # Windows (from setup.ps1)
  py -3 install_config.py `
      --install-root "C:\\ProgramData\\noemaforge" `
      --data-root    "C:\\ProgramData\\noemaforge\\data"

  # Dry run (show what would be written, do not write)
  python install_config.py --install-root /opt/noemaforge --dry-run

After running, noemaforge.conf is placed at:
  <install-root>/noemaforge.conf

All NoemaForge services read this file at startup via platform_paths.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Import write_config and helpers from platform_paths
# (stdlib-only; safe to import at install time before full env is set up)
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from platform_paths import (
    write_config,
    current_platform,
    _default_install_root,
    _default_data_root,
    CONF_FILENAME,
    PLATFORM_WINDOWS,
    PLATFORM_LINUX,
    PLATFORM_MACOS,
)


# ---------------------------------------------------------------------------
# Main entry point (library)
# ---------------------------------------------------------------------------

def run_install_config(
    install_root: Optional[str] = None,
    data_root: Optional[str] = None,
    gui_host: str = "127.0.0.1",
    gui_port: int = 8765,
    dry_run: bool = False,
    extra_paths: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Write noemaforge.conf for the given install/data paths.

    Parameters
    ----------
    install_root :
        Installation directory (default: platform-appropriate default).
    data_root :
        Mutable data/state directory (default: platform-appropriate default).
    gui_host :
        Admin GUI listen host.
    gui_port :
        Admin GUI listen port.
    dry_run :
        If True, compute and return the config dict without writing any files.
    extra_paths :
        Additional [paths] keys to embed in the config.

    Returns
    -------
    dict with keys:
        install_root, data_root, config_file, dry_run, status, message
    """
    platform = current_platform()

    root = Path(install_root) if install_root else _default_install_root(platform)
    droot = Path(data_root) if data_root else _default_data_root(platform)
    conf_dest = root / CONF_FILENAME

    result: Dict[str, Any] = {
        "install_root": str(root),
        "data_root":    str(droot),
        "config_file":  str(conf_dest),
        "gui_host":     gui_host,
        "gui_port":     gui_port,
        "platform":     platform,
        "dry_run":      dry_run,
    }

    if dry_run:
        result["status"]  = "dry_run"
        result["message"] = f"Would write {conf_dest}"
        # Show what the config would contain
        import configparser, io
        cfg = configparser.ConfigParser(interpolation=None)
        cfg["noemaforge"] = {"install_root": str(root), "data_root": str(droot)}
        buf = io.StringIO()
        cfg.write(buf)
        result["preview"] = buf.getvalue()
        return result

    try:
        written = write_config(
            conf_dest, root, droot,
            gui_host=gui_host,
            gui_port=gui_port,
            extra_paths=extra_paths,
        )
        result["status"]  = "ok"
        result["message"] = f"Config written to {written}"
    except OSError as exc:
        result["status"]  = "error"
        result["message"] = str(exc)

    return result


# ---------------------------------------------------------------------------
# Shell bootstrap helpers
# ---------------------------------------------------------------------------

def generate_env_export(install_root: str, data_root: str, shell: str = "bash") -> str:
    """Generate shell export statements for backward-compat env vars.

    Useful for setup.sh / setup.ps1 to export env vars alongside the config.

    Parameters
    ----------
    shell : 'bash', 'sh', 'powershell', 'cmd'
    """
    pairs = [
        ("NOEMAFORGE_ROOT",       install_root),
        ("NOEMAFORGE_DATA_ROOT",  data_root),
    ]
    lines = []
    if shell in ("bash", "sh"):
        for k, v in pairs:
            lines.append(f'export {k}="{v}"')
        lines.append(f'export NOEMAFORGE_CONFIG_FILE="{install_root}/{CONF_FILENAME}"')
    elif shell == "powershell":
        for k, v in pairs:
            lines.append(f'$env:{k} = "{v}"')
        lines.append(f'$env:NOEMAFORGE_CONFIG_FILE = "{install_root}\\{CONF_FILENAME}"')
    elif shell == "cmd":
        for k, v in pairs:
            lines.append(f'SET {k}={v}')
        lines.append(f'SET NOEMAFORGE_CONFIG_FILE={install_root}\\{CONF_FILENAME}')
    return "\n".join(lines)


def validate_config_written(install_root: str) -> Dict[str, Any]:
    """Verify noemaforge.conf was written correctly and is readable.

    Returns a result dict with status='ok' or status='error'.
    Called by the installer's post-install verification step.
    """
    conf_path = Path(install_root) / CONF_FILENAME
    result: Dict[str, Any] = {"config_file": str(conf_path)}

    if not conf_path.exists():
        result["status"]  = "error"
        result["message"] = f"Config file not found: {conf_path}"
        return result

    import configparser
    cfg = configparser.ConfigParser(interpolation=None)
    try:
        cfg.read(conf_path, encoding="utf-8")
    except configparser.Error as exc:
        result["status"]  = "error"
        result["message"] = f"Config parse error: {exc}"
        return result

    missing = []
    for key in ("install_root", "data_root"):
        try:
            cfg.get("noemaforge", key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            missing.append(f"[noemaforge]/{key}")

    if missing:
        result["status"]  = "error"
        result["message"] = f"Missing required keys: {', '.join(missing)}"
    else:
        result["status"]  = "ok"
        result["message"] = "Config valid"
        result["install_root"] = cfg.get("noemaforge", "install_root")
        result["data_root"]    = cfg.get("noemaforge", "data_root")

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    plat = current_platform()
    default_root  = str(_default_install_root(plat))
    default_droot = str(_default_data_root(plat))

    p = argparse.ArgumentParser(
        description="Write NoemaForge installation configuration (noemaforge.conf).",
        epilog=(
            "The generated noemaforge.conf is read by platform_paths.py at "
            "runtime so all services use consistent paths without env vars."
        ),
    )
    p.add_argument("--install-root", default=default_root,
                   help=f"Installation directory (default: {default_root})")
    p.add_argument("--data-root", default=default_droot,
                   help=f"Mutable data directory (default: {default_droot})")
    p.add_argument("--gui-host", default="127.0.0.1",
                   help="Admin GUI listen host (default: 127.0.0.1)")
    p.add_argument("--gui-port", type=int, default=8765,
                   help="Admin GUI listen port (default: 8765)")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be written without writing")
    p.add_argument("--validate", action="store_true",
                   help="Validate existing config and exit")
    p.add_argument("--env-export", choices=["bash", "sh", "powershell", "cmd"],
                   help="Print env export statements for the given shell and exit")
    p.add_argument("--json", action="store_true",
                   help="Output result as JSON")
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)

    if args.env_export:
        print(generate_env_export(args.install_root, args.data_root, shell=args.env_export))
        return 0

    if args.validate:
        result = validate_config_written(args.install_root)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            status = result["status"]
            msg    = result["message"]
            print(f"[{status.upper()}] {msg}")
        return 0 if result["status"] == "ok" else 1

    result = run_install_config(
        install_root=args.install_root,
        data_root=args.data_root,
        gui_host=args.gui_host,
        gui_port=args.gui_port,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = result["status"]
        msg    = result["message"]
        icon = "✓" if status == "ok" else ("~" if status == "dry_run" else "✗")
        print(f"[{icon}] {msg}")
        if status == "dry_run":
            print(f"    install_root = {result['install_root']}")
            print(f"    data_root    = {result['data_root']}")
            print(f"    config_file  = {result['config_file']}")
    return 1 if result["status"] == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
