from pathlib import Path
import tempfile
import subprocess
import sys

LINTER = Path(__file__).parents[1] / "lint" / "guardrails_lint.py"

def run_case(text: str):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "x.ps1").write_text(text, encoding="utf-8")
        p = subprocess.run([sys.executable, str(LINTER), str(root)], capture_output=True, text=True)
        return p.returncode, p.stdout

def test_rejects_prompt_in_argv():
    rc, out = run_case("$arguments += $prompt\nSTAGNATION_LIMIT_PER_TASK\nTRAVERSAL_DEPTH_LIMIT\nREADY_SIGNAL\n")
    assert rc != 0 and "prompt_in_argv" in out

def test_rejects_host_default_stdin_writer():
    rc, out = run_case("$process.StandardInput.Write($Prompt)\nSTAGNATION_LIMIT_PER_TASK\nTRAVERSAL_DEPTH_LIMIT\nREADY_SIGNAL\nAGENT_PROMPT_TRANSPORT=stdin\n")
    assert rc != 0 and "host_default_stdin_text" in out
