#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import admin_gui_server as ags  # noqa: E402
import opt_sync_guard as osg  # noqa: E402


def _executable(path: Path, text: str = "#!/bin/sh\nexit 0\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


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
    for path in [srv.state, srv.runtime_dir, srv.model_selection_state, srv.evolution_state, srv.dev_team_state, srv.modelstore_dir, srv.bootstrap_dir]:
        path.mkdir(parents=True, exist_ok=True)
    return srv


class ProdReadyHotfixTests(unittest.TestCase):
    def test_promote_run_artifacts_empty_path_returns_no_cards(self) -> None:
        self.assertEqual([], ags.promote_run_artifacts(""))

    def test_promote_run_artifacts_keeps_run_dir_and_nested_non_empty_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "run_public_mwp_1"
            for rel, text in {
                "manifest.json": "{}\n",
                "README.md": "readme\n",
                "outputs/final.md": "answer\n",
                "context_packets/packet.json": "{}\n",
                "reviews/review.md": "ok\n",
                "logs/run.log": "log\n",
            }.items():
                path = run / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            (run / "outputs" / "empty.md").write_text("", encoding="utf-8")

            cards = ags.promote_run_artifacts(str(run), status="running")
            labels = {card.get("label") for card in cards}

            self.assertIn("run_dir", labels)
            self.assertIn("manifest.json", labels)
            self.assertIn("outputs/final.md", labels)
            self.assertIn("context_packets/packet.json", labels)
            self.assertIn("reviews/review.md", labels)
            self.assertIn("logs/run.log", labels)
            self.assertNotIn("outputs/empty.md", labels)
            self.assertTrue(all(card.get("open_url") for card in cards))

    def test_runtime_status_exposes_missing_active_model_and_pipeline_guard(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.object(ags, "run_json", return_value={"ok": False, "stdout": "inactive", "returncode": 3}):
            srv = _server(Path(td))
            status = srv.runtime_status()

            self.assertTrue(status["model_selection_required"])
            self.assertTrue(status["missing_main_model_manifest"])
            self.assertEqual("missing", status["active_model"]["state"])
            self.assertIn("Model selection required", status["active_model"]["message"])

            result = srv.pipeline_run("public_mwp", "run", allow_degraded=False)
            self.assertFalse(result["ok"])
            self.assertEqual("model_selection_required", result["error"])
            self.assertTrue(result["model_selection_required"])

    def test_runtime_status_warns_on_manifest_source_realpath_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.object(ags, "run_json", return_value={"ok": False, "stdout": "inactive", "returncode": 3}):
            srv = _server(Path(td))
            main_dir = srv.modelstore_dir / "models" / "main"
            main_dir.mkdir(parents=True)
            chosen = srv.modelstore_dir / "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
            manifest_source = srv.modelstore_dir / "qwen2-5-coder-3b-instruct-q4-k-m.gguf"
            chosen.write_text("chosen", encoding="utf-8")
            manifest_source.write_text("manifest", encoding="utf-8")
            (main_dir / "model.gguf").symlink_to(chosen)
            (main_dir / "noemaforge-model.json").write_text(json.dumps({
                "model_id": "qwen2-5-coder-3b-instruct-q4-k-m",
                "display_name": "Qwen2.5 Coder 3B",
                "source": str(manifest_source),
            }), encoding="utf-8")

            status = srv.runtime_status()
            self.assertTrue(status["model_selection_required"])
            self.assertFalse(status["metadata_consistency"]["ok"])
            self.assertIn("source_realpath_mismatch", status["metadata_consistency"]["mismatches"])
            self.assertNotEqual("ready", status["active_model"]["state"])
            self.assertIn("metadata mismatch", status["active_model"]["message"].lower())
            card = [c for c in status["observer_cards"] if c["id"] == "main-model-manifest"][0]
            self.assertEqual("warn", card["status"])

    def test_runtime_status_accepts_manifest_source_same_realpath(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.object(ags, "run_json", return_value={"ok": False, "stdout": "inactive", "returncode": 3}):
            srv = _server(Path(td))
            main_dir = srv.modelstore_dir / "models" / "main"
            main_dir.mkdir(parents=True)
            chosen = srv.modelstore_dir / "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
            chosen.write_text("chosen", encoding="utf-8")
            (main_dir / "model.gguf").symlink_to(chosen)
            (main_dir / "noemaforge-model.json").write_text(json.dumps({
                "model_id": "qwen2-5-coder-0.5b-instruct-q4-k-m",
                "display_name": "Qwen2.5 Coder 0.5B",
                "source": str(chosen),
            }), encoding="utf-8")

            status = srv.runtime_status()
            self.assertFalse(status["model_selection_required"])
            self.assertTrue(status["metadata_consistency"]["ok"])
            self.assertEqual("ready", status["active_model"]["state"])
            self.assertEqual("", status["active_model"]["message"])

    def test_version_audit_accepts_installed_payload_version_layout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "VERSION").write_text("0.33.0\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "VERSION").write_text("0.33.0\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "noemaforge_version.py").write_text(
                'RUNTIME_VERSION = "0.33.0"\n',
                encoding="utf-8",
            )

            proc = subprocess.run(
                ["bash", str(ROOT / "tools" / "prep" / "noemaforge-version-audit.sh"), "--root", str(root), "--expected", "0.33.0", "--json"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            self.assertTrue(json.loads(proc.stdout)["ok"])

    def test_epoch_status_exposes_missing_model_selection_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            status = srv.epoch_status()

            self.assertTrue(status["model_selection_required"])
            self.assertEqual("", status["current_epoch"]["model_id"])
            self.assertTrue(status["current_epoch"]["selection_required"])
            self.assertFalse(status["current_epoch"]["manifest_exists"])
            self.assertIn("refresh/apply epoch", status["operator_action"])

    def test_conversational_admin_reply_returns_model_selection_required_backend(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.object(ags, "run_json", return_value={"ok": False, "stdout": "inactive", "returncode": 3}) as run_json:
            srv = _server(Path(td))
            reply = srv.conversational_admin_reply("hello", "en")

            self.assertEqual("model_selection_required", reply["backend"])
            self.assertIn("Model selection required", reply["reply"])
            self.assertEqual(2, run_json.call_count)

    def test_health_includes_source_fingerprint_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(ags.shutil, "which", return_value="/opt/noemaforge/bin/noemaforge"), \
                mock.patch.object(ags.subprocess, "check_output", side_effect=["abc123\n", "hotfix/prod-ready\n"]):
            srv = _server(Path(td))
            health = srv.health()

            self.assertEqual(str(ROOT), health["root"])
            self.assertIn("version", health)
            self.assertEqual("abc123", health["git_head"])
            self.assertEqual("hotfix/prod-ready", health["git_branch"])
            self.assertEqual("/opt/noemaforge/bin/noemaforge", health["cli_path"])
            self.assertIn("install_path", health)
            self.assertEqual("git checkout metadata available", health["git_metadata_reason"])

    def test_memory_metrics_maps_proc_meminfo_to_named_fields(self) -> None:
        metrics = ags._memory_metrics({
            "MemTotal": "16777216 kB",
            "MemAvailable": "4194304 kB",
            "SwapTotal": "8388608 kB",
            "SwapFree": "2097152 kB",
        })

        self.assertEqual(17179869184, metrics["ram"]["total"])
        self.assertEqual(12884901888, metrics["ram"]["used"])
        self.assertEqual(75.0, metrics["ram"]["percent"])
        self.assertEqual(8589934592, metrics["swap"]["total"])
        self.assertEqual(6442450944, metrics["swap"]["used"])
        self.assertEqual(75.0, metrics["swap"]["percent"])
        self.assertEqual(metrics["ram"]["used"], metrics["used"])
        self.assertEqual(metrics["swap"]["used"], metrics["swap_used"])

    def test_parse_nvidia_smi_maps_csv_to_named_gpu_fields(self) -> None:
        rows = ags._parse_nvidia_smi_gpus({
            "available": True,
            "stdout": "NVIDIA GeForce RTX 3080 Ti, 53, 111.5, 2048, 12288, 17\n",
            "stderr": "",
        })

        self.assertEqual(1, len(rows))
        self.assertEqual("NVIDIA GeForce RTX 3080 Ti", rows[0]["name"])
        self.assertEqual("53", rows[0]["temperature_c"])
        self.assertEqual("111.5", rows[0]["power_w"])
        self.assertEqual("2048", rows[0]["memory_used_mib"])
        self.assertEqual("12288", rows[0]["memory_total_mib"])
        self.assertEqual("17", rows[0]["utilization_percent"])

    def test_safe_opt_sync_preserves_local_llama_server_when_source_lacks_backend(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = base / "src"
            target = base / "opt" / "noemaforge"
            _executable(source / "bin" / "noemaforge")
            _executable(target / "bin" / "noemaforge-llama-start")
            _executable(target / "bin" / "llama-server")
            _executable(target / "bin" / "llama-server-cpu")

            report = osg.validate_safe_sync(source, target)
            self.assertTrue(report["ok"], report["errors"])
            cmd = osg.rsync_command(source, target)
            self.assertIn("/bin/llama-server", cmd)
            self.assertIn("/bin/noemaforge-llama-start", cmd)
            self.assertIn("/bin/llama-server-cpu", cmd)
            self.assertIn("bin/llama-server-cpu", report["available_real_backends"])

    def test_safe_opt_sync_aborts_when_protected_backend_missing_from_target(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = base / "src"
            target = base / "opt" / "noemaforge"
            _executable(source / "bin" / "noemaforge")
            _executable(source / "bin" / "noemaforge-llama-start")
            _executable(source / "bin" / "llama-server")

            report = osg.validate_safe_sync(source, target)
            self.assertFalse(report["ok"])
            self.assertIn("required_executable_missing_or_not_executable:bin/llama-server", report["errors"])

    def test_safe_opt_sync_wrapper_exists_but_real_backends_missing_is_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = base / "src"
            target = base / "opt" / "noemaforge"
            _executable(source / "bin" / "noemaforge")
            _executable(target / "bin" / "noemaforge-llama-start")
            _executable(target / "bin" / "llama-server")

            report = osg.validate_safe_sync(source, target)
            self.assertFalse(report["ok"])
            self.assertIn("real_backend_missing_or_not_executable:bin/llama-server-cpu|bin/llama-server-cuda", report["errors"])

    def test_safe_opt_sync_source_real_backend_does_not_mask_missing_target_backend(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            source = base / "src"
            target = base / "opt" / "noemaforge"
            _executable(source / "bin" / "noemaforge")
            _executable(source / "bin" / "llama-server-cpu")
            _executable(target / "bin" / "noemaforge-llama-start")
            _executable(target / "bin" / "llama-server")

            report = osg.validate_safe_sync(source, target)
            self.assertFalse(report["ok"])
            self.assertIn("real_backend_missing_or_not_executable:bin/llama-server-cpu|bin/llama-server-cuda", report["errors"])


if __name__ == "__main__":
    unittest.main()
