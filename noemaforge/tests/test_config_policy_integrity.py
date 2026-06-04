#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_config_policy_integrity.py
Zone: tests
Version: 0.32.2
Created: 2026-06-04
Modified: 2026-06-04
Purpose: Structural and integrity tests for config files changed in this PR:
         - noemaforge/configs/docs-hygiene-policy.json
         - noemaforge/configs/manifest-checksum-exclusion-policy.json
         Tests verify: valid JSON, required top-level keys, policy field types,
         version matches 0.32.2, forbidden-text entries use unicode escaping
         (no literals), required runtime tokens present in exclusion policy,
         and structural invariants that release gates rely on.
Inputs: JSON policy files on disk.
Outputs: pytest/unittest pass/fail.
Side effects: None (read-only).
Tests: python3 -m unittest noemaforge/tests/test_config_policy_integrity.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_CONFIGS = _REPO / "noemaforge" / "configs"


def _load_json(path: Path) -> dict:
    """Load a JSON file; raises if invalid."""
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw)


# ---------------------------------------------------------------------------
# docs-hygiene-policy.json
# ---------------------------------------------------------------------------

class TestDocsHygienePolicyJson(unittest.TestCase):
    """docs-hygiene-policy.json must be valid and structurally correct."""

    def setUp(self) -> None:
        self._path = _CONFIGS / "docs-hygiene-policy.json"
        self._doc = _load_json(self._path)

    def test_file_is_valid_json(self) -> None:
        """The file must be parseable as JSON."""
        self.assertIsInstance(self._doc, dict)

    def test_api_version_present(self) -> None:
        self.assertIn("apiVersion", self._doc)

    def test_kind_is_docs_hygiene_policy(self) -> None:
        self.assertEqual(self._doc.get("kind"), "DocsHygienePolicy")

    def test_version_is_0_32_2(self) -> None:
        self.assertEqual(self._doc.get("version"), "0.32.2",
                         "docs-hygiene-policy.json version must be 0.32.2")

    def test_status_present(self) -> None:
        self.assertIn("status", self._doc)

    def test_policy_section_exists(self) -> None:
        self.assertIn("policy", self._doc)
        self.assertIsInstance(self._doc["policy"], dict)

    def test_approved_markdown_prefixes_is_list(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("approved_markdown_prefixes", policy)
        self.assertIsInstance(policy["approved_markdown_prefixes"], list)
        self.assertGreater(len(policy["approved_markdown_prefixes"]), 0)

    def test_noemaforge_docs_in_approved_prefixes(self) -> None:
        """noemaforge/docs/ must be in the approved markdown prefixes."""
        prefixes = self._doc["policy"]["approved_markdown_prefixes"]
        self.assertIn("noemaforge/docs/", prefixes)

    def test_forbidden_markdown_prefixes_is_list(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("forbidden_markdown_prefixes", policy)
        self.assertIsInstance(policy["forbidden_markdown_prefixes"], list)

    def test_forbidden_active_text_is_list(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("forbidden_active_text", policy)
        self.assertIsInstance(policy["forbidden_active_text"], list)
        self.assertGreater(len(policy["forbidden_active_text"]), 0)

    def test_forbidden_active_text_has_no_literal_outdated(self) -> None:
        """The OUTDATED marker must not appear as a literal string in the raw file."""
        raw = self._path.read_text(encoding="utf-8")
        # The policy encodes forbidden strings via unicode escapes in the JSON
        # source to avoid self-referential violations. The decoded value will
        # appear when loaded, but we validate the raw source does not contain
        # the literal forbidden string 'OUTDATED'.
        self.assertNotIn("OUTDATED", raw,
                         "OUTDATED must be unicode-escaped in the JSON source to avoid self-reference")

    def test_required_canonical_files_is_list(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("required_canonical_files", policy)
        self.assertIsInstance(policy["required_canonical_files"], list)
        self.assertGreater(len(policy["required_canonical_files"]), 0)

    def test_required_canonical_files_includes_readme(self) -> None:
        """noemaforge/docs/README.md must be in required_canonical_files."""
        files = self._doc["policy"]["required_canonical_files"]
        self.assertIn("noemaforge/docs/README.md", files)

    def test_required_canonical_files_includes_todo(self) -> None:
        self.assertIn("noemaforge/docs/TODO.md",
                      self._doc["policy"]["required_canonical_files"])

    def test_required_canonical_files_includes_changelog(self) -> None:
        self.assertIn("noemaforge/docs/history/CHANGELOG.md",
                      self._doc["policy"]["required_canonical_files"])

    def test_required_checked_todo_items_is_list(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("required_checked_todo_items", policy)
        self.assertIsInstance(policy["required_checked_todo_items"], list)

    def test_each_checked_todo_item_has_file_and_label(self) -> None:
        """Every required_checked_todo_items entry must have 'file' and 'label'."""
        for item in self._doc["policy"]["required_checked_todo_items"]:
            with self.subTest(item=item):
                self.assertIn("file", item)
                self.assertIn("label", item)
                self.assertTrue(item["file"], "file must not be empty")
                self.assertTrue(item["label"], "label must not be empty")

    def test_refs_section_exists(self) -> None:
        self.assertIn("refs", self._doc)
        self.assertIsInstance(self._doc["refs"], list)
        self.assertGreater(len(self._doc["refs"]), 0)

    def test_legacy_root_markdown_patterns_present(self) -> None:
        """AGENTS.md must be in legacy_root_markdown_patterns (added in this PR)."""
        policy = self._doc["policy"]
        self.assertIn("legacy_root_markdown_patterns", policy)
        patterns = policy["legacy_root_markdown_patterns"]
        self.assertIn("AGENTS.md", patterns,
                      "AGENTS.md must be listed in legacy_root_markdown_patterns")

    def test_forbidden_active_text_entries_are_strings(self) -> None:
        for entry in self._doc["policy"]["forbidden_active_text"]:
            with self.subTest(entry=entry):
                self.assertIsInstance(entry, str)
                self.assertTrue(entry, "forbidden_active_text entries must not be empty")

    def test_forbidden_active_text_count_at_least_three(self) -> None:
        """Policy must forbid at least 3 active text strings."""
        self.assertGreaterEqual(
            len(self._doc["policy"]["forbidden_active_text"]), 3,
            "At least 3 forbidden active text strings must be defined"
        )


# ---------------------------------------------------------------------------
# manifest-checksum-exclusion-policy.json
# ---------------------------------------------------------------------------

class TestManifestChecksumExclusionPolicyJson(unittest.TestCase):
    """manifest-checksum-exclusion-policy.json must be valid and structurally correct."""

    def setUp(self) -> None:
        self._path = _CONFIGS / "manifest-checksum-exclusion-policy.json"
        self._doc = _load_json(self._path)

    def test_file_is_valid_json(self) -> None:
        self.assertIsInstance(self._doc, dict)

    def test_api_version_present(self) -> None:
        self.assertIn("apiVersion", self._doc)

    def test_kind_is_manifest_checksum_exclusion_policy(self) -> None:
        self.assertEqual(self._doc.get("kind"), "ManifestChecksumExclusionPolicy")

    def test_version_is_0_32_2(self) -> None:
        self.assertEqual(self._doc.get("version"), "0.32.2",
                         "manifest-checksum-exclusion-policy.json version must be 0.32.2")

    def test_status_present(self) -> None:
        self.assertIn("status", self._doc)
        self.assertIsInstance(self._doc["status"], str)

    def test_policy_section_exists(self) -> None:
        self.assertIn("policy", self._doc)
        self.assertIsInstance(self._doc["policy"], dict)

    def test_mode_is_offline_contract(self) -> None:
        self.assertEqual(self._doc["policy"].get("mode"), "offline_contract")

    def test_activation_state_present(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("activation_state", policy)
        self.assertEqual(
            policy["activation_state"],
            "trash_and_cache_excluded_from_release_evidence"
        )

    def test_excluded_dir_names_is_list(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("excluded_dir_names", policy)
        self.assertIsInstance(policy["excluded_dir_names"], list)
        self.assertGreater(len(policy["excluded_dir_names"]), 0)

    def test_pycache_excluded(self) -> None:
        """__pycache__ must be in excluded_dir_names."""
        self.assertIn("__pycache__", self._doc["policy"]["excluded_dir_names"])

    def test_git_excluded(self) -> None:
        """'.git' must be in excluded_dir_names."""
        self.assertIn(".git", self._doc["policy"]["excluded_dir_names"])

    def test_trash_excluded(self) -> None:
        """'trash' must be in excluded_dir_names."""
        self.assertIn("trash", self._doc["policy"]["excluded_dir_names"])

    def test_project_manifest_ref_is_string(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("project_manifest_ref", policy)
        self.assertIsInstance(policy["project_manifest_ref"], str)
        self.assertEqual(policy["project_manifest_ref"], "MANIFEST.json")

    def test_project_checksum_refs_is_list(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("project_checksum_refs", policy)
        self.assertIsInstance(policy["project_checksum_refs"], list)
        self.assertIn("SHA256SUMS", policy["project_checksum_refs"])

    def test_required_runtime_scripts_present(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("required_runtime_scripts", policy)
        scripts = policy["required_runtime_scripts"]
        self.assertIsInstance(scripts, list)
        self.assertGreater(len(scripts), 0)

    def test_manifest_exclusion_runtime_script_listed(self) -> None:
        """manifest_checksum_exclusion_runtime.py must be in required_runtime_scripts."""
        scripts = self._doc["policy"]["required_runtime_scripts"]
        self.assertTrue(
            any("manifest_checksum_exclusion_runtime" in s for s in scripts),
            "manifest_checksum_exclusion_runtime.py must be in required_runtime_scripts"
        )

    def test_required_runtime_tokens_present(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("required_runtime_tokens", policy)
        tokens = policy["required_runtime_tokens"]
        self.assertIsInstance(tokens, list)

    def test_activation_token_in_required_tokens(self) -> None:
        """trash_and_cache_excluded_from_release_evidence must be a required token."""
        tokens = self._doc["policy"]["required_runtime_tokens"]
        self.assertIn("trash_and_cache_excluded_from_release_evidence", tokens)

    def test_hash_mismatch_token_in_required_tokens(self) -> None:
        """hash_mismatch must be in required_runtime_tokens."""
        tokens = self._doc["policy"]["required_runtime_tokens"]
        self.assertIn("hash_mismatch", tokens)

    def test_project_excluded_file_refs_includes_agents_md(self) -> None:
        """AGENTS.md must be in project_excluded_file_refs (added in this PR)."""
        policy = self._doc["policy"]
        self.assertIn("project_excluded_file_refs", policy)
        refs = policy["project_excluded_file_refs"]
        self.assertIn("AGENTS.md", refs,
                      "AGENTS.md must be excluded from project checksums")

    def test_project_excluded_file_refs_includes_context_md(self) -> None:
        """context.md must be in project_excluded_file_refs."""
        refs = self._doc["policy"]["project_excluded_file_refs"]
        self.assertIn("context.md", refs)

    def test_refs_section_exists(self) -> None:
        self.assertIn("refs", self._doc)
        self.assertIsInstance(self._doc["refs"], list)
        self.assertGreater(len(self._doc["refs"]), 0)

    def test_project_checksum_self_exclusions_present(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("project_checksum_self_exclusions", policy)
        self.assertIn("SHA256SUMS", policy["project_checksum_self_exclusions"])

    def test_package_checksum_self_exclusions_present(self) -> None:
        policy = self._doc["policy"]
        self.assertIn("package_checksum_self_exclusions", policy)
        self.assertIsInstance(policy["package_checksum_self_exclusions"], list)

    def test_require_registry_attachment_is_bool(self) -> None:
        self.assertIsInstance(self._doc["policy"]["require_registry_attachment"], bool)

    def test_require_no_live_host_dependency_is_bool(self) -> None:
        self.assertIsInstance(self._doc["policy"]["require_no_live_host_dependency"], bool)

    def test_require_no_live_host_dependency_is_true(self) -> None:
        """Policy must require no live host dependency (offline-first invariant)."""
        self.assertTrue(self._doc["policy"]["require_no_live_host_dependency"])


# ---------------------------------------------------------------------------
# Cross-file consistency checks
# ---------------------------------------------------------------------------

class TestPolicyCrossConsistency(unittest.TestCase):
    """Cross-checks between the two policy files."""

    def setUp(self) -> None:
        self._hygiene = _load_json(_CONFIGS / "docs-hygiene-policy.json")
        self._exclusion = _load_json(_CONFIGS / "manifest-checksum-exclusion-policy.json")

    def test_both_have_version_0_32_2(self) -> None:
        self.assertEqual(self._hygiene["version"], "0.32.2")
        self.assertEqual(self._exclusion["version"], "0.32.2")

    def test_both_have_refs_section(self) -> None:
        self.assertIn("refs", self._hygiene)
        self.assertIn("refs", self._exclusion)

    def test_both_have_policy_section(self) -> None:
        self.assertIn("policy", self._hygiene)
        self.assertIn("policy", self._exclusion)

    def test_hygiene_policy_forbids_pycache_implicitly(self) -> None:
        """docs-hygiene-policy should not include __pycache__ in approved prefixes."""
        approved = self._hygiene["policy"].get("approved_markdown_prefixes", [])
        for prefix in approved:
            self.assertNotIn("__pycache__", prefix)

    def test_exclusion_policy_self_refs_its_config_file(self) -> None:
        """manifest-checksum-exclusion-policy.json must ref itself in refs."""
        refs = self._exclusion.get("refs", [])
        self.assertTrue(
            any("manifest-checksum-exclusion-policy.json" in r for r in refs),
            "Policy must include its own config file in refs"
        )

    def test_hygiene_policy_self_refs_its_config_file(self) -> None:
        """docs-hygiene-policy.json must ref itself in refs."""
        refs = self._hygiene.get("refs", [])
        self.assertTrue(
            any("docs-hygiene-policy.json" in r for r in refs),
            "Policy must include its own config file in refs"
        )


if __name__ == "__main__":
    unittest.main()
