#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_docs_hygiene_policy_0322.py
Zone: test
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Validate changes introduced in the 0.32.2 hardening PR — docs-hygiene-policy.json
  structure and content, forbidden-text removal from CLAUDE.md and p0-status-ledger.yml,
  MANIFEST.json consistency, and SHA256SUMS format integrity.
Inputs: Repository config/manifest/doc files touched by the PR diff.
Outputs: unittest assertions only.
Side effects: None (read-only).
Tests: python3 -m unittest noemaforge/tests/test_docs_hygiene_policy_0322.py -v
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

POLICY_PATH = ROOT / "configs" / "docs-hygiene-policy.json"
MANIFEST_PATH = PROJECT_ROOT / "MANIFEST.json"
MANIFEST_SHA256_PATH = PROJECT_ROOT / "MANIFEST.json.sha256"
MANIFEST_SHA256_ALIAS = PROJECT_ROOT / "MANIFEST.sha256"
SHA256SUMS_PATH = PROJECT_ROOT / "SHA256SUMS"
CLAUDE_MD_PATH = PROJECT_ROOT / "CLAUDE.md"
P0_LEDGER_PATH = PROJECT_ROOT / ".github" / "workflows" / "p0-status-ledger.yml"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SUMS_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


# ===========================================================================
# docs-hygiene-policy.json — structure
# ===========================================================================

class TestDocsHygienePolicyStructure(unittest.TestCase):
    """Validate the top-level structure of the newly added docs-hygiene-policy.json."""

    def setUp(self) -> None:
        self.policy = _load_policy()

    def test_file_is_valid_json(self) -> None:
        # If setUp loaded without error the file is valid; assert the result is a dict.
        self.assertIsInstance(self.policy, dict)

    def test_required_top_level_keys_present(self) -> None:
        required = {"apiVersion", "kind", "id", "version", "status", "policy", "refs"}
        missing = required - self.policy.keys()
        self.assertEqual(set(), missing, f"Missing top-level keys: {missing}")

    def test_api_version_is_docs_hygiene_v1(self) -> None:
        self.assertEqual("noemaforge.docs-hygiene/v1", self.policy["apiVersion"])

    def test_kind_is_docs_hygiene_policy(self) -> None:
        self.assertEqual("DocsHygienePolicy", self.policy["kind"])

    def test_id_is_prelaunch_docs_hygiene(self) -> None:
        self.assertEqual("prelaunch-docs-hygiene", self.policy["id"])

    def test_version_is_0_32_2(self) -> None:
        self.assertEqual("0.32.2", self.policy["version"])

    def test_status_is_stable(self) -> None:
        self.assertEqual("stable", self.policy["status"])

    def test_policy_sub_keys_present(self) -> None:
        expected_sub_keys = {
            "approved_markdown_prefixes",
            "allowed_root_markdown",
            "allowed_docs_root_markdown",
            "forbidden_markdown_prefixes",
            "forbidden_active_text",
            "required_canonical_files",
            "required_checked_todo_items",
            "canonical_changelog_refs",
        }
        policy_block = self.policy["policy"]
        missing = expected_sub_keys - policy_block.keys()
        self.assertEqual(set(), missing, f"Missing policy sub-keys: {missing}")

    def test_refs_is_non_empty_list(self) -> None:
        refs = self.policy["refs"]
        self.assertIsInstance(refs, list)
        self.assertGreater(len(refs), 0)


# ===========================================================================
# docs-hygiene-policy.json — allowed / forbidden markdown lists
# ===========================================================================

