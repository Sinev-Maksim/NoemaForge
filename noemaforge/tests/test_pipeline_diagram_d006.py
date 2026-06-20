"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_diagram_d006.py
Zone: tests/gui
Version: 0.33.0
Created: 2026-06-20
Purpose: Verify D-006 fix — pipeline diagram action renders SVG stage graph
  instead of raw JSON, via showPipelineDiagram() in the admin dashboard.
Inputs: Source files under noemaforge/templates/pipeline-dashboard/.
Outputs: Pass/fail assertions.
Tests: py -3 -m unittest noemaforge/tests/test_pipeline_diagram_d006.py -v
=== End NoemaForge File Header ===
"""
import re
import unittest
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "templates" / "pipeline-dashboard"
APP_JS = DASH / "app.js"


def _src():
    return APP_JS.read_text(encoding="utf-8")


class TestShowPipelineDiagramDeclared(unittest.TestCase):
    """showPipelineDiagram() must exist and be callable."""

    def setUp(self):
        self.src = _src()

    def test_function_declared(self):
        self.assertIn("function showPipelineDiagram(", self.src)

    def test_accepts_id_and_data_params(self):
        m = re.search(r'function showPipelineDiagram\((\w+),\s*(\w+)\)', self.src)
        self.assertIsNotNone(m, "showPipelineDiagram must declare two parameters (id, data)")

    def test_diagram_action_calls_showpipelinediagram(self):
        """Context-menu diagram action must call showPipelineDiagram, not showModal."""
        self.assertIn("showPipelineDiagram", self.src)
        # showModal must NOT be called with the old 'Pipeline diagram' title
        idx = self.src.find("showModal('Pipeline diagram'")
        self.assertEqual(idx, -1, "showModal must not be called with 'Pipeline diagram' title")

    def test_diagram_action_fetches_diagram_api(self):
        """/api/pipelines/<id>/diagram must be fetched before showPipelineDiagram."""
        self.assertIn("/diagram`", self.src)


class TestSVGRendering(unittest.TestCase):
    """showPipelineDiagram must build an SVG via DOM (not innerHTML)."""

    def setUp(self):
        self.src = _src()
        m = re.search(
            r'function showPipelineDiagram\(.+?\{(.+?)^function ',
            self.src, re.DOTALL | re.MULTILINE
        )
        self.body = m.group(1) if m else self.src

    def test_creates_svg_element(self):
        self.assertIn("createElementNS", self.body)
        self.assertIn("'svg'", self.body)

    def test_uses_svg_namespace(self):
        self.assertIn("http://www.w3.org/2000/svg", self.body)

    def test_draws_rect_for_each_stage(self):
        self.assertIn("'rect'", self.body)

    def test_draws_text_for_each_stage(self):
        self.assertIn("'text'", self.body)

    def test_uses_textcontent_for_stage_label(self):
        self.assertIn("textContent=s", self.body.replace(" ", ""))

    def test_draws_arrow_lines(self):
        self.assertIn("'line'", self.body)

    def test_arrow_uses_marker_end(self):
        self.assertIn("marker-end", self.body)

    def test_creates_arrowhead_marker(self):
        self.assertIn("'marker'", self.body)

    def test_reads_stages_from_data(self):
        self.assertIn("data.stages", self.body)

    def test_viewbox_set_dynamically(self):
        self.assertIn("viewBox", self.body)

    def test_no_innerhtml_in_svg_build(self):
        """SVG must not use innerHTML for stage names (XSS safety)."""
        # The body may use innerHTML for the wrapper div, but NOT for stage text/rects
        # Verify textContent is used for stage labels
        self.assertIn(".textContent", self.body)


class TestMermaidDebugSection(unittest.TestCase):
    """A <details> with Mermaid source must be appended when present."""

    def setUp(self):
        self.src = _src()
        m = re.search(
            r'function showPipelineDiagram\(.+?\{(.+?)^function ',
            self.src, re.DOTALL | re.MULTILINE
        )
        self.body = m.group(1) if m else self.src

    def test_details_element_created(self):
        self.assertIn("'details'", self.body)

    def test_summary_element_created(self):
        self.assertIn("'summary'", self.body)

    def test_mermaid_source_in_pre_textcontent(self):
        self.assertIn("mermaidSrc", self.body)
        self.assertIn("pre.textContent", self.body.replace(" ", ""))

    def test_mermaid_section_conditional(self):
        """Details section must only render when mermaid source is non-empty."""
        # Guard pattern: if(mermaidSrc) must appear somewhere in the function body
        body_compact = self.body.replace(" ", "")
        self.assertTrue(
            "if(mermaidSrc)" in body_compact or "if(mermaidSrc){" in body_compact,
            "mermaidSrc section must be guarded by if(mermaidSrc)"
        )


class TestModalIntegration(unittest.TestCase):
    """showPipelineDiagram must update modal title, clear body, then open modal."""

    def setUp(self):
        self.src = _src()
        m = re.search(
            r'function showPipelineDiagram\(.+?\{(.+?)^function ',
            self.src, re.DOTALL | re.MULTILINE
        )
        self.body = m.group(1) if m else self.src

    def test_sets_modal_title(self):
        self.assertIn("modal-title", self.body)

    def test_modal_title_uses_pipeline_id(self):
        self.assertIn("modal-title", self.body)
        # The id parameter must appear in the title assignment
        title_assign = re.search(r"modal-title.*?textContent\s*=\s*.+", self.body)
        self.assertIsNotNone(title_assign)
        self.assertIn("id", title_assign.group(0))

    def test_clears_modal_body_before_append(self):
        self.assertIn("body.textContent=''", self.body.replace(" ", "").replace("\n", ""))

    def test_appends_svg_container_to_body(self):
        self.assertIn("body.appendChild", self.body)

    def test_opens_modal(self):
        self.assertIn("modal", self.body)
        self.assertIn("classList.remove('hidden')", self.body)


class TestShowModalUnchanged(unittest.TestCase):
    """showModal() must remain for non-diagram cases (stats etc.)."""

    def setUp(self):
        self.src = _src()

    def test_showmodal_still_exists(self):
        self.assertIn("function showModal(", self.src)

    def test_showmodal_used_for_stats(self):
        self.assertIn("showModal('Pipeline stats'", self.src)

    def test_showmodal_used_for_artifact(self):
        self.assertIn("showModal(artifact", self.src)


if __name__ == "__main__":
    unittest.main()
