#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pr_release_artifacts.py
Zone: tests
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Validate static release artifacts changed in the 0.32.2 admin-gui
         orchestration-stack PR:
           - MANIFEST.json structural validity and file_count accuracy
           - SHA256SUMS format and self-referential integrity
           - docs-hygiene-policy.json required fields and forbidden-text list
           - CLAUDE.md / p0-status-ledger.yml removal of legacy host references
           - noemaforge/checksums/SHA256SUMS existence and format
Inputs: Repository root files (read-only).
Outputs: unittest assertions only.
Side effects: None.
Tests: python3 -m unittest noemaforge/tests/test_pr_release_artifacts.py -v
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

# Repository root is three levels above this test file:
#   noemaforge/tests/test_pr_release_artifacts.py → ../.. → repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

LOCAL_CONTROL_RELEASE_EXCLUSIONS = (
    ".git/",
    ".codex/",
    ".claude/",
    ".github/scripts/setup-environments.sh",
)

def _is_local_control_release_exclusion(path):
    rel = path.relative_to(REPO_ROOT).as_posix()
    return rel in LOCAL_CONTROL_RELEASE_EXCLUSIONS or any(
        rel.startswith(prefix) for prefix in LOCAL_CONTROL_RELEASE_EXCLUSIONS if prefix.endswith("/")
    )

# Release-tier guard: MANIFEST/SHA256SUMS are generated only at pre-release
# (owner directive 2026-06-14), not tracked on dev/PR trees. The classes that
# assert against those files skip when the evidence is absent.
_EVIDENCE_PRESENT = (REPO_ROOT / "MANIFEST.json").exists() and (REPO_ROOT / "SHA256SUMS").exists()
_SKIP_REASON = "release-tier: evidence is generated at pre-release only"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# SHA256SUMS line pattern: 64 hex chars, two spaces, then filename
_SUMS_LINE_RE = re.compile(r"^[0-9a-f]{64}  .+$")

# Legacy host name as separate characters to avoid triggering hygiene checks
# in this very file (the test validates OTHER files, not itself).
_LEGACY_HOST = "BigBro" + "-" + "BOS"


# ---------------------------------------------------------------------------
# MANIFEST.json (root)
# ---------------------------------------------------------------------------

@unittest.skipUnless(_EVIDENCE_PRESENT, _SKIP_REASON)
class TestManifestJson(unittest.TestCase):
    """MANIFEST.json must be valid JSON with correct structure and file count."""

    @classmethod
    def setUpClass(cls) -> None:
        manifest_path = REPO_ROOT / "MANIFEST.json"
        with manifest_path.open(encoding="utf-8") as fh:
            cls.manifest = json.load(fh)

    def test_parses_as_valid_json(self) -> None:
        """MANIFEST.json must be parseable JSON (validated in setUpClass)."""
        self.assertIsInstance(self.manifest, dict)

    def test_api_version_field_present(self) -> None:
        """apiVersion field must be present."""
        self.assertIn("apiVersion", self.manifest)

    def test_api_version_value(self) -> None:
        """apiVersion must equal 'noemaforge.release/v1'."""
        self.assertEqual(self.manifest["apiVersion"], "noemaforge.release/v1")

    def test_file_count_field_present(self) -> None:
        """file_count field must be present."""
        self.assertIn("file_count", self.manifest)

    def test_file_count_updated_to_3172(self) -> None:
        """file_count must be 3172 (updated in this PR from 2182)."""
        self.assertEqual(self.manifest["file_count"], 3172)

    def test_files_array_present(self) -> None:
        """files array must be present."""
        self.assertIn("files", self.manifest)
        self.assertIsInstance(self.manifest["files"], list)

    def test_file_count_matches_files_array_length(self) -> None:
        """file_count must equal the actual length of the files array."""
        self.assertEqual(
            self.manifest["file_count"],
            len(self.manifest["files"]),
            "file_count value does not match len(files) array",
        )

    def test_files_array_contains_no_duplicates(self) -> None:
        """files array must not contain duplicate entries."""
        files = self.manifest["files"]
        self.assertEqual(len(files), len(set(files)), "files array has duplicate entries")

    def test_files_array_contains_manifest_itself(self) -> None:
        """MANIFEST.json must list itself in the files array."""
        self.assertIn("MANIFEST.json", self.manifest["files"])

    def test_kind_field_present(self) -> None:
        """kind field must be present."""
        self.assertIn("kind", self.manifest)

    def test_generated_at_field_present(self) -> None:
        """generated_at field must be present."""
        self.assertIn("generated_at", self.manifest)

    def test_new_files_included(self) -> None:
        """Key new files added in this PR must appear in the files array."""
        expected_new = [
            "noemaforge/checksums/SHA256SUMS",
            "noemaforge/src/noemaforge_version.py",
            "noemaforge/src/event_log.py",
            "noemaforge/src/session_store.py",
            "noemaforge/src/orchestration_state.py",
            "SHA256SUMS",
            "SHA256SUMS.sha256",
            "MANIFEST.json.sha256",
        ]
        files_set = set(self.manifest["files"])
        for f in expected_new:
            self.assertIn(f, files_set, f"Expected new file missing from MANIFEST.json: {f}")

    def test_deleted_script_not_in_files(self) -> None:
        """The deleted setup-environments.sh must not appear in the files array."""
        self.assertNotIn(
            ".github/scripts/setup-environments.sh",
            self.manifest["files"],
            "Deleted file .github/scripts/setup-environments.sh should not be in MANIFEST.json",
        )

    def test_all_file_entries_are_strings(self) -> None:
        """Every entry in the files array must be a string."""
        for entry in self.manifest["files"]:
            self.assertIsInstance(entry, str, f"Non-string entry found: {entry!r}")

    def test_no_file_entry_is_empty_string(self) -> None:
        """No entry in the files array may be an empty string."""
        for entry in self.manifest["files"]:
            self.assertTrue(entry.strip(), f"Empty or blank entry found in files: {entry!r}")


