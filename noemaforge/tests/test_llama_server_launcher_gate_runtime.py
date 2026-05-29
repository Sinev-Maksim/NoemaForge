#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_llama_server_launcher_gate_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate launcher-side llama-server binary/shared-library gate.
Inputs: Workspace llama-server-launcher-gate policy and prep scripts.
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

import llama_server_launcher_gate_runtime as lsg


class LlamaServerLauncherGateRuntimeTests(unittest.TestCase):
    def test_workspace_llama_server_launcher_gate_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "llama-server-launcher-gate-policy.json"
        report = lsg.validate_llama_server_launcher_gate_policy(
            lsg.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["script_reports"])
        self.assertEqual(3, report["metrics"]["valid_script_reports"])
        self.assertEqual(3, report["metrics"]["preflight_checks"])

    def test_ldd_output_classifier_blocks_unresolved_libraries(self) -> None:
        ok = lsg.classify_ldd_output("linux-vdso.so.1\nlibc.so.6 => /lib/libc.so.6", rc=0)
        missing = lsg.classify_ldd_output("libcuda.so.1 => not found\nlibm.so.6 => /lib/libm.so.6", rc=0)
        static = lsg.classify_ldd_output("not a dynamic executable", rc=1)
        failed = lsg.classify_ldd_output("permission denied", rc=1)

        self.assertTrue(ok["ok"])
        self.assertFalse(missing["ok"])
        self.assertEqual("unresolved_libraries", missing["status"])
        self.assertIn("libcuda.so.1 => not found", missing["missing"])
        self.assertTrue(static["ok"])
        self.assertFalse(failed["ok"])

    def test_first_launch_and_gui_prepare_gate_before_model_discovery(self) -> None:
        for path in [
            ROOT / "tools" / "prep" / "noemaforge-first-launch.sh",
            ROOT / "tools" / "prep" / "noemaforge-gui-prepare.sh",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("validate_llama_server_runtime()", text, str(path))
            self.assertIn("command -v ldd", text, str(path))
            self.assertIn("grep -q 'not found'", text, str(path))
            self.assertIn("llama-server binary/shared-library gate passed", text, str(path))
            self.assertLess(text.index("ensure_llama_server"), text.index("safe_model_discovery"), str(path))

    def test_trixie_preflight_keeps_readonly_llama_checks(self) -> None:
        text = (ROOT / "tools" / "prep" / "noemaforge-trixie-preflight.sh").read_text(encoding="utf-8")
        self.assertIn("check llama_start", text)
        self.assertIn("check llama_server", text)
        self.assertIn("check llama_libs", text)
        self.assertIn('ldd "$LLAMA_BIN"', text)


if __name__ == "__main__":
    unittest.main()
