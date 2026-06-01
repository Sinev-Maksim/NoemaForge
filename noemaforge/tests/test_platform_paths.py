#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_platform_paths.py
Zone: tests
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Tests for platform_paths.py — cross-platform path resolution.
         Verifies correct defaults per platform, env-var overrides,
         backward-compatibility shims, and the as_dict/detect_platform helpers.
Tests: python3 -m unittest noemaforge/tests/test_platform_paths.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Stub noemaforge_version before importing platform_paths
stub_ver = types.ModuleType("noemaforge_version")
stub_ver.RUNTIME_VERSION = "0.32.2"
sys.modules.setdefault("noemaforge_version", stub_ver)

from platform_paths import (
    NoemaForgePaths,
    PLATFORM_LINUX, PLATFORM_WINDOWS, PLATFORM_MACOS, PLATFORM_OTHER,
    current_platform,
    DEFAULT_PATHS,
    get_root, get_data_root, get_gui_state_dir, get_jobs_dir,
)


class TestCurrentPlatform(unittest.TestCase):
    """current_platform() must return the right token."""

    def test_linux_detected(self) -> None:
        with patch.object(sys, "platform", "linux"):
            self.assertEqual(current_platform(), PLATFORM_LINUX)

    def test_linux2_detected(self) -> None:
        with patch.object(sys, "platform", "linux2"):
            self.assertEqual(current_platform(), PLATFORM_LINUX)

    def test_windows_detected(self) -> None:
        with patch.object(sys, "platform", "win32"):
            self.assertEqual(current_platform(), PLATFORM_WINDOWS)

    def test_darwin_detected(self) -> None:
        with patch.object(sys, "platform", "darwin"):
            self.assertEqual(current_platform(), PLATFORM_MACOS)

    def test_other_platform(self) -> None:
        with patch.object(sys, "platform", "freebsd13"):
            self.assertEqual(current_platform(), PLATFORM_OTHER)


class TestNoemaForgePathsLinux(unittest.TestCase):
    """Default paths for Linux platform."""

    def setUp(self) -> None:
        # Clear env vars that might affect tests
        self._clean_env = {k: v for k, v in os.environ.items()
                           if not k.startswith("NOEMAFORGE_")}

    def _make(self) -> NoemaForgePaths:
        with patch.dict(os.environ, self._clean_env, clear=True):
            return NoemaForgePaths(platform=PLATFORM_LINUX)

    def test_root_is_opt_noemaforge(self) -> None:
        p = self._make()
        self.assertEqual(p.root, Path("/opt/noemaforge"))

    def test_data_root_is_var_lib(self) -> None:
        p = self._make()
        self.assertEqual(p.data_root, Path("/var/lib/noemaforge"))

    def test_gui_state_dir_under_data_root(self) -> None:
        p = self._make()
        self.assertEqual(p.gui_state_dir, Path("/var/lib/noemaforge/gui"))

    def test_session_state_dir_under_gui(self) -> None:
        p = self._make()
        self.assertEqual(p.session_state_dir, Path("/var/lib/noemaforge/gui/sessions"))

    def test_jobs_dir_under_gui(self) -> None:
        p = self._make()
        self.assertEqual(p.jobs_dir, Path("/var/lib/noemaforge/gui/jobs"))

    def test_pipelines_dir_under_data_root(self) -> None:
        p = self._make()
        self.assertEqual(p.pipelines_dir, Path("/var/lib/noemaforge/pipelines"))

    def test_model_evolution_state_dir(self) -> None:
        p = self._make()
        self.assertEqual(p.model_evolution_state_dir, Path("/var/lib/noemaforge/model-evolution"))

    def test_dev_team_state_dir(self) -> None:
        p = self._make()
        self.assertEqual(p.dev_team_state_dir, Path("/var/lib/noemaforge/dev-team"))

    def test_code_evolution_state_dir(self) -> None:
        p = self._make()
        self.assertEqual(p.code_evolution_state_dir, Path("/var/lib/noemaforge/code-evolution"))

    def test_linux_runtime_bootstrap_share_modelstore_defaults(self) -> None:
        p = self._make()
        self.assertEqual(p.runtime_dir, Path("/run/noemaforge"))
        self.assertEqual(p.bootstrap_dir, Path("/var/lib/noemaforge/bootstrap"))
        self.assertEqual(p.share_dir, Path("/mnt/noemaforge-share"))
        self.assertEqual(p.modelstore_dir, Path("/var/lib/modelstore"))

    def test_linux_socket_defaults(self) -> None:
        p = self._make()
        self.assertEqual(p.llm_gateway_socket, Path("/run/noemaforge/llm/gateway.sock"))
        self.assertEqual(p.llm_main_backend_socket, Path("/run/noemaforge/llm/backends/main.sock"))
        self.assertEqual(p.toolproxy_socket, Path("/run/noemaforge/toolproxy.sock"))

    def test_gui_listen_defaults(self) -> None:
        p = self._make()
        self.assertEqual(p.gui_listen_address, ("127.0.0.1", 8765))

    def test_unix_socket_present_on_linux(self) -> None:
        p = self._make()
        self.assertIsNotNone(p.gui_unix_socket)


