#!/usr/bin/env python3
from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
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
                mock.patch.object(launcher.os, "execl") as execl_mock:
            rc = launcher.main(["noemaforge-llama-start", "main", "/tmp/noemaforge/main.sock"])

        self.assertEqual(70, rc)
        exists_mock.assert_not_called()
        execl_mock.assert_not_called()

    def test_execl_uses_only_literal_installed_llama_server_path(self) -> None:
        launcher = _load_launcher()
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(launcher.os.path, "exists", return_value=True), \
                mock.patch.object(launcher.os, "access", return_value=True), \
                mock.patch.object(launcher.runtime_safety, "validate_artifact_path", return_value=(True, "ok", {"realpath": "/tmp/model.gguf"})), \
                mock.patch.object(launcher.gguf_select, "validate_artifact_path", return_value=(True, "ok", {})), \
                mock.patch.object(launcher.os, "execl") as execl_mock:
            launcher.MODELSTORE = str(Path(td) / "modelstore")
            rc = launcher.main(["noemaforge-llama-start", "main", str(Path(td) / "main.sock")])

        self.assertEqual(127, rc)
        execl_mock.assert_called_once()
        exec_path, argv0, *argv = execl_mock.call_args.args
        self.assertEqual(launcher.DEFAULT_LLAMA_SERVER, exec_path)
        self.assertEqual(launcher.DEFAULT_LLAMA_SERVER, argv0)
        self.assertIn("--keep-display", argv)
        self.assertLess(argv.index("--keep-display"), argv.index("--model"))

    def test_rejects_extra_llama_server_args_before_filesystem_or_exec(self) -> None:
        launcher = _load_launcher()
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(launcher.os.path, "exists") as exists_mock, \
                mock.patch.object(launcher.os, "execl") as execl_mock:
            rc = launcher.main(["noemaforge-llama-start", "main", "/tmp/noemaforge/main.sock", "--threads", "2"])

        self.assertEqual(2, rc)
        exists_mock.assert_not_called()
        execl_mock.assert_not_called()

    def test_packaged_llama_server_wrapper_consumes_keep_display_marker(self) -> None:
        wrapper = ROOT / "bin" / "llama-server"
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            fake_backend = tmp / "llama-server-cpu"
            argv_file = tmp / "argv.txt"
            env_file = tmp / "env.txt"
            fake_backend.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" >\"$TEST_ARGV_FILE\"\n"
                "printf '%s\\n' \"${NOEMAFORGE_KEEP_DISPLAY:-}\" >\"$TEST_ENV_FILE\"\n",
                encoding="utf-8",
            )
            os.chmod(fake_backend, 0o755)
            env = {
                **os.environ,
                "NOEMAFORGE_LLM_MODE": "cpu",
                "NOEMAFORGE_LLAMA_SERVER_CPU": str(fake_backend),
                "TEST_ARGV_FILE": str(argv_file),
                "TEST_ENV_FILE": str(env_file),
            }

            result = subprocess.run(
                ["bash", str(wrapper), "--keep-display", "--model", "/tmp/model.gguf", "--no-display-stop", "--threads", "2"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            forwarded = argv_file.read_text(encoding="utf-8").splitlines()
            keep_display = env_file.read_text(encoding="utf-8").strip()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["--model", "/tmp/model.gguf", "--threads", "2"], forwarded)
        self.assertEqual("1", keep_display)


if __name__ == "__main__":
    unittest.main()
