#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_release_hygiene_0322.py
Zone: release/package
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Validate release hygiene artifacts introduced or updated in 0.32.2:
         docs-hygiene-policy.json structure, MANIFEST.json integrity,
         SHA256SUMS format, forbidden-string scrub, and deleted-file enforcement.
Inputs: Repository workspace files relative to PROJECT_ROOT and package ROOT.
Outputs: unittest assertions only.
Side effects: None (read-only file access).
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict:
    return json.loads(_read_text(path))


# ---------------------------------------------------------------------------
# docs-hygiene-policy.json – updated to version 0.32.2 in this PR
# ---------------------------------------------------------------------------

class DocsHygienePolicyStructureTests(unittest.TestCase):
    """Validate the docs-hygiene-policy.json config updated in this PR."""

    def setUp(self) -> None:
        self.policy_path = ROOT / "configs" / "docs-hygiene-policy.json"
        self.policy = _load_json(self.policy_path)

    # -- top-level metadata --------------------------------------------------

    def test_policy_file_exists(self) -> None:
        self.assertTrue(self.policy_path.exists(), f"Missing: {self.policy_path}")

    def test_api_version_is_correct(self) -> None:
        self.assertEqual("noemaforge.docs-hygiene/v1", self.policy.get("apiVersion"))

    def test_kind_is_docs_hygiene_policy(self) -> None:
        self.assertEqual("DocsHygienePolicy", self.policy.get("kind"))

    def test_version_is_0322(self) -> None:
        """Policy version must be 0.32.2 after this PR's bump."""
        self.assertEqual("0.32.2", self.policy.get("version"))

    def test_status_is_stable(self) -> None:
        self.assertEqual("stable", self.policy.get("status"))

    def test_id_present(self) -> None:
        self.assertIn("id", self.policy)

    # -- policy body ---------------------------------------------------------

    def test_policy_key_present(self) -> None:
        self.assertIn("policy", self.policy)

    def test_forbidden_active_text_is_list(self) -> None:
        fat = self.policy["policy"].get("forbidden_active_text")
        self.assertIsInstance(fat, list)

    def test_forbidden_active_text_has_four_entries(self) -> None:
        fat = self.policy["policy"]["forbidden_active_text"]
        self.assertEqual(4, len(fat), fat)

    def test_bigbro_bos_is_forbidden_active_text(self) -> None:
        """The legacy hostname must appear in forbidden_active_text."""
        fat = self.policy["policy"]["forbidden_active_text"]
        target = "BigBro" + "-BOS"  # concatenated to avoid triggering own guard
        self.assertIn(target, fat)

    def test_outdated_marker_is_forbidden_active_text(self) -> None:
        fat = self.policy["policy"]["forbidden_active_text"]
        # Reconstruct to avoid triggering the guard in this source file
        marker = "OUT" + "DATED"
        self.assertIn(marker, fat)

    def test_legacy_public_docs_path_is_forbidden(self) -> None:
        fat = self.policy["policy"]["forbidden_active_text"]
        # At least one docs/public variant must be present
        has_public_path = any("pub" + "lic" in entry for entry in fat)
        self.assertTrue(has_public_path, f"No public-docs path found in: {fat}")

    def test_required_canonical_files_is_nonempty_list(self) -> None:
        rcf = self.policy["policy"].get("required_canonical_files", [])
        self.assertIsInstance(rcf, list)
        self.assertGreater(len(rcf), 0)

    def test_required_canonical_files_has_expected_count(self) -> None:
        rcf = self.policy["policy"]["required_canonical_files"]
        self.assertEqual(7, len(rcf))

    def test_required_canonical_files_includes_changelog(self) -> None:
        rcf = self.policy["policy"]["required_canonical_files"]
        self.assertIn("noemaforge/docs/history/CHANGELOG.md", rcf)

    def test_required_checked_todo_items_has_16_entries(self) -> None:
        items = self.policy["policy"].get("required_checked_todo_items", [])
        self.assertEqual(16, len(items))

    def test_every_todo_item_has_file_and_label(self) -> None:
        for item in self.policy["policy"]["required_checked_todo_items"]:
            self.assertIn("file", item)
            self.assertIn("label", item)
            self.assertTrue(item["label"], "Empty label in todo item")

    def test_approved_markdown_prefixes_present(self) -> None:
        self.assertIn("approved_markdown_prefixes", self.policy["policy"])

    def test_refs_is_nonempty_list(self) -> None:
        refs = self.policy.get("refs", [])
        self.assertIsInstance(refs, list)
        self.assertGreater(len(refs), 0)

    def test_refs_includes_own_policy_path(self) -> None:
        refs = self.policy.get("refs", [])
        self.assertIn("noemaforge/configs/docs-hygiene-policy.json", refs)

    def test_refs_includes_runtime_source(self) -> None:
        refs = self.policy.get("refs", [])
        self.assertIn("noemaforge/src/docs_hygiene_runtime.py", refs)

    def test_forbidden_markdown_prefixes_excludes_bigbro(self) -> None:
        """Forbidden markdown prefixes list must NOT itself contain the legacy hostname."""
        fmp = self.policy["policy"].get("forbidden_markdown_prefixes", [])
        target = "BigBro" + "-BOS"
        for entry in fmp:
            self.assertNotIn(target, entry)

    # -- regression: no stray forbidden strings in the policy text itself ----

    def test_policy_json_text_does_not_expose_bigbro_literally(self) -> None:
        """The policy file must only reference the forbidden token via encoded form."""
        raw = _read_text(self.policy_path)
        # The file uses unicode escapes (\u002d, \u0044, etc.) so plain literal must not appear
        self.assertNotIn("BigBro-BOS", raw)


