#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_multios_runtime_contract.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate MultiOS runtime host/control contracts and smoke probes.
Inputs: Workspace MultiOS runtime policy and temporary broken fixtures.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

import multios_runtime_contract as mrc
import production_ai_contracts as pac
from noemaforge.runtime.connectors.remote_http import RemoteHTTPRuntimeConnector
from noemaforge.runtime.hardware_probe import detect_hardware
from noemaforge.runtime.os_probe import detect_os
from noemaforge.runtime.registry import load_runtime_policy, profile_by_id
from noemaforge.runtime.selector import select_runtime_profile


class MultiOSRuntimeContractTests(unittest.TestCase):
    def test_workspace_multios_runtime_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "noemaforge.runtime.yaml"
        report = mrc.validate_multios_runtime_policy(
            load_runtime_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(4, report["metrics"]["profiles"])
        self.assertEqual(4, report["metrics"]["passing_profiles"])
        self.assertEqual(1, report["metrics"]["linux_profiles"])
        self.assertEqual(1, report["metrics"]["windows_profiles"])
        self.assertEqual(1, report["metrics"]["macos_profiles"])
        self.assertEqual(1, report["metrics"]["remote_profiles"])
        self.assertEqual(1, report["metrics"]["required_for_first_start_profiles"])
        self.assertEqual(0, report["metrics"]["heavy_local_non_linux_profiles"])
        self.assertEqual(0, report["metrics"]["missing_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "multios-runtime-host-core", "domain": "pipeline"},
            mrc.multios_runtime_report_to_gate_evidence(report, artifact_uri="reports/multios-runtime.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_host_detection_smoke_selects_expected_profiles(self) -> None:
        policy = load_runtime_policy(ROOT / "configs" / "noemaforge.runtime.yaml")

        linux = detect_os(system="Linux", release="6.1", machine="x86_64")
        linux_selection = select_runtime_profile(
            policy,
            host_os_report=linux,
            hardware_report=detect_hardware(machine="x86_64", memory_total_mb=32768, gpu="nvidia"),
        )
        self.assertEqual("linux-reference-systemd", linux_selection["selected_profile_id"])
        self.assertEqual("enabled_exact", linux_selection["mode"])

        windows = detect_os(system="Windows", release="11", machine="AMD64")
        windows_selection = select_runtime_profile(
            policy,
            host_os_report=windows,
            hardware_report=detect_hardware(machine="AMD64", memory_total_mb=16384),
        )
        self.assertEqual("windows-control-host", windows_selection["selected_profile_id"])
        self.assertEqual("control_only", windows_selection["mode"])

        macos = detect_os(system="Darwin", release="23", machine="arm64")
        macos_selection = select_runtime_profile(
            policy,
            host_os_report=macos,
            hardware_report=detect_hardware(machine="arm64", processor="Apple M2", memory_total_mb=24576),
        )
        self.assertEqual("macos-control-host", macos_selection["selected_profile_id"])
        self.assertEqual("control_only", macos_selection["mode"])

    def test_remote_http_connector_is_offline_by_default(self) -> None:
        policy = load_runtime_policy(ROOT / "configs" / "noemaforge.runtime.yaml")
        profile = profile_by_id(policy, "remote-http-runtime")
        self.assertIsNotNone(profile)
        health = RemoteHTTPRuntimeConnector(profile).health()
        self.assertFalse(health["ok"])
        self.assertEqual("disabled_by_default", health["status"])
        self.assertEqual("offline_contract", health["mode"])
        self.assertEqual("skipped", health["checks"][0]["status"])

    def test_invalid_host_paths_and_dependencies_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "noemaforge.runtime.yaml"
        payload = copy.deepcopy(load_runtime_policy(policy_path))
        for profile in payload["profiles"]:
            if profile["id"] == "windows-control-host":
                profile["enabled"] = True
                profile["required_for_first_start"] = True
                profile["allow_heavy_local_inference"] = True
            if profile["id"] == "macos-control-host":
                profile["connector"] = "local_mlx"
            if profile["id"] == "remote-http-runtime":
                profile["enabled"] = True
                profile["live_network_check_default"] = True
                profile["health_report_required"] = False
            if profile["id"] == "linux-reference-systemd":
                profile["launcher"] = "new_launcher"

        report = mrc.validate_multios_runtime_policy(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("host_control_enabled_by_default:windows-control-host", report["failures"])
        self.assertIn("profile_non_linux_required_for_first_start:windows-control-host", report["failures"])
        self.assertIn("host_control_allows_heavy_local_inference:windows-control-host", report["failures"])
        self.assertIn("host_control_connector_not_remote_http:macos-control-host:local_mlx", report["failures"])
        self.assertIn("remote_http_enabled_by_default:remote-http-runtime", report["failures"])
        self.assertIn("remote_live_network_check_enabled:remote-http-runtime", report["failures"])
        self.assertIn("remote_health_report_not_required:remote-http-runtime", report["failures"])
        self.assertIn("linux_launcher_not_systemd_existing:linux-reference-systemd", report["failures"])


if __name__ == "__main__":
    unittest.main()