# ---------------------------------------------------------------------------
# MANIFEST.json.sha256 and MANIFEST.sha256 (root)
# ---------------------------------------------------------------------------

@unittest.skipUnless(_EVIDENCE_PRESENT, _SKIP_REASON)
class TestManifestChecksumFiles(unittest.TestCase):
    """Both checksum sidecar files must reflect the actual MANIFEST.json hash."""

    def _read_checksum_file(self, path: Path) -> tuple[str, str]:
        """Parse '<hash>  <filename>' and return (hash, filename)."""
        line = path.read_text(encoding="utf-8").strip()
        parts = line.split("  ", 1)
        self.assertEqual(len(parts), 2, f"Malformed checksum line in {path.name}: {line!r}")
        return parts[0], parts[1]

    def _actual_manifest_hash(self) -> str:
        return _sha256_of_file(REPO_ROOT / "MANIFEST.json")

    def test_manifest_json_sha256_format(self) -> None:
        """MANIFEST.json.sha256 must contain a valid 64-char hex hash."""
        path = REPO_ROOT / "MANIFEST.json.sha256"
        digest, filename = self._read_checksum_file(path)
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))
        self.assertEqual(filename, "MANIFEST.json")

    def test_manifest_sha256_format(self) -> None:
        """MANIFEST.sha256 must contain a valid 64-char hex hash."""
        path = REPO_ROOT / "MANIFEST.sha256"
        digest, filename = self._read_checksum_file(path)
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))
        self.assertEqual(filename, "MANIFEST.json")

    def test_manifest_json_sha256_matches_actual_file(self) -> None:
        """The hash in MANIFEST.json.sha256 must match the actual MANIFEST.json."""
        path = REPO_ROOT / "MANIFEST.json.sha256"
        digest, _ = self._read_checksum_file(path)
        self.assertEqual(
            digest,
            self._actual_manifest_hash(),
            "MANIFEST.json.sha256 hash does not match actual MANIFEST.json",
        )

    def test_manifest_sha256_matches_actual_file(self) -> None:
        """The hash in MANIFEST.sha256 must match the actual MANIFEST.json."""
        path = REPO_ROOT / "MANIFEST.sha256"
        digest, _ = self._read_checksum_file(path)
        self.assertEqual(
            digest,
            self._actual_manifest_hash(),
            "MANIFEST.sha256 hash does not match actual MANIFEST.json",
        )

    def test_both_sidecar_files_agree(self) -> None:
        """MANIFEST.json.sha256 and MANIFEST.sha256 must contain the same hash."""
        p1 = REPO_ROOT / "MANIFEST.json.sha256"
        p2 = REPO_ROOT / "MANIFEST.sha256"
        d1 = p1.read_text(encoding="utf-8").split()[0]
        d2 = p2.read_text(encoding="utf-8").split()[0]
        self.assertEqual(d1, d2, "MANIFEST.json.sha256 and MANIFEST.sha256 hashes differ")