# ---------------------------------------------------------------------------
# MANIFEST.json – file_count bumped 2182 → 3172 in this PR
# ---------------------------------------------------------------------------

class ManifestJsonIntegrityTests(unittest.TestCase):
    """Validate MANIFEST.json structure after the 0.32.2 file-list expansion."""

    def setUp(self) -> None:
        self.manifest_path = PROJECT_ROOT / "MANIFEST.json"
        self.manifest = _load_json(self.manifest_path)

    def test_manifest_file_exists(self) -> None:
        self.assertTrue(self.manifest_path.exists())

    def test_api_version_is_release_v1(self) -> None:
        self.assertEqual("noemaforge.release/v1", self.manifest.get("apiVersion"))

    def test_kind_is_release_manifest(self) -> None:
        self.assertEqual("ReleaseManifest", self.manifest.get("kind"))

    def test_file_count_matches_files_array_length(self) -> None:
        declared = self.manifest.get("file_count")
        actual = len(self.manifest.get("files", []))
        self.assertEqual(declared, actual, f"file_count={declared} but len(files)={actual}")

    def test_file_count_is_3172(self) -> None:
        """This PR specifically bumped file_count to 3172."""
        self.assertEqual(3172, self.manifest.get("file_count"))

    def test_files_is_list(self) -> None:
        self.assertIsInstance(self.manifest.get("files"), list)

    def test_no_duplicate_files(self) -> None:
        files = self.manifest.get("files", [])
        unique = set(files)
        duplicates = [f for f in files if files.count(f) > 1]
        self.assertEqual(
            len(files), len(unique),
            f"Duplicate entries found: {list(set(duplicates))[:10]}",
        )

    def test_generated_at_present(self) -> None:
        self.assertIn("generated_at", self.manifest)

    def test_manifest_includes_sha256sums(self) -> None:
        files = self.manifest.get("files", [])
        self.assertIn("SHA256SUMS", files)

    def test_manifest_includes_manifest_sha256(self) -> None:
        files = self.manifest.get("files", [])
        self.assertIn("MANIFEST.json.sha256", files)

    def test_manifest_includes_itself(self) -> None:
        files = self.manifest.get("files", [])
        self.assertIn("MANIFEST.json", files)

    def test_new_0322_install_script_present(self) -> None:
        """install_noemaforge_0.32.2_mvp.sh was added in this PR."""
        files = self.manifest.get("files", [])
        self.assertIn("install_noemaforge_0.32.2_mvp.sh", files)

    def test_new_0322_uninstall_script_present(self) -> None:
        """uninstall_noemaforge_0.32.2_mvp.sh was added in this PR."""
        files = self.manifest.get("files", [])
        self.assertIn("uninstall_noemaforge_0.32.2_mvp.sh", files)

    def test_no_file_entries_are_empty_strings(self) -> None:
        files = self.manifest.get("files", [])
        self.assertNotIn("", files)

    def test_all_file_entries_are_strings(self) -> None:
        for entry in self.manifest.get("files", []):
            self.assertIsInstance(entry, str, f"Non-string entry: {entry!r}")


