#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_release_gate_03200_alpha.py
Zone: release/package
Version: 0.32.0.alpha
Created: 2026-05-22
Modified: 2026-05-22
Purpose: Validate the 0.32.0.alpha release-gate hygiene and documentation completeness surface.
Inputs: Active project tree, canonical docs and release metadata.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import re
import time
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = PACKAGE_ROOT.parent
EXPECTED_VERSION = "0.32.0.alpha"
CANONICAL_CHANGELOG = Path("noemaforge/docs/history/CHANGELOG.md")
QUALITY_REPORT = Path("noemaforge/docs/quality/VERIFICATION_AND_AUDIT.md")


EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "trash",
}
ARCHIVE_SUFFIXES = {".zip", ".gz", ".tgz", ".tar", ".7z", ".rar"}
ROOT_DOCS_MARKDOWN = {
    Path("noemaforge/docs/README.md"),
    Path("noemaforge/docs/Manifest.md"),
    Path("noemaforge/docs/TODO.md"),
}
FORBIDDEN_DOC_DIRS = [
    Path("noemaforge/docs/source_reports"),
    Path("noemaforge/docs/research_sources"),
    Path("noemaforge/docs/research"),
    Path("noemaforge/docs/todo"),
    Path("noemaforge/docs/patches"),
    Path("noemaforge/docs") / ("pub" + "lic"),
    Path("noemaforge/docs/wiki") / ("pub" + "lic"),
]
REQUIRED_COMPLETENESS_TOPICS = [
    "TODO-driven autonomous improvement process",
    "Release gates and completion discipline",
    "Strict Markdown/documentation hygiene",
    "Single canonical changelog/release-history policy",
    "Deep research integration policy",
    "GitHub main repository publication workflow",
    "GitHub Wiki publication workflow",
    "Windows PowerShell lessons and safe upload scripts",
    "MultiOS runtime direction",
    "Trust-adaptive governance direction",
    "Edge/TinyML/OTA direction",
    "Local-first/privacy-first constraints",
    "Clean distribution allowlist",
    "Trash/quarantine policy",
    "Executable-bit preservation",
    "Manifest/checksum regeneration and validation",
    "QA and performance test requirements",
    "Documentation completeness matrix",
    "Known blockers and next safe TODO items",
]


def _active_files(root: Path = PROJECT_ROOT) -> list[Path]:
    files: list[Path] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name not in EXCLUDED_DIRS]
        base = Path(current)
        for name in names:
            path = base / name
            if path.suffix.lower() in ARCHIVE_SUFFIXES:
                continue
            files.append(path)
    return sorted(files, key=lambda item: item.as_posix())


def _rel(path: Path) -> Path:
    return Path(path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix())


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


class ReleaseGate03200AlphaTests(unittest.TestCase):
    def test_version_metadata_uses_alpha_release_spelling(self) -> None:
        for rel in [Path("VERSION"), Path("noemaforge/VERSION"), Path("noemaforge/docs/VERSION")]:
            with self.subTest(path=rel):
                self.assertEqual(EXPECTED_VERSION, (PROJECT_ROOT / rel).read_text(encoding="utf-8").strip())

        release = json.loads((PROJECT_ROOT / "release.json").read_text(encoding="utf-8"))
        manifest = json.loads((PROJECT_ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(EXPECTED_VERSION, release["version"])
        self.assertEqual(EXPECTED_VERSION, manifest["runtime_base_version"])
        self.assertIn(EXPECTED_VERSION, release["summary"])

    def test_strict_markdown_placement_and_release_history_policy(self) -> None:
        markdown_files = [_rel(path) for path in _active_files() if path.suffix.lower() == ".md"]
        violations: list[str] = []
        for rel in markdown_files:
            rel_text = rel.as_posix()
            allowed = (
                rel_text.startswith("helpers/")
                or rel_text.startswith("prelaunch/")
                or rel in ROOT_DOCS_MARKDOWN
                or re.match(r"^noemaforge/docs/[^/]+/", rel_text)
            )
            if not allowed:
                violations.append(rel_text)
        self.assertEqual([], violations)

        changelog_like = [
            rel
            for rel in markdown_files
            if re.search(r"(CHANGELOG|RELEASE_NOTES|RELEASE[-_ ]?HISTORY)", rel.name, re.IGNORECASE)
        ]
        self.assertEqual([CANONICAL_CHANGELOG], changelog_like)
        self.assertTrue((PROJECT_ROOT / CANONICAL_CHANGELOG).exists())

    def test_forbidden_dirs_text_and_raw_research_files_are_absent(self) -> None:
        for rel in FORBIDDEN_DOC_DIRS:
            self.assertFalse((PROJECT_ROOT / rel).exists(), str(rel))

        raw_markers = ["deep" + "-research", "source" + "-report", "research" + "-dump"]
        raw_matches = [
            _rel(path).as_posix()
            for path in _active_files()
            if path.suffix.lower() == ".md" and any(marker in path.name.lower() for marker in raw_markers)
        ]
        self.assertEqual([], raw_matches)

        forbidden_tokens = ["BigBro" + "-BOS", "docs/" + "public", "noemaforge/docs/" + "public", "OUT" + "DATED"]
        matches: list[str] = []
        for path in _active_files():
            if path.suffix.lower() in ARCHIVE_SUFFIXES:
                continue
            text = _read_text(path)
            for token in forbidden_tokens:
                if token in text:
                    matches.append(f"{_rel(path).as_posix()}:{token}")
        self.assertEqual([], matches)

    def test_completeness_matrix_covers_required_topics(self) -> None:
        report = _read_text(PROJECT_ROOT / QUALITY_REPORT)
        self.assertIn("Release-gate report: 0.32.0.alpha", report)
        for topic in REQUIRED_COMPLETENESS_TOPICS:
            with self.subTest(topic=topic):
                self.assertIn(topic, report)
        matrix_lines = [line for line in report.splitlines() if line.startswith("|")]
        current_lines = [line for line in matrix_lines if any(topic in line for topic in REQUIRED_COMPLETENESS_TOPICS)]
        self.assertGreaterEqual(len(current_lines), len(REQUIRED_COMPLETENESS_TOPICS))
        self.assertFalse(any("| missing |" in line.lower() or "| partial |" in line.lower() for line in current_lines))

    def test_wiki_pages_are_not_link_only_stubs(self) -> None:
        wiki_files = [path for path in _active_files(PACKAGE_ROOT / "docs" / "wiki") if path.suffix.lower() == ".md"]
        sparse: list[str] = []
        for path in wiki_files:
            text = _read_text(path)
            words = re.findall(r"\b[\w-]+\b", text)
            link_lines = [line for line in text.splitlines() if re.search(r"\[[^\]]+\]\([^)]+\)", line)]
            prose_lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith(("#", "-", "|"))]
            if len(words) < 50 or (link_lines and len(prose_lines) < 2):
                sparse.append(_rel(path).as_posix())
        self.assertEqual([], sparse)

    def test_release_gate_scan_stays_bounded(self) -> None:
        started = time.perf_counter()
        files = _active_files()
        markdown = sum(1 for path in files if path.suffix.lower() == ".md")
        elapsed = time.perf_counter() - started
        self.assertGreater(len(files), 1500)
        self.assertGreater(markdown, 100)
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
