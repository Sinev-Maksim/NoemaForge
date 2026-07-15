#!/usr/bin/env python3
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: src/knowledge/error_learning.py
# Purpose: Implement the knowledge subsystem module 'error_learning'.
# Invoked by / imported from:
#   - pytest discovery or direct CLI/testing workflows
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-30 (manual)
# === End NoemaForge Autodoc File Header ===

# === NoemaForge File Header ===
# File: src/knowledge/error_learning.py
# Zone: brain
# Purpose: Provide a durable SQLite adapter for the hypergraph error-learning loop.
# Callers: src/brainctl.py, future extraction/linking runtimes, tests/test_error_learning_runtime.py
# Inputs: sql/error_learning_loop.sqlite.sql, local SQLite paths, structured error/correction payloads
# Outputs: SQLite rows and optional JSONL exports of regression/training artifacts
# Side effects: creates and mutates the error-learning database and export directories
# Security notes:
#   - invariants: every learning artifact must point back to a concrete processing run and source error
#   - threats: silently losing adjudication context, exporting unapproved corrections into training deltas
# === End NoemaForge File Header ===


import datetime as dt
import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[2]
SQL_PATH = ROOT / 'sql' / 'error_learning_loop.sqlite.sql'
LIST_ERRORS_SQL = """
SELECT *
FROM error_events
WHERE (? = '' OR component = ?)
  AND (? = '' OR review_status = ?)
ORDER BY created_at DESC
LIMIT ?
"""
EXPORT_REGRESSION_SQL = """
SELECT *
FROM regression_cases
WHERE case_status = ?
  AND (? = '' OR component = ?)
ORDER BY promoted_at ASC
"""


def _nowz() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace('+00:00', 'Z')


def _j(obj: Any) -> str:
    return json.dumps(obj if obj is not None else {}, ensure_ascii=False, sort_keys=True)


def _jd(raw: Any) -> Any:
    if raw in (None, ''):
        return None
    try:
        return json.loads(str(raw))
    except Exception:
        return None