class TestNoemaForgePathsWindows(unittest.TestCase):
    """Default paths for Windows platform."""

    def setUp(self) -> None:
        self._clean_env = {k: v for k, v in os.environ.items()
                           if not k.startswith("NOEMAFORGE_")}
        # Ensure ProgramData is set for Windows tests
        self._clean_env.setdefault("ProgramData", r"C:\ProgramData")

    def _make(self) -> NoemaForgePaths:
        with patch.dict(os.environ, self._clean_env, clear=True):
            return NoemaForgePaths(platform=PLATFORM_WINDOWS)

    def test_root_under_programdata(self) -> None:
        p = self._make()
        self.assertIn("ProgramData", str(p.root) + str(Path(r"C:\ProgramData")))
        self.assertTrue(str(p.root).endswith("noemaforge"))

    def test_data_root_under_programdata(self) -> None:
        p = self._make()
        self.assertIn("noemaforge", str(p.data_root))

    def test_no_unix_socket_on_windows(self) -> None:
        p = self._make()
        self.assertIsNone(p.gui_unix_socket)

    def test_runtime_paths_are_data_relative_on_windows(self) -> None:
        p = self._make()
        self.assertEqual(p.runtime_dir, p.data_root / "run")
        self.assertEqual(p.bootstrap_dir, p.data_root / "bootstrap")
        self.assertEqual(p.share_dir, p.data_root / "share")
        self.assertEqual(p.modelstore_dir, p.data_root / "modelstore")
        self.assertIsNone(p.legacy_brainos_gateway_socket)

    def test_socket_paths_are_runtime_relative_on_windows(self) -> None:
        p = self._make()
        self.assertEqual(p.llm_gateway_socket, p.runtime_dir / "llm" / "gateway.sock")
        self.assertEqual(p.llm_main_backend_socket, p.runtime_dir / "llm" / "backends" / "main.sock")

    def test_root_and_data_root_differ_on_linux(self) -> None:
        """On Linux, root ≠ data_root (different filesystem conventions)."""
        with patch.dict(os.environ, self._clean_env, clear=True):
            p_linux = NoemaForgePaths(platform=PLATFORM_LINUX)
        self.assertNotEqual(p_linux.root, p_linux.data_root)


