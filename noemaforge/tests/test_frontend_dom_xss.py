import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendDomXssTests(unittest.TestCase):
    def test_dashboard_renderers_treat_api_fields_as_text(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for frontend DOM behavior tests")
        result = subprocess.run(
            [node, "--test", str(ROOT / "tests" / "frontend_dom_xss.test.js")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
