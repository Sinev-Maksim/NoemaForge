#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_error_learning_runtime.py
Zone: release/package
Version: 0.32.1
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
# File: tests/test_error_learning_runtime.py
# Purpose: Helper / validation script 'test_error_learning_runtime.py'.
# Invoked by / imported from:
#   - pytest discovery or direct CLI/testing workflows
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-30 (manual)
# === End NoemaForge Autodoc File Header ===


import os
import sys
from pathlib import Path

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from knowledge.error_learning import ErrorLearningStore


def test_error_learning_store_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / 'errors.sqlite'
    es = ErrorLearningStore(str(db))
    run_id = es.start_run(component='claim_extractor', book_id='book:1', model_id='main', profile_id='claim_sentence_v1')
    err_id = es.add_error_event(
        run_id=run_id,
        component='claim_extractor',
        error_type='missed_gold_claim',
        severity='medium',
        source_address={'book_id': 'book:1', 'section_path': '1.1'},
        expected_payload={'text': 'From A01 follows B01'},
        predicted_payload={'matched': False},
    )
    corr_id = es.add_correction(
        error_id=err_id,
        corrected_by='tester',
        correction_kind='expected_claim',
        old_value={'matched': False},
        new_value={'text': 'From A01 follows B01'},
        approved_for_training=True,
        approved_for_eval=True,
    )
    es.add_adjudication(error_id=err_id, correction_id=corr_id, adjudicated_by='tester', adjudication_status='accepted', reasoning='Gold claim is valid.')
    es.promote_regression_case(error_id=err_id, source_correction_id=corr_id, component='claim_extractor', input_payload={'query': 'A01->B01'}, expected_payload={'text': 'From A01 follows B01'}, promoted_by='tester')
    es.promote_training_delta(error_id=err_id, correction_id=corr_id, target_model_family='claim_extractor', delta_payload={'gold': 'From A01 follows B01'})
    es.finish_run(run_id=run_id, status='completed')

    listed = es.list_errors(component='claim_extractor')
    assert listed and listed[0]['error_id'] == err_id
    exported = es.export_regression_cases(str(tmp_path / 'out'), component='claim_extractor')
    assert exported['ok'] is True
    assert exported['count'] == 1


def test_error_learning_filters_treat_sql_metacharacters_as_values(tmp_path: Path) -> None:
    db = tmp_path / 'errors.sqlite'
    es = ErrorLearningStore(str(db))
    run_id = es.start_run(component='claim_extractor', book_id='book:1')
    err_id = es.add_error_event(
        run_id=run_id,
        component='claim_extractor',
        error_type='missed_gold_claim',
    )
    corr_id = es.add_correction(
        error_id=err_id,
        corrected_by='tester',
        correction_kind='expected_claim',
        approved_for_eval=True,
    )
    es.promote_regression_case(
        error_id=err_id,
        source_correction_id=corr_id,
        component='claim_extractor',
        input_payload={'query': 'A01->B01'},
        expected_payload={'text': 'From A01 follows B01'},
        promoted_by='tester',
    )

    injected_component = "claim_extractor' OR 1=1 --"
    assert es.list_errors(component=injected_component) == []
    assert es.export_regression_cases(str(tmp_path / 'out'), component=injected_component)['count'] == 0
    assert es.export_regression_cases(str(tmp_path / 'out2'), status="active' OR 1=1 --")['count'] == 0
    assert es.list_errors(component='claim_extractor')[0]['error_id'] == err_id