class TestEnvVarOverrides(unittest.TestCase):
    """Environment variables must override platform defaults."""

    def test_noemaforge_root_overrides_default(self) -> None:
        with patch.dict(os.environ, {"NOEMAFORGE_ROOT": "/custom/root"}, clear=False):
            p = NoemaForgePaths(platform=PLATFORM_LINUX)
            self.assertEqual(p.root, Path("/custom/root"))

    def test_noemaforge_data_root_overrides_default(self) -> None:
        with patch.dict(os.environ, {"NOEMAFORGE_DATA_ROOT": "/mnt/data"}, clear=False):
            p = NoemaForgePaths(platform=PLATFORM_LINUX)
            self.assertEqual(p.data_root, Path("/mnt/data"))

    def test_session_state_env_var(self) -> None:
        with patch.dict(os.environ, {"NOEMAFORGE_SESSION_STATE": "/tmp/sessions"}, clear=False):
            p = NoemaForgePaths(platform=PLATFORM_LINUX)
            self.assertEqual(p.session_state_dir, Path("/tmp/sessions"))

    def test_gui_host_env_var(self) -> None:
        with patch.dict(os.environ, {"NOEMAFORGE_GUI_HOST": "0.0.0.0",
                                     "NOEMAFORGE_GUI_PORT": "9000"}, clear=False):
            p = NoemaForgePaths()
            host, port = p.gui_listen_address
            self.assertEqual(host, "0.0.0.0")
            self.assertEqual(port, 9000)

    def test_gui_port_bad_value_defaults_to_8765(self) -> None:
        with patch.dict(os.environ, {"NOEMAFORGE_GUI_PORT": "notanumber"}, clear=False):
            p = NoemaForgePaths()
            _, port = p.gui_listen_address
            self.assertEqual(port, 8765)

    def test_root_constructor_arg_takes_precedence(self) -> None:
        with patch.dict(os.environ, {"NOEMAFORGE_ROOT": "/env/root"}, clear=False):
            p = NoemaForgePaths(root=Path("/arg/root"))
            self.assertEqual(p.root, Path("/arg/root"))

    def test_runtime_path_env_vars_override_defaults(self) -> None:
        env = {
            "NOEMAFORGE_RUNTIME_DIR": "/tmp/nf-run",
            "NOEMAFORGE_BOOTSTRAP_DIR": "/tmp/nf-bootstrap",
            "NOEMAFORGE_SHARE_DIR": "/tmp/nf-share",
            "NOEMAFORGE_MODELSTORE_DIR": "/tmp/nf-modelstore",
            "NOEMAFORGE_GATEWAY_SOCKET": "/tmp/nf-run/llm/gateway.sock",
            "NOEMAFORGE_MAIN_BACKEND_SOCKET": "/tmp/nf-run/llm/backends/main.sock",
        }
        with patch.dict(os.environ, env, clear=False):
            p = NoemaForgePaths(platform=PLATFORM_LINUX)
            self.assertEqual(p.runtime_dir, Path("/tmp/nf-run"))
            self.assertEqual(p.bootstrap_dir, Path("/tmp/nf-bootstrap"))
            self.assertEqual(p.share_dir, Path("/tmp/nf-share"))
            self.assertEqual(p.modelstore_dir, Path("/tmp/nf-modelstore"))
            self.assertEqual(p.llm_gateway_socket, Path("/tmp/nf-run/llm/gateway.sock"))
            self.assertEqual(p.llm_main_backend_socket, Path("/tmp/nf-run/llm/backends/main.sock"))


class TestAsDictAndDetect(unittest.TestCase):
    """as_dict() and detect_platform() return expected shapes."""

    def test_as_dict_has_all_required_keys(self) -> None:
        p = NoemaForgePaths(platform=PLATFORM_LINUX)
        d = p.as_dict()
        for key in ("platform", "root", "data_root", "gui_state_dir",
                    "session_state_dir", "jobs_dir", "pipelines_dir",
                    "model_evolution_state_dir", "dev_team_state_dir",
                    "code_evolution_state_dir", "runtime_dir", "bootstrap_dir",
                    "share_dir", "modelstore_dir", "llm_gateway_socket",
                    "llm_main_backend_socket", "gui_listen_address"):
            with self.subTest(key=key):
                self.assertIn(key, d)

    def test_as_dict_values_are_strings(self) -> None:
        p = NoemaForgePaths(platform=PLATFORM_LINUX)
        d = p.as_dict()
        for key, val in d.items():
            if val is not None and key != "gui_listen_address":
                self.assertIsInstance(val, str, f"{key} should be str, got {type(val)}")

    def test_detect_platform_has_platform_key(self) -> None:
        info = NoemaForgePaths.detect_platform()
        self.assertIn("platform", info)
        self.assertIn(info["platform"], {PLATFORM_LINUX, PLATFORM_WINDOWS,
                                          PLATFORM_MACOS, PLATFORM_OTHER})

    def test_detect_platform_has_bool_flags(self) -> None:
        info = NoemaForgePaths.detect_platform()
        self.assertIn("is_linux", info)
        self.assertIn("is_windows", info)
        self.assertIn("is_macos", info)


