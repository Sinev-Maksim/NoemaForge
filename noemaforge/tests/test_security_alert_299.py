#!/usr/bin/env python3
from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_launcher():
    path = ROOT / "bin" / "noemaforge-llama-start"
    loader = importlib.machinery.SourceFileLoader("noemaforge_llama_start_alert_299", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("cannot load noemaforge-llama-start")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SecurityAlert299Tests(unittest.TestCase):
    def test_rejects_env_controlled_llama_server_before_filesystem_or_exec(self) -> None:
        launcher = _load_launcher()
        with mock.patch.dict(os.environ, {"NOEMAFORGE_LLAMA_SERVER": "/tmp/attacker/llama-server"}), \
                mock.patch.object(launcher.os.path, "exists") as exists_mock, \
                mock.patch.object(launcher.os, "execv") as execv_mock:
            rc = launcher.main(["noemaforge-llama-start", "main", "/tmp/noemaforge/main.sock"])

        self.assertEqual(70, rc)
        exists_mock.assert_not_called()
        execv_mock.assert_not_called()

    def test_execv_uses_only_literal_installed_llama_server_path(self) -> None:
        launcher = _load_launcher()
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(launcher.os.path, "exists", return_value=True), \
                mock.patch.object(launcher.os, "access", return_value=True), \
                mock.patch.object(launcher.runtime_safety, "validate_artifact_path", return_value=(True, "ok", {"realpath": "/tmp/model.gguf"})), \
                mock.patch.object(launcher.gguf_select, "validate_artifact_path", return_value=(True, "ok", {})), \
                mock.patch.object(launcher.os, "execv") as execv_mock:
            launcher.MODELSTORE = str(Path(td) / "modelstore")
            rc = launcher.main(["noemaforge-llama-start", "main", str(Path(td) / "main.sock"), "--threads", "2"])

        self.assertEqual(127, rc)
        execv_mock.assert_called_once()
        exec_path, argv = execv_mock.call_args.args
        self.assertEqual(launcher.DEFAULT_LLAMA_SERVER, exec_path)
        self.assertEqual(launcher.DEFAULT_LLAMA_SERVER, argv[0])
        self.assertIn("--threads", argv)


if __name__ == "__main__":
    unittest.main()
