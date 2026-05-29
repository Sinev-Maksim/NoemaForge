#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/knowledge/prep_store.py
Zone: release/package
Version: 0.32.2
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
# File: src/knowledge/prep_store.py
# Zone: brain
# Purpose: Provide the durable prep-store for long-form source preprocessing, queueing,
#   topic-adjacency chunk planning metadata, and JSONL import/export.
# Callers: src/brainctl.py, future long-form ingest pipelines, tests/test_prep_store.py
# Inputs: knowledge-policy paths, SQLite DDL in sql/prep_store.sqlite.sql, JSONL row files
# Outputs: SQLite database files, JSONL exports, queue/provenance records
# Side effects: creates directories, opens SQLite databases, writes JSONL files
# Security notes:
#   - invariants: prep metadata is durable; transient chunk bodies are not persisted here
#   - threats: provenance corruption, silent schema drift, accidental reuse across checksum mismatch
# === End NoemaForge Autodoc File Header ===

"""NoemaForge durable prep-store runtime adapter.

This module implements the Phase B2 runtime layer for long-form source preprocessing.
It is intentionally separate from the canonical hypergraph ontology. The prep-store keeps
stable metadata that makes book/chapter/section processing reproducible:

- queue-first ingestion
- normalized text artifacts
- sentence topic maps
- adjacency groups
- split trees
- passage / claim provenance origins

Leaf chunk bodies are expected to be handled in memory by downstream pipelines and are
not persisted here by default.
"""


import hashlib
import json
import mimetypes
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence


def _nowz() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _j(obj: Any) -> str:
    return json.dumps(obj if obj is not None else {}, ensure_ascii=False, sort_keys=True)


def _uuid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _sentence_num_from_id(sentence_id: str) -> int:
    try:
        return int(str(sentence_id).rsplit(':', 1)[-1])
    except Exception:
        return 0


TABLE_ORDER: List[str] = [
    "books",
    "book_queue_entries",
    "chapters",
    "sections",
    "normalized_text_artifacts",
    "processing_runs",
    "sentences",
    "sentence_topic_maps",
    "adjacency_groups",
    "split_nodes",
    "passage_origins",
    "claim_origins",
]