class ErrorLearningStore:
    """Durable adapter for the error-learning loop.

    The store is deliberately generic: it can be fed by prep-model runs, extraction
    runs, future model-based linkers, and manual review operations.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = str(db_path)
        os.makedirs(os.path.dirname(self.db_path) or '.', exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys = ON')
        return con

    def _init_db(self) -> None:
        sql = SQL_PATH.read_text(encoding='utf-8')
        con = self._connect()
        con.executescript(sql)
        con.commit()
        con.close()

    def list_tables(self) -> List[str]:
        con = self._connect()
        rows = con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        con.close()
        return [str(r['name']) for r in rows]

    def start_run(
        self,
        *,
        component: str,
        book_id: str = '',
        model_id: str = '',
        model_version: str = '',
        prompt_hash: str = '',
        profile_id: str = '',
        policy_epoch: str = '',
        code_version: str = '',
        thresholds: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> str:
        rid = str(run_id or f'run:{uuid.uuid4()}')
        con = self._connect()
        con.execute(
            """
            INSERT OR REPLACE INTO processing_runs(
              run_id, component, book_id, model_id, model_version, prompt_hash,
              profile_id, policy_epoch, code_version, thresholds_json,
              started_at, finished_at, run_status, error_code, error_message
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                rid,
                str(component or ''),
                str(book_id or ''),
                str(model_id or ''),
                str(model_version or ''),
                str(prompt_hash or ''),
                str(profile_id or ''),
                str(policy_epoch or ''),
                str(code_version or ''),
                _j(thresholds or {}),
                _nowz(),
                None,
                'running',
                '',
                '',
            ),
        )
        con.commit()
        con.close()
        return rid

    def finish_run(self, *, run_id: str, status: str = 'completed', error_code: str = '', error_message: str = '') -> Dict[str, Any]:
        con = self._connect()
        cur = con.execute(
            "UPDATE processing_runs SET finished_at=?, run_status=?, error_code=?, error_message=? WHERE run_id=?",
            (_nowz(), str(status or 'completed'), str(error_code or ''), str(error_message or ''), str(run_id)),
        )
        con.commit()
        con.close()
        return {'ok': cur.rowcount > 0, 'run_id': str(run_id), 'status': str(status)}

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        con = self._connect()
        row = con.execute('SELECT * FROM processing_runs WHERE run_id=?', (str(run_id),)).fetchone()
        con.close()
        if not row:
            return None
        d = dict(row)
        d['thresholds'] = _jd(d.get('thresholds_json')) or {}
        return d

    def add_error_event(
        self,
        *,
        run_id: str,
        component: str,
        error_type: str,
        severity: str = 'medium',
        source_address: Optional[Dict[str, Any]] = None,
        object_kind: str = '',
        object_id: str = '',
        predicted_payload: Optional[Dict[str, Any]] = None,
        expected_payload: Optional[Dict[str, Any]] = None,
        source_defect: bool = False,
        reviewer_note: str = '',
        error_id: Optional[str] = None,
    ) -> str:
        eid = str(error_id or f'error:{uuid.uuid4()}')
        con = self._connect()
        con.execute(
            """
            INSERT OR REPLACE INTO error_events(
              error_id, run_id, component, severity, error_type, source_address_json,
              object_kind, object_id, predicted_payload_json, expected_payload_json,
              source_defect, review_status, created_at, reviewer_note
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                eid,
                str(run_id),
                str(component or ''),
                str(severity or 'medium'),
                str(error_type or ''),
                _j(source_address or {}),
                str(object_kind or ''),
                str(object_id or ''),
                _j(predicted_payload or {}),
                _j(expected_payload or {}),
                1 if bool(source_defect) else 0,
                'open',
                _nowz(),
                str(reviewer_note or ''),
            ),
        )
        con.commit()
        con.close()
        return eid

    def get_error(self, error_id: str) -> Optional[Dict[str, Any]]:
        con = self._connect()
        row = con.execute('SELECT * FROM error_events WHERE error_id=?', (str(error_id),)).fetchone()
        con.close()
        if not row:
            return None
        d = dict(row)
        for k in ('source_address_json', 'predicted_payload_json', 'expected_payload_json'):
            d[k[:-5]] = _jd(d.get(k)) or {}
        return d

    def list_errors(self, *, component: str = '', review_status: str = '', limit: int = 200) -> List[Dict[str, Any]]:
        component_filter = str(component or '').strip()
        review_status_filter = str(review_status or '').strip()
        vals: List[Any] = [
            component_filter,
            component_filter,
            review_status_filter,
            review_status_filter,
            int(limit),
        ]
        con = self._connect()
        rows = con.execute(LIST_ERRORS_SQL, tuple(vals)).fetchall()
        con.close()
        out = []
        for row in rows:
            d = dict(row)
            d['source_address'] = _jd(d.get('source_address_json')) or {}
            d['predicted_payload'] = _jd(d.get('predicted_payload_json')) or {}
            d['expected_payload'] = _jd(d.get('expected_payload_json')) or {}
            out.append(d)
        return out

    def set_error_review_status(self, *, error_id: str, review_status: str, reviewer_note: str = '') -> Dict[str, Any]:
        con = self._connect()
        cur = con.execute('UPDATE error_events SET review_status=?, reviewer_note=? WHERE error_id=?', (str(review_status), str(reviewer_note or ''), str(error_id)))
        con.commit()
        con.close()
        return {'ok': cur.rowcount > 0, 'error_id': str(error_id), 'review_status': str(review_status)}

    def add_correction(
        self,
        *,
        error_id: str,
        corrected_by: str,
        correction_kind: str,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        rationale: str = '',
        approved_for_training: bool = False,
        approved_for_eval: bool = False,
        correction_id: Optional[str] = None,
    ) -> str:
        cid = str(correction_id or f'corr:{uuid.uuid4()}')
        con = self._connect()
        con.execute(
            """
            INSERT OR REPLACE INTO corrections(
              correction_id, error_id, corrected_by, correction_kind, old_value_json,
              new_value_json, rationale, created_at, approved_for_training, approved_for_eval
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                cid,
                str(error_id),
                str(corrected_by or ''),
                str(correction_kind or ''),
                _j(old_value or {}),
                _j(new_value or {}),
                str(rationale or ''),
                _nowz(),
                1 if bool(approved_for_training) else 0,
                1 if bool(approved_for_eval) else 0,
            ),
        )
        con.commit()
        con.close()
        return cid

    def get_correction(self, correction_id: str) -> Optional[Dict[str, Any]]:
        con = self._connect()
        row = con.execute('SELECT * FROM corrections WHERE correction_id=?', (str(correction_id),)).fetchone()
        con.close()
        if not row:
            return None
        d = dict(row)
        d['old_value'] = _jd(d.get('old_value_json')) or {}
        d['new_value'] = _jd(d.get('new_value_json')) or {}
        return d

    def add_adjudication(
        self,
        *,
        error_id: str,
        adjudicated_by: str,
        adjudication_status: str,
        correction_id: str = '',
        reasoning: str = '',
        adjudication_id: Optional[str] = None,
    ) -> str:
        aid = str(adjudication_id or f'adj:{uuid.uuid4()}')
        con = self._connect()
        con.execute(
            "INSERT OR REPLACE INTO adjudications(adjudication_id, error_id, correction_id, adjudicated_by, adjudication_status, reasoning, created_at) VALUES(?,?,?,?,?,?,?)",
            (aid, str(error_id), str(correction_id or ''), str(adjudicated_by or ''), str(adjudication_status or ''), str(reasoning or ''), _nowz()),
        )
        con.commit()
        con.close()
        return aid

    def promote_regression_case(
        self,
        *,
        error_id: str,
        component: str,
        input_payload: Dict[str, Any],
        expected_payload: Dict[str, Any],
        promoted_by: str,
        source_correction_id: str = '',
        acceptance_policy: Optional[Dict[str, Any]] = None,
        regression_case_id: Optional[str] = None,
    ) -> str:
        rid = str(regression_case_id or f'regr:{uuid.uuid4()}')
        con = self._connect()
        con.execute(
            """
            INSERT OR REPLACE INTO regression_cases(
              regression_case_id, source_error_id, source_correction_id, component,
              input_payload_json, expected_payload_json, acceptance_policy_json,
              promoted_at, promoted_by, case_status
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                rid,
                str(error_id),
                str(source_correction_id or ''),
                str(component or ''),
                _j(input_payload or {}),
                _j(expected_payload or {}),
                _j(acceptance_policy or {}),
                _nowz(),
                str(promoted_by or ''),
                'active',
            ),
        )
        con.commit()
        con.close()
        return rid

    def promote_training_delta(
        self,
        *,
        error_id: str,
        correction_id: str,
        target_model_family: str,
        delta_payload: Dict[str, Any],
        notes: str = '',
        training_delta_id: Optional[str] = None,
    ) -> str:
        tid = str(training_delta_id or f'tdelta:{uuid.uuid4()}')
        con = self._connect()
        con.execute(
            "INSERT OR REPLACE INTO training_deltas(training_delta_id, source_error_id, source_correction_id, target_model_family, delta_payload_json, export_status, created_at, notes) VALUES(?,?,?,?,?,?,?,?)",
            (tid, str(error_id), str(correction_id), str(target_model_family or ''), _j(delta_payload or {}), 'pending', _nowz(), str(notes or '')),
        )
        con.commit()
        con.close()
        return tid

    def export_regression_cases(self, out_dir: str, *, component: str = '', status: str = 'active') -> Dict[str, Any]:
        os.makedirs(str(out_dir), exist_ok=True)
        con = self._connect()
        component_filter = str(component or '').strip()
        vals: List[Any] = [str(status), component_filter, component_filter]
        rows = con.execute(EXPORT_REGRESSION_SQL, tuple(vals)).fetchall()
        con.close()
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            d = dict(row)
            d['input_payload'] = _jd(d.get('input_payload_json')) or {}
            d['expected_payload'] = _jd(d.get('expected_payload_json')) or {}
            d['acceptance_policy'] = _jd(d.get('acceptance_policy_json')) or {}
            grouped.setdefault(str(d.get('component') or 'misc'), []).append(d)
        files = []
        for comp, items in grouped.items():
            p = Path(out_dir) / f'{comp}.jsonl'
            with p.open('w', encoding='utf-8') as f:
                for item in items:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
            files.append(str(p))
        return {'ok': True, 'files': files, 'count': sum(len(v) for v in grouped.values())}
