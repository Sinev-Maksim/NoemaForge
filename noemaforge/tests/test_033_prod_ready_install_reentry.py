#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent


class ProdReadyInstallReentryTests(unittest.TestCase):
    def test_installer_normalizes_opt_payload_modes_in_rootfs_install(self) -> None:
        script = PROJECT_ROOT / "install_noemaforge_mvp.sh"
        with tempfile.TemporaryDirectory(prefix="noemaforge-rootfs-") as rootfs:
            existing_opt = Path(rootfs) / "opt" / "noemaforge"
            existing_opt.mkdir(parents=True)
            (existing_opt / "existing-symlink").symlink_to("bin/noemaforge")
            result = subprocess.run(
                [str(script), "--rootfs", rootfs, "--with-share", "/mnt/noemaforge-share"],
                cwd=str(PROJECT_ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=60,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            opt_root = Path(rootfs) / "opt" / "noemaforge"
            manifest = opt_root / "tools" / "prep" / "executable_manifest.txt"
            self.assertTrue(manifest.exists())
            for rel in manifest.read_text(encoding="utf-8").splitlines():
                rel = rel.split("#", 1)[0].strip()
                if not rel.startswith("noemaforge/"):
                    continue
                target = opt_root / rel.removeprefix("noemaforge/")
                self.assertTrue(target.exists(), rel)
                self.assertTrue(os.access(target, os.X_OK), rel)
            group_writable = [
                str(path.relative_to(opt_root))
                for path in opt_root.rglob("*")
                if not path.is_symlink()
                and (path.is_file() or path.is_dir())
                and (path.stat().st_mode & stat.S_IWGRP)
            ]
            self.assertEqual([], group_writable[:10])
            self.assertTrue((opt_root / "existing-symlink").is_symlink())

    def test_safe_start_does_not_enable_units_without_persist_flag(self) -> None:
        script = ROOT / "tools" / "ops" / "noemaforge-op-safe-start.sh"
        text = script.read_text(encoding="utf-8")
        self.assertIn("--persist-services", text)
        self.assertIn("starting safe core without changing persistent unit enablement", text)
        self.assertNotIn("systemctl disable \"$MAIN_UNIT\"", text)
        self.assertNotIn("systemctl disable --now noemaforge-llm-backends-manager.timer", text)

    def test_smoke_runtime_only_classifies_backend_as_expected_skip(self) -> None:
        script = ROOT / "tools" / "ops" / "noemaforge-op-smoke.sh"
        text = script.read_text(encoding="utf-8")
        self.assertIn("--profile runtime_only", text)
        self.assertIn("--profile requires a value", text)
        self.assertIn("skipped_expected_runtime_only", text)
        self.assertIn("main backend intentionally absent for runtime_only profile", text)
        env = os.environ.copy()
        env["NOEMAFORGE_ROOT"] = str(ROOT)
        help_result = subprocess.run(
            [str(ROOT / "bin" / "noemaforge"), "smoke", "--help"],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        self.assertIn("--profile runtime_only", help_result.stdout)

    def test_mvp_smoke_failure_records_have_artifact_metadata(self) -> None:
        script = ROOT / "tools" / "prep" / "noemaforge-mvp-smoke.sh"
        text = script.read_text(encoding="utf-8")
        self.assertIn("CHECKS_DIR=\"$STATE/checks\"", text)
        self.assertIn("stdout_path", text)
        self.assertIn("stderr_path", text)
        self.assertIn("report_path", text)
        self.assertIn("pipeline validate --json", text)
        self.assertIn("--allow-degraded", text)

    def test_systemd_surface_is_current_versioned_and_hotfix_cleanup_is_installed(self) -> None:
        stale = []
        for path in (ROOT / "systemd").rglob("*"):
            if path.is_file() and path.suffix in {".service", ".timer", ".conf"}:
                text = path.read_text(encoding="utf-8")
                if "# Version: 0.32.1" in text:
                    stale.append(str(path.relative_to(ROOT)))
        self.assertEqual([], stale)
        installer = (PROJECT_ROOT / "install_noemaforge_mvp.sh").read_text(encoding="utf-8")
        self.assertIn("remove_stale_hotfix_dropins", installer)
        self.assertIn("-name '*hotfix*' -delete", installer)

    def test_media_team_is_defined_for_media_catalog_entries(self) -> None:
        teams = json.loads((ROOT / "configs" / "pipeline-teams.json").read_text(encoding="utf-8"))
        self.assertIn("media_team", teams)
        self.assertIn("privacy_reviewer", teams["media_team"]["roles"])


if __name__ == "__main__":
    unittest.main()
