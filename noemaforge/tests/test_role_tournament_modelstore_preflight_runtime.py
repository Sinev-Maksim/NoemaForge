#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import role_tournament as rt


class RoleTournamentModelStorePreflightRuntimeTests(unittest.TestCase):
    def test_modelstore_staging_preflight_writes_machine_readable_success(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = root / "state"
            modelstore = root / "modelstore"

            doc = rt.preflight_modelstore_staging(str(modelstore))

            self.assertTrue(doc["ok"], doc)
            self.assertFalse(Path(doc["probe_dir"]).exists())
            self.assertIn("create_model_symlink", doc["checked"])

    def test_modelstore_staging_preflight_cleanup_failure_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = root / "state"
            modelstore = root / "modelstore"

            with patch.object(rt.Path, "rmdir", side_effect=OSError("busy")):
                doc = rt.preflight_modelstore_staging(str(modelstore))

            self.assertFalse(doc["ok"], doc)
            self.assertEqual("cleanup_probe_dir_failed", doc["reason"])
            self.assertTrue(doc["cleanup_errors"])
            self.assertNotIn("cleanup_probe_dir", doc["checked"])

    def test_run_mode_modelstore_preflight_permission_failure_is_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = root / "state"
            modelstore = root / "modelstore"
            source = root / "candidate.gguf"
            source.write_bytes(b"gguf")
            llama = root / "llama-server"
            llama.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            llama.chmod(0o755)
            inventory = {
                "models": [
                    {
                        "model_id": "candidate",
                        "display_name": "candidate",
                        "artifact_format": "gguf",
                        "runtime_family": "llama.cpp",
                        "source_path": str(source),
                        "capabilities": ["llm"],
                        "artifact_valid": True,
                    }
                ]
            }
            catalog = {
                "roles": {
                    "operator.admin/administrator": {
                        "required_capabilities": ["llm"],
                        "tasks_per_model": 1,
                        "top_k": 1,
                    }
                }
            }

            def deny_preflight(modelstore_root: str) -> dict:
                return {
                    "apiVersion": "noemaforge.modelstore-preflight/v1",
                    "kind": "ModelStoreStagingPreflight",
                    "ok": False,
                    "reason": "modelstore_staging_permission_denied",
                    "message": "ModelStore staging is not writable by the current user.",
                    "operator_actions": ["Run as the ModelStore service user or use sudo for the approved first-start command."],
                }

            old_llama = os.environ.get("NOEMAFORGE_LLAMA_SERVER")
            os.environ["NOEMAFORGE_LLAMA_SERVER"] = str(llama)
            try:
                with patch.object(rt, "preflight_modelstore_staging", side_effect=deny_preflight), \
                        patch.object(rt, "write_modelstore_manifest", side_effect=AssertionError("staging loop must not start")), \
                        patch.object(rt, "start_gguf_backend", side_effect=AssertionError("backend must not start")):
                    doc = rt.run_tournament(
                        inventory,
                        catalog,
                        state_dir=str(state),
                        modelstore_root=str(modelstore),
                        scorecards_dir=str(root / "scorecards"),
                        runtime_mode="run",
                    )
            finally:
                if old_llama is None:
                    os.environ.pop("NOEMAFORGE_LLAMA_SERVER", None)
                else:
                    os.environ["NOEMAFORGE_LLAMA_SERVER"] = old_llama

            self.assertEqual("run", doc["runtime_mode"])
            self.assertEqual(1, len(doc["model_run_records"]))
            self.assertFalse(doc["model_run_records"][0]["started"])
            self.assertFalse(doc["model_run_records"][0]["candidate_iteration_started"])
            self.assertEqual("modelstore_staging_preflight_failed", doc["model_run_records"][0]["reason"])
            preflight_doc = json.loads((state / "modelstore-staging-preflight.json").read_text(encoding="utf-8"))
            self.assertEqual("modelstore_staging_permission_denied", preflight_doc["reason"])
            candidate_map = json.loads((state / "role-candidate-map.json").read_text(encoding="utf-8"))
            self.assertEqual(
                "modelstore_staging_preflight_failed",
                candidate_map["selection_diagnostics"]["no_candidates_reason"],
            )

    def test_run_mode_attaches_successful_modelstore_preflight_to_results(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = root / "state"
            modelstore = root / "modelstore"
            source = root / "candidate.gguf"
            source.write_bytes(b"gguf")
            catalog = {
                "roles": {
                    "operator.admin/administrator": {
                        "required_capabilities": ["llm"],
                        "tasks_per_model": 1,
                        "top_k": 1,
                    }
                }
            }

            def pass_preflight(modelstore_root: str) -> dict:
                return {
                    "apiVersion": "noemaforge.modelstore-preflight/v1",
                    "kind": "ModelStoreStagingPreflight",
                    "ok": True,
                    "reason": "ok",
                    "message": "ModelStore staging preflight passed.",
                }

            inventory = {
                "models": [
                    {
                        "model_id": "candidate",
                        "display_name": "candidate",
                        "artifact_format": "gguf",
                        "runtime_family": "llama.cpp",
                        "source_path": str(source),
                        "capabilities": ["llm"],
                        "artifact_valid": True,
                    }
                ]
            }
            with patch.object(rt, "runtime_state", return_value={"available": True, "implemented": True, "probe": {}}), \
                    patch.object(rt, "preflight_modelstore_staging", side_effect=pass_preflight), \
                    patch.object(rt, "write_modelstore_manifest"), \
                    patch.object(rt, "start_gguf_backend", return_value=(False, "sock", "systemctl_start_failed:5")):
                doc = rt.run_tournament(
                    inventory,
                    catalog,
                    state_dir=str(state),
                    modelstore_root=str(modelstore),
                    scorecards_dir=str(root / "scorecards"),
                    runtime_mode="run",
                )

            self.assertEqual(str(state / "modelstore-staging-preflight.json"), doc["modelstore_staging_preflight"])
            written = json.loads((state / "role-tournament-results.json").read_text(encoding="utf-8"))
            self.assertEqual(str(state / "modelstore-staging-preflight.json"), written["modelstore_staging_preflight"])

    def test_cli_runtime_run_requires_critical_role_selection(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            inventory = root / "inventory.json"
            catalog = root / "role-catalog.yaml"
            state = root / "state"
            inventory.write_text('{"models":[]}\n', encoding="utf-8")
            catalog.write_text("roles: {}\n", encoding="utf-8")
            doc = {
                "roles": {
                    "writing.story/writer": {
                        "selected": [{"model_id": "writer-model"}],
                    },
                    "operator.admin/administrator": {
                        "selected": [],
                    },
                    "dev.work/solution_architect": {
                        "selected": [],
                    },
                },
                "modelstore_staging_preflight": {"ok": True, "reason": "ok"},
            }

            out = StringIO()
            with patch.object(rt, "run_tournament", return_value=doc), redirect_stdout(out):
                code = rt.main([
                    "run",
                    "--inventory", str(inventory),
                    "--role-catalog", str(catalog),
                    "--state-dir", str(state),
                    "--runtime-mode", "run",
                ])

            payload = json.loads(out.getvalue())
            self.assertEqual(73, code)
            self.assertFalse(payload["ok"], payload)
            self.assertEqual(0, payload["critical_selected_models"])


if __name__ == "__main__":
    unittest.main()
