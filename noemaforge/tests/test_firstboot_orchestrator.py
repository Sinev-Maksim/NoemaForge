#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_orchestrator.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Coordinate first-start model inventory, tournament, staffing and epoch safety checks.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: tests/test_firstboot_orchestrator.py
# Purpose: Helper / validation script 'test_firstboot_orchestrator.py'.
# Invoked by / imported from:
#   - direct operator invocation or test discovery
# Public API / entry functions:
#   - module-level helpers / CLI entrypoint
# Inputs:
#   - local filesystem paths, command-line arguments, and NoemaForge runtime/install state
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-13 (manual)
# === End NoemaForge Autodoc File Header ===


import os
import sys
import json
from pathlib import Path

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import firstboot_orchestrator


def test_main_alias_materialization_synchronizes_active_manifests(tmp_path: Path, monkeypatch):
    modelstore = tmp_path / "modelstore"
    src = modelstore / "models" / "qwen2-5-coder-0-5b-instruct-q4-k-m"
    src.mkdir(parents=True)
    artifact = tmp_path / "artifacts" / "qwen-0.5b.gguf"
    artifact.parent.mkdir()
    artifact.write_bytes(b"model")
    os.symlink(str(artifact), src / "model.gguf")
    (src / "manifest.yaml").write_text(
        "model_id: qwen2-5-coder-0-5b-instruct-q4-k-m\n"
        "display_name: Qwen 2.5 Coder 0.5B\n"
        "source: stale-relative.gguf\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(firstboot_orchestrator.runtime_safety, "validate_modelstore_backend", lambda *a, **k: (True, "", {}))

    result = firstboot_orchestrator._ensure_main_alias(str(modelstore), "qwen2-5-coder-0-5b-instruct-q4-k-m")

    assert result["aliased"] is True
    main = modelstore / "models" / "main"
    assert (main / "model.gguf").resolve() == artifact
    assert (main / "manifest.yaml").is_file()
    for name in ["noemaforge-model.json", "brainos-model.json"]:
        manifest = json.loads((main / name).read_text(encoding="utf-8"))
        assert manifest["model_id"] == "qwen2-5-coder-0-5b-instruct-q4-k-m"
        assert manifest["display_name"] == "Qwen 2.5 Coder 0.5B"
        assert manifest["source"] == str(artifact)
        assert manifest["selection_provenance"]["reason"] == "firstboot_selected_main_model"


def test_main_alias_replaces_stale_legacy_manifest(tmp_path: Path, monkeypatch):
    modelstore = tmp_path / "modelstore"
    src = modelstore / "models" / "qwen2-5-coder-0-5b-instruct-q4-k-m"
    main = modelstore / "models" / "main"
    src.mkdir(parents=True)
    main.mkdir(parents=True)
    artifact = tmp_path / "artifacts" / "qwen-0.5b.gguf"
    artifact.parent.mkdir()
    artifact.write_bytes(b"new-model")
    os.symlink(str(artifact), src / "model.gguf")
    (src / "manifest.yaml").write_text("display_name: Qwen 0.5B\n", encoding="utf-8")
    (main / "brainos-model.json").write_text(json.dumps({"model_id": "old-3b", "source": "/old/3b.gguf"}), encoding="utf-8")
    monkeypatch.setattr(firstboot_orchestrator.runtime_safety, "validate_modelstore_backend", lambda *a, **k: (True, "", {}))

    result = firstboot_orchestrator._ensure_main_alias(str(modelstore), "qwen2-5-coder-0-5b-instruct-q4-k-m")

    legacy = json.loads((main / "brainos-model.json").read_text(encoding="utf-8"))
    assert legacy["model_id"] == "qwen2-5-coder-0-5b-instruct-q4-k-m"
    assert legacy["source"] == str(artifact)
    assert "old-3b" not in (main / "brainos-model.json").read_text(encoding="utf-8")
    rollback = Path(result["rollback_dir"])
    assert json.loads((rollback / "brainos-model.json").read_text(encoding="utf-8"))["model_id"] == "old-3b"


def test_main_alias_restores_previous_active_files_on_replace_failure(tmp_path: Path, monkeypatch):
    modelstore = tmp_path / "modelstore"
    src = modelstore / "models" / "qwen2-5-coder-0-5b-instruct-q4-k-m"
    main = modelstore / "models" / "main"
    src.mkdir(parents=True)
    main.mkdir(parents=True)
    new_artifact = tmp_path / "artifacts" / "qwen-0.5b.gguf"
    old_artifact = tmp_path / "artifacts" / "old.gguf"
    new_artifact.parent.mkdir()
    new_artifact.write_bytes(b"new-model")
    old_artifact.write_bytes(b"old-model")
    os.symlink(str(new_artifact), src / "model.gguf")
    os.symlink(str(old_artifact), main / "model.gguf")
    (src / "manifest.yaml").write_text("display_name: Qwen 0.5B\n", encoding="utf-8")
    (main / "brainos-model.json").write_text(json.dumps({"model_id": "old-3b", "source": str(old_artifact)}), encoding="utf-8")
    monkeypatch.setattr(firstboot_orchestrator.runtime_safety, "validate_modelstore_backend", lambda *a, **k: (True, "", {}))

    real_replace = firstboot_orchestrator.os.replace
    calls = {"count": 0}

    def fail_second_replace(src_path, dst_path):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("injected replace failure")
        return real_replace(src_path, dst_path)

    monkeypatch.setattr(firstboot_orchestrator.os, "replace", fail_second_replace)

    result = firstboot_orchestrator._ensure_main_alias(str(modelstore), "qwen2-5-coder-0-5b-instruct-q4-k-m")

    assert result["aliased"] is False
    assert result["reason"] == "main_alias_materialization_failed"
    assert "injected replace failure" in result["error"]
    assert (main / "model.gguf").resolve() == old_artifact
    assert json.loads((main / "brainos-model.json").read_text(encoding="utf-8"))["model_id"] == "old-3b"
    assert not (main / ".materialize-main.lock").exists()
    assert not any((main / ".staging").glob("alias-materialization-*"))


def test_threshold_pass_true():
    assert firstboot_orchestrator._threshold_pass(
        {'pass_rate': 0.7, 'json_parse_rate': 0.9, 'quality_score': 0.6},
        {'pass_rate': 0.6, 'json_parse_rate': 0.8, 'quality_score': 0.55},
    )


def test_profile_available_missing_required(tmp_path: Path):
    ok, missing = firstboot_orchestrator._profile_available('x', {'x': {'available_when': [{'path': str(tmp_path / 'missing'), 'kind': 'file'}]}})
    assert ok is False
    assert missing


def test_discover_gguf_shortlist(tmp_path: Path):
    root = tmp_path / 'Vault' / 'models-gguf'
    root.mkdir(parents=True)
    (root / 'qwen.gguf').write_bytes(b'1')
    (root / 'phi.gguf').write_bytes(b'12')
    out = firstboot_orchestrator._discover_gguf(str(tmp_path / 'Vault'), include_download_mirror=False, shortlist=['phi'], candidate_limit=10)
    assert len(out) == 1
    assert out[0].endswith('phi.gguf')


def test_discover_gguf_filters_non_head_shards(tmp_path: Path):
    root = tmp_path / 'Vault' / 'models-gguf'
    root.mkdir(parents=True)
    (root / 'model-00001-of-00003.gguf').write_bytes(b'head')
    (root / 'model-00002-of-00003.gguf').write_bytes(b'tail')
    (root / 'model-00003-of-00003.gguf').write_bytes(b'tail')
    out = firstboot_orchestrator._discover_gguf(str(tmp_path / 'Vault'), candidate_limit=10)
    assert len(out) == 1
    assert out[0].endswith('model-00001-of-00003.gguf')
    assert '00002-of' not in out[0]