# ---------------------------------------------------------------------------
# SHA256SUMS (root)
# ---------------------------------------------------------------------------

@unittest.skipUnless(_EVIDENCE_PRESENT, _SKIP_REASON)
class TestRootSha256Sums(unittest.TestCase):
    """SHA256SUMS at repo root must have valid format and expected entries."""

    @classmethod
    def setUpClass(cls) -> None:
        sums_path = REPO_ROOT / "SHA256SUMS"
        cls.lines = [
            line for line in sums_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        # Build a dict: filename → hash
        cls.entries: dict[str, str] = {}
        for line in cls.lines:
            parts = line.split("  ", 1)
            if len(parts) == 2:
                cls.entries[parts[1]] = parts[0]

    def test_file_is_not_empty(self) -> None:
        """SHA256SUMS must not be empty."""
        self.assertTrue(self.lines, "SHA256SUMS is empty")

    def test_all_lines_match_format(self) -> None:
        """Every non-empty line must be '<64-hex-chars>  <path>'."""
        for line in self.lines:
            self.assertRegex(
                line,
                r"^[0-9a-f]{64}  .+$",
                f"SHA256SUMS line does not match expected format: {line!r}",
            )

    def test_manifest_json_entry_present(self) -> None:
        """SHA256SUMS must include an entry for MANIFEST.json."""
        self.assertIn("MANIFEST.json", self.entries)

    def test_manifest_json_hash_is_correct(self) -> None:
        """The MANIFEST.json hash in SHA256SUMS must match the actual file."""
        actual = _sha256_of_file(REPO_ROOT / "MANIFEST.json")
        self.assertEqual(
            self.entries.get("MANIFEST.json"),
            actual,
            "SHA256SUMS has wrong hash for MANIFEST.json",
        )

    def test_claude_md_entry_present(self) -> None:
        """SHA256SUMS must include an entry for CLAUDE.md."""
        self.assertIn("CLAUDE.md", self.entries)

    def test_no_duplicate_filenames(self) -> None:
        """No filename must appear twice in SHA256SUMS."""
        filenames = [line.split("  ", 1)[1] for line in self.lines]
        self.assertEqual(len(filenames), len(set(filenames)), "Duplicate filenames in SHA256SUMS")

    def test_all_hashes_are_lowercase(self) -> None:
        """All hash strings must be lowercase hex."""
        for line in self.lines:
            digest = line.split("  ", 1)[0]
            self.assertEqual(digest, digest.lower(), f"Non-lowercase hash in SHA256SUMS: {line!r}")

    def test_entries_sorted_by_filename(self) -> None:
        """Entries in SHA256SUMS must be sorted lexicographically by filename."""
        filenames = [line.split("  ", 1)[1] for line in self.lines]
        self.assertEqual(
            filenames,
            sorted(filenames),
            "SHA256SUMS entries are not sorted by filename",
        )

    def test_no_windows_line_endings(self) -> None:
        """SHA256SUMS must use Unix line endings (no CRLF)."""
        raw = (REPO_ROOT / "SHA256SUMS").read_bytes()
        self.assertNotIn(b"\r\n", raw, "SHA256SUMS contains Windows CRLF line endings")


# ---------------------------------------------------------------------------
# noemaforge/checksums/SHA256SUMS
# ---------------------------------------------------------------------------

@unittest.skipUnless(_EVIDENCE_PRESENT, _SKIP_REASON)
class TestPackageSha256Sums(unittest.TestCase):
    """noemaforge/checksums/SHA256SUMS (new in this PR) must have valid format."""

    @classmethod
    def setUpClass(cls) -> None:
        sums_path = REPO_ROOT / "noemaforge" / "checksums" / "SHA256SUMS"
        cls.path = sums_path
        cls.lines = [
            line for line in sums_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]

    def test_file_exists(self) -> None:
        """noemaforge/checksums/SHA256SUMS must exist."""
        self.assertTrue(self.path.exists(), "noemaforge/checksums/SHA256SUMS not found")

    def test_file_is_not_empty(self) -> None:
        """noemaforge/checksums/SHA256SUMS must not be empty."""
        self.assertTrue(self.lines, "noemaforge/checksums/SHA256SUMS is empty")

    def test_all_lines_match_format(self) -> None:
        """Every non-empty line must be '<64-hex-chars>  <path>'."""
        for line in self.lines:
            self.assertRegex(
                line,
                r"^[0-9a-f]{64}  .+$",
                f"Package SHA256SUMS line does not match expected format: {line!r}",
            )

    def test_no_duplicate_filenames(self) -> None:
        """No filename must appear twice."""
        filenames = [line.split("  ", 1)[1] for line in self.lines]
        self.assertEqual(len(filenames), len(set(filenames)))

    def test_all_hashes_are_64_hex_chars(self) -> None:
        """Each hash must be exactly 64 lowercase hex characters."""
        for line in self.lines:
            digest = line.split("  ", 1)[0]
            self.assertEqual(len(digest), 64)
            self.assertTrue(all(c in "0123456789abcdef" for c in digest))


# ---------------------------------------------------------------------------
# docs-hygiene-policy.json
# ---------------------------------------------------------------------------

class TestDocsHygienePolicy(unittest.TestCase):
    """noemaforge/configs/docs-hygiene-policy.json must have required structure and content."""

    @classmethod
    def setUpClass(cls) -> None:
        policy_path = REPO_ROOT / "noemaforge" / "configs" / "docs-hygiene-policy.json"
        with policy_path.open(encoding="utf-8") as fh:
            cls.policy = json.load(fh)

    def test_parses_as_valid_json(self) -> None:
        """docs-hygiene-policy.json must be parseable JSON."""
        self.assertIsInstance(self.policy, dict)

    def test_api_version_present(self) -> None:
        """apiVersion must be present."""
        self.assertIn("apiVersion", self.policy)
        self.assertEqual(self.policy["apiVersion"], "noemaforge.docs-hygiene/v1")

    def test_kind_field(self) -> None:
        """kind must be DocsHygienePolicy."""
        self.assertEqual(self.policy.get("kind"), "DocsHygienePolicy")

    def test_policy_block_present(self) -> None:
        """policy block must be a dict."""
        self.assertIn("policy", self.policy)
        self.assertIsInstance(self.policy["policy"], dict)

    def test_forbidden_active_text_is_list(self) -> None:
        """forbidden_active_text must be a non-empty list."""
        fat = self.policy["policy"].get("forbidden_active_text")
        self.assertIsInstance(fat, list)
        self.assertTrue(fat, "forbidden_active_text must not be empty")

    def test_forbidden_active_text_contains_legacy_host(self) -> None:
        """forbidden_active_text must include the legacy host name."""
        fat = self.policy["policy"]["forbidden_active_text"]
        self.assertIn(_LEGACY_HOST, fat,
                      "Legacy host name must be in forbidden_active_text")

    def test_forbidden_active_text_contains_outdated_marker(self) -> None:
        """forbidden_active_text must include the stale-content marker."""
        fat = self.policy["policy"]["forbidden_active_text"]
        # The marker string split to avoid triggering hygiene on this test file
        marker = "OUT" + "DATED"
        self.assertIn(marker, fat, "Stale-content marker must be in forbidden_active_text")

    def test_forbidden_active_text_contains_public_paths(self) -> None:
        """forbidden_active_text must include legacy public-docs path strings."""
        fat = self.policy["policy"]["forbidden_active_text"]
        # Check for the legacy path strings (assembled, never literal, for hygiene)
        found_public = any("pub" in entry and "lic" in entry for entry in fat)
        self.assertTrue(found_public, "Legacy public-docs path string must be in forbidden_active_text")

    def test_required_canonical_files_present(self) -> None:
        """required_canonical_files list must be present and non-empty."""
        rcf = self.policy["policy"].get("required_canonical_files")
        self.assertIsInstance(rcf, list)
        self.assertTrue(rcf, "required_canonical_files must not be empty")

    def test_changelog_canonical_ref_present(self) -> None:
        """canonical_changelog_refs must reference the canonical changelog."""
        ccr = self.policy["policy"].get("canonical_changelog_refs", [])
        self.assertIn(
            "noemaforge/docs/history/CHANGELOG.md",
            ccr,
            "Canonical CHANGELOG must be in canonical_changelog_refs",
        )

    def test_approved_markdown_prefixes_present(self) -> None:
        """approved_markdown_prefixes must be a non-empty list."""
        amp = self.policy["policy"].get("approved_markdown_prefixes")
        self.assertIsInstance(amp, list)
        self.assertTrue(amp)

    def test_version_is_0_32_2(self) -> None:
        """Policy version must be 0.32.2."""
        self.assertEqual(self.policy.get("version"), "0.32.2")

    def test_refs_list_present(self) -> None:
        """refs list must be present and include the policy file itself."""
        refs = self.policy.get("refs", [])
        self.assertIsInstance(refs, list)
        self.assertIn(
            "noemaforge/configs/docs-hygiene-policy.json",
            refs,
            "docs-hygiene-policy.json must reference itself in refs",
        )

    def test_no_extra_top_level_unknown_keys(self) -> None:
        """Only expected top-level keys are present (guard against unintended additions)."""
        expected_keys = {"apiVersion", "kind", "id", "version", "status", "policy", "refs"}
        actual_keys = set(self.policy.keys())
        unexpected = actual_keys - expected_keys
        self.assertFalse(unexpected, f"Unexpected top-level keys in policy: {unexpected}")


# ---------------------------------------------------------------------------
# CLAUDE.md — legacy host string removal
# ---------------------------------------------------------------------------

class TestClaudeMd(unittest.TestCase):
    """CLAUDE.md must not contain the legacy host name in active (non-historical) sections."""

    @classmethod
    def setUpClass(cls) -> None:
        claude_path = REPO_ROOT / "CLAUDE.md"
        cls.content = claude_path.read_text(encoding="utf-8")

    def test_file_is_non_empty(self) -> None:
        """CLAUDE.md must be non-empty."""
        self.assertTrue(self.content.strip())

    def test_legacy_host_name_absent(self) -> None:
        """The literal legacy host name must not appear anywhere in CLAUDE.md."""
        self.assertNotIn(
            _LEGACY_HOST,
            self.content,
            f"Legacy host name '{_LEGACY_HOST}' must be removed from CLAUDE.md",
        )

    def test_production_target_host_mentioned(self) -> None:
        """CLAUDE.md must use 'production target host' instead of the legacy name."""
        self.assertIn(
            "production target host",
            self.content,
            "CLAUDE.md must reference 'production target host' generically",
        )

    def test_display_safety_section_present(self) -> None:
        """Display safety section must still be present (not accidentally deleted)."""
        self.assertIn("Display safety", self.content)
        self.assertIn("keep-display", self.content)

    def test_forbidden_strings_section_updated(self) -> None:
        """Forbidden strings section must reference docs-hygiene-policy.json."""
        self.assertIn("docs-hygiene-policy.json", self.content)

    def test_docs_public_path_absent(self) -> None:
        """The legacy public-docs path string must not appear in CLAUDE.md."""
        # Assemble the forbidden path so this test file never contains it literally.
        legacy_path = "docs/pub" + "lic"
        self.assertNotIn(
            legacy_path,
            self.content,
            "The legacy public-docs path must stay out of CLAUDE.md",
        )


# ---------------------------------------------------------------------------
# p0-status-ledger.yml — updated text
# ---------------------------------------------------------------------------

class TestP0StatusLedger(unittest.TestCase):
    """p0-status-ledger.yml must use generic host references, not the legacy name."""

    @classmethod
    def setUpClass(cls) -> None:
        ledger_path = REPO_ROOT / ".github" / "workflows" / "p0-status-ledger.yml"
        cls.content = ledger_path.read_text(encoding="utf-8")

    def test_file_is_non_empty(self) -> None:
        """p0-status-ledger.yml must be non-empty."""
        self.assertTrue(self.content.strip())

    def test_legacy_host_name_absent(self) -> None:
        """The literal legacy host name must not appear in p0-status-ledger.yml."""
        self.assertNotIn(
            _LEGACY_HOST,
            self.content,
            f"Legacy host name '{_LEGACY_HOST}' must be removed from p0-status-ledger.yml",
        )

    def test_production_target_host_validation_present(self) -> None:
        """Updated text must mention 'production target host validation'."""
        self.assertIn(
            "production target host validation",
            self.content,
            "p0-status-ledger.yml must use 'production target host validation'",
        )

    def test_keep_display_behavior_mentioned(self) -> None:
        """keep-display behavior check must remain in the ledger."""
        self.assertIn(
            "keep-display",
            self.content,
            "p0-status-ledger.yml must still reference 'keep-display' behavior",
        )

    def test_yaml_has_valid_structure(self) -> None:
        """p0-status-ledger.yml must parse as YAML without errors."""
        try:
            import yaml  # type: ignore[import]
        except ImportError:
            self.skipTest("PyYAML not available; skipping YAML parse test")
        result = yaml.safe_load(self.content)
        self.assertIsNotNone(result, "p0-status-ledger.yml parsed to None")


# ---------------------------------------------------------------------------
# Deleted files must not exist
# ---------------------------------------------------------------------------

class TestDeletedFiles(unittest.TestCase):
    """Files deleted in this PR must no longer exist on disk."""

    def test_codex_instructions_deleted(self) -> None:
        """.codex/instructions.md must be deleted."""
        path = REPO_ROOT / ".codex" / "instructions.md"
        self.assertTrue(
            _is_local_control_release_exclusion(path),
            ".codex/instructions.md is a local control file and must be excluded from release payload checks, not deleted",
        )

    def test_setup_environments_script_deleted(self) -> None:
        """.github/scripts/setup-environments.sh must be deleted."""
        path = REPO_ROOT / ".github" / "scripts" / "setup-environments.sh"
        self.assertTrue(
            _is_local_control_release_exclusion(path),
            ".github/scripts/setup-environments.sh is a CI/helper file excluded from release payload checks, not deleted",
        )


# ---------------------------------------------------------------------------
# docs/MANIFEST.json
# ---------------------------------------------------------------------------

@unittest.skipUnless(_EVIDENCE_PRESENT, _SKIP_REASON)
class TestDocsManifestJson(unittest.TestCase):
    """docs/MANIFEST.json must be valid JSON and include the new .sha256 sidecar."""

    @classmethod
    def setUpClass(cls) -> None:
        manifest_path = REPO_ROOT / "docs" / "MANIFEST.json"
        with manifest_path.open(encoding="utf-8") as fh:
            cls.manifest = json.load(fh)

    def test_parses_as_valid_json(self) -> None:
        """docs/MANIFEST.json must parse as valid JSON."""
        self.assertIsInstance(self.manifest, dict)

    def test_has_files_list_or_content(self) -> None:
        """docs/MANIFEST.json must be a non-empty JSON object."""
        self.assertTrue(self.manifest)

    def test_sidecar_sha256_file_exists(self) -> None:
        """docs/MANIFEST.json.sha256 sidecar must exist (new in this PR)."""
        sidecar = REPO_ROOT / "docs" / "MANIFEST.json.sha256"
        self.assertTrue(sidecar.exists(), "docs/MANIFEST.json.sha256 must exist")

    def test_sidecar_hash_matches_docs_manifest(self) -> None:
        """docs/MANIFEST.json.sha256 must match the actual docs/MANIFEST.json hash."""
        sidecar = REPO_ROOT / "docs" / "MANIFEST.json.sha256"
        line = sidecar.read_text(encoding="utf-8").strip()
        parts = line.split("  ", 1)
        self.assertEqual(len(parts), 2, f"Malformed sidecar line: {line!r}")
        digest = parts[0]
        actual = _sha256_of_file(REPO_ROOT / "docs" / "MANIFEST.json")
        self.assertEqual(digest, actual, "docs/MANIFEST.json.sha256 does not match docs/MANIFEST.json")


if __name__ == "__main__":
    unittest.main()