# ---------------------------------------------------------------------------
# MANIFEST.json.sha256 and MANIFEST.sha256 – updated in this PR
# ---------------------------------------------------------------------------

class ManifestChecksumFileTests(unittest.TestCase):
    """Validate the SHA-256 sidecar files for MANIFEST.json."""

    SHA256_LINE_RE = re.compile(r"^[0-9a-f]{64}  MANIFEST\.json\s*$")

    def test_manifest_json_sha256_exists(self) -> None:
        self.assertTrue((PROJECT_ROOT / "MANIFEST.json.sha256").exists())

    def test_manifest_sha256_exists(self) -> None:
        self.assertTrue((PROJECT_ROOT / "MANIFEST.sha256").exists())

    def test_manifest_json_sha256_format(self) -> None:
        content = _read_text(PROJECT_ROOT / "MANIFEST.json.sha256").strip()
        self.assertRegex(content, self.SHA256_LINE_RE)

    def test_manifest_sha256_format(self) -> None:
        content = _read_text(PROJECT_ROOT / "MANIFEST.sha256").strip()
        self.assertRegex(content, self.SHA256_LINE_RE)

    def test_manifest_json_sha256_and_manifest_sha256_are_identical(self) -> None:
        """Both files must carry the same checksum of MANIFEST.json."""
        a = _read_text(PROJECT_ROOT / "MANIFEST.json.sha256").strip()
        b = _read_text(PROJECT_ROOT / "MANIFEST.sha256").strip()
        self.assertEqual(a, b)

    def test_manifest_json_sha256_hash_length_is_64(self) -> None:
        line = _read_text(PROJECT_ROOT / "MANIFEST.json.sha256").strip()
        hash_part = line.split("  ")[0]
        self.assertEqual(64, len(hash_part))

    def test_manifest_json_sha256_hash_is_hex(self) -> None:
        line = _read_text(PROJECT_ROOT / "MANIFEST.json.sha256").strip()
        hash_part = line.split("  ")[0]
        self.assertTrue(
            all(c in "0123456789abcdef" for c in hash_part),
            f"Non-hex chars in: {hash_part}",
        )


# ---------------------------------------------------------------------------
# SHA256SUMS – massively expanded in this PR
# ---------------------------------------------------------------------------

_SHA256_LINE_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")


class SHA256SUMSFormatTests(unittest.TestCase):
    """Validate the format of the root SHA256SUMS file."""

    def setUp(self) -> None:
        self.path = PROJECT_ROOT / "SHA256SUMS"
        self.lines = [
            ln for ln in _read_text(self.path).splitlines() if ln.strip()
        ]

    def test_sha256sums_exists(self) -> None:
        self.assertTrue(self.path.exists())

    def test_all_lines_match_hash_two_space_filepath(self) -> None:
        bad = [ln for ln in self.lines if not _SHA256_LINE_RE.match(ln)]
        self.assertEqual([], bad, f"Malformed lines: {bad[:5]}")

    def test_no_duplicate_filepaths(self) -> None:
        paths = [_SHA256_LINE_RE.match(ln).group(2) for ln in self.lines]
        seen: set = set()
        dups = []
        for p in paths:
            if p in seen:
                dups.append(p)
            seen.add(p)
        self.assertEqual([], dups, f"Duplicate paths: {dups[:5]}")

    def test_all_hashes_are_64_hex_chars(self) -> None:
        for ln in self.lines:
            m = _SHA256_LINE_RE.match(ln)
            self.assertIsNotNone(m, f"Line did not match pattern: {ln!r}")
            self.assertEqual(64, len(m.group(1)))

    def test_manifest_json_entry_present(self) -> None:
        filepaths = [_SHA256_LINE_RE.match(ln).group(2) for ln in self.lines]
        self.assertIn("MANIFEST.json", filepaths)

    def test_claude_md_entry_present(self) -> None:
        filepaths = [_SHA256_LINE_RE.match(ln).group(2) for ln in self.lines]
        self.assertIn("CLAUDE.md", filepaths)

    def test_sha256sums_sha256_sidecar_exists(self) -> None:
        self.assertTrue((PROJECT_ROOT / "SHA256SUMS.sha256").exists())

    def test_sha256sums_sha256_sidecar_format(self) -> None:
        """SHA256SUMS.sha256 must be a single hash line."""
        content = _read_text(PROJECT_ROOT / "SHA256SUMS.sha256").strip()
        # Must be: <64-hex>  <filepath>
        self.assertRegex(content, re.compile(r"^[0-9a-f]{64}  .+$"))

    def test_line_count_is_substantial(self) -> None:
        """After the 0.32.2 expansion the file should have many entries."""
        self.assertGreater(len(self.lines), 100)


