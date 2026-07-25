#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_systemd_socket_cleanup.py
Zone: release/package
Version: 0.33.0
Created: 2026-07-25
Modified: 2026-07-25
Purpose: Verify that systemd service units have ExecStopPost directives to remove
         stale Unix socket files after service shutdown.
Inputs: Systemd unit files from noemaforge/systemd/ directory.
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
sys.path.insert(0, str(ROOT / "src"))


class SystemdSocketCleanupTests(unittest.TestCase):
    def test_toolproxy_service_has_execstoppost_for_socket_cleanup(self) -> None:
        """Verify noemaforge-toolproxy.service removes its socket on stop."""
        service_file = ROOT / "systemd" / "noemaforge-toolproxy.service"
        self.assertTrue(service_file.exists(), f"Service file not found: {service_file}")

        content = service_file.read_text(encoding="utf-8")
        self.assertIn("ExecStopPost=-/bin/rm -f /run/noemaforge/toolproxy.sock", content,
                      "ExecStopPost directive for toolproxy.sock not found in service file")

    def test_llm_gateway_service_has_execstoppost_for_socket_cleanup(self) -> None:
        """Verify noemaforge-llm-gateway.service removes its socket on stop."""
        service_file = ROOT / "systemd" / "noemaforge-llm-gateway.service"
        self.assertTrue(service_file.exists(), f"Service file not found: {service_file}")

        content = service_file.read_text(encoding="utf-8")
        self.assertIn("ExecStopPost=-/bin/rm -f /run/noemaforge/llm/gateway.sock", content,
                      "ExecStopPost directive for gateway.sock not found in service file")

    def test_socket_cleanup_is_in_service_section(self) -> None:
        """Verify ExecStopPost directives are in the [Service] section."""
        toolproxy_file = ROOT / "systemd" / "noemaforge-toolproxy.service"
        gateway_file = ROOT / "systemd" / "noemaforge-llm-gateway.service"

        for service_file in [toolproxy_file, gateway_file]:
            content = service_file.read_text(encoding="utf-8")
            lines = content.split("\n")

            in_service_section = False
            found_execstoppost = False
            for i, line in enumerate(lines):
                if line.strip() == "[Service]":
                    in_service_section = True
                elif line.strip().startswith("[") and line.strip() != "[Service]":
                    in_service_section = False

                if in_service_section and line.strip().startswith("ExecStopPost="):
                    found_execstoppost = True
                    break

            self.assertTrue(found_execstoppost,
                          f"ExecStopPost not found in [Service] section of {service_file.name}")

    def test_socket_cleanup_uses_nonzero_exit_tolerant_prefix(self) -> None:
        """Verify ExecStopPost uses '-' prefix for non-fatal exit handling."""
        toolproxy_file = ROOT / "systemd" / "noemaforge-toolproxy.service"
        gateway_file = ROOT / "systemd" / "noemaforge-llm-gateway.service"

        for service_file in [toolproxy_file, gateway_file]:
            content = service_file.read_text(encoding="utf-8")
            lines = content.split("\n")

            for line in lines:
                if line.strip().startswith("ExecStopPost="):
                    # The line should be of the form: ExecStopPost=-/bin/rm -f /path/to/socket
                    self.assertTrue(line.strip().startswith("ExecStopPost=-"),
                                  f"ExecStopPost in {service_file.name} should start with '-' prefix for non-fatal handling")
                    break


if __name__ == "__main__":
    unittest.main()