class TestDocsHygienePolicyMarkdownLists(unittest.TestCase):
    """Validate markdown path allow/block lists in the policy."""

    def setUp(self) -> None:
        self.p = _load_policy()["policy"]

    def test_approved_markdown_prefixes_contains_docs_roots(self) -> None:
        prefixes = self.p["approved_markdown_prefixes"]
        self.assertIn("noemaforge/docs/", prefixes)
        self.assertIn("docs/", prefixes)

    def test_allowed_root_markdown_contains_claude_readme_context(self) -> None:
        allowed = self.p["allowed_root_markdown"]
        self.assertIn("CLAUDE.md", allowed)
        self.assertIn("README.md", allowed)
        self.assertIn("context.md", allowed)

    def test_allowed_docs_root_markdown_contains_canonical_files(self) -> None:
        allowed = self.p["allowed_docs_root_markdown"]
        self.assertIn("noemaforge/docs/README.md", allowed)
        self.assertIn("noemaforge/docs/Manifest.md", allowed)
        self.assertIn("noemaforge/docs/TODO.md", allowed)

    def test_forbidden_markdown_prefixes_is_non_empty(self) -> None:
        self.assertGreater(len(self.p["forbidden_markdown_prefixes"]), 0)

    def test_forbidden_markdown_prefixes_contain_no_approved_path(self) -> None:
        approved = set(self.p["approved_markdown_prefixes"])
        for prefix in self.p["forbidden_markdown_prefixes"]:
            self.assertNotIn(prefix, approved, f"Prefix '{prefix}' is both approved and forbidden")

    def test_canonical_changelog_ref_points_to_single_canonical_location(self) -> None:
        refs = self.p["canonical_changelog_refs"]
        self.assertEqual(["noemaforge/docs/history/CHANGELOG.md"], refs)


# ===========================================================================
# docs-hygiene-policy.json — forbidden_active_text content
# ===========================================================================

class TestDocsHygienePolicyForbiddenActiveText(unittest.TestCase):
    """Validate that the correct forbidden strings are declared in the policy."""

    def setUp(self) -> None:
        self.forbidden = _load_policy()["policy"]["forbidden_active_text"]

    def test_forbidden_list_is_non_empty(self) -> None:
        self.assertGreater(len(self.forbidden), 0)

    def test_legacy_hostname_is_forbidden(self) -> None:
        # "BigBro-BOS" is stored with unicode escape \u002d for "-"
        target = "BigBro" + "-" + "BOS"
        self.assertIn(target, self.forbidden)

    def test_stale_content_marker_is_forbidden(self) -> None:
        # "OUTDATED" is stored with unicode escape \u0044 for "D"
        target = "OUT" + "DATED"
        self.assertIn(target, self.forbidden)

    def test_legacy_public_docs_paths_are_forbidden(self) -> None:
        # "docs/public" and "noemaforge/docs/public" stored with \u006c for "l"
        public_path = "docs/" + "public"
        nf_public_path = "noemaforge/docs/" + "public"
        self.assertIn(public_path, self.forbidden)
        self.assertIn(nf_public_path, self.forbidden)

    def test_no_empty_strings_in_forbidden_list(self) -> None:
        for entry in self.forbidden:
            self.assertNotEqual("", entry.strip(), "Empty string in forbidden_active_text")

    def test_forbidden_entries_are_all_strings(self) -> None:
        for entry in self.forbidden:
            self.assertIsInstance(entry, str)

    def test_forbidden_list_has_expected_length(self) -> None:
        # Exactly 4 entries: legacy hostname, docs/public, noemaforge/docs/public, OUTDATED
        self.assertEqual(4, len(self.forbidden))


# ===========================================================================
# docs-hygiene-policy.json — required_canonical_files
# ===========================================================================

class TestDocsHygienePolicyRequiredFiles(unittest.TestCase):
    """Validate required canonical file declarations."""

    def setUp(self) -> None:
        self.p = _load_policy()["policy"]

    def test_required_canonical_files_is_non_empty_list(self) -> None:
        files = self.p["required_canonical_files"]
        self.assertIsInstance(files, list)
        self.assertGreater(len(files), 0)

    def test_required_canonical_files_are_all_strings(self) -> None:
        for f in self.p["required_canonical_files"]:
            self.assertIsInstance(f, str)

    def test_todo_md_is_required_canonical(self) -> None:
        self.assertIn("noemaforge/docs/TODO.md", self.p["required_canonical_files"])

    def test_changelog_is_required_canonical(self) -> None:
        self.assertIn("noemaforge/docs/history/CHANGELOG.md", self.p["required_canonical_files"])

    def test_required_checked_todo_items_has_16_entries(self) -> None:
        items = self.p["required_checked_todo_items"]
        self.assertEqual(16, len(items))

    def test_required_checked_todo_items_each_have_file_and_label(self) -> None:
        for item in self.p["required_checked_todo_items"]:
            self.assertIn("file", item, f"Item missing 'file': {item}")
            self.assertIn("label", item, f"Item missing 'label': {item}")
            self.assertIsInstance(item["file"], str)
            self.assertIsInstance(item["label"], str)
            self.assertNotEqual("", item["label"].strip())

    def test_all_todo_items_target_noemaforge_docs_todo_md(self) -> None:
        for item in self.p["required_checked_todo_items"]:
            self.assertEqual("noemaforge/docs/TODO.md", item["file"])