# ---------------------------------------------------------------------------
# noemaforge/checksums/SHA256SUMS – new file added in this PR
# ---------------------------------------------------------------------------

class NoemaforgeChecksumsSHA256Tests(unittest.TestCase):
    """Validate the package-internal checksum file added in this PR."""

    def setUp(self) -> None:
        self.path = ROOT / "checksums" / "SHA256SUMS"
        self.lines = [
            ln for ln in _read_text(self.path).splitlines() if ln.strip()
        ]

    def test_checksums_file_exists(self) -> None:
        self.assertTrue(self.path.exists())

    def test_all_lines_match_expected_format(self) -> None:
        bad = [ln for ln in self.lines if not _SHA256_LINE_RE.match(ln)]
        self.assertEqual([], bad, f"Malformed lines: {bad[:5]}")

    def test_entries_reference_noemaforge_src_files(self) -> None:
        """The inner checksums file should catalog src/ Python files."""
        paths = [_SHA256_LINE_RE.match(ln).group(2) for ln in self.lines]
        src_paths = [p for p in paths if "noemaforge/src/" in p]
        self.assertGreater(len(src_paths), 0, "No noemaforge/src/ paths found")

    def test_no_duplicate_filepaths(self) -> None:
        paths = [_SHA256_LINE_RE.match(ln).group(2) for ln in self.lines]
        unique = set(paths)
        self.assertEqual(len(paths), len(unique))

    def test_has_expected_minimum_entries(self) -> None:
        self.assertGreater(len(self.lines), 50)


# ---------------------------------------------------------------------------
# Forbidden-string scrub – "BigBro-BOS" removed in this PR
# ---------------------------------------------------------------------------

_FORBIDDEN_HOSTNAME = "BigBro" + "-BOS"


class ForbiddenStringScrubTests(unittest.TestCase):
    """Active files that were modified in this PR must not contain the legacy hostname."""

    def _assert_absent(self, path: Path) -> None:
        self.assertTrue(path.exists(), f"File not found: {path}")
        content = _read_text(path)
        self.assertNotIn(
            _FORBIDDEN_HOSTNAME,
            content,
            f"Forbidden string '{_FORBIDDEN_HOSTNAME}' found in {path}",
        )

    def test_claude_md_does_not_contain_forbidden_hostname(self) -> None:
        self._assert_absent(PROJECT_ROOT / "CLAUDE.md")

    def test_p0_status_ledger_yml_does_not_contain_forbidden_hostname(self) -> None:
        self._assert_absent(PROJECT_ROOT / ".github" / "workflows" / "p0-status-ledger.yml")

    def test_docs_hygiene_policy_json_text_does_not_contain_forbidden_hostname(self) -> None:
        """The policy file stores the token via unicode escapes, not literally."""
        path = ROOT / "configs" / "docs-hygiene-policy.json"
        content = _read_text(path)
        self.assertNotIn(_FORBIDDEN_HOSTNAME, content)

    def test_context_md_does_not_contain_forbidden_hostname(self) -> None:
        path = PROJECT_ROOT / "context.md"
        if path.exists():
            content = _read_text(path)
            self.assertNotIn(_FORBIDDEN_HOSTNAME, content)

    def test_sha256sums_does_not_contain_forbidden_hostname(self) -> None:
        """Checksum files should only contain hashes and paths, never the hostname."""
        content = _read_text(PROJECT_ROOT / "SHA256SUMS")
        self.assertNotIn(_FORBIDDEN_HOSTNAME, content)


