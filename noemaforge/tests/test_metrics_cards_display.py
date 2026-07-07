"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_metrics_cards_display.py
Zone: tests/gui
Version: 0.33.0
Created: 2026-06-19
Purpose: Verify D-001 (hardware card human units) and D-004 (product metrics
  labeled rows) — both metrics cards no longer render raw JSON in the default view.
Inputs: Source file noemaforge/templates/pipeline-dashboard/app.js.
Outputs: Pass/fail assertions.
Tests: py -3 -m unittest noemaforge/tests/test_metrics_cards_display.py -v
=== End NoemaForge File Header ===
"""
import re
import unittest
from pathlib import Path

APP_JS = (Path(__file__).resolve().parents[1]
          / "templates" / "pipeline-dashboard" / "app.js")


def _src():
    return APP_JS.read_text(encoding="utf-8")


class TestHardwareCardD001(unittest.TestCase):
    """D-001: hardware card uses human units (GiB, percent), not raw JSON."""

    def setUp(self):
        self.src = _src()

    def test_gib_helper_exists(self):
        self.assertIn("function _gib(", self.src)

    def test_pct_helper_exists(self):
        self.assertIn("function _pct(", self.src)

    def test_fmt_hardware_helper_exists(self):
        self.assertIn("function _fmtHardware(", self.src)

    def test_hardware_metrics_uses_fmt_helper(self):
        # The assignment must call _fmtHardware, not JSON.stringify.
        m = re.search(r"el\('hardware-metrics'\)\.textContent\s*=\s*(.+)", self.src)
        self.assertIsNotNone(m, "hardware-metrics assignment not found")
        rhs = m.group(1)
        self.assertIn("_fmtHardware", rhs)
        self.assertNotIn("JSON.stringify", rhs)

    def test_gib_conversion_divides_bytes(self):
        # _gib must divide by 1073741824 (2^30).
        self.assertIn("1073741824", self.src)

    def test_fmt_hardware_shows_ram_row(self):
        m = re.search(r'function _fmtHardware\(hw\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "_fmtHardware body not found")
        body = m.group(1)
        self.assertIn("RAM", body)
        self.assertIn("Swap", body)

    def test_fmt_hardware_no_json_stringify(self):
        m = re.search(r'function _fmtHardware\(hw\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "_fmtHardware body not found")
        self.assertNotIn("JSON.stringify", m.group(1))

    def test_fmt_hardware_maps_meminfo_and_gpu_fields(self):
        self.assertIn("function _memoryBucket(", self.src)
        self.assertIn("function _parseGpuCsv(", self.src)
        self.assertIn("function _fmtGpuRows(", self.src)
        self.assertIn("temperature_c", self.src)
        self.assertIn("memory_used_mib", self.src)
        self.assertIn("memory_total_mib", self.src)


class TestProductMetricsCardD004(unittest.TestCase):
    """D-004: product metrics card shows labeled rows, not raw JSON."""

    def setUp(self):
        self.src = _src()

    def test_fmt_product_metrics_helper_exists(self):
        self.assertIn("function _fmtProductMetrics(", self.src)

    def test_product_metrics_uses_fmt_helper(self):
        m = re.search(r"el\('product-metrics'\)\.textContent\s*=\s*(.+)", self.src)
        self.assertIsNotNone(m, "product-metrics assignment not found")
        rhs = m.group(1)
        self.assertIn("_fmtProductMetrics", rhs)
        self.assertNotIn("JSON.stringify", rhs)

    def test_fmt_product_shows_model_row(self):
        m = re.search(r'function _fmtProductMetrics\(prod\)\s*\{(.+?)\n\}',
                      self.src, re.DOTALL)
        self.assertIsNotNone(m, "_fmtProductMetrics body not found")
        body = m.group(1)
        self.assertIn("Selected model", body)

    def test_fmt_product_shows_pass_rate(self):
        m = re.search(r'function _fmtProductMetrics\(prod\)\s*\{(.+?)\n\}',
                      self.src, re.DOTALL)
        self.assertIsNotNone(m)
        self.assertIn("Pass rate", m.group(1))

    def test_fmt_product_shows_quality_score(self):
        m = re.search(r'function _fmtProductMetrics\(prod\)\s*\{(.+?)\n\}',
                      self.src, re.DOTALL)
        self.assertIsNotNone(m)
        self.assertIn("Quality score", m.group(1))

    def test_fmt_product_shows_avg_latency(self):
        m = re.search(r'function _fmtProductMetrics\(prod\)\s*\{(.+?)\n\}',
                      self.src, re.DOTALL)
        self.assertIsNotNone(m)
        self.assertIn("Avg latency", m.group(1))

    def test_fmt_product_no_json_stringify(self):
        m = re.search(r'function _fmtProductMetrics\(prod\)\s*\{(.+?)\n\}',
                      self.src, re.DOTALL)
        self.assertIsNotNone(m)
        self.assertNotIn("JSON.stringify", m.group(1))

    def test_metric_row_helper_pads_label(self):
        self.assertIn("function _metricRow(", self.src)
        m = re.search(r'function _metricRow\(label, value\)\s*\{(.+?)\}', self.src)
        self.assertIsNotNone(m, "_metricRow body not found")
        self.assertIn("padEnd", m.group(1))

    def test_software_card_explains_missing_git_metadata(self):
        self.assertIn("Git metadata:", self.src)
        self.assertIn("git_metadata_reason", self.src)
        self.assertIn("package/release install metadata only", self.src)


if __name__ == "__main__":
    unittest.main()