# ===========================================================================
# docs-hygiene-policy.json — refs section
# ===========================================================================

class TestDocsHygienePolicyRefs(unittest.TestCase):
    """Validate that refs in the policy point to expected project artifacts."""

    def setUp(self) -> None:
        self.refs = _load_policy()["refs"]

    def test_refs_contains_self_reference(self) -> None:
        self.assertIn("noemaforge/configs/docs-hygiene-policy.json", self.refs)

    def test_refs_contains_runtime_source(self) -> None:
        self.assertIn("noemaforge/src/docs_hygiene_runtime.py", self.refs)

    def test_refs_contains_test_files(self) -> None:
        self.assertIn("noemaforge/tests/test_docs_hygiene_runtime.py", self.refs)
        self.assertIn("noemaforge/tests/test_docs_hygiene_qa.py", self.refs)

    def test_refs_contains_schema(self) -> None:
        self.assertIn("noemaforge/contracts/docs_hygiene_policy.schema.json", self.refs)

    def test_refs_are_all_strings(self) -> None:
        for ref in self.refs:
            self.assertIsInstance(ref, str)

    def test_refs_has_no_duplicates(self) -> None:
        self.assertEqual(len(self.refs), len(set(self.refs)))


# ===========================================================================
# CLAUDE.md — forbidden text removal
# ===========================================================================

class TestClaudeMdForbiddenTextRemoval(unittest.TestCase):
    """Verify that CLAUDE.md no longer contains the forbidden active-text strings
    that were removed as part of the 0.32.2 hardening changes."""

    def setUp(self) -> None:
        self.text = CLAUDE_MD_PATH.read_text(encoding="utf-8")

    def test_no_legacy_hostname_in_claude_md(self) -> None:
        legacy_host = "BigBro" + "-" + "BOS"
        self.assertNotIn(legacy_host, self.text)

    def test_no_docs_public_path_in_claude_md(self) -> None:
        self.assertNotIn("docs/public", self.text)

    def test_no_outdated_marker_in_claude_md(self) -> None:
        # The marker "OUTDATED" should no longer appear as a hardcoded entry
        # (it is permitted to appear in the reference to the policy, but not as
        # a bare active-text entry).
        self.assertNotIn("OUTDATED", self.text)

    def test_claude_md_references_docs_hygiene_policy_json(self) -> None:
        self.assertIn("docs-hygiene-policy.json", self.text)

    def test_claude_md_references_forbidden_active_text_key(self) -> None:
        self.assertIn("forbidden_active_text", self.text)

    def test_production_target_host_wording_used(self) -> None:
        self.assertIn("production target host", self.text)


# ===========================================================================
# p0-status-ledger.yml — forbidden text removal
# ===========================================================================

class TestP0LedgerForbiddenTextRemoval(unittest.TestCase):
    """Verify that p0-status-ledger.yml uses the generic hostname phrasing
    instead of the legacy literal hostname."""

    def setUp(self) -> None:
        self.text = P0_LEDGER_PATH.read_text(encoding="utf-8")

    def test_no_legacy_hostname_in_ledger(self) -> None:
        legacy_host = "BigBro" + "-" + "BOS"
        self.assertNotIn(legacy_host, self.text)

    def test_production_target_host_phrasing_present(self) -> None:
        self.assertIn("production target host", self.text)


