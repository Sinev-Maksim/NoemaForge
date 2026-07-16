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
from unittest import mock

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import role_tournament as rt


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class RoleTournamentModelStorePreflightTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "ModelStore symlink staging is Linux target behavior")
    def test_modelstore_staging_preflight_checks_and_cleans_probe_dir(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            modelstore = Path(raw) / "modelstore"

            report = rt.preflight_modelstore_staging(str(modelstore))

            self.assertTrue(report["ok"], report)
            self.assertEqual(str(modelstore), report["modelstore_root"])
            self.assertTrue((modelstore / "models").is_dir())
            self.assertFalse(Path(report["probe_dir"]).exists())
            self.assertIn("create_model_symlink", report["checked"])

    def test_run_mode_fails_before_candidate_iteration_when_modelstore_preflight_fails(self) -> None:
        inventory = {
            "models": [
                {
                    "model_id": "alpha",
                    "artifact_format": "gguf",
                    "source_path": "/tmp/alpha.gguf",
                    "capabilities": ["llm"],
                    "runtime_family": "llama.cpp",
                },
                {
                    "model_id": "beta",
                    "artifact_format": "gguf",
                    "source_path": "/tmp/beta.gguf",
                    "capabilities": ["llm"],
                    "runtime_family": "llama.cpp",
                },
            ]
        }
        catalog = {"roles": {"operator.admin/administrator": {"required_capabilities": ["llm"], "top_k": 1, "tasks_per_model": 1}}}
        failed_preflight = {
            "apiVersion": "noemaforge.modelstore/v1",
            "kind": "ModelStoreStagingPreflight",
            "ok": False,
            "modelstore_root": "/var/lib/modelstore",
            "models_dir": "/var/lib/modelstore/models",
            "reason": "PermissionError: [Errno 13] Permission denied",
            "operator_actions": [
                "Run the approved first-start or tournament command as the service user/group that owns ModelStore.",
                "When elevation is required for model selection, preserve the graphical session with the approved --keep-display path.",
            ],
        }

        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw) / "state"
            with mock.patch.object(rt, "runtime_state", return_value={"available": True, "implemented": True, "probe": {}}), \
                 mock.patch.object(rt, "preflight_modelstore_staging", return_value=failed_preflight), \
                 mock.patch.object(rt, "write_modelstore_manifest") as write_manifest, \
                 mock.patch.object(rt, "start_gguf_backend") as start_backend:
                doc = rt.run_tournament(
                    inventory,
                    catalog,
                    state_dir=str(state),
                    modelstore_root="/var/lib/modelstore",
                    runtime_mode="run",
                    selection_mode="full",
                )

            write_manifest.assert_not_called()
            start_backend.assert_not_called()
            self.assertEqual("run", doc["runtime_mode"])
            self.assertEqual(1, len(doc["model_run_records"]))
            self.assertFalse(doc["model_run_records"][0]["started"])
            self.assertFalse(doc["model_run_records"][0]["candidate_iteration_started"])
            self.assertEqual("modelstore_staging_preflight_failed", doc["model_run_records"][0]["reason"])

            preflight_doc = load_json(state / "modelstore-staging-preflight.json")
            candidate_map = load_json(state / "role-candidate-map.json")
            progress = load_json(state / "role-tournament-progress.json")

        self.assertFalse(preflight_doc["ok"])
        self.assertIn("--keep-display", "\n".join(preflight_doc["operator_actions"]))
        self.assertEqual(
            "modelstore_staging_preflight_failed",
            candidate_map["selection_diagnostics"]["no_candidates_reason"],
        )
        self.assertEqual("complete", progress["phase"])

    def test_cli_reports_preflight_failure_as_not_ok(self) -> None:
        inventory = {
            "models": [
                {
                    "model_id": "alpha",
                    "artifact_format": "gguf",
                    "source_path": "/tmp/alpha.gguf",
                    "capabilities": ["llm"],
                    "runtime_family": "llama.cpp",
                }
            ]
        }
        failed_preflight = {
            "apiVersion": "noemaforge.modelstore/v1",
            "kind": "ModelStoreStagingPreflight",
            "ok": False,
            "modelstore_root": "/var/lib/modelstore",
            "models_dir": "/var/lib/modelstore/models",
            "reason": "PermissionError: [Errno 13] Permission denied",
            "message": "Current user cannot stage ModelStore model directories required by live role tournament.",
            "operator_actions": ["Repair /var/lib/modelstore ownership or group write/search permissions before rerunning live mode."],
        }

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            inventory_path = root / "inventory.json"
            catalog_path = root / "roles.yaml"
            state = root / "state"
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            catalog_path.write_text(
                "roles:\n  operator.admin/administrator:\n    required_capabilities:\n      - llm\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            with mock.patch.object(rt, "runtime_state", return_value={"available": True, "implemented": True, "probe": {}}), \
                 mock.patch.object(rt, "preflight_modelstore_staging", return_value=failed_preflight), \
                 redirect_stdout(stdout):
                rc = rt.main([
                    "run",
                    "--inventory", str(inventory_path),
                    "--role-catalog", str(catalog_path),
                    "--state-dir", str(state),
                    "--modelstore-root", "/var/lib/modelstore",
                    "--runtime-mode", "run",
                ])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(73, rc)
        self.assertFalse(payload["ok"])
        self.assertEqual("modelstore_staging_preflight_failed", payload["error"])
        self.assertIn("PermissionError", payload["reason"])


if __name__ == "__main__":
    unittest.main()