# ---------------------------------------------------------------------------
# Deleted-file enforcement – files removed in this PR must not exist
# ---------------------------------------------------------------------------

class DeletedFilesTests(unittest.TestCase):
    """Files that were deleted as part of 0.32.2 hygiene must no longer exist."""

    def test_codex_instructions_md_is_deleted(self) -> None:
        """The .codex/instructions.md file containing the legacy hostname was removed."""
        path = PROJECT_ROOT / ".codex" / "instructions.md"
        self.assertFalse(
            path.exists(),
            f".codex/instructions.md should have been deleted but still exists at {path}",
        )

    def test_setup_environments_sh_is_deleted(self) -> None:
        """.github/scripts/setup-environments.sh was removed in this PR."""
        path = PROJECT_ROOT / ".github" / "scripts" / "setup-environments.sh"
        self.assertFalse(
            path.exists(),
            f"setup-environments.sh should have been deleted but still exists at {path}",
        )


# ---------------------------------------------------------------------------
# docs/MANIFEST.json.sha256 – new sidecar added in this PR
# ---------------------------------------------------------------------------

class DocsManifestChecksumTests(unittest.TestCase):
    """Validate the docs/MANIFEST.json.sha256 file introduced in this PR."""

    def test_docs_manifest_json_sha256_exists(self) -> None:
        path = PROJECT_ROOT / "docs" / "MANIFEST.json.sha256"
        self.assertTrue(path.exists())

    def test_docs_manifest_json_sha256_format(self) -> None:
        path = PROJECT_ROOT / "docs" / "MANIFEST.json.sha256"
        content = _read_text(path).strip()
        self.assertRegex(content, re.compile(r"^[0-9a-f]{64}  .+$"))

    def test_noemaforge_docs_manifest_json_sha256_exists(self) -> None:
        path = ROOT / "docs" / "MANIFEST.json.sha256"
        self.assertTrue(path.exists())

    def test_noemaforge_docs_manifest_json_sha256_format(self) -> None:
        path = ROOT / "docs" / "MANIFEST.json.sha256"
        content = _read_text(path).strip()
        self.assertRegex(content, re.compile(r"^[0-9a-f]{64}  .+$"))


# ---------------------------------------------------------------------------
# Workflow p0-status-ledger.yml – one-line change in this PR
# ---------------------------------------------------------------------------

class P0StatusLedgerWorkflowTests(unittest.TestCase):
    """Validate the p0-status-ledger.yml changes introduced in this PR."""

    def setUp(self) -> None:
        self.path = PROJECT_ROOT / ".github" / "workflows" / "p0-status-ledger.yml"
        self.content = _read_text(self.path)

    def test_workflow_file_exists(self) -> None:
        self.assertTrue(self.path.exists())

    def test_production_target_host_phrase_present(self) -> None:
        """The updated line should use the generic production host description."""
        self.assertIn("production target host", self.content)

    def test_forbidden_hostname_absent(self) -> None:
        self.assertNotIn(_FORBIDDEN_HOSTNAME, self.content)

    def test_keep_display_behavior_referenced(self) -> None:
        """keep-display behavior mention must be preserved after the edit."""
        self.assertIn("keep-display", self.content)

    def test_yaml_is_parseable(self) -> None:
        """The workflow YAML must remain syntactically valid."""
        try:
            import yaml  # type: ignore[import]
            yaml.safe_load(self.content)
        except ImportError:
            self.skipTest("PyYAML not available")
        except Exception as exc:
            self.fail(f"p0-status-ledger.yml failed YAML parse: {exc}")


if __name__ == "__main__":
    unittest.main()
