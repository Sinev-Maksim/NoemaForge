#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_machine_local_defaults_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate /etc/default/noemaforge-* machine-local override defaults.
Inputs: Workspace machine-local-defaults policy, examples, installer and systemd units.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import machine_local_defaults_runtime as mldr


class MachineLocalDefaultsRuntimeTests(unittest.TestCase):
    def test_workspace_machine_local_defaults_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "machine-local-defaults-policy.json"
        report = mldr.validate_machine_local_defaults_policy(
            mldr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["defaults"])
        self.assertEqual(3, report["metrics"]["valid_defaults"])
        self.assertEqual(6, report["metrics"]["services"])
        self.assertEqual(6, report["metrics"]["valid_services"])

    def test_runtime_example_preserves_single_llm_and_manual_heavy_defaults(self) -> None:
        text = (PROJECT_ROOT / "policies" / "noemaforge-runtime.example").read_text(encoding="utf-8")
        env = mldr.parse_default_env(text)

        self.assertEqual("/opt/noemaforge", env["NOEMAFORGE_ROOT"])
        self.assertEqual("/var/lib/noemaforge", env["NOEMAFORGE_STATE"])
        self.assertEqual("1", env["NOEMAFORGE_MAX_ACTIVE_LLMS"])
        self.assertEqual("manual_only", env["NOEMAFORGE_HEAVY_LLM_AUTOSTART"])
        self.assertTrue(env["NOEMAFORGE_GATEWAY_SOCKET"].startswith("/run/noemaforge/"))
        self.assertTrue(env["NOEMAFORGE_TOOLPROXY_SOCKET"].startswith("/run/noemaforge/"))

    def test_systemd_units_load_optional_machine_local_overrides(self) -> None:
        for service in [
            "noemaforge-toolproxy.service",
            "noemaforge-llm-gateway.service",
            "noemaforge-llama@.service",
            "noemaforge-memsentinel.service",
        ]:
            text = (PROJECT_ROOT / "systemd" / service).read_text(encoding="utf-8")
            self.assertIn("EnvironmentFile=-/etc/default/noemaforge-runtime", text, service)

        for service in ["noemaforge-autostart-gui.service", "noemaforge-autostart-wogui.service"]:
            text = (PROJECT_ROOT / "systemd" / service).read_text(encoding="utf-8")
            self.assertIn("EnvironmentFile=-/etc/default/noemaforge-runtime", text, service)
            self.assertIn("EnvironmentFile=-/etc/default/noemaforge-firstboot", text, service)

    def test_installer_installs_default_examples_without_overwriting_local_files(self) -> None:
        installer = (PROJECT_ROOT / "install_noemaforge_0.31.21.alpha_mvp.sh").read_text(encoding="utf-8")
        self.assertIn("install_default_once()", installer)
        self.assertIn('[[ -e "$(target "$rel")" ]] && return 0', installer)
        self.assertIn("/etc/default/noemaforge-recovery", installer)
        self.assertIn("/etc/default/noemaforge-runtime", installer)
        self.assertIn("/etc/default/noemaforge-firstboot", installer)
        self.assertIn('install_default_once "$PKG_DIR/policies/${default_name}.example" "/etc/default/$default_name" 0644', installer)


if __name__ == "__main__":
    unittest.main()
