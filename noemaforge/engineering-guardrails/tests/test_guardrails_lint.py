from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile

LINTER = Path(__file__).parents[1] / "lint" / "guardrails_lint.py"


def run_case(files: dict[str, str]):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        process = subprocess.run(
            [sys.executable, str(LINTER), str(root)],
            capture_output=True,
            text=True,
        )
        return process.returncode, process.stdout


def base_markers() -> str:
    return "STAGNATION_LIMIT_PER_TASK\nTRAVERSAL_DEPTH_LIMIT\nREADY_SIGNAL\n"


def test_rejects_prompt_in_argv():
    rc, out = run_case({"x.ps1": "$arguments += $prompt\n" + base_markers()})
    assert rc != 0 and "prompt_in_argv" in out


def test_rejects_host_default_stdin_writer():
    rc, out = run_case(
        {
            "x.ps1": (
                "$process.StandardInput.Write($Prompt)\n"
                + base_markers()
                + "AGENT_PROMPT_TRANSPORT=stdin\n"
            )
        }
    )
    assert rc != 0 and "host_default_stdin_text" in out


def test_rejects_agent_mode_contract_drift():
    controller = (
        base_markers()
        + "AGENT_PROTOCOL_PARITY_PREFLIGHT\n"
        + "PACKAGE_CLOSURE_PREFLIGHT\n"
        + '-Mode "transport"\n'
    )
    protocol = {
        "apiVersion": "noemaforge.agent-protocol/v1",
        "modes": ["implementer", "diagnostic"],
    }
    requirements = {
        "apiVersion": "noemaforge.package-requirements/v1",
        "requiredFiles": [],
    }
    rc, out = run_case(
        {
            "RUN_AGENT_SELF_HEAL.ps1": controller,
            "AGENT_PROTOCOL.json": json.dumps(protocol),
            "PACKAGE_REQUIREMENTS.json": json.dumps(requirements),
        }
    )
    assert rc != 0 and "AGENT_MODE_CALLSITE_OUTSIDE_CONTRACT" in out


def test_rejects_incomplete_package_dependency_closure():
    controller = (
        base_markers()
        + "AGENT_PROTOCOL_PARITY_PREFLIGHT\n"
        + "PACKAGE_CLOSURE_PREFLIGHT\n"
    )
    protocol = {
        "apiVersion": "noemaforge.agent-protocol/v1",
        "modes": ["implementer"],
    }
    requirements = {
        "apiVersion": "noemaforge.package-requirements/v1",
        "requiredFiles": [
            {
                "path": "payload/noemaforge/src/runtime.py",
                "sha256": "0" * 64,
            }
        ],
    }
    rc, out = run_case(
        {
            "RUN_AGENT_SELF_HEAL.ps1": controller,
            "AGENT_PROTOCOL.json": json.dumps(protocol),
            "PACKAGE_REQUIREMENTS.json": json.dumps(requirements),
        }
    )
    assert rc != 0 and "MISSING_REQUIRED_FILE" in out


def test_rejects_wrong_required_file_hash():
    controller = (
        base_markers()
        + "AGENT_PROTOCOL_PARITY_PREFLIGHT\n"
        + "PACKAGE_CLOSURE_PREFLIGHT\n"
    )
    protocol = {
        "apiVersion": "noemaforge.agent-protocol/v1",
        "modes": ["implementer"],
    }
    payload = "hello\n"
    requirements = {
        "apiVersion": "noemaforge.package-requirements/v1",
        "requiredFiles": [
            {
                "path": "payload/runtime.py",
                "sha256": hashlib.sha256(b"different").hexdigest(),
            }
        ],
    }
    rc, out = run_case(
        {
            "RUN_AGENT_SELF_HEAL.ps1": controller,
            "AGENT_PROTOCOL.json": json.dumps(protocol),
            "PACKAGE_REQUIREMENTS.json": json.dumps(requirements),
            "payload/runtime.py": payload,
        }
    )
    assert rc != 0 and "REQUIRED_FILE_SHA_MISMATCH" in out


def test_rejects_review_verdict_stderr_contamination():
    controller = (
        base_markers()
        + "AGENT_PROTOCOL_PARITY_PREFLIGHT\nPACKAGE_CLOSURE_PREFLIGHT\n"
        + '$reviewText = $reviewer.stdout + "`n" + $reviewer.stderr\n'
    )
    protocol = {"apiVersion": "noemaforge.agent-protocol/v1", "modes": ["reviewer"]}
    requirements = {"apiVersion": "noemaforge.package-requirements/v1", "requiredFiles": []}
    rc, out = run_case(
        {
            "RUN_AGENT_SELF_HEAL.ps1": controller,
            "AGENT_PROTOCOL.json": json.dumps(protocol),
            "PACKAGE_REQUIREMENTS.json": json.dumps(requirements),
        }
    )
    assert rc != 0 and "review_stdout_stderr_concat" in out


def test_rejects_controller_without_review_and_plane_guards():
    controller = base_markers() + "AGENT_PROTOCOL_PARITY_PREFLIGHT\nPACKAGE_CLOSURE_PREFLIGHT\n"
    protocol = {"apiVersion": "noemaforge.agent-protocol/v1", "modes": ["reviewer"]}
    requirements = {"apiVersion": "noemaforge.package-requirements/v1", "requiredFiles": []}
    rc, out = run_case(
        {
            "RUN_AGENT_SELF_HEAL.ps1": controller,
            "AGENT_PROTOCOL.json": json.dumps(protocol),
            "PACKAGE_REQUIREMENTS.json": json.dumps(requirements),
        }
    )
    assert rc != 0
    assert "MISSING_LOCAL_REVIEW_RESULT_PARSER" in out
    assert "MISSING_CONTROL_PLANE_RETRY_BOUNDARY" in out
    assert "MISSING_PROPOSAL_EOL_NORMALIZATION" in out
