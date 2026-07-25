#!/usr/bin/env python3
"""
Focused regression tests for 0.33.0 pre-release security hardening.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PREP = ROOT / "tools" / "prep"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(PREP) not in sys.path:
    sys.path.insert(0, str(PREP))

import brainui  # noqa: E402
import persona_runtime  # noqa: E402
import prestart  # noqa: E402
import privileged_gui_job_runner as pgr  # noqa: E402
import scan_tg  # noqa: E402
import task_tools  # noqa: E402
import taskqueue  # noqa: E402
import ui_snapshot  # noqa: E402
import vstore  # noqa: E402
from knowledge.prep_store import PrepStore  # noqa: E402


class BrainUiStaticAssetTests(unittest.TestCase):
    def test_static_asset_resolver_rejects_traversal_and_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf-brainui-") as tmp:
            base = Path(tmp) / "assets"
            outside = Path(tmp) / "outside.txt"
            base.mkdir()
            (base / "index.html").write_text("ok", encoding="utf-8")
            outside.write_text("secret", encoding="utf-8")

            resolved, data = brainui._read_static_asset(str(base), "/index.html")
            self.assertEqual(Path(resolved).name, "index.html")
            self.assertEqual(data, b"ok")

            with self.assertRaises(PermissionError):
                brainui._read_static_asset(str(base), "/../outside.txt")

            link = base / "escape.txt"
            try:
                link.symlink_to(outside)
            except OSError:
                return
            with self.assertRaises(PermissionError):
                brainui._read_static_asset(str(base), "/escape.txt")


class XmlHardeningTests(unittest.TestCase):
    def test_persona_xml_fallback_rejects_entities(self) -> None:
        if persona_runtime._DEFUSED_XML:
            self.skipTest("defusedxml handles entity rejection")
        with self.assertRaises(ValueError):
            persona_runtime._parse_portrait_xml("<!DOCTYPE svg [<!ENTITY x 'y'>]><svg>&x;</svg>")

    def test_polkit_xml_fallback_rejects_entities(self) -> None:
        if pgr._DEFUSED_XML:
            self.skipTest("defusedxml handles entity rejection")
        with tempfile.TemporaryDirectory(prefix="nf-polkit-") as tmp:
            path = Path(tmp) / "policy.xml"
            path.write_text("<!DOCTYPE policyconfig [<!ENTITY x 'y'>]><policyconfig>&x;</policyconfig>", encoding="utf-8")
            with self.assertRaises(ValueError):
                pgr._parse_policy_xml(path)


class PrestartCanaryRunnerTests(unittest.TestCase):
    def test_canary_runner_rejects_unsupported_suite_before_subprocess(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf-contracts-") as contracts:
            root = Path(contracts)
            base = root / "00001"
            cand = root / "00002"
            base.mkdir()
            cand.mkdir()
            runner = SRC / "canary_runner.py"
            with mock.patch("prestart.subprocess.run") as run_mock:
                with self.assertRaises(ValueError):
                    prestart._run_canary_runner(
                        runner=str(runner),
                        base=str(base),
                        cand=str(cand),
                        law=str(base),
                        suite="smoke;rm -rf /",
                        timeout_sec=1,
                        contracts_root=str(root),
                    )
                run_mock.assert_not_called()

    def test_canary_runner_builds_shell_false_argv(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf-contracts-") as contracts:
            root = Path(contracts)
            base = root / "00001"
            cand = root / "00002"
            base.mkdir()
            cand.mkdir()
            runner = SRC / "canary_runner.py"
            completed = mock.Mock(stdout='{"ok": true}', returncode=0)
            with mock.patch("prestart.subprocess.run", return_value=completed) as run_mock:
                result = prestart._run_canary_runner(
                    runner=str(runner),
                    base=str(base),
                    cand=str(cand),
                    law=str(base),
                    suite="smoke",
                    timeout_sec=1,
                    contracts_root=str(root),
                )
            self.assertIs(result, completed)
            kwargs = run_mock.call_args.kwargs
            self.assertIs(kwargs["shell"], False)
            self.assertIn("--suite", run_mock.call_args.args[0])


class VStoreSqlPrefilterTests(unittest.TestCase):
    def test_query_prefilter_keeps_filter_values_parameterized(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf-vstore-") as tmp:
            store = vstore.VStore(
                "security",
                cfg=vstore.VStoreConfig(base_dir=tmp, max_items_per_segment=10),
            )
            store.upsert_many(
                [
                    {
                        "entry_id": "safe-entry",
                        "vector": [1.0, 0.0],
                        "model_id": "model-a",
                        "stream_id": "safe",
                        "project_id": "project-a",
                        "kind": "note",
                    },
                    {
                        "entry_id": "other-entry",
                        "vector": [0.9, 0.1],
                        "model_id": "model-a",
                        "stream_id": "other",
                        "project_id": "project-a",
                        "kind": "note",
                    },
                ]
            )

            safe = store.query(
                [1.0, 0.0],
                dims=2,
                model_id="model-a",
                filters={"stream_id": "safe"},
            )
            self.assertEqual([match["entry_id"] for match in safe["matches"]], ["safe-entry"])

            injected = store.query(
                [1.0, 0.0],
                dims=2,
                model_id="model-a",
                filters={"stream_id": "safe' OR 1=1 --"},
            )
            self.assertEqual(injected["matches"], [])
            self.assertTrue(store.entry_exists("safe-entry"))


class SqlAllowlistHelperTests(unittest.TestCase):
    def test_sql_identifier_helpers_reject_unknown_tokens(self) -> None:
        with self.assertRaises(ValueError):
            taskqueue._where_clause(["status=?; DROP TABLE tasks"])
        with self.assertRaises(ValueError):
            task_tools._assignment("status=?, title='pwned'")
        with self.assertRaises(ValueError):
            ui_snapshot._task_order_sql("created_at DESC; DROP TABLE tasks")

    def test_ui_snapshot_task_fetch_uses_static_order_queries(self) -> None:
        self.assertEqual(set(ui_snapshot.TASK_ORDER_SQL), set(ui_snapshot.TASK_FETCH_QUERIES))
        for key, query in ui_snapshot.TASK_FETCH_QUERIES.items():
            self.assertNotIn("CASE WHEN", query.upper())
            self.assertIn(f"ORDER BY {ui_snapshot.TASK_ORDER_SQL[key]}", query)
            self.assertEqual(2, query.count("?"))

        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        try:
            con.execute(
                """
                CREATE TABLE tasks (
                    task_id TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    domain TEXT,
                    priority_class TEXT,
                    prio_index INTEGER,
                    status TEXT,
                    kind TEXT,
                    module TEXT,
                    title TEXT,
                    group_key TEXT,
                    repeats INTEGER,
                    attempts INTEGER,
                    claimed_by TEXT,
                    claimed_at TEXT,
                    lease_until TEXT,
                    last_error TEXT
                )
                """
            )
            con.execute(
                """
                INSERT INTO tasks (
                    task_id, created_at, updated_at, domain, priority_class, prio_index, status, kind,
                    module, title, group_key, repeats, attempts, claimed_by, claimed_at, lease_until, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "task-safe",
                    "2026-07-15T01:00:00Z",
                    "2026-07-15T01:05:00Z",
                    "SECURITY",
                    "normal",
                    1,
                    "TODO",
                    "module",
                    "ui_snapshot",
                    "safe task",
                    "",
                    0,
                    0,
                    "",
                    "",
                    "",
                    "",
                ),
            )

            injected = ui_snapshot._tq_fetch(
                con,
                status="TODO",
                limit=5,
                order_sql="created_at DESC; DROP TABLE tasks;--",
            )
            self.assertEqual([], injected)

            safe = ui_snapshot._tq_fetch(con, status="TODO", limit=5, order_sql="created_at DESC")
            self.assertEqual(["task-safe"], [task["task_id"] for task in safe])
        finally:
            con.close()

    def test_ui_snapshot_task_fetch_executes_prebuilt_query_only(self) -> None:
        class _FakeCursor:
            def fetchall(self) -> list:
                return []

        class _FakeConnection:
            def __init__(self) -> None:
                self.calls = []

            def execute(self, query: str, params: tuple) -> _FakeCursor:
                self.calls.append((query, params))
                return _FakeCursor()

        for key, order_sql in ui_snapshot.TASK_ORDER_SQL.items():
            for order_input in (key, order_sql):
                con = _FakeConnection()
                rows = ui_snapshot._tq_fetch(con, status="todo", limit="7", order_sql=order_input)
                self.assertEqual([], rows)
                self.assertEqual([(ui_snapshot.TASK_FETCH_QUERIES[key], ("TODO", 7))], con.calls)

        con = _FakeConnection()
        rows = ui_snapshot._tq_fetch(
            con,
            status="TODO",
            limit=7,
            order_sql="created_at DESC; DROP TABLE tasks;--",
        )
        self.assertEqual([], rows)
        self.assertEqual([], con.calls)

    def test_prep_store_table_columns_use_bound_pragma(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf-prep-store-") as tmp:
            store = PrepStore(str(Path(tmp) / "prep.sqlite"))
            with store._connect() as con:
                self.assertIn("book_id", store._table_columns(con, "books"))
                self.assertEqual([], store._table_columns(con, "books); DROP TABLE books;--"))

    def test_prep_store_import_ignores_untrusted_table_names(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf-prep-store-import-") as tmp:
            root = Path(tmp)
            store = PrepStore(str(root / "prep.sqlite"))
            payload_dir = root / "jsonl"
            payload_dir.mkdir()
            bad_table = "books); DROP TABLE books;--"
            (payload_dir / f"{bad_table}.jsonl").write_text(
                '{"book_id": "book_bad", "source_id": "src_bad"}\n',
                encoding="utf-8",
            )

            result = store.import_jsonl(in_dir=str(payload_dir), tables=[bad_table])

            self.assertEqual({"ok": True, "in_dir": str(payload_dir), "merge": "replace", "tables": {}}, result)
            with store._connect() as con:
                self.assertIn("books", store._all_tables(con))

    def test_scan_tg_schema_upgrade_uses_ddl_allowlist(self) -> None:
        with self.assertRaises(ValueError):
            scan_tg._message_schema_upgrade_sql("pi_bad_lines; DROP TABLE messages;--", "INTEGER")
        with self.assertRaises(ValueError):
            scan_tg._message_schema_upgrade_sql("pi_bad_lines", "INTEGER; DROP TABLE messages;--")

        with tempfile.TemporaryDirectory(prefix="nf-scan-tg-") as tmp:
            con = scan_tg._connect(Path(tmp) / "tg.sqlite")
            try:
                con.execute(
                    """
                    CREATE TABLE messages (
                        chat_id TEXT,
                        msg_id TEXT,
                        date TEXT,
                        sender TEXT,
                        sender_id TEXT,
                        text_clean TEXT,
                        pi_severity TEXT,
                        pi_score INTEGER,
                        source_file TEXT,
                        ingested_at TEXT,
                        PRIMARY KEY(chat_id, msg_id)
                    )
                    """
                )
                scan_tg._init_db(con)
                columns = {row[1] for row in con.execute("PRAGMA table_info(messages)").fetchall()}
                self.assertIn("pi_post_severity", columns)
                self.assertIn("pi_post_score", columns)
                self.assertIn("pi_bad_lines", columns)
            finally:
                con.close()

    def test_taskqueue_list_tasks_binds_filter_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf-taskqueue-") as tmp:
            policy = {"queue": {"db_path": str(Path(tmp) / "taskqueue.sqlite")}}
            taskqueue.enqueue_task(
                policy=policy,
                domain="SECURITY",
                kind="module",
                module="scary_sweep",
                title="security sweep",
            )
            taskqueue.enqueue_task(
                policy=policy,
                domain="WORK",
                kind="module",
                module="teamworker",
                title="work item",
            )

            self.assertEqual(2, len(taskqueue.list_tasks(policy=policy, status="TODO")))
            self.assertEqual(
                [],
                taskqueue.list_tasks(policy=policy, status="TODO' OR 1=1 --"),
            )
            self.assertEqual(
                [],
                taskqueue.list_tasks(policy=policy, domain="SECURITY' OR 1=1 --"),
            )
            self.assertEqual(1, len(taskqueue.list_tasks(policy=policy, domain="SECURITY")))

    def test_taskqueue_priority_class_filter_binds_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf-taskqueue-priority-") as tmp:
            policy = {"queue": {"db_path": str(Path(tmp) / "taskqueue.sqlite")}}
            taskqueue.enqueue_task(
                policy=policy,
                domain="SECURITY",
                kind="module",
                priority_class="daily_sla",
                module="scary_sweep",
                title="security sweep",
            )

            self.assertTrue(
                taskqueue.has_todo_with_priority_classes(
                    policy=policy,
                    priority_classes=["DAILY_SLA"],
                )
            )
            self.assertFalse(
                taskqueue.has_todo_with_priority_classes(
                    policy=policy,
                    priority_classes=["daily_sla') OR 1=1 --"],
                )
            )
            self.assertEqual(1, len(taskqueue.list_tasks(policy=policy, status="TODO")))

    def test_user_task_listing_binds_filter_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf-user-tasks-") as tmp:
            policy = {"queue": {"db_path": str(Path(tmp) / "taskqueue.sqlite")}}
            task_tools.create_user_task(
                policy=policy,
                project_id="project-safe",
                title="queued task",
                status="queued",
            )
            task_tools.create_user_task(
                policy=policy,
                project_id="project-safe",
                title="done task",
                status="done",
            )
            task_tools.create_user_task(
                policy=policy,
                project_id="project-other",
                title="other task",
                status="queued",
            )

            self.assertEqual(2, len(task_tools.list_user_tasks(policy=policy, project_id="project-safe")["tasks"]))
            self.assertEqual(2, len(task_tools.list_user_tasks(policy=policy, status="queued")["tasks"]))
            self.assertEqual(
                [],
                task_tools.list_user_tasks(policy=policy, status="queued' OR 1=1 --")["tasks"],
            )
            self.assertEqual(
                [],
                task_tools.list_user_tasks(policy=policy, project_id="project-safe' OR 1=1 --")["tasks"],
            )
            self.assertEqual(
                1,
                len(task_tools.list_user_tasks(policy=policy, project_id="project-safe", status="done")["tasks"]),
            )

    def test_user_task_update_binds_patch_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf-user-task-update-") as tmp:
            db_path = Path(tmp) / "taskqueue.sqlite"
            policy = {"queue": {"db_path": str(db_path)}}
            created = task_tools.create_user_task(
                policy=policy,
                project_id="project-safe",
                title="original",
                status="queued",
            )
            task_id = created["task"]["user_task_id"]

            injected_title = "safe title', status='done"
            updated = task_tools.update_user_task(
                policy=policy,
                user_task_id=task_id,
                patch={
                    "title": injected_title,
                    "status": "queued' OR 1=1 --",
                    "payload": {"note": "x'); DROP TABLE user_tasks; --"},
                },
            )

            task = updated["task"]
            self.assertEqual(injected_title, task["title"])
            self.assertEqual("queued' OR 1=1 --", task["status"])
            self.assertEqual({"note": "x'); DROP TABLE user_tasks; --"}, task["payload"])

            con = sqlite3.connect(str(db_path))
            try:
                row_count = con.execute("SELECT COUNT(*) FROM user_tasks").fetchone()[0]
                self.assertEqual(1, row_count)
            finally:
                con.close()

    def test_user_task_update_preserves_falsy_patch_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf-user-task-falsy-") as tmp:
            policy = {"queue": {"db_path": str(Path(tmp) / "taskqueue.sqlite")}}
            created = task_tools.create_user_task(
                policy=policy,
                project_id="project-safe",
                title="original",
                kind="generic",
            )
            task_id = created["task"]["user_task_id"]

            updated = task_tools.update_user_task(
                policy=policy,
                user_task_id=task_id,
                patch={
                    "title": 0,
                    "description": False,
                    "owner": 0,
                    "status": False,
                    "priority_class": 0,
                    "worktree_id": False,
                },
            )["task"]

            self.assertEqual("0", updated["title"])
            self.assertEqual("False", updated["description"])
            self.assertEqual("0", updated["owner"])
            self.assertEqual("False", updated["status"])
            self.assertEqual("0", updated["priority_class"])
            self.assertEqual("False", updated["worktree_id"])

    def test_user_task_update_rejects_empty_title_and_kind(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf-user-task-not-null-") as tmp:
            policy = {"queue": {"db_path": str(Path(tmp) / "taskqueue.sqlite")}}
            created = task_tools.create_user_task(
                policy=policy,
                project_id="project-safe",
                title="original",
                kind="manual",
            )
            task_id = created["task"]["user_task_id"]

            with self.assertRaisesRegex(ValueError, "missing_title"):
                task_tools.update_user_task(
                    policy=policy,
                    user_task_id=task_id,
                    patch={"title": "   "},
                )

            with self.assertRaisesRegex(ValueError, "missing_kind"):
                task_tools.update_user_task(
                    policy=policy,
                    user_task_id=task_id,
                    patch={"kind": ""},
                )

            current = task_tools.get_user_task(policy=policy, user_task_id=task_id)["task"]
            self.assertEqual("manual", current["kind"])
            self.assertEqual("original", current["title"])


if __name__ == "__main__":
    unittest.main()
