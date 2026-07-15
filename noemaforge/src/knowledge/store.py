#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/store.py
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
# File: src/knowledge/store.py
# Purpose: Implement the knowledge subsystem module 'store'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/knowledge/__init__.py
#   - src/knowledge/embedding_worker.py
#   - src/knowledge/gatekeeper.py
#   - src/knowledge/ingest.py
#   - src/knowledge/retrieval.py
#   - src/knowledge/trails.py
#   - src/knowledge_maintainer.py
# Public API / entry functions:
#   - class KnowledgeStore
# Inputs:
#   - Imports: __future__, json, os, sqlite3, time, uuid, typing
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""knowledge.store (v0.16.0)

Canonical Hypergraph Store (SQLite).

This is the "structure/provenance" layer. It is NOT the vector search layer.
Vectors live in VStore and are linked by stable IDs.

Design notes
-----------
- IDs are stable strings (UUIDs by default), never auto-increment ints.
- Most fields are stored as JSON for flexibility (MVP). We can normalize later.
- Provenance is always stored (created_at + created_by + source refs).

Minimum entity set implemented in v0.16.0:
- Source, Passage
- Concept
- Claim
- Conflict
- Trail + TrailStep
- Realm + RealmBridge (basic)

This matches the idea of "library -> hypergraph knowledge" while keeping
engineering scope reasonable for an MVP seed kit.
"""


import json
import os
import sqlite3
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple


FETCH_BY_ID_QUERIES = {
    "sources": "SELECT * FROM sources WHERE source_id=?",
    "passages": "SELECT * FROM passages WHERE passage_id=?",
    "concepts": "SELECT * FROM concepts WHERE concept_id=?",
    "claims": "SELECT * FROM claims WHERE claim_id=?",
    "conflicts": "SELECT * FROM conflicts WHERE conflict_id=?",
    "realms": "SELECT * FROM realms WHERE realm_id=?",
    "realm_bridges": "SELECT * FROM realm_bridges WHERE bridge_id=?",
    "trails": "SELECT * FROM trails WHERE trail_id=?",
}


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/caps.py
#   - src/casebase.py
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
# Calls:
#   - strftime, gmtime
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# === NoemaForge Autodoc Function Header ===
# Function: _j(obj)
# Purpose: Implement the routine ' j'.
# Inputs:
#   - obj
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - dumps
# Returns / emits: str
# Side effects:
#   - serializes structured data
# === End NoemaForge Autodoc Function Header ===
def _j(obj: Any) -> str:
    return json.dumps(obj or {}, ensure_ascii=False, sort_keys=True)


# === NoemaForge Autodoc Function Header ===
# Function: _jd(s: str)
# Purpose: Implement the routine ' jd'.
# Inputs:
#   - s: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - loads
# Returns / emits: Any
# === End NoemaForge Autodoc Function Header ===
def _jd(s: str) -> Any:
    try:
        return json.loads(s) if s else {}
    except Exception:
        return {}


class KnowledgeStore:
    # === NoemaForge Autodoc Function Header ===
    # Function: __init__(self, db_path: str)
    # Purpose: Implement the routine '  init  '.
    # Inputs:
    #   - self
    #   - db_path: str
    # Called by:
    #   - src/model_scorecards.py
    #   - src/team_scorecards.py
    #   - src/toolproxy.py
    # Calls:
    #   - makedirs, _init_db, dirname
    # Returns / emits: unspecified Python value
    # Side effects:
    #   - creates directories
    # === End NoemaForge Autodoc Function Header ===
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    # === NoemaForge Autodoc Function Header ===
    # Function: _connect(self)
    # Purpose: Implement the routine ' connect'.
    # Inputs:
    #   - self
    # Called by:
    #   - src/casebase.py
    #   - src/dream_cycle.py
    #   - src/memory_system.py
    #   - src/pipelines/finance_budget.py
    #   - src/roadmap.py
    #   - src/task_tools.py
    #   - src/taskqueue.py
    #   - src/vstore.py
    # Calls:
    #   - connect
    # Returns / emits: sqlite3.Connection
    # Side effects:
    #   - opens a database or socket connection
    # Key locals:
    #   - con
    # === End NoemaForge Autodoc Function Header ===
    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    # === NoemaForge Autodoc Function Header ===
    # Function: _init_db(self)
    # Purpose: Implement the routine ' init db'.
    # Inputs:
    #   - self
    # Called by:
    #   - src/memory_system.py
    #   - src/vstore.py
    #   - tools/prep/scan_tabs.py
    #   - tools/prep/scan_tg.py
    # Calls:
    #   - _connect, cursor, execute, commit, close
    # Returns / emits: None
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur
    # === End NoemaForge Autodoc Function Header ===
    def _init_db(self) -> None:
        con = self._connect()
        cur = con.cursor()

        # Core tables
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
              source_id TEXT PRIMARY KEY,
              type TEXT,
              metadata_json TEXT,
              primary_realm TEXT,
              license TEXT,
              version_info TEXT,
              created_at TEXT,
              created_by TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS passages (
              passage_id TEXT PRIMARY KEY,
              source_id TEXT,
              anchor_json TEXT,
              text TEXT,
              realm_override TEXT,
              created_at TEXT,
              created_by TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_passages_source ON passages(source_id)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS concepts (
              concept_id TEXT PRIMARY KEY,
              labels_json TEXT,
              definition_passages_json TEXT,
              realms_json TEXT,
              realm_scope TEXT,
              introduced_in TEXT,
              created_at TEXT,
              created_by TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS claims (
              claim_id TEXT PRIMARY KEY,
              text_normalized TEXT,
              about_concepts_json TEXT,
              realm_context_json TEXT,
              status TEXT,
              confidence REAL,
              extracted_from_passages_json TEXT,
              supported_by_evidence_json TEXT,
              counterclaims_json TEXT,
              created_at TEXT,
              created_by TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS conflicts (
              conflict_id TEXT PRIMARY KEY,
              entity_a TEXT,
              entity_b TEXT,
              incompatibility_type TEXT,
              realm_context_json TEXT,
              status TEXT,
              confidence REAL,
              unresolved_reason TEXT,
              decision_trace TEXT,
              created_at TEXT,
              created_by TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_conflicts_entities ON conflicts(entity_a, entity_b)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS realms (
              realm_id TEXT PRIMARY KEY,
              modality TEXT,
              domain_json TEXT,
              scale TEXT,
              assumptions_json TEXT,
              validity_conditions TEXT,
              parent_realm TEXT,
              created_at TEXT,
              created_by TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS realm_bridges (
              bridge_id TEXT PRIMARY KEY,
              from_realm TEXT,
              to_realm TEXT,
              bridge_type TEXT,
              validity_conditions TEXT,
              distortion_notes TEXT,
              support_passages_json TEXT,
              confidence REAL,
              created_at TEXT,
              created_by TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS trails (
              trail_id TEXT PRIMARY KEY,
              level TEXT,
              goal TEXT,
              goal_type TEXT,
              realm_profile_json TEXT,
              gates_json TEXT,
              entry_conditions_json TEXT,
              exit_outcomes_json TEXT,
              subtrails_json TEXT,
              created_at TEXT,
              created_by TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS trail_steps (
              trail_id TEXT,
              step_idx INTEGER,
              node_ref_json TEXT,
              step_type TEXT,
              why_this_step TEXT,
              expected_takeaway TEXT,
              branch_options_json TEXT,
              PRIMARY KEY(trail_id, step_idx)
            )
            """
        )

        # Gatekeeper reports (publication gates / invariant checks)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS gate_reports (
              object_kind TEXT,
              object_id TEXT,
              decision TEXT,
              severity TEXT,
              violations_json TEXT,
              created_at TEXT,
              updated_at TEXT,
              PRIMARY KEY(object_kind, object_id)
            )
            """
        )

        # Linkbase / overlays (non-destructive context over base objects)
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS contexts (
              context_id TEXT PRIMARY KEY,
              title TEXT,
              description TEXT,
              policies_json TEXT,
              created_at TEXT,
              created_by TEXT
            )
            '''
        )

        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS annotations (
              annotation_id TEXT PRIMARY KEY,
              target_kind TEXT,
              target_id TEXT,
              context_id TEXT,
              anchor_json TEXT,
              annotation_type TEXT,
              content TEXT,
              created_at TEXT,
              created_by TEXT
            )
            '''
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_annotations_target ON annotations(target_kind, target_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_annotations_context ON annotations(context_id)')

        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS links (
              link_id TEXT PRIMARY KEY,
              from_kind TEXT,
              from_id TEXT,
              to_kind TEXT,
              to_id TEXT,
              link_type TEXT,
              conditions_json TEXT,
              created_at TEXT,
              created_by TEXT
            )
            '''
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_links_from ON links(from_kind, from_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_links_to ON links(to_kind, to_id)')

        # Evidence / arguments / issues (explicit reasoning objects)
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS evidence (
              evidence_id TEXT PRIMARY KEY,
              kind TEXT,
              strength REAL,
              source_refs_json TEXT,
              support_passages_json TEXT,
              realm_context_json TEXT,
              notes TEXT,
              created_at TEXT,
              created_by TEXT
            )
            '''
        )

        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS arguments (
              argument_id TEXT PRIMARY KEY,
              argument_type TEXT,
              premises_json TEXT,
              conclusion_claim_id TEXT,
              assumptions_json TEXT,
              evidence_refs_json TEXT,
              created_at TEXT,
              created_by TEXT
            )
            '''
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_arguments_conclusion ON arguments(conclusion_claim_id)')

        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS issues (
              issue_id TEXT PRIMARY KEY,
              question TEXT,
              positions_json TEXT,
              argument_refs_json TEXT,
              created_at TEXT,
              created_by TEXT
            )
            '''
        )

        # Lineage links (explicit derivation between objects)
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS lineage_links (
              lineage_id TEXT PRIMARY KEY,
              child_kind TEXT,
              child_id TEXT,
              relation_type TEXT,
              parents_json TEXT,
              declared_derivation_json TEXT,
              computed_checks_json TEXT,
              support_passages_json TEXT,
              confidence REAL,
              realm_context_json TEXT,
              created_at TEXT,
              created_by TEXT
            )
            '''
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_lineage_child ON lineage_links(child_kind, child_id)')


        con.commit()
        con.close()

    # -------------------
    # CRUD helpers
    # -------------------

    # === NoemaForge Autodoc Function Header ===
    # Function: add_source(self, source_id: Optional[str] = None, type: str = 'web', metadata: Optional[Dict[str, Any]] = None, primary_realm: str = '', license: str = '', version_info: str = '', created_by: str = 'system')
    # Purpose: Implement the routine 'add source'.
    # Inputs:
    #   - self
    #   - source_id: Optional[str] = None
    #   - type: str = 'web'
    #   - metadata: Optional[Dict[str, Any]] = None
    #   - primary_realm: str = ''
    #   - license: str = ''
    #   - version_info: str = ''
    #   - created_by: str = 'system'
    # Called by:
    #   - src/knowledge/ingest.py
    # Calls:
    #   - str, _connect, cursor, execute, commit, close, uuid4, _j, _nowz
    # Returns / emits: str
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, sid
    # === End NoemaForge Autodoc Function Header ===
    def add_source(
        self,
        *,
        source_id: Optional[str] = None,
        type: str = "web",
        metadata: Optional[Dict[str, Any]] = None,
        primary_realm: str = "",
        license: str = "",
        version_info: str = "",
        created_by: str = "system",
    ) -> str:
        sid = str(source_id or uuid.uuid4())
        con = self._connect()
        cur = con.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO sources(source_id, type, metadata_json, primary_realm, license, version_info, created_at, created_by) VALUES(?,?,?,?,?,?,?,?)",
            (sid, str(type), _j(metadata or {}), str(primary_realm), str(license), str(version_info), _nowz(), str(created_by)),
        )
        con.commit()
        con.close()
        return sid

    # === NoemaForge Autodoc Function Header ===
    # Function: get_source(self, source_id: str)
    # Purpose: Implement the routine 'get source'.
    # Inputs:
    #   - self
    #   - source_id: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, execute, fetchone, close, dict, _jd, str, get
    # Returns / emits: Optional[Dict[str, Any]]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, d, row
    # === End NoemaForge Autodoc Function Header ===
    def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        con = self._connect()
        cur = con.cursor()
        cur.execute("SELECT * FROM sources WHERE source_id=?", (str(source_id),))
        row = cur.fetchone()
        con.close()
        if not row:
            return None
        d = dict(row)
        d["metadata"] = _jd(d.get("metadata_json") or "")
        return d

    # === NoemaForge Autodoc Function Header ===
    # Function: add_passage(self, passage_id: Optional[str] = None, source_id: str, anchor: Optional[Dict[str, Any]] = None, text: str = '', realm_override: str = '', created_by: str = 'system')
    # Purpose: Implement the routine 'add passage'.
    # Inputs:
    #   - self
    #   - passage_id: Optional[str] = None
    #   - source_id: str
    #   - anchor: Optional[Dict[str, Any]] = None
    #   - text: str = ''
    #   - realm_override: str = ''
    #   - created_by: str = 'system'
    # Called by:
    #   - src/knowledge/ingest.py
    # Calls:
    #   - str, _connect, cursor, execute, commit, close, uuid4, _j, _nowz
    # Returns / emits: str
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, pid
    # === End NoemaForge Autodoc Function Header ===
    def add_passage(
        self,
        *,
        passage_id: Optional[str] = None,
        source_id: str,
        anchor: Optional[Dict[str, Any]] = None,
        text: str = "",
        realm_override: str = "",
        created_by: str = "system",
    ) -> str:
        pid = str(passage_id or uuid.uuid4())
        con = self._connect()
        cur = con.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO passages(passage_id, source_id, anchor_json, text, realm_override, created_at, created_by) VALUES(?,?,?,?,?,?,?)",
            (pid, str(source_id), _j(anchor or {}), str(text), str(realm_override), _nowz(), str(created_by)),
        )
        con.commit()
        con.close()
        return pid


    # === NoemaForge Autodoc Function Header ===
    # Function: iter_passages(self, limit: int = 500, offset: int = 0)
    # Purpose: Return passages (newest first).
    # Inputs:
    #   - self
    #   - limit: int = 500
    #   - offset: int = 0
    # Called by:
    #   - src/knowledge/embedding_worker.py
    # Calls:
    #   - connect, cursor, execute, fetchall, close, dict, int
    # Returns / emits: List[Dict[str, Any]]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, rows
    # === End NoemaForge Autodoc Function Header ===
    def iter_passages(self, *, limit: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
        """Return passages (newest first).

        Used by embedding/gatekeeper workers.
        """

        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            "SELECT passage_id, source_id, anchor_json, text, realm_override, created_at, created_by FROM passages ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (int(limit), int(offset)),
        )
        rows = cur.fetchall()
        con.close()
        return [dict(r) for r in rows]


    # === NoemaForge Autodoc Function Header ===
    # Function: iter_claims(self, limit: int = 500, offset: int = 0)
    # Purpose: Return claims (newest first).
    # Inputs:
    #   - self
    #   - limit: int = 500
    #   - offset: int = 0
    # Called by:
    #   - src/knowledge/embedding_worker.py
    # Calls:
    #   - connect, cursor, execute, fetchall, close, dict, int
    # Returns / emits: List[Dict[str, Any]]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, rows
    # === End NoemaForge Autodoc Function Header ===
    def iter_claims(self, *, limit: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
        """Return claims (newest first).

        Used by embedding/gatekeeper workers.
        """

        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            "SELECT claim_id, text_normalized, about_concepts_json, realm_context_json, status, confidence, extracted_from_passages_json, created_at, created_by FROM claims ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (int(limit), int(offset)),
        )
        rows = cur.fetchall()
        con.close()
        return [dict(r) for r in rows]


    # === NoemaForge Autodoc Function Header ===
    # Function: iter_concepts(self, limit: int = 500, offset: int = 0)
    # Purpose: Return concepts (newest first).
    # Inputs:
    #   - self
    #   - limit: int = 500
    #   - offset: int = 0
    # Called by:
    #   - src/knowledge/embedding_worker.py
    # Calls:
    #   - connect, cursor, execute, fetchall, close, dict, int
    # Returns / emits: List[Dict[str, Any]]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, rows
    # === End NoemaForge Autodoc Function Header ===
    def iter_concepts(self, *, limit: int = 500, offset: int = 0) -> List[Dict[str, Any]]:
        """Return concepts (newest first).

        Used by embedding/gatekeeper workers.
        """

        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            "SELECT concept_id, labels_json, definition_passages_json, realms_json, realm_scope, introduced_in, created_at, created_by FROM concepts ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (int(limit), int(offset)),
        )
        rows = cur.fetchall()
        con.close()
        return [dict(r) for r in rows]


    # === NoemaForge Autodoc Function Header ===
    # Function: upsert_gate_report(self, object_kind: str, object_id: str, decision: str, severity: str, violations: List[Dict[str, Any]])
    # Purpose: Insert/replace a gatekeeper report for an object.
    # Inputs:
    #   - self
    #   - object_kind: str
    #   - object_id: str
    #   - decision: str
    #   - severity: str
    #   - violations: List[Dict[str, Any]]
    # Called by:
    #   - src/knowledge/gatekeeper.py
    # Calls:
    #   - strip, _nowz, connect, cursor, execute, commit, close, str, dumps
    # Returns / emits: None
    # Side effects:
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, now, oid, okind
    # === End NoemaForge Autodoc Function Header ===
    def upsert_gate_report(
        self,
        *,
        object_kind: str,
        object_id: str,
        decision: str,
        severity: str,
        violations: List[Dict[str, Any]],
    ) -> None:
        """Insert/replace a gatekeeper report for an object."""

        okind = str(object_kind or "").strip()
        oid = str(object_id or "").strip()
        if not okind or not oid:
            return
        now = _nowz()
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO gate_reports(object_kind, object_id, decision, severity, violations_json, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (okind, oid, str(decision or ""), str(severity or ""), json.dumps(violations or []), now, now),
        )
        con.commit()
        con.close()


    # === NoemaForge Autodoc Function Header ===
    # Function: get_gate_report(self, object_kind: str, object_id: str)
    # Purpose: Implement the routine 'get gate report'.
    # Inputs:
    #   - self
    #   - object_kind: str
    #   - object_id: str
    # Called by:
    #   - src/knowledge/retrieval.py
    # Calls:
    #   - strip, connect, cursor, execute, fetchone, close, dict, str
    # Returns / emits: Dict[str, Any]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, oid, okind, row
    # === End NoemaForge Autodoc Function Header ===
    def get_gate_report(self, *, object_kind: str, object_id: str) -> Dict[str, Any]:
        okind = str(object_kind or "").strip()
        oid = str(object_id or "").strip()
        if not okind or not oid:
            return {}
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT * FROM gate_reports WHERE object_kind=? AND object_id=?", (okind, oid))
        row = cur.fetchone()
        con.close()
        return dict(row) if row else {}

    # === NoemaForge Autodoc Function Header ===
    # Function: get_passage(self, passage_id: str)
    # Purpose: Implement the routine 'get passage'.
    # Inputs:
    #   - self
    #   - passage_id: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, execute, fetchone, close, dict, _jd, str, get
    # Returns / emits: Optional[Dict[str, Any]]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, d, row
    # === End NoemaForge Autodoc Function Header ===
    def get_passage(self, passage_id: str) -> Optional[Dict[str, Any]]:
        con = self._connect()
        cur = con.cursor()
        cur.execute("SELECT * FROM passages WHERE passage_id=?", (str(passage_id),))
        row = cur.fetchone()
        con.close()
        if not row:
            return None
        d = dict(row)
        d["anchor"] = _jd(d.get("anchor_json") or "")
        return d

    def get_claim(self, claim_id: str) -> Optional[Dict[str, Any]]:
        con = self._connect()
        cur = con.cursor()
        cur.execute("SELECT * FROM claims WHERE claim_id=?", (str(claim_id),))
        row = cur.fetchone()
        con.close()
        if not row:
            return None
        d = dict(row)
        d["about_concepts"] = _jd(d.get("about_concepts_json") or "")
        d["realm_context"] = _jd(d.get("realm_context_json") or "")
        d["extracted_from_passages"] = _jd(d.get("extracted_from_passages_json") or "")
        d["supported_by_evidence"] = _jd(d.get("supported_by_evidence_json") or "")
        d["counterclaims"] = _jd(d.get("counterclaims_json") or "")
        return d

    def get_concept(self, concept_id: str) -> Optional[Dict[str, Any]]:
        con = self._connect()
        cur = con.cursor()
        cur.execute("SELECT * FROM concepts WHERE concept_id=?", (str(concept_id),))
        row = cur.fetchone()
        con.close()
        if not row:
            return None
        d = dict(row)
        d["labels"] = _jd(d.get("labels_json") or "")
        d["definition_passage_ids"] = _jd(d.get("definition_passages_json") or "")
        d["realms"] = _jd(d.get("realms_json") or "")
        return d

    # === NoemaForge Autodoc Function Header ===
    # Function: add_concept(self, concept_id: Optional[str] = None, labels: Optional[List[str]] = None, definition_passage_ids: Optional[List[str]] = None, realms: Optional[List[str]] = None, realm_scope: str = '', introduced_in: str = '', created_by: str = 'system')
    # Purpose: Implement the routine 'add concept'.
    # Inputs:
    #   - self
    #   - concept_id: Optional[str] = None
    #   - labels: Optional[List[str]] = None
    #   - definition_passage_ids: Optional[List[str]] = None
    #   - realms: Optional[List[str]] = None
    #   - realm_scope: str = ''
    #   - introduced_in: str = ''
    #   - created_by: str = 'system'
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - str, _connect, cursor, execute, commit, close, uuid4, _j, _nowz
    # Returns / emits: str
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - cid, con, cur
    # === End NoemaForge Autodoc Function Header ===
    def add_concept(
        self,
        *,
        concept_id: Optional[str] = None,
        labels: Optional[List[str]] = None,
        definition_passage_ids: Optional[List[str]] = None,
        realms: Optional[List[str]] = None,
        realm_scope: str = "",
        introduced_in: str = "",
        created_by: str = "system",
    ) -> str:
        cid = str(concept_id or uuid.uuid4())
        con = self._connect()
        cur = con.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO concepts(concept_id, labels_json, definition_passages_json, realms_json, realm_scope, introduced_in, created_at, created_by) VALUES(?,?,?,?,?,?,?,?)",
            (
                cid,
                _j(labels or []),
                _j(definition_passage_ids or []),
                _j(realms or []),
                str(realm_scope),
                str(introduced_in),
                _nowz(),
                str(created_by),
            ),
        )
        con.commit()
        con.close()
        return cid

    def upsert_auto_concept(
        self,
        *,
        concept_id: str,
        label: str,
        definition_passage_id: str = "",
        realms: Optional[List[str]] = None,
        introduced_in: str = "",
        created_by: str = "system",
    ) -> str:
        existing = self.get_concept(str(concept_id)) or {}
        labels = []
        for item in list(existing.get("labels") or []) + [str(label or "")]:
            v = str(item or "").strip()
            if v and v not in labels:
                labels.append(v)
        defs = []
        for item in list(existing.get("definition_passage_ids") or []) + ([str(definition_passage_id)] if str(definition_passage_id or "").strip() else []):
            v = str(item or "").strip()
            if v and v not in defs:
                defs.append(v)
        all_realms = []
        for item in list(existing.get("realms") or []) + list(realms or []):
            v = str(item or "").strip()
            if v and v not in all_realms:
                all_realms.append(v)
        return self.add_concept(
            concept_id=str(concept_id),
            labels=labels,
            definition_passage_ids=defs,
            realms=all_realms,
            realm_scope=str(existing.get("realm_scope") or ""),
            introduced_in=str(introduced_in or existing.get("introduced_in") or ""),
            created_by=str(created_by or "system"),
        )

    # === NoemaForge Autodoc Function Header ===
    # Function: add_claim(self, claim_id: Optional[str] = None, text_normalized: str, about_concepts: Optional[List[str]] = None, realm_context: Optional[Dict[str, Any]] = None, status: str = 'hypothesis', confidence: float = 0.1, extracted_from_passages: Optional[List[str]] = None, supported_by_evidence: Optional[List[str]] = None, counterclaims: Optional[List[str]] = None, created_by: str = 'system')
    # Purpose: Implement the routine 'add claim'.
    # Inputs:
    #   - self
    #   - claim_id: Optional[str] = None
    #   - text_normalized: str
    #   - about_concepts: Optional[List[str]] = None
    #   - realm_context: Optional[Dict[str, Any]] = None
    #   - status: str = 'hypothesis'
    #   - confidence: float = 0.1
    #   - extracted_from_passages: Optional[List[str]] = None
    #   - supported_by_evidence: Optional[List[str]] = None
    #   - counterclaims: Optional[List[str]] = None
    #   - created_by: str = 'system'
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - str, _connect, cursor, execute, commit, close, uuid4, _j, float, _nowz
    # Returns / emits: str
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - cid, con, cur, pids
    # === End NoemaForge Autodoc Function Header ===
    def add_claim(
        self,
        *,
        claim_id: Optional[str] = None,
        text_normalized: str,
        about_concepts: Optional[List[str]] = None,
        realm_context: Optional[Dict[str, Any]] = None,
        status: str = "hypothesis",
        confidence: float = 0.1,
        extracted_from_passages: Optional[List[str]] = None,
        supported_by_evidence: Optional[List[str]] = None,
        counterclaims: Optional[List[str]] = None,
        created_by: str = "system",
    ) -> str:
        cid = str(claim_id or uuid.uuid4())
        # Invariant (soft): claim should not float without passages.
        pids = extracted_from_passages or []
        con = self._connect()
        cur = con.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO claims(claim_id, text_normalized, about_concepts_json, realm_context_json, status, confidence, extracted_from_passages_json, supported_by_evidence_json, counterclaims_json, created_at, created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                cid,
                str(text_normalized),
                _j(about_concepts or []),
                _j(realm_context or {}),
                str(status),
                float(confidence),
                _j(pids),
                _j(supported_by_evidence or []),
                _j(counterclaims or []),
                _nowz(),
                str(created_by),
            ),
        )
        con.commit()
        con.close()
        return cid

    # === NoemaForge Autodoc Function Header ===
    # Function: add_conflict(self, conflict_id: Optional[str] = None, entity_a: str, entity_b: str, incompatibility_type: str = 'logical_exclusion', realm_context: Optional[Dict[str, Any]] = None, status: str = 'Unresolved', confidence: float = 0.5, unresolved_reason: str = 'insufficient_evidence', decision_trace: str = '', created_by: str = 'system')
    # Purpose: Implement the routine 'add conflict'.
    # Inputs:
    #   - self
    #   - conflict_id: Optional[str] = None
    #   - entity_a: str
    #   - entity_b: str
    #   - incompatibility_type: str = 'logical_exclusion'
    #   - realm_context: Optional[Dict[str, Any]] = None
    #   - status: str = 'Unresolved'
    #   - confidence: float = 0.5
    #   - unresolved_reason: str = 'insufficient_evidence'
    #   - decision_trace: str = ''
    #   - created_by: str = 'system'
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - str, _connect, cursor, execute, commit, close, uuid4, _j, float, _nowz
    # Returns / emits: str
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - cid, con, cur
    # === End NoemaForge Autodoc Function Header ===
    def add_conflict(
        self,
        *,
        conflict_id: Optional[str] = None,
        entity_a: str,
        entity_b: str,
        incompatibility_type: str = "logical_exclusion",
        realm_context: Optional[Dict[str, Any]] = None,
        status: str = "Unresolved",
        confidence: float = 0.5,
        unresolved_reason: str = "insufficient_evidence",
        decision_trace: str = "",
        created_by: str = "system",
    ) -> str:
        cid = str(conflict_id or uuid.uuid4())
        con = self._connect()
        cur = con.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO conflicts(conflict_id, entity_a, entity_b, incompatibility_type, realm_context_json, status, confidence, unresolved_reason, decision_trace, created_at, created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                cid,
                str(entity_a),
                str(entity_b),
                str(incompatibility_type),
                _j(realm_context or {}),
                str(status),
                float(confidence),
                str(unresolved_reason),
                str(decision_trace),
                _nowz(),
                str(created_by),
            ),
        )
        con.commit()
        con.close()
        return cid

    # === NoemaForge Autodoc Function Header ===
    # Function: add_trail(self, trail_id: Optional[str] = None, level: str, goal: str, goal_type: str = 'learn', realm_profile: Optional[Dict[str, Any]] = None, gates: Optional[Dict[str, Any]] = None, entry_conditions: Optional[Dict[str, Any]] = None, exit_outcomes: Optional[Dict[str, Any]] = None, subtrails: Optional[List[str]] = None, created_by: str = 'system')
    # Purpose: Implement the routine 'add trail'.
    # Inputs:
    #   - self
    #   - trail_id: Optional[str] = None
    #   - level: str
    #   - goal: str
    #   - goal_type: str = 'learn'
    #   - realm_profile: Optional[Dict[str, Any]] = None
    #   - gates: Optional[Dict[str, Any]] = None
    #   - entry_conditions: Optional[Dict[str, Any]] = None
    #   - exit_outcomes: Optional[Dict[str, Any]] = None
    #   - subtrails: Optional[List[str]] = None
    #   - created_by: str = 'system'
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - str, _connect, cursor, execute, commit, close, uuid4, _j, _nowz
    # Returns / emits: str
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, tid
    # === End NoemaForge Autodoc Function Header ===
    def add_trail(
        self,
        *,
        trail_id: Optional[str] = None,
        level: str,
        goal: str,
        goal_type: str = "learn",
        realm_profile: Optional[Dict[str, Any]] = None,
        gates: Optional[Dict[str, Any]] = None,
        entry_conditions: Optional[Dict[str, Any]] = None,
        exit_outcomes: Optional[Dict[str, Any]] = None,
        subtrails: Optional[List[str]] = None,
        created_by: str = "system",
    ) -> str:
        tid = str(trail_id or uuid.uuid4())
        con = self._connect()
        cur = con.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO trails(trail_id, level, goal, goal_type, realm_profile_json, gates_json, entry_conditions_json, exit_outcomes_json, subtrails_json, created_at, created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                tid,
                str(level),
                str(goal),
                str(goal_type),
                _j(realm_profile or {}),
                _j(gates or {}),
                _j(entry_conditions or {}),
                _j(exit_outcomes or {}),
                _j(subtrails or []),
                _nowz(),
                str(created_by),
            ),
        )
        con.commit()
        con.close()
        return tid

    # === NoemaForge Autodoc Function Header ===
    # Function: add_trail_step(self, trail_id: str, step_idx: int, node_ref: Dict[str, Any], step_type: str = 'node', why_this_step: str = '', expected_takeaway: str = '', branch_options: Optional[Dict[str, Any]] = None)
    # Purpose: Implement the routine 'add trail step'.
    # Inputs:
    #   - self
    #   - trail_id: str
    #   - step_idx: int
    #   - node_ref: Dict[str, Any]
    #   - step_type: str = 'node'
    #   - why_this_step: str = ''
    #   - expected_takeaway: str = ''
    #   - branch_options: Optional[Dict[str, Any]] = None
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, execute, commit, close, str, int, _j
    # Returns / emits: None
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur
    # === End NoemaForge Autodoc Function Header ===
    def add_trail_step(
        self,
        *,
        trail_id: str,
        step_idx: int,
        node_ref: Dict[str, Any],
        step_type: str = "node",
        why_this_step: str = "",
        expected_takeaway: str = "",
        branch_options: Optional[Dict[str, Any]] = None,
    ) -> None:
        con = self._connect()
        cur = con.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO trail_steps(trail_id, step_idx, node_ref_json, step_type, why_this_step, expected_takeaway, branch_options_json) VALUES(?,?,?,?,?,?,?)",
            (
                str(trail_id),
                int(step_idx),
                _j(node_ref),
                str(step_type),
                str(why_this_step),
                str(expected_takeaway),
                _j(branch_options or {}),
            ),
        )
        con.commit()
        con.close()

    # -------------------
    # Retrieval primitives
    # -------------------

    # === NoemaForge Autodoc Function Header ===
    # Function: list_trail_steps(self, trail_id: str)
    # Purpose: Implement the routine 'list trail steps'.
    # Inputs:
    #   - self
    #   - trail_id: str
    # Called by:
    #   - src/knowledge/trails.py
    # Calls:
    #   - _connect, cursor, execute, close, dict, _jd, str, fetchall, get
    # Returns / emits: List[Dict[str, Any]]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, r, rows
    # === End NoemaForge Autodoc Function Header ===
    def list_trail_steps(self, trail_id: str) -> List[Dict[str, Any]]:
        con = self._connect()
        cur = con.cursor()
        cur.execute("SELECT * FROM trail_steps WHERE trail_id=? ORDER BY step_idx ASC", (str(trail_id),))
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        for r in rows:
            r["node_ref"] = _jd(r.get("node_ref_json") or "")
            r["branch_options"] = _jd(r.get("branch_options_json") or "")
        return rows

    # === NoemaForge Autodoc Function Header ===
    # Function: fetch_by_ids(self, table: str, ids: Iterable[str])
    # Purpose: Implement the routine 'fetch by ids'.
    # Inputs:
    #   - self
    #   - table: str
    #   - ids: Iterable[str]
    # Called by:
    #   - src/knowledge/trails.py
    # Calls:
    #   - _connect, cursor, execute, close, str, dict, strip, join, fetchall, len
    # Returns / emits: List[Dict[str, Any]]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, ids, pk, q, rows
    # === End NoemaForge Autodoc Function Header ===
    def fetch_by_ids(self, table: str, ids: Iterable[str]) -> List[Dict[str, Any]]:
        ids = [str(x) for x in ids if str(x).strip()]
        if not ids:
            return []
        query = FETCH_BY_ID_QUERIES.get(table)
        if not query:
            return []
        con = self._connect()
        cur = con.cursor()
        rows = []
        seen = set()
        for object_id in ids:
            if object_id in seen:
                continue
            seen.add(object_id)
            cur.execute(query, (object_id,))
            row = cur.fetchone()
            if row:
                rows.append(dict(row))
        con.close()
        return rows


    # -------------------
    # Linkbase / overlays / lineage (v0.19.0)
    # -------------------

    # === NoemaForge Autodoc Function Header ===
    # Function: create_context(self, title: str, description: str = '', policies: Optional[Dict[str, Any]] = None, created_by: str = '')
    # Purpose: Implement the routine 'create context'.
    # Inputs:
    #   - self
    #   - title: str
    #   - description: str = ''
    #   - policies: Optional[Dict[str, Any]] = None
    #   - created_by: str = ''
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - str, _connect, execute, commit, close, uuid4, dumps, _nowz
    # Returns / emits: str
    # Side effects:
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - cid, con
    # === End NoemaForge Autodoc Function Header ===
    def create_context(self, *, title: str, description: str = "", policies: Optional[Dict[str, Any]] = None, created_by: str = "") -> str:
        cid = str(uuid.uuid4())
        con = self._connect()
        con.execute(
            "INSERT INTO contexts(context_id, title, description, policies_json, created_at, created_by) VALUES(?,?,?,?,?,?)",
            (
                cid,
                str(title or ""),
                str(description or ""),
                json.dumps(policies or {}, ensure_ascii=False),
                _nowz(),
                str(created_by or ""),
            ),
        )
        con.commit()
        con.close()
        return cid

    # === NoemaForge Autodoc Function Header ===
    # Function: add_annotation(self, target_kind: str, target_id: str, context_id: str = '', anchor: Optional[Dict[str, Any]] = None, annotation_type: str = 'note', content: str = '', created_by: str = '')
    # Purpose: Implement the routine 'add annotation'.
    # Inputs:
    #   - self
    #   - target_kind: str
    #   - target_id: str
    #   - context_id: str = ''
    #   - anchor: Optional[Dict[str, Any]] = None
    #   - annotation_type: str = 'note'
    #   - content: str = ''
    #   - created_by: str = ''
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - str, _connect, execute, commit, close, uuid4, dumps, _nowz
    # Returns / emits: str
    # Side effects:
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - aid, con
    # === End NoemaForge Autodoc Function Header ===
    def add_annotation(
        self,
        *,
        target_kind: str,
        target_id: str,
        context_id: str = "",
        anchor: Optional[Dict[str, Any]] = None,
        annotation_type: str = "note",
        content: str = "",
        created_by: str = "",
    ) -> str:
        aid = str(uuid.uuid4())
        con = self._connect()
        con.execute(
            "INSERT INTO annotations(annotation_id, target_kind, target_id, context_id, anchor_json, annotation_type, content, created_at, created_by) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                aid,
                str(target_kind or ""),
                str(target_id or ""),
                str(context_id or ""),
                json.dumps(anchor or {}, ensure_ascii=False),
                str(annotation_type or "note"),
                str(content or ""),
                _nowz(),
                str(created_by or ""),
            ),
        )
        con.commit()
        con.close()
        return aid

    # === NoemaForge Autodoc Function Header ===
    # Function: list_annotations(self, target_kind: str, target_id: str, context_id: str = '')
    # Purpose: Implement the routine 'list annotations'.
    # Inputs:
    #   - self
    #   - target_kind: str
    #   - target_id: str
    #   - context_id: str = ''
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, execute, close, str, append, tuple, dict, fetchall
    # Returns / emits: List[Dict[str, Any]]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    #   - appends to logs or files
    # Key locals:
    #   - args, con, cur, q, rows
    # === End NoemaForge Autodoc Function Header ===
    def list_annotations(self, *, target_kind: str, target_id: str, context_id: str = "") -> List[Dict[str, Any]]:
        con = self._connect()
        cur = con.cursor()
        q = "SELECT annotation_id, context_id, annotation_type, content, created_at, created_by FROM annotations WHERE target_kind=? AND target_id=?"
        args: List[Any] = [str(target_kind), str(target_id)]
        if context_id:
            q += " AND context_id=?"
            args.append(str(context_id))
        q += " ORDER BY created_at ASC"
        cur.execute(q, tuple(args))
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return rows

    # === NoemaForge Autodoc Function Header ===
    # Function: add_link(self, from_kind: str, from_id: str, to_kind: str, to_id: str, link_type: str, conditions: Optional[Dict[str, Any]] = None, created_by: str = '')
    # Purpose: Implement the routine 'add link'.
    # Inputs:
    #   - self
    #   - from_kind: str
    #   - from_id: str
    #   - to_kind: str
    #   - to_id: str
    #   - link_type: str
    #   - conditions: Optional[Dict[str, Any]] = None
    #   - created_by: str = ''
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - str, _connect, execute, commit, close, uuid4, dumps, _nowz
    # Returns / emits: str
    # Side effects:
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, lid
    # === End NoemaForge Autodoc Function Header ===
    def add_link(
        self,
        *,
        from_kind: str,
        from_id: str,
        to_kind: str,
        to_id: str,
        link_type: str,
        conditions: Optional[Dict[str, Any]] = None,
        created_by: str = "",
        link_id: Optional[str] = None,
    ) -> str:
        lid = str(link_id or uuid.uuid4())
        con = self._connect()
        con.execute(
            "INSERT OR REPLACE INTO links(link_id, from_kind, from_id, to_kind, to_id, link_type, conditions_json, created_at, created_by) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                lid,
                str(from_kind),
                str(from_id),
                str(to_kind),
                str(to_id),
                str(link_type),
                json.dumps(conditions or {}, ensure_ascii=False),
                _nowz(),
                str(created_by or ""),
            ),
        )
        con.commit()
        con.close()
        return lid

    # === NoemaForge Autodoc Function Header ===
    # Function: list_links(self, kind: str, obj_id: str, direction: str = 'out')
    # Purpose: Implement the routine 'list links'.
    # Inputs:
    #   - self
    #   - kind: str
    #   - obj_id: str
    #   - direction: str = 'out'
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, close, execute, dict, fetchall, str
    # Returns / emits: List[Dict[str, Any]]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, rows
    # === End NoemaForge Autodoc Function Header ===
    def list_links(self, *, kind: str, obj_id: str, direction: str = "out") -> List[Dict[str, Any]]:
        con = self._connect()
        cur = con.cursor()
        if direction == "in":
            cur.execute(
                "SELECT link_id, from_kind, from_id, to_kind, to_id, link_type, created_at, created_by FROM links WHERE to_kind=? AND to_id=? ORDER BY created_at ASC",
                (str(kind), str(obj_id)),
            )
        else:
            cur.execute(
                "SELECT link_id, from_kind, from_id, to_kind, to_id, link_type, created_at, created_by FROM links WHERE from_kind=? AND from_id=? ORDER BY created_at ASC",
                (str(kind), str(obj_id)),
            )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return rows

    # === NoemaForge Autodoc Function Header ===
    # Function: add_evidence(self, kind: str, strength: float = 0.5, source_refs: Optional[List[Dict[str, Any]]] = None, support_passages: Optional[List[Dict[str, Any]]] = None, realm_context: Optional[Dict[str, Any]] = None, notes: str = '', created_by: str = '')
    # Purpose: Implement the routine 'add evidence'.
    # Inputs:
    #   - self
    #   - kind: str
    #   - strength: float = 0.5
    #   - source_refs: Optional[List[Dict[str, Any]]] = None
    #   - support_passages: Optional[List[Dict[str, Any]]] = None
    #   - realm_context: Optional[Dict[str, Any]] = None
    #   - notes: str = ''
    #   - created_by: str = ''
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - str, _connect, execute, commit, close, uuid4, float, dumps, _nowz
    # Returns / emits: str
    # Side effects:
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, eid
    # === End NoemaForge Autodoc Function Header ===
    def add_evidence(
        self,
        *,
        kind: str,
        strength: float = 0.5,
        source_refs: Optional[List[Dict[str, Any]]] = None,
        support_passages: Optional[List[Dict[str, Any]]] = None,
        realm_context: Optional[Dict[str, Any]] = None,
        notes: str = "",
        created_by: str = "",
        evidence_id: Optional[str] = None,
    ) -> str:
        eid = str(evidence_id or uuid.uuid4())
        con = self._connect()
        con.execute(
            "INSERT OR REPLACE INTO evidence(evidence_id, kind, strength, source_refs_json, support_passages_json, realm_context_json, notes, created_at, created_by) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                eid,
                str(kind or ""),
                float(strength),
                json.dumps(source_refs or [], ensure_ascii=False),
                json.dumps(support_passages or [], ensure_ascii=False),
                json.dumps(realm_context or {}, ensure_ascii=False),
                str(notes or ""),
                _nowz(),
                str(created_by or ""),
            ),
        )
        con.commit()
        con.close()
        return eid

    # === NoemaForge Autodoc Function Header ===
    # Function: add_argument(self, argument_type: str, premises: Optional[List[Dict[str, Any]]] = None, conclusion_claim_id: str = '', assumptions: Optional[List[Dict[str, Any]]] = None, evidence_refs: Optional[List[str]] = None, created_by: str = '')
    # Purpose: Implement the routine 'add argument'.
    # Inputs:
    #   - self
    #   - argument_type: str
    #   - premises: Optional[List[Dict[str, Any]]] = None
    #   - conclusion_claim_id: str = ''
    #   - assumptions: Optional[List[Dict[str, Any]]] = None
    #   - evidence_refs: Optional[List[str]] = None
    #   - created_by: str = ''
    # Called by:
    #   - bootstrap/microvm/noemaforge-microvm-run.py
    #   - src/bootdoctor.py
    #   - src/brainctl.py
    #   - src/noemaforge_core.py
    #   - src/brainui.py
    #   - src/canary_runner.py
    #   - src/coordinator_fanout.py
    #   - src/doctor.py
    # Calls:
    #   - str, _connect, execute, commit, close, uuid4, dumps, _nowz
    # Returns / emits: str
    # Side effects:
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - aid, con
    # === End NoemaForge Autodoc Function Header ===
    def add_argument(
        self,
        *,
        argument_type: str,
        premises: Optional[List[Dict[str, Any]]] = None,
        conclusion_claim_id: str = "",
        assumptions: Optional[List[Dict[str, Any]]] = None,
        evidence_refs: Optional[List[str]] = None,
        created_by: str = "",
    ) -> str:
        aid = str(uuid.uuid4())
        con = self._connect()
        con.execute(
            "INSERT INTO arguments(argument_id, argument_type, premises_json, conclusion_claim_id, assumptions_json, evidence_refs_json, created_at, created_by) VALUES(?,?,?,?,?,?,?,?)",
            (
                aid,
                str(argument_type or ""),
                json.dumps(premises or [], ensure_ascii=False),
                str(conclusion_claim_id or ""),
                json.dumps(assumptions or [], ensure_ascii=False),
                json.dumps(evidence_refs or [], ensure_ascii=False),
                _nowz(),
                str(created_by or ""),
            ),
        )
        con.commit()
        con.close()
        return aid

    # === NoemaForge Autodoc Function Header ===
    # Function: add_issue(self, question: str, positions: Optional[List[Dict[str, Any]]] = None, argument_refs: Optional[List[str]] = None, created_by: str = '')
    # Purpose: Implement the routine 'add issue'.
    # Inputs:
    #   - self
    #   - question: str
    #   - positions: Optional[List[Dict[str, Any]]] = None
    #   - argument_refs: Optional[List[str]] = None
    #   - created_by: str = ''
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - str, _connect, execute, commit, close, uuid4, dumps, _nowz
    # Returns / emits: str
    # Side effects:
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, iid
    # === End NoemaForge Autodoc Function Header ===
    def add_issue(
        self,
        *,
        question: str,
        positions: Optional[List[Dict[str, Any]]] = None,
        argument_refs: Optional[List[str]] = None,
        created_by: str = "",
    ) -> str:
        iid = str(uuid.uuid4())
        con = self._connect()
        con.execute(
            "INSERT INTO issues(issue_id, question, positions_json, argument_refs_json, created_at, created_by) VALUES(?,?,?,?,?,?)",
            (
                iid,
                str(question or ""),
                json.dumps(positions or [], ensure_ascii=False),
                json.dumps(argument_refs or [], ensure_ascii=False),
                _nowz(),
                str(created_by or ""),
            ),
        )
        con.commit()
        con.close()
        return iid

    # === NoemaForge Autodoc Function Header ===
    # Function: add_lineage_link(self, child_kind: str, child_id: str, relation_type: str, parents: Optional[List[Dict[str, Any]]] = None, declared_derivation: Optional[Dict[str, Any]] = None, computed_checks: Optional[Dict[str, Any]] = None, support_passages: Optional[List[Dict[str, Any]]] = None, confidence: float = 0.5, realm_context: Optional[Dict[str, Any]] = None, created_by: str = '')
    # Purpose: Implement the routine 'add lineage link'.
    # Inputs:
    #   - self
    #   - child_kind: str
    #   - child_id: str
    #   - relation_type: str
    #   - parents: Optional[List[Dict[str, Any]]] = None
    #   - declared_derivation: Optional[Dict[str, Any]] = None
    #   - computed_checks: Optional[Dict[str, Any]] = None
    #   - support_passages: Optional[List[Dict[str, Any]]] = None
    #   - confidence: float = 0.5
    #   - realm_context: Optional[Dict[str, Any]] = None
    #   - created_by: str = ''
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - str, _connect, execute, commit, close, uuid4, dumps, float, _nowz
    # Returns / emits: str
    # Side effects:
    #   - serializes structured data
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, lid
    # === End NoemaForge Autodoc Function Header ===
    def add_lineage_link(
        self,
        *,
        child_kind: str,
        child_id: str,
        relation_type: str,
        parents: Optional[List[Dict[str, Any]]] = None,
        declared_derivation: Optional[Dict[str, Any]] = None,
        computed_checks: Optional[Dict[str, Any]] = None,
        support_passages: Optional[List[Dict[str, Any]]] = None,
        confidence: float = 0.5,
        realm_context: Optional[Dict[str, Any]] = None,
        created_by: str = "",
        lineage_id: Optional[str] = None,
    ) -> str:
        lid = str(lineage_id or uuid.uuid4())
        con = self._connect()
        con.execute(
            "INSERT OR REPLACE INTO lineage_links(lineage_id, child_kind, child_id, relation_type, parents_json, declared_derivation_json, computed_checks_json, support_passages_json, confidence, realm_context_json, created_at, created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                lid,
                str(child_kind or ""),
                str(child_id or ""),
                str(relation_type or ""),
                json.dumps(parents or [], ensure_ascii=False),
                json.dumps(declared_derivation or {}, ensure_ascii=False),
                json.dumps(computed_checks or {}, ensure_ascii=False),
                json.dumps(support_passages or [], ensure_ascii=False),
                float(confidence),
                json.dumps(realm_context or {}, ensure_ascii=False),
                _nowz(),
                str(created_by or ""),
            ),
        )
        con.commit()
        con.close()
        return lid

    # === NoemaForge Autodoc Function Header ===
    # Function: list_lineage_for_child(self, child_kind: str, child_id: str)
    # Purpose: Implement the routine 'list lineage for child'.
    # Inputs:
    #   - self
    #   - child_kind: str
    #   - child_id: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _connect, cursor, execute, close, dict, _jd, str, fetchall, get
    # Returns / emits: List[Dict[str, Any]]
    # Side effects:
    #   - opens a database or socket connection
    #   - executes SQL or shell-like commands
    # Key locals:
    #   - con, cur, r, rows
    # === End NoemaForge Autodoc Function Header ===
    def list_lineage_for_child(self, *, child_kind: str, child_id: str) -> List[Dict[str, Any]]:
        con = self._connect()
        cur = con.cursor()
        cur.execute(
            "SELECT lineage_id, relation_type, parents_json, declared_derivation_json, computed_checks_json, support_passages_json, confidence, created_at, created_by FROM lineage_links WHERE child_kind=? AND child_id=? ORDER BY created_at ASC",
            (str(child_kind), str(child_id)),
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        for r in rows:
            r['parents'] = _jd(r.get('parents_json') or '')
            r['declared_derivation'] = _jd(r.get('declared_derivation_json') or '')
            r['computed_checks'] = _jd(r.get('computed_checks_json') or '')
            r['support_passages'] = _jd(r.get('support_passages_json') or '')
        return rows