class PrepStore:
    """Durable SQLite prep-store for long-form source preprocessing."""

    def _decode_passage_origin_row(self, row: sqlite3.Row | None) -> Dict[str, Any] | None:
        if not row:
            return None
        d = dict(row)
        return d

    def _decode_claim_origin_row(self, row: sqlite3.Row | None) -> Dict[str, Any] | None:
        if not row:
            return None
        d = dict(row)
        try:
            d['primary_address'] = json.loads(str(d.get('primary_address_json') or '{}'))
        except Exception:
            d['primary_address'] = {}
        try:
            d['evidence_spans'] = json.loads(str(d.get('evidence_spans_json') or '[]'))
        except Exception:
            d['evidence_spans'] = []
        return d


    def __init__(self, db_path: str, *, sql_path: str | None = None):
        self.db_path = str(db_path)
        self.sql_path = sql_path or str(Path(__file__).resolve().parents[2] / "sql" / "prep_store.sqlite.sql")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def _init_db(self) -> None:
        sql = Path(self.sql_path).read_text(encoding="utf-8")
        with self._connect() as con:
            con.executescript(sql)
            con.commit()

    def _table_columns(self, con: sqlite3.Connection, table: str) -> List[str]:
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        return [str(r["name"]) for r in rows]

    def _all_tables(self, con: sqlite3.Connection) -> List[str]:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [str(r["name"]) for r in rows]

    def list_tables(self) -> List[str]:
        with self._connect() as con:
            return self._all_tables(con)

    def next_queue_position(self, *, queue_name: str = "default") -> int:
        with self._connect() as con:
            row = con.execute(
                "SELECT COALESCE(MAX(ingest_queue_position), 0) + 1 AS pos FROM book_queue_entries WHERE queue_name=?",
                (str(queue_name),),
            ).fetchone()
            return int((row["pos"] if row else 1) or 1)

    def find_reusable_book(self, *, book_checksum: str, canonicalization_profile: str) -> Dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM books WHERE book_checksum=? AND canonicalization_profile=? ORDER BY enqueue_ts DESC LIMIT 1",
                (str(book_checksum), str(canonicalization_profile)),
            ).fetchone()
            return dict(row) if row else None

    def enqueue_book(
        self,
        *,
        source_id: str,
        source_path: str,
        source_mime: str = "",
        source_size_bytes: int | None = None,
        book_title: str = "",
        edition: str = "",
        language: str = "",
        book_checksum: str,
        book_checksum_alg: str = "sha256",
        canonicalization_profile: str = "default",
        queue_name: str = "default",
        priority: int = 100,
        ingest_queue_position: int | None = None,
        enqueue_ts: str | None = None,
        status: str = "queued",
    ) -> Dict[str, Any]:
        queue_entry_id = _uuid("queue")
        ts = str(enqueue_ts or _nowz())
        pos = int(ingest_queue_position or self.next_queue_position(queue_name=str(queue_name)))
        with self._connect() as con:
            row = con.execute(
                "SELECT book_id FROM books WHERE source_id=? AND book_checksum=? AND canonicalization_profile=? ORDER BY enqueue_ts DESC LIMIT 1",
                (str(source_id), str(book_checksum), str(canonicalization_profile)),
            ).fetchone()
            book_id = str(row["book_id"]) if row else _uuid("book")
            reused_book = bool(row)
            if not row:
                con.execute(
                    """
                    INSERT INTO books (
                      book_id, source_id, source_path, source_mime, source_size_bytes,
                      book_title, edition, language, book_checksum, book_checksum_alg,
                      canonicalization_profile, enqueue_ts, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        book_id,
                        str(source_id),
                        str(source_path),
                        str(source_mime or ""),
                        source_size_bytes,
                        str(book_title or ""),
                        str(edition or ""),
                        str(language or ""),
                        str(book_checksum),
                        str(book_checksum_alg),
                        str(canonicalization_profile),
                        ts,
                        str(status),
                    ),
                )
            qrow = con.execute(
                "SELECT ingest_queue_entry_id, ingest_queue_position, queue_name, queue_status FROM book_queue_entries WHERE book_id=? LIMIT 1",
                (str(book_id),),
            ).fetchone()
            if qrow:
                con.commit()
                return {
                    "ok": True,
                    "book_id": book_id,
                    "ingest_queue_entry_id": str(qrow["ingest_queue_entry_id"]),
                    "ingest_queue_position": int(qrow["ingest_queue_position"]),
                    "queue_name": str(qrow["queue_name"]),
                    "queue_status": str(qrow["queue_status"]),
                    "book_checksum": str(book_checksum),
                    "reused_book": reused_book,
                    "reused_queue_entry": True,
                }
            con.execute(
                """
                INSERT INTO book_queue_entries (
                  ingest_queue_entry_id, book_id, queue_name, ingest_queue_position,
                  priority, enqueued_at, queue_status
                ) VALUES (?, ?, ?, ?, ?, ?, 'queued')
                """,
                (queue_entry_id, book_id, str(queue_name), pos, int(priority), ts),
            )
            con.commit()
        return {
            "ok": True,
            "book_id": book_id,
            "ingest_queue_entry_id": queue_entry_id,
            "ingest_queue_position": pos,
            "queue_name": str(queue_name),
            "book_checksum": str(book_checksum),
            "reused_book": reused_book,
            "reused_queue_entry": False,
        }

    def enqueue_book_path(
        self,
        *,
        path: str,
        source_id: str | None = None,
        book_title: str = "",
        edition: str = "",
        language: str = "",
        canonicalization_profile: str = "default",
        queue_name: str = "default",
        priority: int = 100,
    ) -> Dict[str, Any]:
        ap = os.path.abspath(path)
        if not os.path.exists(ap):
            return {"ok": False, "reason": "file_not_found", "path": ap}
        chksum = _sha256_file(ap)
        mime = mimetypes.guess_type(ap)[0] or ""
        size = os.path.getsize(ap)
        sid = source_id or f"source:{chksum[:16]}"
        reusable = self.find_reusable_book(book_checksum=chksum, canonicalization_profile=str(canonicalization_profile))
        rep = self.enqueue_book(
            source_id=sid,
            source_path=ap,
            source_mime=mime,
            source_size_bytes=size,
            book_title=book_title or os.path.splitext(os.path.basename(ap))[0],
            edition=edition,
            language=language,
            book_checksum=chksum,
            canonicalization_profile=canonicalization_profile,
            queue_name=queue_name,
            priority=priority,
        )
        rep["reusable_book"] = reusable or {}
        rep["can_reuse_metadata"] = bool(reusable)
        return rep

    def mark_book_status(self, *, book_id: str, status: str, error_code: str = "", error_message: str = "") -> None:
        with self._connect() as con:
            con.execute(
                "UPDATE books SET status=?, last_error_code=?, last_error_message=? WHERE book_id=?",
                (str(status), str(error_code or ""), str(error_message or ""), str(book_id)),
            )
            con.commit()

    def add_chapter(
        self,
        *,
        book_id: str,
        chapter_no: int | None = None,
        chapter_title: str = "",
        chapter_path: str = "",
        raw_char_start: int | None = None,
        raw_char_end: int | None = None,
    ) -> str:
        chapter_id = _uuid("chapter")
        with self._connect() as con:
            con.execute(
                "INSERT INTO chapters (chapter_id, book_id, chapter_no, chapter_title, chapter_path, raw_char_start, raw_char_end) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chapter_id, str(book_id), chapter_no, str(chapter_title or ""), str(chapter_path or ""), raw_char_start, raw_char_end),
            )
            con.commit()
        return chapter_id

    def add_section(
        self,
        *,
        book_id: str,
        section_path: str,
        chapter_id: str | None = None,
        section_title: str = "",
        section_level: int | None = None,
        raw_char_start: int | None = None,
        raw_char_end: int | None = None,
    ) -> str:
        section_id = _uuid("section")
        with self._connect() as con:
            con.execute(
                "INSERT INTO sections (section_id, book_id, chapter_id, section_path, section_title, section_level, raw_char_start, raw_char_end) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (section_id, str(book_id), str(chapter_id) if chapter_id else None, str(section_path), str(section_title or ""), section_level, raw_char_start, raw_char_end),
            )
            con.commit()
        return section_id

    def add_normalized_text_artifact(
        self,
        *,
        book_id: str,
        artifact_scope: str,
        text: str,
        normalization_version: str,
        canonicalization_profile: str,
        chapter_id: str | None = None,
        section_id: str | None = None,
        created_at: str | None = None,
        checksum_alg: str = "sha256",
        artifact_relpath: str = "",
        artifact_encoding: str = "utf-8",
    ) -> Dict[str, Any]:
        normalized_text_artifact_id = _uuid("norm")
        checksum = hashlib.new(checksum_alg, (text or "").encode("utf-8")).hexdigest()
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO normalized_text_artifacts (
                  normalized_text_artifact_id, book_id, chapter_id, section_id, artifact_scope,
                  normalization_version, canonicalization_profile, normalized_text_checksum,
                  normalized_text_checksum_alg, artifact_relpath, artifact_encoding, text_length_chars, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_text_artifact_id,
                    str(book_id),
                    str(chapter_id) if chapter_id else None,
                    str(section_id) if section_id else None,
                    str(artifact_scope),
                    str(normalization_version),
                    str(canonicalization_profile),
                    checksum,
                    str(checksum_alg),
                    str(artifact_relpath or "") or None,
                    str(artifact_encoding or "utf-8"),
                    len(text or ""),
                    str(created_at or _nowz()),
                ),
            )
            con.commit()
        return {
            "normalized_text_artifact_id": normalized_text_artifact_id,
            "normalized_text_checksum": checksum,
            "normalized_text_checksum_alg": str(checksum_alg),
            "text_length_chars": len(text or ""),
            "artifact_relpath": str(artifact_relpath or ""),
            "artifact_encoding": str(artifact_encoding or "utf-8"),
        }

    def start_processing_run(
        self,
        *,
        component: str,
        book_id: str | None = None,
        model_id: str = "",
        model_version: str = "",
        prompt_hash: str = "",
        profile_id: str = "",
        policy_epoch: str = "",
        code_version: str = "",
        thresholds: Dict[str, Any] | None = None,
        started_at: str | None = None,
    ) -> str:
        run_id = _uuid("run")
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO processing_runs (
                  run_id, component, book_id, model_id, model_version, prompt_hash,
                  profile_id, policy_epoch, code_version, thresholds_json, started_at, run_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'running')
                """,
                (
                    run_id,
                    str(component),
                    str(book_id) if book_id else None,
                    str(model_id or ""),
                    str(model_version or ""),
                    str(prompt_hash or ""),
                    str(profile_id or ""),
                    str(policy_epoch or ""),
                    str(code_version or ""),
                    _j(thresholds or {}),
                    str(started_at or _nowz()),
                ),
            )
            con.commit()
        return run_id

    def finish_processing_run(
        self,
        *,
        run_id: str,
        run_status: str = "completed",
        error_code: str = "",
        error_message: str = "",
        finished_at: str | None = None,
    ) -> None:
        with self._connect() as con:
            con.execute(
                "UPDATE processing_runs SET finished_at=?, run_status=?, error_code=?, error_message=? WHERE run_id=?",
                (str(finished_at or _nowz()), str(run_status), str(error_code or ""), str(error_message or ""), str(run_id)),
            )
            con.commit()

    def add_sentence(
        self,
        *,
        book_id: str,
        normalized_text_artifact_id: str,
        sentence_no: int,
        char_start: int,
        char_end: int,
        text: str,
        chapter_id: str | None = None,
        section_id: str | None = None,
        paragraph_no: int | None = None,
        token_estimate: int | None = None,
        text_hash_alg: str = "sha256",
    ) -> str:
        sentence_id = f"sentence:{normalized_text_artifact_id}:{int(sentence_no)}"
        text_hash = hashlib.new(text_hash_alg, (text or "").encode("utf-8")).hexdigest()
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO sentences (
                  sentence_id, book_id, chapter_id, section_id, normalized_text_artifact_id,
                  sentence_no, paragraph_no, char_start, char_end, token_estimate, text_hash, text_hash_alg
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sentence_id,
                    str(book_id),
                    str(chapter_id) if chapter_id else None,
                    str(section_id) if section_id else None,
                    str(normalized_text_artifact_id),
                    int(sentence_no),
                    paragraph_no,
                    int(char_start),
                    int(char_end),
                    token_estimate,
                    text_hash,
                    str(text_hash_alg),
                ),
            )
            con.commit()
        return sentence_id

    def add_sentence_topic_map(
        self,
        *,
        sentence_id: str,
        labeling_run_id: str,
        topic_tags: Sequence[str],
        topic_signature: str,
        topic_confidence: float,
        adjacency_group_id: str | None = None,
        note: str = "",
    ) -> str:
        sentence_topic_map_id = _uuid("sentmap")
        with self._connect() as con:
            con.execute(
                "INSERT INTO sentence_topic_maps (sentence_topic_map_id, sentence_id, labeling_run_id, topic_tags_json, topic_signature, topic_confidence, adjacency_group_id, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sentence_topic_map_id,
                    str(sentence_id),
                    str(labeling_run_id),
                    _j(list(topic_tags)),
                    str(topic_signature),
                    float(topic_confidence),
                    str(adjacency_group_id) if adjacency_group_id else None,
                    str(note or ""),
                ),
            )
            con.commit()
        return sentence_topic_map_id

    def add_adjacency_group(
        self,
        *,
        book_id: str,
        built_run_id: str,
        sentence_start_id: str,
        sentence_end_id: str,
        topic_signature: str,
        topic_tags_union: Sequence[str],
        chapter_id: str | None = None,
        section_id: str | None = None,
        cohesion_score: float | None = None,
        estimated_tokens: int | None = None,
    ) -> str:
        adjacency_group_id = _uuid("adj")
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO adjacency_groups (
                  adjacency_group_id, book_id, chapter_id, section_id, built_run_id,
                  sentence_start_id, sentence_end_id, topic_signature, topic_tags_union_json,
                  cohesion_score, estimated_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    adjacency_group_id,
                    str(book_id),
                    str(chapter_id) if chapter_id else None,
                    str(section_id) if section_id else None,
                    str(built_run_id),
                    str(sentence_start_id),
                    str(sentence_end_id),
                    str(topic_signature),
                    _j(list(topic_tags_union)),
                    cohesion_score,
                    estimated_tokens,
                ),
            )
            con.commit()
        return adjacency_group_id

    def add_split_node(
        self,
        *,
        book_id: str,
        built_run_id: str,
        sentence_start_id: str,
        sentence_end_id: str,
        chapter_id: str | None = None,
        section_id: str | None = None,
        parent_split_node_id: str | None = None,
        adjacency_group_id: str | None = None,
        char_start: int | None = None,
        char_end: int | None = None,
        estimated_tokens: int | None = None,
        split_strategy: str = "",
        split_reason: str = "",
        boundary_mode: str = "sentence_span",
        fragment_spec: Dict[str, Any] | None = None,
        split_depth: int = 0,
        leaf_sequence_no: int | None = None,
        is_leaf: bool = False,
        chunk_quality_metrics: Dict[str, Any] | None = None,
    ) -> str:
        split_node_id = _uuid("split")
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO split_nodes (
                  split_node_id, book_id, chapter_id, section_id, built_run_id,
                  parent_split_node_id, adjacency_group_id, sentence_start_id, sentence_end_id,
                  char_start, char_end, estimated_tokens, split_strategy, split_reason, boundary_mode, fragment_spec_json, split_depth,
                  leaf_sequence_no, is_leaf, chunk_quality_metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    split_node_id,
                    str(book_id),
                    str(chapter_id) if chapter_id else None,
                    str(section_id) if section_id else None,
                    str(built_run_id),
                    str(parent_split_node_id) if parent_split_node_id else None,
                    str(adjacency_group_id) if adjacency_group_id else None,
                    str(sentence_start_id),
                    str(sentence_end_id),
                    char_start,
                    char_end,
                    estimated_tokens,
                    str(split_strategy or ""),
                    str(split_reason or ""),
                    str(boundary_mode or "sentence_span"),
                    _j(fragment_spec or {}),
                    int(split_depth),
                    leaf_sequence_no,
                    1 if is_leaf else 0,
                    _j(chunk_quality_metrics or {}),
                ),
            )
            con.commit()
        return split_node_id

    def record_passage_origin(
        self,
        *,
        passage_id: str,
        book_id: str,
        normalized_text_artifact_id: str,
        sentence_start_id: str,
        sentence_end_id: str,
        char_start: int,
        char_end: int,
        quote_fingerprint: str,
        extraction_run_id: str,
        chapter_id: str | None = None,
        section_id: str | None = None,
        split_leaf_id: str | None = None,
        trace_level: str = "L2",
        trace_completeness_score: float = 0.0,
    ) -> str:
        passage_origin_id = _uuid("porigin")
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO passage_origins (
                  passage_origin_id, passage_id, book_id, chapter_id, section_id,
                  normalized_text_artifact_id, split_leaf_id, sentence_start_id, sentence_end_id,
                  char_start, char_end, quote_fingerprint, extraction_run_id,
                  trace_level, trace_completeness_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    passage_origin_id,
                    str(passage_id),
                    str(book_id),
                    str(chapter_id) if chapter_id else None,
                    str(section_id) if section_id else None,
                    str(normalized_text_artifact_id),
                    str(split_leaf_id) if split_leaf_id else None,
                    str(sentence_start_id),
                    str(sentence_end_id),
                    int(char_start),
                    int(char_end),
                    str(quote_fingerprint),
                    str(extraction_run_id),
                    str(trace_level),
                    float(trace_completeness_score),
                ),
            )
            con.commit()
        return passage_origin_id

    def record_claim_origin(
        self,
        *,
        claim_id: str,
        source_id: str,
        passage_id: str,
        primary_address: Dict[str, Any],
        evidence_spans: List[Dict[str, Any]],
        claim_mode: str,
        quote_fingerprint: str,
        extraction_run_id: str,
        book_id: str | None = None,
        chapter_id: str | None = None,
        section_id: str | None = None,
        normalized_text_artifact_id: str | None = None,
        split_leaf_id: str | None = None,
        sentence_start_id: str | None = None,
        sentence_end_id: str | None = None,
        char_start: int | None = None,
        char_end: int | None = None,
        trace_level: str = "L3",
        trace_completeness_score: float = 0.0,
    ) -> str:
        claim_origin_id = _uuid("corigin")
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO claim_origins (
                  claim_origin_id, claim_id, source_id, book_id, chapter_id, section_id,
                  normalized_text_artifact_id, passage_id, split_leaf_id, sentence_start_id,
                  sentence_end_id, char_start, char_end, primary_address_json, evidence_spans_json,
                  claim_mode, quote_fingerprint, extraction_run_id, trace_level, trace_completeness_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_origin_id,
                    str(claim_id),
                    str(source_id),
                    str(book_id) if book_id else None,
                    str(chapter_id) if chapter_id else None,
                    str(section_id) if section_id else None,
                    str(normalized_text_artifact_id) if normalized_text_artifact_id else None,
                    str(passage_id),
                    str(split_leaf_id) if split_leaf_id else None,
                    str(sentence_start_id) if sentence_start_id else None,
                    str(sentence_end_id) if sentence_end_id else None,
                    char_start,
                    char_end,
                    _j(primary_address),
                    _j(evidence_spans),
                    str(claim_mode),
                    str(quote_fingerprint),
                    str(extraction_run_id),
                    str(trace_level),
                    float(trace_completeness_score),
                ),
            )
            con.commit()
        return claim_origin_id

    def list_queue(self, *, queue_name: str = "default", queue_status: str = "") -> List[Dict[str, Any]]:
        sql = """
            SELECT q.*, b.book_title, b.source_path, b.book_checksum, b.status AS book_status
            FROM book_queue_entries q
            JOIN books b ON b.book_id = q.book_id
            WHERE q.queue_name=?
        """
        params: List[Any] = [str(queue_name)]
        if str(queue_status or "").strip():
            sql += " AND q.queue_status=?"
            params.append(str(queue_status))
        sql += " ORDER BY q.priority ASC, q.ingest_queue_position ASC"
        with self._connect() as con:
            rows = con.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def lease_next_queue_entry(self, *, queue_name: str = "default", worker_id: str, lease_ttl_sec: int = 600, now: str | None = None) -> Dict[str, Any]:
        now_ts = str(now or _nowz())
        expires_epoch = int(time.time()) + int(lease_ttl_sec)
        lease_expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires_epoch))
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                """
                SELECT * FROM book_queue_entries
                WHERE queue_name=? AND queue_status='queued'
                ORDER BY priority ASC, ingest_queue_position ASC
                LIMIT 1
                """,
                (str(queue_name),),
            ).fetchone()
            if not row:
                con.rollback()
                return {"ok": True, "leased": False}
            con.execute(
                """
                UPDATE book_queue_entries
                SET queue_status='leased', worker_id=?, dequeued_at=?, lease_expires_at=?
                WHERE ingest_queue_entry_id=?
                """,
                (str(worker_id), now_ts, lease_expires_at, str(row["ingest_queue_entry_id"])),
            )
            con.commit()
            rep = dict(row)
            rep.update({
                "queue_status": "leased",
                "worker_id": str(worker_id),
                "dequeued_at": now_ts,
                "lease_expires_at": lease_expires_at,
            })
            return {"ok": True, "leased": True, "entry": rep}

    def complete_queue_entry(self, *, ingest_queue_entry_id: str, queue_status: str = "completed", completed_at: str | None = None) -> None:
        with self._connect() as con:
            con.execute(
                "UPDATE book_queue_entries SET queue_status=?, completed_at=?, lease_expires_at=NULL WHERE ingest_queue_entry_id=?",
                (str(queue_status), str(completed_at or _nowz()), str(ingest_queue_entry_id)),
            )
            con.commit()

    def get_book(self, *, book_id: str) -> Dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM books WHERE book_id=?", (str(book_id),)).fetchone()
            return dict(row) if row else None

    def get_queue_entry(self, *, ingest_queue_entry_id: str) -> Dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM book_queue_entries WHERE ingest_queue_entry_id=?", (str(ingest_queue_entry_id),)).fetchone()
            return dict(row) if row else None

    def list_book_chapters(self, *, book_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM chapters WHERE book_id=? ORDER BY COALESCE(chapter_no, 0), COALESCE(raw_char_start, 0)", (str(book_id),)).fetchall()
            return [dict(r) for r in rows]

    def list_book_sections(self, *, book_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM sections WHERE book_id=? ORDER BY COALESCE(raw_char_start, 0), section_path", (str(book_id),)).fetchall()
            return [dict(r) for r in rows]

    def list_book_sentences(self, *, book_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM sentences WHERE book_id=? ORDER BY sentence_no", (str(book_id),)).fetchall()
            return [dict(r) for r in rows]

    def list_book_adjacency_groups(self, *, book_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM adjacency_groups WHERE book_id=? ORDER BY COALESCE(chapter_id,''), COALESCE(section_id,''), rowid", (str(book_id),)).fetchall()
            return [dict(r) for r in rows]

    def list_leaf_nodes(self, *, book_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM split_nodes WHERE book_id=? AND is_leaf=1 ORDER BY leaf_sequence_no, split_depth, rowid", (str(book_id),)).fetchall()
            return [dict(r) for r in rows]

    def bind_adjacency_group(self, *, sentence_ids: Sequence[str], adjacency_group_id: str) -> None:
        if not sentence_ids:
            return
        with self._connect() as con:
            con.executemany(
                "UPDATE sentence_topic_maps SET adjacency_group_id=? WHERE sentence_id=?",
                [(str(adjacency_group_id), str(sid)) for sid in sentence_ids],
            )
            con.commit()

    def get_normalized_text_artifact(self, *, normalized_text_artifact_id: str) -> Dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM normalized_text_artifacts WHERE normalized_text_artifact_id=?", (str(normalized_text_artifact_id),)).fetchone()
            return dict(row) if row else None

    def get_sentence(self, *, sentence_id: str) -> Dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM sentences WHERE sentence_id=?", (str(sentence_id),)).fetchone()
            return dict(row) if row else None

    def list_sentences_between(self, *, sentence_start_id: str, sentence_end_id: str, artifact_root: str = "") -> List[Dict[str, Any]]:
        start_no = _sentence_num_from_id(sentence_start_id)
        end_no = _sentence_num_from_id(sentence_end_id)
        parts = str(sentence_start_id).split(":")
        artifact_id = parts[1] if len(parts) >= 3 else ""
        if not artifact_id:
            return []
        if end_no < start_no:
            start_no, end_no = end_no, start_no
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM sentences WHERE normalized_text_artifact_id=? AND sentence_no>=? AND sentence_no<=? ORDER BY sentence_no",
                (str(artifact_id), int(start_no), int(end_no)),
            ).fetchall()
            out = [dict(r) for r in rows]
        if artifact_root and out:
            txt = self.read_normalized_text(normalized_text_artifact_id=str(artifact_id), artifact_root=str(artifact_root))
            for row in out:
                row["text"] = txt[int(row.get("char_start") or 0):int(row.get("char_end") or 0)]
        return out

    def get_passage_origin(self, *, passage_id: str) -> Dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM passage_origins WHERE passage_id=?", (str(passage_id),)).fetchone()
            return self._decode_passage_origin_row(row)

    def get_claim_origin(self, *, claim_id: str) -> Dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM claim_origins WHERE claim_id=?", (str(claim_id),)).fetchone()
            return self._decode_claim_origin_row(row)

    def list_passage_origins(self, *, book_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM passage_origins WHERE book_id=? ORDER BY rowid", (str(book_id),)).fetchall()
            return [self._decode_passage_origin_row(r) for r in rows if r is not None]

    def list_claim_origins(self, *, book_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM claim_origins WHERE book_id=? ORDER BY rowid", (str(book_id),)).fetchall()
            return [self._decode_claim_origin_row(r) for r in rows if r is not None]

    def list_books_ready_for_extraction(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT b.*, q.priority, q.ingest_queue_position,
                       (SELECT COUNT(*) FROM split_nodes sn WHERE sn.book_id=b.book_id AND sn.is_leaf=1) AS leaf_count,
                       (SELECT COUNT(*) FROM passage_origins po WHERE po.book_id=b.book_id) AS passage_count,
                       (SELECT COUNT(*) FROM claim_origins co WHERE co.book_id=b.book_id) AS claim_count
                FROM books b
                LEFT JOIN book_queue_entries q ON q.book_id=b.book_id
                WHERE (SELECT COUNT(*) FROM split_nodes sn WHERE sn.book_id=b.book_id AND sn.is_leaf=1) > 0
                ORDER BY COALESCE(q.priority, 100) ASC, COALESCE(q.ingest_queue_position, 999999) ASC, b.enqueue_ts ASC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]

    def read_normalized_text(self, *, normalized_text_artifact_id: str, artifact_root: str) -> str:
        rec = self.get_normalized_text_artifact(normalized_text_artifact_id=str(normalized_text_artifact_id))
        if not rec:
            raise FileNotFoundError(f"normalized_text_artifact not found: {normalized_text_artifact_id}")
        rel = str(rec.get("artifact_relpath") or "").strip()
        if not rel:
            raise FileNotFoundError(f"artifact_relpath missing for {normalized_text_artifact_id}")
        path = os.path.join(str(artifact_root), rel)
        enc = str(rec.get("artifact_encoding") or "utf-8")
        with open(path, "r", encoding=enc) as f:
            return f.read()

    def iter_leaf_chunk_bodies(self, *, book_id: str, artifact_root: str) -> Iterator[Dict[str, Any]]:
        leaves = self.list_leaf_nodes(book_id=str(book_id))
        cache: Dict[str, str] = {}
        for leaf in leaves:
            s_start = str(leaf.get("sentence_start_id") or "")
            parts = s_start.split(":")
            normalized_text_artifact_id = parts[1] if len(parts) >= 3 else ""
            if not normalized_text_artifact_id:
                continue
            if normalized_text_artifact_id not in cache:
                cache[normalized_text_artifact_id] = self.read_normalized_text(normalized_text_artifact_id=normalized_text_artifact_id, artifact_root=str(artifact_root))
            text = cache[normalized_text_artifact_id]
            with self._connect() as con:
                srow = con.execute("SELECT sentence_no, char_start, char_end FROM sentences WHERE sentence_id=?", (str(leaf["sentence_start_id"]),)).fetchone()
                erow = con.execute("SELECT sentence_no, char_start, char_end FROM sentences WHERE sentence_id=?", (str(leaf["sentence_end_id"]),)).fetchone()
            start = int(leaf.get("char_start") if leaf.get("char_start") is not None else (srow["char_start"] if srow else 0))
            end = int(leaf.get("char_end") if leaf.get("char_end") is not None else (erow["char_end"] if erow else len(text)))
            yield {
                "split_node_id": str(leaf["split_node_id"]),
                "book_id": str(book_id),
                "normalized_text_artifact_id": normalized_text_artifact_id,
                "sentence_start_id": str(leaf["sentence_start_id"]),
                "sentence_end_id": str(leaf["sentence_end_id"]),
                "char_start": start,
                "char_end": end,
                "boundary_mode": str(leaf.get("boundary_mode") or "sentence_span"),
                "estimated_tokens": leaf.get("estimated_tokens"),
                "text": text[start:end],
            }

    def summarize_book(self, *, book_id: str) -> Dict[str, Any]:
        with self._connect() as con:
            def c(table: str) -> int:
                if table == "sentence_topic_maps":
                    row = con.execute(
                        "SELECT COUNT(*) AS n FROM sentence_topic_maps stm JOIN sentences s ON s.sentence_id = stm.sentence_id WHERE s.book_id=?",
                        (str(book_id),),
                    ).fetchone()
                elif table == "passage_origins":
                    row = con.execute("SELECT COUNT(*) AS n FROM passage_origins WHERE book_id=?", (str(book_id),)).fetchone()
                elif table == "claim_origins":
                    row = con.execute("SELECT COUNT(*) AS n FROM claim_origins WHERE book_id=?", (str(book_id),)).fetchone()
                else:
                    row = con.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE book_id=?", (str(book_id),)).fetchone()
                return int(row["n"] if row else 0)
            book = con.execute("SELECT * FROM books WHERE book_id=?", (str(book_id),)).fetchone()
            row = con.execute("SELECT COUNT(*) AS n FROM split_nodes WHERE book_id=? AND is_leaf=1", (str(book_id),)).fetchone()
            leaves = int(row["n"] if row else 0)
        return {
            "ok": bool(book),
            "book": dict(book) if book else {},
            "counts": {
                "chapters": c("chapters") if book else 0,
                "sections": c("sections") if book else 0,
                "normalized_text_artifacts": c("normalized_text_artifacts") if book else 0,
                "sentences": c("sentences") if book else 0,
                "sentence_topic_maps": c("sentence_topic_maps") if book else 0,
                "adjacency_groups": c("adjacency_groups") if book else 0,
                "split_nodes": c("split_nodes") if book else 0,
                "passage_origins": c("passage_origins") if book else 0,
                "claim_origins": c("claim_origins") if book else 0,
                "leaf_nodes": leaves if book else 0,
            },
        }

    def export_jsonl(self, *, out_dir: str, tables: Sequence[str] | None = None) -> Dict[str, Any]:
        tgt = Path(out_dir)
        tgt.mkdir(parents=True, exist_ok=True)
        names = list(tables) if tables else TABLE_ORDER
        exported: Dict[str, int] = {}
        with self._connect() as con:
            available = set(self._all_tables(con))
            for table in names:
                if table not in available:
                    continue
                rows = con.execute(f"SELECT * FROM {table}").fetchall()
                out_path = tgt / f"{table}.jsonl"
                with open(out_path, "w", encoding="utf-8") as f:
                    for r in rows:
                        f.write(json.dumps(dict(r), ensure_ascii=False, sort_keys=True) + "\n")
                exported[table] = len(rows)
        meta = {"schema": "noemaforge.prep_store.export/v1", "exported_at": _nowz(), "tables": exported}
        (tgt / "_export_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {"ok": True, "out_dir": str(tgt), "tables": exported}

    def import_jsonl(self, *, in_dir: str, merge: str = "replace", tables: Sequence[str] | None = None) -> Dict[str, Any]:
        src = Path(in_dir)
        if not src.exists():
            return {"ok": False, "reason": "input_dir_not_found", "in_dir": str(src)}
        mode = str(merge or "replace").strip().lower()
        if mode not in {"replace", "insert"}:
            return {"ok": False, "reason": "bad_merge_mode", "merge": mode}
        names = list(tables) if tables else TABLE_ORDER
        imported: Dict[str, int] = {}
        with self._connect() as con:
            available = set(self._all_tables(con))
            for table in names:
                p = src / f"{table}.jsonl"
                if table not in available or not p.exists():
                    continue
                cols = self._table_columns(con, table)
                placeholders = ", ".join(["?"] * len(cols))
                verb = "INSERT OR REPLACE" if mode == "replace" else "INSERT OR IGNORE"
                sql = f"{verb} INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
                count = 0
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        raw = line.strip()
                        if not raw:
                            continue
                        obj = json.loads(raw)
                        vals = [obj.get(c) for c in cols]
                        con.execute(sql, vals)
                        count += 1
                imported[table] = count
            con.commit()
        return {"ok": True, "in_dir": str(src), "merge": mode, "tables": imported}


__all__ = ["PrepStore"]