class TestConfigFileSupport(unittest.TestCase):
    """Config file (noemaforge.conf) is read and takes precedence over defaults."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil; shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_conf(self, content: str) -> Path:
        p = Path(self._tmpdir) / "noemaforge.conf"
        p.write_text(content, encoding="utf-8")
        return p

    def test_config_file_root_overrides_platform_default(self) -> None:
        conf = self._write_conf(
            "[noemaforge]\ninstall_root = /custom/install\ndata_root = /custom/data\n"
        )
        with patch.dict(os.environ, {}, clear=True):
            p = NoemaForgePaths(platform=PLATFORM_LINUX, config_file=conf)
        self.assertEqual(p.root, Path("/custom/install"))
        self.assertEqual(p.data_root, Path("/custom/data"))

    def test_config_file_gui_address(self) -> None:
        conf = self._write_conf(
            "[noemaforge]\ninstall_root = /x\ndata_root = /y\n"
            "[gui]\nhost = 0.0.0.0\nport = 9999\n"
        )
        with patch.dict(os.environ, {}, clear=True):
            p = NoemaForgePaths(config_file=conf)
        host, port = p.gui_listen_address
        self.assertEqual(host, "0.0.0.0")
        self.assertEqual(port, 9999)

    def test_config_file_paths_section(self) -> None:
        conf = self._write_conf(
            "[noemaforge]\ninstall_root = /x\ndata_root = /y\n"
            "[paths]\njobs_dir = /custom/jobs\nbootstrap_dir = /custom/bootstrap\n"
        )
        with patch.dict(os.environ, {}, clear=True):
            p = NoemaForgePaths(config_file=conf)
        self.assertEqual(p.jobs_dir, Path("/custom/jobs"))
        self.assertEqual(p.bootstrap_dir, Path("/custom/bootstrap"))

    def test_env_var_overrides_config_file(self) -> None:
        conf = self._write_conf("[noemaforge]\ninstall_root = /config/root\ndata_root = /y\n")
        with patch.dict(os.environ, {"NOEMAFORGE_ROOT": "/env/root"}, clear=False):
            p = NoemaForgePaths(config_file=conf)
        self.assertEqual(p.root, Path("/env/root"))

    def test_config_file_used_property(self) -> None:
        conf = self._write_conf("[noemaforge]\ninstall_root = /x\ndata_root = /y\n")
        with patch.dict(os.environ, {}, clear=True):
            p = NoemaForgePaths(config_file=conf)
        self.assertEqual(p.config_file_used, conf)

    def test_no_config_file_config_file_used_is_none(self) -> None:
        with patch.dict(os.environ, {"NOEMAFORGE_CONFIG_FILE": "/does/not/exist.conf"}, clear=False):
            p = NoemaForgePaths(platform=PLATFORM_LINUX)
        # config file not found → None
        self.assertIsNone(p.config_file_used)

    def test_write_config_creates_valid_ini(self) -> None:
        from platform_paths import write_config
        import configparser
        dest = Path(self._tmpdir) / "noemaforge.conf"
        inst = Path(self._tmpdir) / "inst"
        data = Path(self._tmpdir) / "data"
        write_config(dest, inst, data)
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read(dest, encoding="utf-8")
        # Compare as Path objects so forward/backslash differences don't matter
        self.assertEqual(Path(cfg.get("noemaforge", "install_root")), inst)
        self.assertEqual(Path(cfg.get("noemaforge", "data_root")),    data)
        self.assertIn("jobs_dir", cfg.options("paths"))
        self.assertIn("sessions_dir", cfg.options("paths"))
        self.assertIn("runtime_dir", cfg.options("paths"))
        self.assertIn("bootstrap_dir", cfg.options("paths"))
        self.assertIn("share_dir", cfg.options("paths"))
        self.assertIn("modelstore_dir", cfg.options("paths"))

    def test_written_config_is_read_back_by_noemaforge_paths(self) -> None:
        from platform_paths import write_config
        dest = Path(self._tmpdir) / "noemaforge.conf"
        inst = Path(self._tmpdir) / "written_root"
        data = Path(self._tmpdir) / "written_data"
        write_config(dest, inst, data)
        with patch.dict(os.environ, {}, clear=True):
            p = NoemaForgePaths(config_file=dest)
        self.assertEqual(p.root,      inst)
        self.assertEqual(p.data_root, data)
        self.assertEqual(p.jobs_dir,  data / "gui" / "jobs")


class TestBackwardCompatShims(unittest.TestCase):
    """Module-level shim functions must return Path objects."""

    def test_get_root_returns_path(self) -> None:
        self.assertIsInstance(get_root(), Path)

    def test_get_data_root_returns_path(self) -> None:
        self.assertIsInstance(get_data_root(), Path)

    def test_get_gui_state_dir_returns_path(self) -> None:
        self.assertIsInstance(get_gui_state_dir(), Path)

    def test_get_jobs_dir_returns_path(self) -> None:
        self.assertIsInstance(get_jobs_dir(), Path)

    def test_default_paths_singleton_is_noemaforge_paths(self) -> None:
        self.assertIsInstance(DEFAULT_PATHS, NoemaForgePaths)


class TestAdminGuiServerImportsPlatformPaths(unittest.TestCase):
    """admin_gui_server.py must import from platform_paths instead of hardcoding."""

    def test_platform_paths_imported_in_admin_gui_server(self) -> None:
        src = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")
        self.assertIn("from platform_paths import", src,
                      "admin_gui_server.py must import from platform_paths")

    def test_no_hardcoded_opt_noemaforge_default(self) -> None:
        src = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")
        # Should not appear as a hardcoded string default anymore
        self.assertNotIn('"/opt/noemaforge"', src,
                         "admin_gui_server.py must not hardcode /opt/noemaforge")

    def test_default_constants_use_platform_paths(self) -> None:
        """DEFAULT_ROOT/DATA_ROOT must delegate to _platform_paths, not os.environ hardcodes."""
        src = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")
        # The old pattern was: Path(os.environ.get("...", "/var/lib/noemaforge/..."))
        # After migration the constants must not contain os.environ.get + /var/lib hardcode
        # Find DEFAULT_ROOT line and verify it uses platform_paths
        for line in src.splitlines():
            if "DEFAULT_ROOT" in line and "=" in line and "def " not in line:
                self.assertIn("_platform_paths", line,
                              f"DEFAULT_ROOT must use _platform_paths, got: {line.strip()}")
                break

    def test_admin_gui_bootstrap_and_modelstore_use_platform_paths(self) -> None:
        src = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")
        self.assertIn("DEFAULT_BOOTSTRAP_DIR = _platform_paths.bootstrap_dir", src)
        self.assertIn("DEFAULT_MODELSTORE_DIR = _platform_paths.modelstore_dir", src)
        self.assertNotIn('Path("/var/lib/noemaforge/bootstrap', src)
        self.assertNotIn('Path("/var/lib/modelstore', src)


if __name__ == "__main__":
    unittest.main()
