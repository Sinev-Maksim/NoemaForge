#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/noema_cli.py
Zone: runtime/cli
Version: 0.33.0
Created: 2026-06-07
Modified: 2026-06-07
Purpose: Unified `noema` command-line entrypoint. Dispatches to the 0.33.0 operator commands
  (doctor, release, upgrade) so they share one discoverable surface instead of being invoked as
  separate module scripts. Thin dispatcher: it parses the subcommand and delegates argv to the
  owning module's main(); it adds no behavior of its own beyond --version/--help.
Inputs: argv (subcommand + that subcommand's arguments).
Outputs: delegates stdout/exit code to the chosen subcommand.
Side effects: none of its own; subcommands are read-only by default (upgrade apply needs --apply).
Tests: python3 -m unittest noemaforge/tests/test_noema_cli.py
Notes: Code comments are English-only. Display-safe: no subcommand here starts GPU/model/display work.
=== End NoemaForge File Header ===

Usage:
    noema <command> [args...]
    noema --version
    noema --help

Commands:
    start     one-button start: readiness + ensure dirs + launch the Admin GUI
    doctor    read-only readiness report
    release   build (pack) / verify release manifests
    upgrade   plan / apply an in-place upgrade (preserves user state)
"""
from __future__ import annotations

import sys
from typing import Callable, Dict, List, Optional


def _subcommands() -> Dict[str, Callable[[Optional[List[str]]], int]]:
    """Import the owning modules lazily so a failure in one does not block the others."""
    import noema_catalog
    import noema_doctor
    import noema_policy
    import noema_release
    import noema_start
    import noema_upgrade
    return {
        "start": noema_start.main,
        "doctor": noema_doctor.main,
        "release": noema_release.main,
        "upgrade": noema_upgrade.main,
        "policy": noema_policy.main,
        "catalog": noema_catalog.main,
    }


_USAGE = (
    "usage: noema <command> [args...]\n"
    "\n"
    "commands:\n"
    "  start     one-button start: readiness + ensure dirs + launch the Admin GUI\n"
    "  doctor    read-only readiness report\n"
    "  release   build (pack) / verify release manifests\n"
    "  upgrade   plan / apply an in-place upgrade (preserves user state)\n"
    "  policy    test policies against the deny-by-default contract\n"
    "  catalog   project declared contracts into a capability catalog\n"
    "\n"
    "  noema --version    print the runtime version\n"
    "  noema --help       show this help\n"
)


def _runtime_version() -> str:
    try:
        from noemaforge_version import RUNTIME_VERSION
        return str(RUNTIME_VERSION)
    except Exception:
        return "unknown"


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(_USAGE)
        return 0
    if argv[0] in ("-V", "--version"):
        print(f"noema {_runtime_version()}")
        return 0

    command, rest = argv[0], argv[1:]
    commands = _subcommands()
    handler = commands.get(command)
    if handler is None:
        sys.stderr.write(f"noema: unknown command {command!r}\n\n{_USAGE}")
        return 2
    return handler(rest)


if __name__ == "__main__":
    raise SystemExit(main())
