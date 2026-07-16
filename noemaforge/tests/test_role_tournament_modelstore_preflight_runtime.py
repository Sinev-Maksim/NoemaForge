#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
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

            doc = rt.modelstore_staging_preflight(str(modelstore), state_dir=str(state))

            self.assertTrue(doc["ok"], doc)
            self.assertEqual("ok", doc["reason"])
            self.assertFalse(any((modelstore / "models").glob(".noemaforge-staging-preflight-*")))
            written = json.loads((state / "modelstore-staging-preflight.json").read_text(encoding="utf-8"))
            self.assertTrue(written["ok"], written)
            self.assertIn("create_model_symlink", written["checks"])

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

            def deny_preflight(modelstore_root: str, state_dir: str = rt.DEFAULT_STATE_DIR) -> dict:
                doc = {
                    "apiVersion": "noemaforge.modelstore-preflight/v1",
                    "kind": "ModelStoreStagingPreflight",
                    "ok": False,
                    "reason": "modelstore_staging_permission_denied",
                    "message": "ModelStore staging is not writable by the current user.",
                    "operator_action": ["Run as the ModelStore service user or use sudo for the approved first-start command."],
                }
                rt.write_json(os.path.join(state_dir, "modelstore-staging-preflight.json"), doc)
                return doc

            old_llama = os.environ.get("NOEMAFORGE_LLAMA_SERVER")
            os.environ["NOEMAFORGE_LLAMA_SERVER"] = str(llama)
            try:
                with patch.object(rt, "modelstore_staging_preflight", side_effect=deny_preflight), \
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
            self.assertEqual([], doc["model_run_records"])
            self.assertEqual("modelstore_staging_permission_denied", doc["modelstore_staging_preflight"]["reason"])
            candidate_map = json.loads((state / "role-candidate-map.json").read_text(encoding="utf-8"))
            self.assertEqual(
                "modelstore_staging_permission_denied",
                candidate_map["selection_diagnostics"]["no_candidates_reason"],
            )


if __name__ == "__main__":
    unittest.main()
