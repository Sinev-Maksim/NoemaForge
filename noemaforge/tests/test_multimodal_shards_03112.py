"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_multimodal_shards_03112.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
import json
import os
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2]
ROOT = PACKAGE / "noemaforge"
PYTHON = os.environ.get("NOEMAFORGE_TEST_PYTHON", "/usr/bin/python3")


def test_multimodal_scan_excludes_non_head_gguf_shards(tmp_path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    (vault / "model-00001-of-00003.gguf").write_bytes(b"head")
    (vault / "model-00002-of-00003.gguf").write_bytes(b"tail2")
    (vault / "model-00003-of-00003.gguf").write_bytes(b"tail3")
    (vault / "musicgen.safetensors").write_bytes(b"music")
    proc = subprocess.run([
        PYTHON, str(ROOT / "src" / "multimodal_runtime.py"),
        "--root", str(ROOT), "--vault", str(vault), "--json", "scan",
    ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    names = {item["name"] for item in doc["entries"]}
    excluded = {item["name"] for item in doc["excluded_non_head_shards"]}
    assert "model-00001-of-00003.gguf" in names
    assert "model-00002-of-00003.gguf" not in names
    assert "model-00003-of-00003.gguf" not in names
    assert excluded == {"model-00002-of-00003.gguf", "model-00003-of-00003.gguf"}
    assert doc["capabilities"]["text_llm_gguf"] == 1
    assert doc["capabilities"]["music_generation"] == 1
