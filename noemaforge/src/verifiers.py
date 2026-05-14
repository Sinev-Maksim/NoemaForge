#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/verifiers.py
Zone: release/package
Version: 0.31.13.alpha
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
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/verifiers.py
# Purpose: Load the verifier catalog and run deterministic stream-level verifiers for manifests, coverage, numeric reconciliation, and artifact sanity checks.
# Invoked by / imported from:
#   - tests/test_verifiers.py
#   - tools/checker/noemaforge_check.py
# Public API / entry functions:
#   - SUPPORTED_TYPES
#   - load_catalog
#   - list_verifiers
#   - verify
#   - main
# Inputs:
#   - --epoch-dir
#   - --verifier
#   - --payload
#   - --out
#   - configs/verifiers.yaml
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (manual)
# === End NoemaForge Autodoc File Header ===

"""Deterministic verifier runtime for NoemaForge seed catalogs.

The verifier catalog has existed as configuration for streams and canaries,
but prior releases did not ship a runtime module that could execute it.
This file closes that gap with a small offline implementation that can be
used by tests, checkers, and later orchestration glue.
"""


import argparse
import json
import os
from typing import Any, Dict, List, Tuple

import yaml


DEFAULT_CATALOG_PATH = '/opt/noemaforge/configs/verifiers.yaml'
SUPPORTED_TYPES = {
    'checklist',
    'json_schema',
    'coverage',
    'sumcheck',
    'render_check',
    'mesh_sanity',
}


# === NoemaForge Autodoc Function Header ===
# Function: _load_yaml(path: str)
# Purpose: Load a YAML document from disk.
# Inputs:
#   - path: str
# Called by:
#   - load_catalog
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        obj = yaml.safe_load(f) or {}
    return obj if isinstance(obj, dict) else {}


# === NoemaForge Autodoc Function Header ===
# Function: _save_json(path: str, obj: Dict[str, Any])
# Purpose: Persist verifier output as JSON.
# Inputs:
#   - path: str
#   - obj: Dict[str, Any]
# Called by:
#   - main
# Returns / emits: None
# Side effects:
#   - creates directories
#   - writes files
# === End NoemaForge Autodoc Function Header ===
def _save_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# === NoemaForge Autodoc Function Header ===
# Function: load_catalog(epoch_dir: str = '/opt/noemaforge/configs')
# Purpose: Load and normalize the verifier catalog.
# Inputs:
#   - epoch_dir: str = '/opt/noemaforge/configs'
# Called by:
#   - list_verifiers
#   - verify
#   - tools/checker/noemaforge_check.py
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def load_catalog(epoch_dir: str = '/opt/noemaforge/configs') -> Dict[str, Any]:
    path = epoch_dir
    if os.path.isdir(epoch_dir):
        path = os.path.join(epoch_dir, 'verifiers.yaml')
    if not str(path or '').strip():
        path = DEFAULT_CATALOG_PATH
    if not os.path.exists(path):
        return {'apiVersion': 'noemaforge.verifiers/v1', 'kind': 'VerifierCatalog', 'verifiers': {}}
    doc = _load_yaml(path)
    if not isinstance(doc.get('verifiers'), dict):
        doc['verifiers'] = {}
    return doc


# === NoemaForge Autodoc Function Header ===
# Function: list_verifiers(epoch_dir: str = '/opt/noemaforge/configs')
# Purpose: Return verifier identifiers with their declared types.
# Inputs:
#   - epoch_dir: str = '/opt/noemaforge/configs'
# Called by:
#   - tests/test_verifiers.py
# Returns / emits: Dict[str, str]
# === End NoemaForge Autodoc Function Header ===
def list_verifiers(epoch_dir: str = '/opt/noemaforge/configs') -> Dict[str, str]:
    doc = load_catalog(epoch_dir)
    out: Dict[str, str] = {}
    for vid, rec in (doc.get('verifiers') or {}).items():
        if isinstance(rec, dict):
            out[str(vid)] = str(rec.get('type') or '')
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _extract_path(obj: Any, path: str)
# Purpose: Resolve a simple JSON-path-like expression such as $.a.b from Python data.
# Inputs:
#   - obj: Any
#   - path: str
# Called by:
#   - _run_sumcheck
# Returns / emits: Any
# === End NoemaForge Autodoc Function Header ===
def _extract_path(obj: Any, path: str) -> Any:
    cur = obj
    parts = [p for p in str(path or '').strip().lstrip('$').split('.') if p]
    for part in parts:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


