from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[2]
FULL_SHA_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _load_workflow(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in document and "on" not in document:
        document["on"] = document.pop(True)
    return document


def _uses_references(value: Any) -> list[str]:
    if isinstance(value, dict):
        references = [value["uses"]] if isinstance(value.get("uses"), str) else []
        for nested in value.values():
            references.extend(_uses_references(nested))
        return references
    if isinstance(value, list):
        references: list[str] = []
        for nested in value:
            references.extend(_uses_references(nested))
        return references
    return []


class SecurityAutomationWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_path = REPO / ".github" / "workflows" / "semgrep.yml"
        cls.workflow_text = cls.workflow_path.read_text(encoding="utf-8")
        cls.workflow = _load_workflow(cls.workflow_path)
        cls.job = cls.workflow["jobs"]["scan"]
        cls.steps = cls.job["steps"]
        cls.dependabot = yaml.safe_load(
            (REPO / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        )

    def test_dependabot_tracks_only_repository_ecosystems(self) -> None:
        updates = self.dependabot["updates"]
        self.assertEqual(
            {update["package-ecosystem"] for update in updates},
            {"github-actions", "pip"},
        )
        for update in updates:
            self.assertEqual(update["directory"], "/")
            self.assertEqual(update["schedule"]["interval"], "weekly")
            self.assertGreater(update["open-pull-requests-limit"], 0)
            self.assertTrue(update["groups"])

    def test_triggers_are_bounded_and_weekly(self) -> None:
        triggers = self.workflow["on"]
        expected_branches = ["main", "release/0.33.0-dev"]
        self.assertEqual(triggers["pull_request"]["branches"], expected_branches)
        self.assertEqual(triggers["push"]["branches"], expected_branches)
        self.assertEqual(len(triggers["schedule"]), 1)
        self.assertIn("workflow_dispatch", triggers)

    def test_permissions_are_least_privilege(self) -> None:
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertEqual(
            self.job["permissions"],
            {"contents": "read", "security-events": "write"},
        )
        self.assertLessEqual(self.job["timeout-minutes"], 20)

    def test_all_actions_are_pinned_to_full_commit_shas(self) -> None:
        references = _uses_references(self.workflow)
        self.assertTrue(references)
        self.assertTrue(all(FULL_SHA_ACTION.fullmatch(ref) for ref in references))

    def test_checkouts_do_not_persist_credentials(self) -> None:
        checkouts = [
            step
            for step in self.steps
            if step.get("uses", "").startswith("actions/checkout@")
        ]
        self.assertEqual(len(checkouts), 2)
        self.assertTrue(
            all(
                step.get("with", {}).get("persist-credentials") is False
                for step in checkouts
            )
        )

    def test_semgrep_and_rules_are_immutable(self) -> None:
        self.assertEqual(
            self.job["container"]["image"],
            "semgrep/semgrep:1.166.0@sha256:"
            "c180f0c93a17b420c0af5006214a29d3c747c5459c732b740191adf657dd0068",
        )
        rules_step = next(
            step
            for step in self.steps
            if step.get("with", {}).get("repository") == "semgrep/semgrep-rules"
        )
        self.assertEqual(
            rules_step["with"]["ref"],
            "d41fb34cf74466e2878af5f268ebf54466a04541",
        )
        self.assertEqual(rules_step["with"]["path"], ".semgrep-rules")
        self.assertFalse(rules_step["with"]["persist-credentials"])

    def test_scan_uses_local_security_configs_and_sarif(self) -> None:
        command = next(step["run"] for step in self.steps if "run" in step)
        for language in ("python", "javascript", "typescript", "go"):
            self.assertIn(f"--config .semgrep-rules/{language}", command)
        for option in (
            "--exclude .semgrep-rules",
            "--severity ERROR",
            "--sarif",
            "--output semgrep.sarif",
            "--metrics=off",
        ):
            self.assertIn(option, command)
        self.assertNotIn("--config auto", command)

    def test_sarif_uses_codeql_v4_uploader(self) -> None:
        upload = next(
            step for step in self.steps if step.get("name") == "Upload Semgrep SARIF"
        )
        self.assertEqual(
            upload["uses"],
            "github/codeql-action/upload-sarif@8aad20d150bbac5944a9f9d289da16a4b0d87c1e",
        )
        self.assertEqual(upload["with"]["category"], "semgrep-ce")

    def test_sarif_artifact_is_short_lived_and_sha_pinned(self) -> None:
        artifact = next(
            step
            for step in self.steps
            if step.get("name") == "Upload Semgrep SARIF artifact"
        )
        self.assertEqual(
            artifact["uses"],
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
        )
        self.assertEqual(artifact["with"]["name"], "semgrep-sarif-${{ github.sha }}")
        self.assertEqual(artifact["with"]["path"], "semgrep.sarif")
        self.assertEqual(artifact["with"]["retention-days"], 7)
        self.assertEqual(artifact["with"]["if-no-files-found"], "error")

    def test_forbidden_automation_is_absent(self) -> None:
        lowered = self.workflow_text.lower()
        self.assertNotIn("issues: write", lowered)
        self.assertNotIn("github-script", lowered)
        self.assertNotIn("returntocorp/semgrep-action", lowered)
        self.assertFalse((REPO / ".github" / "workflows" / "codeql.yml").exists())


if __name__ == "__main__":
    unittest.main()
