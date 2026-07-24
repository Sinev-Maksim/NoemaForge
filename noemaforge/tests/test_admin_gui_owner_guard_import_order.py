#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_gui_owner_guard_import_order.py
Zone: tests
Version: 0.33.0
Created: 2026-07-24
Modified: 2026-07-24
Purpose: Prove fresh-process owner-guard installation, source-to-policy coverage and package-root code-evolution layout handling.
Inputs: Admin GUI server source, mutation policy and temporary isolated package/state directories.
Outputs: unittest assertions only.
Side effects: Temporary local files and one ephemeral loopback listening socket closed during the test.
Tests: direct unittest execution from the premerge quality workflow.
Notes: A subprocess is required because in-process imports would hide the real production import order.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# Imported TestCase classes are intentionally included by unittest.main() when
# this executable regression module is loaded by the premerge workflow.
from test_code_evolution_layout import CodeEvolutionLayoutTests  # noqa: E402,F401


class AdminGuiOwnerGuardImportOrderTests(unittest.TestCase):
    def test_fresh_admin_gui_server_uses_guarded_base_and_handler(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            package_root = temp / "package"
            ui = package_root / "templates" / "pipeline-dashboard"
            ui.mkdir(parents=True)
            (ui / "index.html").write_text("<!doctype html><title>test</title>", encoding="utf-8")
            data_root = temp / "data"
            states = [temp / name for name in ("pipelines", "personas", "evolution", "selection", "dev")]
            for path in states:
                path.mkdir(parents=True)

            script = textwrap.dedent(
                f"""
                from pathlib import Path
                import http.server
                import admin_gui_server as gui

                root = Path({str(package_root)!r})
                data = Path({str(data_root)!r})
                state_paths = {[str(path) for path in states]!r}
                gui.DEFAULT_DATA_ROOT = data

                assert getattr(gui.ThreadingHTTPServer, '_noemaforge_owner_guarded_base', False)
                assert getattr(http.server.ThreadingHTTPServer, '_noemaforge_owner_guarded_base', False)
                assert issubclass(gui.AdminGuiServer, gui.ThreadingHTTPServer)

                server = gui.AdminGuiServer(
                    ('127.0.0.1', 0),
                    root,
                    *(Path(item) for item in state_paths),
                )
                try:
                    assert getattr(server.RequestHandlerClass, '_noemaforge_owner_guard_installed', False)
                    assert callable(getattr(server.RequestHandlerClass, '_noemaforge_owner_guard_original_do_post', None))
                finally:
                    server.server_close()
                """
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC)
            env["PYTHONPYCACHEPREFIX"] = str(temp / "pycache")
            result = subprocess.run(
                [sys.executable, "-W", "error::ResourceWarning", "-c", script],
                cwd=str(ROOT.parent),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(
                0,
                result.returncode,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )

    def test_inline_post_branches_are_present_in_mutation_inventory(self) -> None:
        source = (SRC / "admin_gui_server.py").read_text(encoding="utf-8")
        post_start = source.index("    def do_POST")
        post_end = source.index("    def _serve_static", post_start)
        post_source = source[post_start:post_end]

        exact_routes = set(
            re.findall(r'(?:if|elif) path == "([^"]+)"', post_source)
        )
        prefix_routes = set(
            re.findall(
                r'if path\.startswith\("([^"]+)"\) and path\.endswith\("([^"]+)"\)',
                post_source,
            )
        )
        policy = json.loads(
            (ROOT / "configs" / "admin-gui-mutation-policy.json").read_text(encoding="utf-8")
        )["policy"]
        owner_exact = set(policy["owner_required_exact_routes"])
        owner_prefix = {
            (item["prefix"], item["suffix"])
            for item in policy["owner_required_prefix_routes"]
        }

        self.assertEqual({"/api/session/mode", "/api/shutdown"}, exact_routes)
        self.assertTrue(exact_routes.issubset(owner_exact))
        self.assertEqual(prefix_routes, owner_prefix)


if __name__ == "__main__":
    unittest.main()
