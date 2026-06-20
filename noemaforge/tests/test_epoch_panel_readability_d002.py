"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_epoch_panel_readability_d002.py
Zone: tests/gui
Version: 0.33.0
Created: 2026-06-19
Purpose: Verify D-002 — epoch/model-selection panel is operator-readable:
  tooltips on all state fields, human-readable staffing state, full model path
  on hover, consistent progress numbers, plan mode with date.
Inputs: noemaforge/templates/pipeline-dashboard/app.js, index.html.
Outputs: Pass/fail assertions.
Tests: py -3 -m unittest noemaforge/tests/test_epoch_panel_readability_d002.py -v
=== End NoemaForge File Header ===
"""
import re
import unittest
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "templates" / "pipeline-dashboard"
APP_JS = DASH / "app.js"
INDEX_HTML = DASH / "index.html"


def _src():
    return APP_JS.read_text(encoding="utf-8")


def _html():
    return INDEX_HTML.read_text(encoding="utf-8")


class TestHumanStaffingState(unittest.TestCase):
    """_humanStaffingState() maps raw identifiers to readable labels."""

    def setUp(self):
        self.src = _src()

    def test_helper_declared(self):
        self.assertIn("function _humanStaffingState(", self.src)

    def test_staffing_labels_map_declared(self):
        self.assertIn("_STAFFING_LABELS", self.src)

    def test_selected_state_mapped(self):
        self.assertIn("Model selected", self.src)

    def test_degraded_selected_mapped(self):
        self.assertIn("degraded_selected", self.src)
        self.assertIn("degraded", self.src.lower())

    def test_no_further_improvement_mapped(self):
        self.assertIn("no_further_improvement_found", self.src)

    def test_selecting_state_mapped(self):
        self.assertIn("selecting", self.src)


class TestRefreshEpochTooltips(unittest.TestCase):
    """refreshEpoch() sets .title on all epoch elements."""

    def setUp(self):
        m = re.search(r'async function refreshEpoch\(showMessage=false\)\s*\{(.+?)\n\}', _src(), re.DOTALL)
        self.body = m.group(1) if m else ""
        self.assertNotEqual(self.body, "", "refreshEpoch body not found")

    def test_current_model_has_title(self):
        self.assertIn("epoch-current-model", self.body)
        self.assertIn(".title", self.body)

    def test_full_model_path_in_title(self):
        self.assertIn("fullModel", self.body)
        self.assertRegex(self.body, r"epoch-current-model.*?\.title\s*=")

    def test_staffing_has_title(self):
        self.assertIn("epoch-staffing", self.body)
        self.assertRegex(self.body, r"epoch-staffing.*?\.title\s*=")

    def test_progress_has_title(self):
        self.assertIn("epoch-progress", self.body)
        self.assertRegex(self.body, r"epoch-progress.*?\.title\s*=")

    def test_latest_plan_has_title(self):
        self.assertIn("epoch-latest-plan", self.body)
        self.assertRegex(self.body, r"epoch-latest-plan.*?\.title\s*=")

    def test_status_pill_has_title(self):
        self.assertIn("epoch-status-pill", self.body)
        self.assertRegex(self.body, r"epoch-status-pill.*?\.title\s*=")

    def test_human_staffing_used_in_display(self):
        self.assertIn("_humanStaffingState", self.body)

    def test_plan_includes_date(self):
        self.assertIn("toLocaleDateString", self.body)

    def test_progress_separates_tested_failed_remaining(self):
        # Tooltip text must show failed and remaining separately.
        self.assertIn("Failed:", self.body)
        self.assertIn("Remaining:", self.body)

    def test_apply_available_in_plan_tooltip(self):
        self.assertIn("Apply available", self.body)

    def test_show_message_uses_human_label(self):
        self.assertIn("_humanStaffingState(staffState)", self.body)


class TestEpochGridLabels(unittest.TestCase):
    """index.html epoch grid labels must be operator-readable, not raw API keys."""

    def setUp(self):
        self.html = _html()

    def test_active_model_label(self):
        self.assertIn("Active model", self.html)

    def test_selection_state_label(self):
        self.assertIn("Selection state", self.html)

    def test_candidates_tested_label(self):
        self.assertIn("Candidates tested", self.html)

    def test_last_selection_plan_label(self):
        self.assertIn("Last selection plan", self.html)

    def test_grid_cells_have_title_attrs(self):
        # Each epoch grid cell should carry a descriptive title for accessibility.
        count = self.html.count('<div title=')
        self.assertGreaterEqual(count, 4, "All 4 epoch grid cells need a title attribute")

    def test_no_raw_staffing_label(self):
        # "Staffing" (the old raw API label) should not appear as a visible label.
        self.assertNotIn(">Staffing<", self.html)

    def test_no_raw_progress_label(self):
        self.assertNotIn(">Progress<", self.html)


if __name__ == "__main__":
    unittest.main()