# === NoemaForge Autodoc Function Header ===
# Function: _run_checklist(payload: Dict[str, Any], params: Dict[str, Any])
# Purpose: Verify textual outputs against simple checklist expectations.
# Inputs:
#   - payload: Dict[str, Any]
#   - params: Dict[str, Any]
# Called by:
#   - verify
# Returns / emits: Tuple[bool, Dict[str, Any]]
# === End NoemaForge Autodoc Function Header ===
def _run_checklist(payload: Dict[str, Any], params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    outputs = payload.get('outputs') if isinstance(payload.get('outputs'), list) else []
    min_outputs = int(params.get('min_outputs') or 1)
    min_lines = int(params.get('min_lines') or 1)
    required_sections = [str(x) for x in (params.get('required_sections') or [])]
    ok_outputs = len(outputs) >= min_outputs
    best_text = ''
    for rec in outputs:
        if isinstance(rec, dict):
            txt = str(rec.get('content') or '')
            if len(txt) > len(best_text):
                best_text = txt
    line_count = best_text.count('\n') + (1 if best_text else 0)
    ok_lines = line_count >= min_lines
    missing_sections = [sec for sec in required_sections if sec.lower() not in best_text.lower()]
    return ok_outputs and ok_lines and not missing_sections, {
        'output_count': len(outputs),
        'line_count': line_count,
        'missing_sections': missing_sections,
    }


# === NoemaForge Autodoc Function Header ===
# Function: _run_json_schema(payload: Dict[str, Any], params: Dict[str, Any])
# Purpose: Verify that a manifest-like payload contains required top-level keys.
# Inputs:
#   - payload: Dict[str, Any]
#   - params: Dict[str, Any]
# Called by:
#   - verify
# Returns / emits: Tuple[bool, Dict[str, Any]]
# === End NoemaForge Autodoc Function Header ===
def _run_json_schema(payload: Dict[str, Any], params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    manifest = payload.get('manifest') if isinstance(payload.get('manifest'), dict) else payload
    required_keys = [str(x) for x in (params.get('required_keys') or [])]
    missing = [k for k in required_keys if k not in manifest]
    allow_empty = bool(params.get('allow_empty', True))
    empty = False
    if not allow_empty and isinstance(manifest.get('items'), list):
        empty = len(manifest.get('items') or []) == 0
    return not missing and not empty, {'missing_keys': missing, 'empty_items': empty}


# === NoemaForge Autodoc Function Header ===
# Function: _run_coverage(payload: Dict[str, Any], params: Dict[str, Any])
# Purpose: Verify expected versus observed input coverage.
# Inputs:
#   - payload: Dict[str, Any]
#   - params: Dict[str, Any]
# Called by:
#   - verify
# Returns / emits: Tuple[bool, Dict[str, Any]]
# === End NoemaForge Autodoc Function Header ===
def _run_coverage(payload: Dict[str, Any], params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    expected = payload.get('expected_inputs') if isinstance(payload.get('expected_inputs'), list) else []
    observed = payload.get('observed_inputs') if isinstance(payload.get('observed_inputs'), list) else []
    exp = {str(x) for x in expected}
    obs = {str(x) for x in observed}
    ratio = 1.0 if not exp else float(len(exp & obs)) / float(len(exp))
    min_ratio = float(params.get('min_ratio') or 1.0)
    return ratio >= min_ratio, {'coverage_ratio': ratio, 'missing': sorted(list(exp - obs))}


# === NoemaForge Autodoc Function Header ===
# Function: _run_sumcheck(payload: Dict[str, Any], params: Dict[str, Any])
# Purpose: Verify numeric reconciliation within a configured tolerance.
# Inputs:
#   - payload: Dict[str, Any]
#   - params: Dict[str, Any]
# Called by:
#   - verify
# Returns / emits: Tuple[bool, Dict[str, Any]]
# === End NoemaForge Autodoc Function Header ===
def _run_sumcheck(payload: Dict[str, Any], params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    tolerance = float(params.get('tolerance') or 0.0)
    expected = payload.get('expected')
    actual = payload.get('actual')
    if expected is None and actual is None and isinstance(payload.get('values'), list):
        values = [float(x) for x in payload.get('values') or []]
        expected = float(payload.get('expected_sum') or 0.0)
        actual = sum(values)
    if expected is None or actual is None:
        expected = _extract_path(payload, params.get('expected_path') or '$.expected')
        actual = _extract_path(payload, params.get('actual_path') or '$.actual')
    try:
        expected_f = float(expected)
        actual_f = float(actual)
    except Exception:
        return False, {'error': 'non_numeric', 'expected': expected, 'actual': actual}
    delta = abs(expected_f - actual_f)
    return delta <= tolerance, {'expected': expected_f, 'actual': actual_f, 'delta': delta, 'tolerance': tolerance}


# === NoemaForge Autodoc Function Header ===
# Function: _run_render_check(payload: Dict[str, Any], params: Dict[str, Any])
# Purpose: Verify that rendered outputs exist and match expected file extensions.
# Inputs:
#   - payload: Dict[str, Any]
#   - params: Dict[str, Any]
# Called by:
#   - verify
# Returns / emits: Tuple[bool, Dict[str, Any]]
# === End NoemaForge Autodoc Function Header ===
def _run_render_check(payload: Dict[str, Any], params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    outs = payload.get('outputs') if isinstance(payload.get('outputs'), list) else []
    min_outputs = int(params.get('min_outputs') or 1)
    required_exts = {str(x).lower() for x in (params.get('required_extensions') or [])}
    matched = []
    for rec in outs:
        if not isinstance(rec, dict):
            continue
        path = str(rec.get('path') or '').lower()
        if required_exts and not any(path.endswith(ext) for ext in required_exts):
            continue
        matched.append(path)
    return len(matched) >= min_outputs, {'matched_outputs': matched, 'required_extensions': sorted(list(required_exts))}


# === NoemaForge Autodoc Function Header ===
# Function: _run_mesh_sanity(payload: Dict[str, Any], params: Dict[str, Any])
# Purpose: Verify basic mesh cardinality and watertight hints.
# Inputs:
#   - payload: Dict[str, Any]
#   - params: Dict[str, Any]
# Called by:
#   - verify
# Returns / emits: Tuple[bool, Dict[str, Any]]
# === End NoemaForge Autodoc Function Header ===
def _run_mesh_sanity(payload: Dict[str, Any], params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    mesh = payload.get('mesh') if isinstance(payload.get('mesh'), dict) else payload
    try:
        vertices = int(mesh.get('vertices') or 0)
        faces = int(mesh.get('faces') or 0)
    except Exception:
        return False, {'error': 'non_numeric'}
    min_vertices = int(params.get('min_vertices') or 3)
    min_faces = int(params.get('min_faces') or 1)
    watertight = mesh.get('watertight')
    ok = vertices >= min_vertices and faces >= min_faces and watertight is not False
    return ok, {'vertices': vertices, 'faces': faces, 'watertight': watertight}


RUNNERS = {
    'checklist': _run_checklist,
    'json_schema': _run_json_schema,
    'coverage': _run_coverage,
    'sumcheck': _run_sumcheck,
    'render_check': _run_render_check,
    'mesh_sanity': _run_mesh_sanity,
}


# === NoemaForge Autodoc Function Header ===
# Function: verify(verifier_id: str, payload: Dict[str, Any], epoch_dir: str = '/opt/noemaforge/configs', catalog: Dict[str, Any] | None = None)
# Purpose: Run a configured verifier against a payload.
# Inputs:
#   - verifier_id: str
#   - payload: Dict[str, Any]
#   - epoch_dir: str = '/opt/noemaforge/configs'
#   - catalog: Dict[str, Any] | None = None
# Called by:
#   - main
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def verify(verifier_id: str, payload: Dict[str, Any], epoch_dir: str = '/opt/noemaforge/configs', catalog: Dict[str, Any] | None = None) -> Dict[str, Any]:
    catalog = catalog if isinstance(catalog, dict) else load_catalog(epoch_dir)
    rec = (catalog.get('verifiers') or {}).get(verifier_id)
    if not isinstance(rec, dict):
        return {'ok': False, 'verifier_id': verifier_id, 'error': 'unknown_verifier'}
    vtype = str(rec.get('type') or '').strip()
    if vtype not in SUPPORTED_TYPES or vtype not in RUNNERS:
        return {'ok': False, 'verifier_id': verifier_id, 'error': 'unsupported_type', 'type': vtype}
    params = rec.get('params') if isinstance(rec.get('params'), dict) else {}
    ok, details = RUNNERS[vtype](payload if isinstance(payload, dict) else {}, params)
    return {
        'ok': bool(ok),
        'verifier_id': verifier_id,
        'type': vtype,
        'details': details,
    }


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: List[str] | None = None)
# Purpose: CLI entrypoint for the verifier runtime.
# Inputs:
#   - argv: List[str] | None = None
# Called by:
#   - CLI entrypoint
# Returns / emits: int
# Side effects:
#   - reads files
#   - writes JSON files
# === End NoemaForge Autodoc Function Header ===
def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--epoch-dir', default='/opt/noemaforge/configs')
    ap.add_argument('--verifier', required=True)
    ap.add_argument('--payload', required=True)
    ap.add_argument('--out', default='')
    args = ap.parse_args(argv)

    with open(args.payload, 'r', encoding='utf-8') as f:
        payload = json.load(f) or {}
    result = verify(args.verifier, payload if isinstance(payload, dict) else {}, epoch_dir=args.epoch_dir)
    if args.out:
        _save_json(args.out, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('ok') else 2


if __name__ == '__main__':
    raise SystemExit(main())