# ===========================================================================
# MANIFEST.json — structure and consistency
# ===========================================================================

class TestManifestJsonStructure(unittest.TestCase):
    """Validate the updated MANIFEST.json after the 0.32.2 file additions."""

    def setUp(self) -> None:
        self.manifest = _load_manifest()

    def test_manifest_is_valid_json(self) -> None:
        self.assertIsInstance(self.manifest, dict)

    def test_required_top_level_keys(self) -> None:
        required = {"apiVersion", "file_count", "files", "generated_at", "kind"}
        missing = required - self.manifest.keys()
        self.assertEqual(set(), missing, f"Missing keys: {missing}")

    def test_api_version_is_release_v1(self) -> None:
        self.assertEqual("noemaforge.release/v1", self.manifest["apiVersion"])

    def test_kind_is_release_manifest(self) -> None:
        self.assertEqual("ReleaseManifest", self.manifest["kind"])

    def test_file_count_is_3172(self) -> None:
        self.assertEqual(3172, self.manifest["file_count"])

    def test_file_count_equals_files_list_length(self) -> None:
        self.assertEqual(self.manifest["file_count"], len(self.manifest["files"]))

    def test_files_is_non_empty_list(self) -> None:
        self.assertIsInstance(self.manifest["files"], list)
        self.assertGreater(len(self.manifest["files"]), 0)

    def test_manifest_json_itself_is_listed(self) -> None:
        self.assertIn("MANIFEST.json", self.manifest["files"])

    def test_claude_md_is_listed(self) -> None:
        self.assertIn("CLAUDE.md", self.manifest["files"])

    def test_sha256sums_is_listed(self) -> None:
        self.assertIn("SHA256SUMS", self.manifest["files"])

    def test_noemaforge_version_py_is_listed(self) -> None:
        self.assertIn("noemaforge/src/noemaforge_version.py", self.manifest["files"])

    def test_docs_hygiene_policy_json_is_listed(self) -> None:
        # The new config file introduced in this PR must appear in the manifest.
        self.assertIn("noemaforge/configs/docs-hygiene-policy.json", self.manifest["files"])

    def test_files_list_has_no_duplicates(self) -> None:
        files = self.manifest["files"]
        self.assertEqual(len(files), len(set(files)), "Duplicate entries in MANIFEST.json files list")

    def test_files_list_entries_are_strings(self) -> None:
        for f in self.manifest["files"][:20]:  # sample first 20
            self.assertIsInstance(f, str)

    def test_generated_at_is_non_empty_string(self) -> None:
        self.assertIsInstance(self.manifest["generated_at"], str)
        self.assertGreater(len(self.manifest["generated_at"]), 0)


# ===========================================================================
# MANIFEST.json.sha256 and MANIFEST.sha256 — checksum file consistency
# ===========================================================================

class TestManifestChecksumFiles(unittest.TestCase):
    """Validate the SHA-256 checksum companion files for MANIFEST.json."""

    def _read_checksum_line(self, path: Path) -> tuple[str, str]:
        """Return (hash, filename) from a single-line checksum file."""
        line = path.read_text(encoding="utf-8").strip()
        match = _SUMS_LINE.match(line)
        self.assertIsNotNone(match, f"Invalid checksum line format in {path}: {line!r}")
        return match.group(1), match.group(2)

    def test_manifest_json_sha256_has_valid_format(self) -> None:
        self._read_checksum_line(MANIFEST_SHA256_PATH)

    def test_manifest_sha256_has_valid_format(self) -> None:
        self._read_checksum_line(MANIFEST_SHA256_ALIAS)

    def test_manifest_json_sha256_references_manifest_json(self) -> None:
        _, filename = self._read_checksum_line(MANIFEST_SHA256_PATH)
        self.assertEqual("MANIFEST.json", filename)

    def test_manifest_sha256_references_manifest_json(self) -> None:
        _, filename = self._read_checksum_line(MANIFEST_SHA256_ALIAS)
        self.assertEqual("MANIFEST.json", filename)

    def test_both_checksum_files_agree_on_hash(self) -> None:
        hash1, _ = self._read_checksum_line(MANIFEST_SHA256_PATH)
        hash2, _ = self._read_checksum_line(MANIFEST_SHA256_ALIAS)
        self.assertEqual(hash1, hash2, "MANIFEST.json.sha256 and MANIFEST.sha256 have different hashes")

    def test_hash_is_64_hex_chars(self) -> None:
        hash_val, _ = self._read_checksum_line(MANIFEST_SHA256_PATH)
        self.assertTrue(_HEX64.match(hash_val), f"Hash is not 64 lowercase hex chars: {hash_val!r}")

    def test_hash_is_not_all_zeros(self) -> None:
        hash_val, _ = self._read_checksum_line(MANIFEST_SHA256_PATH)
        self.assertNotEqual("0" * 64, hash_val)


