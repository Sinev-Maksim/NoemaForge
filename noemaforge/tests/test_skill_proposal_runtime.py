#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import skill_proposal_runtime as spr


class SkillProposalRuntimeTests(unittest.TestCase):
    def test_frontmatter_and_sections_become_quarantine_only_proposal(self) -> None:
        text = """---
id: external_writer
title: External Writer
description: Drafts local notes for review.
requested_tools:
  - docs.search
  - file.read
requested_permissions: [workspace.read, artifacts.write]
---
# Instructions
Read local context and draft a review note.

## Constraints
Do not execute shell commands.
"""

        proposal = spr.build_skill_proposal_from_text(text, source_uri="quarantine://incoming/SKILL.md")

        self.assertTrue(proposal["ok"], proposal)
        self.assertEqual("SkillProposal", proposal["kind"])
        self.assertEqual("quarantine_only", proposal["import_mode"])
        self.assertEqual("quarantined", proposal["activation_state"])
        self.assertTrue(proposal["safety"]["no_code_execution"])
        self.assertTrue(proposal["safety"]["no_active_registration"])
        self.assertEqual(["docs.search", "file.read"], proposal["requested_tools"])
        self.assertEqual(["workspace.read", "artifacts.write"], proposal["requested_permissions"])
        self.assertEqual("External Writer", proposal["parsed_skill"]["title"])
        self.assertIn("Instructions", [section["title"] for section in proposal["parsed_skill"]["sections"]])

    def test_missing_review_fields_warns_but_still_stays_quarantined(self) -> None:
        proposal = spr.build_skill_proposal_from_text("# Instructions\nOnly prose.\n")

        self.assertTrue(proposal["ok"], proposal)
        self.assertEqual("quarantined", proposal["decision"])
        self.assertIn("requested_tools_empty", proposal["warnings"])
        self.assertIn("requested_permissions_empty", proposal["warnings"])

    def test_size_and_section_limits_fail_closed_without_activation(self) -> None:
        headings = "\n".join(f"## Section {idx}\nbody" for idx in range(spr.MAX_SECTIONS + 4))
        text = "---\nid: huge\n---\n" + headings + ("x" * (spr.MAX_SKILL_BYTES + 1))

        proposal = spr.build_skill_proposal_from_text(text)

        self.assertFalse(proposal["ok"])
        self.assertIn("skill_md_exceeds_size_limit", proposal["failures"])
        self.assertIn("section_count_exceeds_limit", proposal["failures"])
        self.assertEqual("quarantine_only", proposal["import_mode"])
        self.assertTrue(proposal["safety"]["requires_epoch_before_activation"])

    def test_write_quarantine_proposal_only_writes_under_skill_proposals(self) -> None:
        proposal = spr.build_skill_proposal_from_text("---\nid: demo\n---\n# Instructions\nReview only.\n")
        with tempfile.TemporaryDirectory(prefix="nf_skill_proposal_") as td:
            out = spr.write_quarantine_proposal(proposal, td)

            self.assertEqual(Path(td) / "skill_proposals", out.parent)
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual("demo", saved["proposal_id"])
            self.assertEqual("quarantined", saved["activation_state"])


if __name__ == "__main__":
    unittest.main()
