#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/conftest.py
Zone: tests
Purpose: Make broad pytest collection order-independent.

         Many legacy unit tests install lightweight stand-in modules into
         sys.modules at *import time* (orchestration_state, production_ai_
         contracts, privileged_gui_job_runner, job_manager, platform_paths, ...)
         and never tear them down. Two incompatible styles coexist:

           * setdefault stubs (e.g. test_serve_static): intentionally
             incomplete; they only ever worked because a sibling test had
             already imported the *real* module, so setdefault was a no-op.
             Run first, the incomplete stub leaks and breaks every later test
             that needs the real module, e.g.:
                 from orchestration_state import _safe_int
                 ImportError: cannot import name '_safe_int' ... (unknown location)

           * assignment stubs (e.g. test_job_state_machine): rich, controlled
             doubles installed with ``sys.modules[name] = stub`` plus
             ``sys.modules.pop("admin_gui_server")``; the test validates against
             its own stub but then leaks it into later modules.

         Both failure modes are order-dependent (broad collection only) and pass
         when each test runs alone.

         This guard makes collection deterministic with one uniform mechanism,
         touching no individual test file and no runtime code:

           1. pytest_configure pre-imports the real runtime leaf modules, so an
              incomplete ``setdefault`` stub always finds the real module already
              present and becomes a no-op (real module wins, as in a passing run).
           2. pytest_collectstart restores that pristine baseline before each
              test module imports, so an import-time assignment stub / popped
              module cannot leak into the next module (collection phase).
           3. an autouse fixture restores the baseline after every test, so a
              stub a test installs in setUp/a test body (e.g. audit_remediation
              installs a platform_paths double) cannot leak into a later test
              that imports the real module during execution (execution phase).
Inputs: pytest collection hooks.
Outputs: side-effect only (normalises sys.modules between test-module imports).
Side effects: re-imports/restores runtime modules in sys.modules during collection.
Notes: Code comments are English-only. stdlib + pytest only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

# Real runtime source tree. A module is "runtime-owned" when it was imported
# from here; the test stubs that double these modules carry no __file__ at all.
_SRC = (Path(__file__).resolve().parent.parent / "src").resolve()

# Real leaf modules that tests stub or rebind. Pre-importing them means an
# incomplete ``setdefault`` stub finds the real module already cached and is a
# no-op. Importing admin_gui_server/session_store cascades to most of the rest;
# the explicit list keeps the intent clear and tolerates partial import failure.
_PRELOAD = (
    "platform_paths",
    "noemaforge_version",
    "orchestration_state",
    "production_ai_contracts",
    "privileged_gui_job_runner",
    "job_manager",
    "event_log",
    "session_store",
    "admin_gui_server",
)

# Snapshot of sys.modules right after pre-loading, and the runtime subset of it.
_BASELINE: dict[str, ModuleType] = {}
_BASELINE_RUNTIME: dict[str, ModuleType] = {}


def _is_runtime_owned(module: Any) -> bool:
    origin = getattr(module, "__file__", None)
    if origin is None:
        return False
    try:
        return _SRC in Path(origin).resolve().parents
    except OSError:
        return False


def _is_runtime_or_stub(module: Any) -> bool:
    """Runtime module, or a bare stub a test installed (ModuleType, no __file__)."""
    if module is None:
        return False
    if getattr(module, "__file__", None) is None:
        return True
    return _is_runtime_owned(module)


def pytest_configure(config: Any) -> None:
    """Pre-import real runtime modules and snapshot the clean baseline."""
    global _BASELINE, _BASELINE_RUNTIME
    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    for name in _PRELOAD:
        try:
            importlib.import_module(name)
        except Exception:  # noqa: BLE001 - a missing optional dep just isn't pre-seeded
            pass
    _BASELINE = dict(sys.modules)
    _BASELINE_RUNTIME = {
        name: module
        for name, module in _BASELINE.items()
        if _is_runtime_owned(module)
    }


def _restore_baseline() -> list[str]:
    changed: list[str] = []
    # Drop runtime modules and bare stubs a test added since the baseline.
    for name in list(sys.modules):
        if name in _BASELINE:
            continue
        if _is_runtime_or_stub(sys.modules.get(name)):
            del sys.modules[name]
            changed.append(name)
    # Undo in-place overrides / pops of baseline runtime modules (assignment stubs).
    for name, module in _BASELINE_RUNTIME.items():
        if sys.modules.get(name) is not module:
            sys.modules[name] = module
            changed.append(f"{name}*")
    return changed


@pytest.hookimpl(tryfirst=True)
def pytest_collectstart(collector: Any) -> None:
    """Restore the baseline import cache right before each test module imports.

    ``pytest_collectstart`` fires once per collector immediately before it
    collects. For a ``Module`` the import happens inside ``Module.collect()``,
    so clearing here runs *between* the previous module's import and this one's.
    (Earlier hooks such as ``pytest_collect_file``/``pytest_pycollect_makemodule``
    run during the up-front collector-creation pass, before any module is
    imported, which is why clearing there does not help.)
    """
    if not isinstance(collector, pytest.Module):
        return
    changed = _restore_baseline()
    if changed and os.environ.get("NOEMAFORGE_TEST_ISOLATION_DEBUG"):
        name = getattr(collector, "name", "?")
        print(
            f"[noemaforge-test-isolation] before={name} changed={sorted(changed)}",
            flush=True,
        )


@pytest.fixture(autouse=True)
def _isolate_sys_modules() -> Any:
    """Restore the baseline import cache after every test.

    Some tests install module doubles during setUp or a test body and never tear
    them down. Restoring here keeps execution order-independent, mirroring the
    collection-phase reset in ``pytest_collectstart``.
    """
    yield
    _restore_baseline()