# ===========================================================================
# SHA256SUMS — format integrity
# ===========================================================================

class TestSha256SumsFormat(unittest.TestCase):
    """Validate the format and basic integrity of the root SHA256SUMS file."""

    def setUp(self) -> None:
        self.lines = [
            ln for ln in SHA256SUMS_PATH.read_text(encoding="utf-8").splitlines()
            if ln.strip()  # ignore blank lines at EOF
        ]

    def test_sha256sums_is_non_empty(self) -> None:
        self.assertGreater(len(self.lines), 0)

    def test_all_lines_match_hash_filename_format(self) -> None:
        bad = [ln for ln in self.lines if not _SUMS_LINE.match(ln)]
        self.assertEqual([], bad, f"Malformed SHA256SUMS lines: {bad[:5]}")

    def test_all_hashes_are_64_lowercase_hex(self) -> None:
        for ln in self.lines:
            m = _SUMS_LINE.match(ln)
            if m:
                self.assertTrue(_HEX64.match(m.group(1)), f"Bad hash in line: {ln!r}")

    def test_manifest_json_entry_present_in_sha256sums(self) -> None:
        filenames = {_SUMS_LINE.match(ln).group(2) for ln in self.lines if _SUMS_LINE.match(ln)}
        self.assertIn("MANIFEST.json", filenames)

    def test_sha256sums_hash_for_manifest_matches_manifest_sha256_file(self) -> None:
        sums_hash = None
        for ln in self.lines:
            m = _SUMS_LINE.match(ln)
            if m and m.group(2) == "MANIFEST.json":
                sums_hash = m.group(1)
                break
        self.assertIsNotNone(sums_hash, "MANIFEST.json not found in SHA256SUMS")

        checksum_line = MANIFEST_SHA256_PATH.read_text(encoding="utf-8").strip()
        checksum_hash = _SUMS_LINE.match(checksum_line).group(1)
        self.assertEqual(checksum_hash, sums_hash,
                         "Hash for MANIFEST.json differs between SHA256SUMS and MANIFEST.json.sha256")

    def test_no_duplicate_filenames_in_sha256sums(self) -> None:
        filenames = [_SUMS_LINE.match(ln).group(2) for ln in self.lines if _SUMS_LINE.match(ln)]
        duplicates = {f for f in filenames if filenames.count(f) > 1}
        self.assertEqual(set(), duplicates, f"Duplicate filenames in SHA256SUMS: {duplicates}")

    def test_sha256sums_itself_is_listed_in_manifest(self) -> None:
        manifest = _load_manifest()
        self.assertIn("SHA256SUMS", manifest["files"])


# ===========================================================================
# Regression — ensure deleted files are absent
# ===========================================================================

class TestDeletedFilesAbsent(unittest.TestCase):
    """Regression tests verifying that files removed in this PR no longer exist."""

    def test_codex_instructions_md_deleted(self) -> None:
        deleted = PROJECT_ROOT / ".codex" / "instructions.md"
        self.assertFalse(deleted.exists(), ".codex/instructions.md was not deleted")

    def test_setup_environments_sh_deleted(self) -> None:
        deleted = PROJECT_ROOT / ".github" / "scripts" / "setup-environments.sh"
        self.assertFalse(deleted.exists(), ".github/scripts/setup-environments.sh was not deleted")


if __name__ == "__main__":
    unittest.main()
