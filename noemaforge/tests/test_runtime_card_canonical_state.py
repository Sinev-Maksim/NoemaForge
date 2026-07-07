#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import admin_gui_server as ags  # noqa: E402


def _server(tmp: Path) -> ags.AdminGuiServer:
    srv = object.__new__(ags.AdminGuiServer)
    srv.root = ROOT
    srv.state = tmp / "pipelines"
    srv.data_root = tmp / "data"
    srv.runtime_dir = srv.data_root / "runtime"
    srv.model_selection_state = tmp / "model-selection"
    srv.evolution_state = tmp / "model-evolution"
    srv.dev_team_state = tmp / "dev-team"
    srv.modelstore_dir = tmp / "modelstore"
    srv.bootstrap_dir = tmp / "bootstrap"
    srv.llm_gateway_socket = tmp / "gateway.sock"
    srv.llm_main_backend_socket = tmp / "main.sock"
    srv.legacy_llm_gateway_socket = None
    for path in [
        srv.state,
        srv.runtime_dir,
        srv.model_selection_state,
        srv.evolution_state,
        srv.dev_team_state,
        srv.modelstore_dir,
        srv.bootstrap_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
    return srv


def _active_systemctl(cmd, **_kwargs):
    unit = cmd[-1]
    return {"ok": True, "returncode": 0, "cmd": list(cmd), "stdout": "active", "stderr": "", "unit": unit}


class RuntimeCardCanonicalStateTests(unittest.TestCase):
    def test_runtime_status_maps_main_backend_to_canonical_service_and_socket(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.object(ags, "run_json", side_effect=_active_systemctl):
            srv = _server(Path(td))
            srv.llm_gateway_socket.write_text("", encoding="utf-8")
            srv.llm_main_backend_socket.write_text("", encoding="utf-8")
            model_dir = srv.modelstore_dir / "models" / "main"
            model_dir.mkdir(parents=True)
            (model_dir / "noemaforge-model.json").write_text(json.dumps({"model_id": "main-local"}), encoding="utf-8")
            (model_dir / "model.gguf").write_text("placeholder", encoding="utf-8")

            status = srv.runtime_status()

        main_service = status["service_states"]["main_backend"]
        main_socket = status["socket_states"]["main_backend"]
        self.assertEqual("noemaforge-llama@main.service", main_service["unit"])
        self.assertEqual("active", main_service["state"])
        self.assertTrue(main_service["active"])
        self.assertEqual("/run/noemaforge/llm/backends/main.sock", main_socket["path"])
        self.assertEqual("present", main_socket["state"])
        self.assertTrue(main_socket["present"])
        self.assertEqual("main-local", status["selected_model"]["model_id"])
        self.assertEqual("fresh", status["state_freshness"]["state"])

        cards = {card["id"]: card for card in status["observer_cards"]}
        self.assertEqual("active", cards["main-backend-service"]["state"])
        self.assertEqual("present", cards["main-backend-socket"]["state"])
        self.assertEqual("affirmed", cards["main-backend-socket"]["smoke_affirmation"])

    def test_telemetry_api_payload_uses_same_runtime_state_as_runtime_card(self) -> None:
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(ags, "run_json", side_effect=_active_systemctl), \
                mock.patch.object(ags.AdminGuiServer, "_command_output", return_value={"available": False, "stdout": "", "stderr": "missing command"}):
            srv = _server(Path(td))
            srv.llm_gateway_socket.write_text("", encoding="utf-8")
            srv.llm_main_backend_socket.write_text("", encoding="utf-8")

            payload = srv.telemetry_status()

        runtime = payload["runtime"]
        cards = {card["id"]: card for card in runtime["observer_cards"]}
        self.assertEqual("active", runtime["service_states"]["main_backend"]["state"])
        self.assertEqual("present", runtime["socket_states"]["main_backend"]["state"])
        self.assertEqual(runtime["service_states"]["main_backend"]["state"], cards["main-backend-service"]["state"])
        self.assertEqual(runtime["socket_states"]["main_backend"]["state"], cards["main-backend-socket"]["state"])

    def test_observer_cards_prefer_present_fallback_over_missing_canonical_socket(self) -> None:
        fallback = Path("/tmp/noemaforge-main-test.sock")
        with mock.patch.object(ags, "DEFAULT_LLM_MAIN_BACKEND_SOCKET", fallback):
            payload = {
                "sockets": {
                    "/run/noemaforge/llm/backends/main.sock": False,
                    str(fallback): True,
                },
                "main_backend": {"ok": True, "returncode": 0, "stdout": "active"},
                "gateway": {"ok": True, "returncode": 0, "stdout": "active"},
                "main_manifest": {"model_id": "main-local"},
                "device_policy": {"policy": "cpu"},
            }

            cards = {card["id"]: card for card in ags.build_runtime_observer_cards(payload)}

        self.assertEqual("present", cards["main-backend-socket"]["state"])
        self.assertEqual("affirmed", cards["main-backend-socket"]["smoke_affirmation"])


if __name__ == "__main__":
    unittest.main()
