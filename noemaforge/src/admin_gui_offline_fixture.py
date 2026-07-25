#!/usr/bin/env python3
"""Shared offline AdminGuiServer doubles for runtime validators and unit tests."""
from __future__ import annotations

import copy
import threading
from pathlib import Path
from typing import Any, Callable, Dict


def build_offline_admin_gui_server(
    *,
    package_root: Path | str,
    data_root: Path | str | None = None,
    create_dirs: bool = False,
) -> Any:
    import admin_gui_server  # type: ignore

    root = Path(package_root).resolve()
    state_root = Path(data_root).resolve() if data_root is not None else root / "_memory_only_gui_state"
    server = object.__new__(admin_gui_server.AdminGuiServer)
    server.root = root
    server.state = state_root / "pipelines"
    server.persona_state = state_root / "personas"
    server.evolution_state = state_root / "model-evolution"
    server.model_selection_state = state_root / "model-selection"
    server.dev_team_state = state_root / "dev-team"
    server.data_root = state_root
    server.gui_state_dir = state_root / "gui"
    server.jobs_dir = state_root / "jobs"
    server.tasks_dir = state_root / "tasks"
    server.review_dir = state_root / "review"
    server.runtime_dir = state_root / "runtime"
    server.bootstrap_dir = state_root / "bootstrap"
    server.modelstore_dir = state_root / "modelstore"
    server.ui_dir = root / "templates" / "pipeline-dashboard"
    server.llm_gateway_socket = state_root / "runtime" / "gateway.sock"
    server.llm_main_backend_socket = state_root / "runtime" / "main.sock"
    server.legacy_llm_gateway_socket = None
    # Parity with AdminGuiServer.__init__: read-modify-write locks. The double
    # bypasses __init__ via object.__new__, so these must be set explicitly.
    server._jobs_lock = threading.Lock()
    server._tasks_lock = threading.Lock()
    server._conv_lock = threading.Lock()
    if create_dirs:
        for path in (
            server.state,
            server.persona_state,
            server.model_selection_state,
            server.evolution_state,
            server.dev_team_state,
            server.gui_state_dir,
            server.jobs_dir,
            server.tasks_dir,
            server.runtime_dir,
            server.bootstrap_dir,
            server.modelstore_dir,
            server.review_dir / "sr" / "inbox",
            server.review_dir / "ssr" / "inbox",
        ):
            path.mkdir(parents=True, exist_ok=True)
    return server


def attach_memory_json_store(
    server: Any,
    *,
    store: Dict[str, Any] | None = None,
    read_json: Callable[[Path, Any], Any] | None = None,
) -> Dict[str, Any]:
    memory_store: Dict[str, Any] = {} if store is None else store

    def default_read_json(path: Path, default: Any) -> Any:
        key = str(Path(path))
        if key not in memory_store:
            return copy.deepcopy(default)
        return copy.deepcopy(memory_store[key])

    def write_json(path: Path, obj: Any) -> None:
        memory_store[str(Path(path))] = copy.deepcopy(obj)

    def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
        key = str(Path(path))
        memory_store.setdefault(key, []).append(copy.deepcopy(obj))

    server._memory_store = memory_store
    server._read_json = read_json or default_read_json
    server._write_json = write_json
    server._append_jsonl = append_jsonl
    return memory_store
