#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/_cli_bridge.py
Zone: tests
Purpose: Cross-platform bridge for the bin/noemaforge operator-CLI integration
         tests. bin/noemaforge is a `#!/usr/bin/env bash` wrapper that dispatches
         each subcommand to a Python entrypoint and internally calls /usr/bin/
         python3 + Linux-only tools, so it cannot run on a host without a working
         POSIX shell (e.g. a Windows dev box). These tests call the underlying
         Python entrypoint directly via sys.executable instead.

         LIMITATION: this bypasses the bin/noemaforge bash wrapper itself — its
         dispatch and argument handling are validated on the Debian target host
         and in CI. Here we exercise the Python command surface cross-platform.
Inputs: package root + the argv as passed to bin/noemaforge.
Outputs: an argv list to run the mapped Python entrypoint.
Notes: Code comments are English-only. stdlib only. Mirrors the cmd_* dispatch
       in bin/noemaforge; raises on an unmapped command so a test fails loudly.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple


def _toolproxy(rest: List[str]) -> List[str]:
    # cmd_toolproxy_diag: diag/diagnose/status strip the action; test/test-llm
    # become --test-llm; anything else passes through unchanged.
    if rest and rest[0] in ("diag", "diagnose", "status"):
        return rest[1:]
    if rest and rest[0] in ("test", "test-llm"):
        return ["--test-llm", *rest[1:]]
    return rest


def _schema(rest: List[str]) -> List[str]:
    if rest and rest[0] in ("validate", "check"):
        return ["schema-validate", *rest[1:]]
    return rest


# Top-level command -> (src module, arg transform). The command token is consumed
# by bin/noemaforge's dispatch; the remaining args are forwarded to the module.
_DISPATCH: Dict[str, Tuple[str, Callable[[List[str]], List[str]]]] = {
    "pipeline": ("pipeline_runtime.py", lambda r: r),
    "pipelines": ("pipeline_runtime.py", lambda r: r),
    "schema": ("pipeline_runtime.py", _schema),
    "admin": ("admin_runtime.py", lambda r: r),
    "dev-team": ("dev_team_runtime.py", lambda r: r),
    "member": ("team_member_runtime.py", lambda r: r),
    "qa": ("code_qa_runtime.py", lambda r: r),
    "code-qa": ("code_qa_runtime.py", lambda r: r),
    "testbench": ("selftest_runtime.py", lambda r: r),
    "selftest": ("selftest_runtime.py", lambda r: r),
    "wiki-patch": ("selftest_runtime.py", lambda r: ["wiki-patch", *r]),
    "toolproxy": ("noemaforge_toolproxy_diag.py", _toolproxy),
}


def noemaforge_cli(root: Path | str, *args: object) -> List[str]:
    """argv to run a bin/noemaforge subcommand via its Python entrypoint.

    ``root`` is the package root (the directory holding bin/ and src/). ``args``
    is the vector exactly as passed to bin/noemaforge — the first item is the
    top-level command. Raises KeyError for an unmapped command so a test fails
    loudly rather than silently mis-routing.
    """
    argv: Sequence[str] = [str(a) for a in args]
    if not argv:
        raise ValueError("noemaforge_cli requires at least the top-level command")
    command, rest = argv[0], list(argv[1:])
    module, transform = _DISPATCH[command]
    entrypoint = Path(root) / "src" / module
    return [sys.executable, str(entrypoint), *transform(rest)]
