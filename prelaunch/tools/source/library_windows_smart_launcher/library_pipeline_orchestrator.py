#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: prelaunch/tools/source/library_windows_smart_launcher/library_pipeline_orchestrator.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Manage NoemaForge pipeline catalog, runs, gates, artifacts and state.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

UTC = timezone.utc

def now_ts() -> int:
    return int(time.time())

def iso_now(ts: Optional[int] = None) -> str:
    if ts is None:
        ts = now_ts()
    return datetime.fromtimestamp(ts, tz=UTC).astimezone().isoformat(timespec="seconds")

def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}

def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except Exception:
        return default

def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except Exception:
        return default

def safe_print(msg: str = "") -> None:
    print(msg, flush=True)

class Logger:
    def __init__(self, state_dir: Path):
        state_dir.mkdir(parents=True, exist_ok=True)
        self.run_log = state_dir / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.latest_log = state_dir / "pipeline_latest.log"

    def log(self, msg: str = "") -> None:
        safe_print(msg)
        line = msg + "\n"
        self.run_log.parent.mkdir(parents=True, exist_ok=True)
        with self.run_log.open("a", encoding="utf-8") as f:
            f.write(line)
        with self.latest_log.open("a", encoding="utf-8") as f:
            f.write(line)

@dataclass
class Config:
    root: Path
    script_dir: Path
    logdir: Path
    state_dir: Path
    cooldown_minutes: int
    max_fails_per_source: int
    auto_install_aws: bool
    run_oapen: bool
    run_oapen_chapters: bool
    run_openalex: bool
    openalex_mode: str
    run_pmc_metadata: bool
    run_pmc_comm: bool
    run_pmc_noncomm: bool
    run_pmc_phe: bool
    oapen_delay: float
    oapen_retries: int
    oapen_timeout: int
    oapen_backoff: float
    oapen_max_retry_wait: float

def load_config() -> Config:
    root = Path(os.environ.get("ROOT", r"E:\noemaforge-lab\data\Library\inbox"))
    script_dir = Path(os.environ.get("SCRIPT_DIR", Path(__file__).resolve().parent))
    logdir = root / "logs"
    state_dir = logdir / "_pipeline"
    return Config(
        root=root,
        script_dir=script_dir,
        logdir=logdir,
        state_dir=state_dir,
        cooldown_minutes=env_int("COOLDOWN_MINUTES", 15),
        max_fails_per_source=env_int("MAX_FAILS_PER_SOURCE", 8),
        auto_install_aws=env_bool("AUTO_INSTALL_AWS", True),
        run_oapen=env_bool("RUN_OAPEN", True),
        run_oapen_chapters=env_bool("RUN_OAPEN_CHAPTERS", False),
        run_openalex=env_bool("RUN_OPENALEX", True),
        openalex_mode=os.environ.get("OPENALEX_MODE", "works").strip().lower() or "works",
        run_pmc_metadata=env_bool("RUN_PMC_METADATA", True),
        run_pmc_comm=env_bool("RUN_PMC_COMM", True),
        run_pmc_noncomm=env_bool("RUN_PMC_NONCOMM", True),
        run_pmc_phe=env_bool("RUN_PMC_PHE", False),
        oapen_delay=env_float("OAPEN_DELAY", 0.8),
        oapen_retries=env_int("OAPEN_RETRIES", 2),
        oapen_timeout=env_int("OAPEN_TIMEOUT", 120),
        oapen_backoff=env_float("OAPEN_BACKOFF", 2.0),
        oapen_max_retry_wait=env_float("OAPEN_MAX_RETRY_WAIT", 20.0),
    )

class Pipeline:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cfg.logdir.mkdir(parents=True, exist_ok=True)
        self.cfg.state_dir.mkdir(parents=True, exist_ok=True)
        self.logger = Logger(self.cfg.state_dir)
        self.state_path = self.cfg.state_dir / "pipeline_state.json"
        self.state = self.load_state()
        self.aws_exe: Optional[str] = None
        self.python_exe = sys.executable

    def load_state(self) -> Dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"version": 1, "sources": {}, "tasks": {}, "passes": 0, "updated_at": iso_now()}

    def save_state(self) -> None:
        self.state["updated_at"] = iso_now()
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        for source_id, src_state in self.state.get("sources", {}).items():
            p = self.cfg.state_dir / f"source_{source_id}.json"
            p.write_text(json.dumps(src_state, ensure_ascii=False, indent=2), encoding="utf-8")

    def log(self, msg: str = "") -> None:
        self.logger.log(msg)

    def task_done_marker(self, task_id: str) -> Path:
        return self.cfg.state_dir / f"{task_id}.done"

    def is_task_done(self, task_id: str) -> bool:
        if self.task_done_marker(task_id).exists():
            self.state.setdefault("tasks", {}).setdefault(task_id, {})["done"] = True
            return True
        return bool(self.state.get("tasks", {}).get(task_id, {}).get("done"))

    def mark_task_done(self, task_id: str) -> None:
        self.state.setdefault("tasks", {}).setdefault(task_id, {})["done"] = True
        self.state["tasks"][task_id]["done_at"] = iso_now()
        self.task_done_marker(task_id).write_text(iso_now() + "\n", encoding="utf-8")
        self.save_state()

    def task_enabled(self, task_id: str) -> bool:
        mapping = {
            "10_oapen_metadata": self.cfg.run_oapen,
            "11_oapen_books": self.cfg.run_oapen,
            "12_oapen_chapters": self.cfg.run_oapen_chapters,
            "20_openalex": self.cfg.run_openalex,
            "30_pmc_metadata": self.cfg.run_pmc_metadata,
            "31_pmc_comm": self.cfg.run_pmc_comm,
            "32_pmc_noncomm": self.cfg.run_pmc_noncomm,
            "33_pmc_phe": self.cfg.run_pmc_phe,
        }
        return mapping.get(task_id, True)

    def get_source(self, source_id: str) -> Dict:
        src = self.state.setdefault("sources", {}).setdefault(source_id, {
            "source_id": source_id,
            "status": "ready",
            "consecutive_fail_count": 0,
            "total_fail_count": 0,
            "last_fail_ts": 0,
            "last_fail_iso": "",
            "blocked_until_ts": 0,
            "blocked_until_iso": "",
            "last_rc": 0,
            "last_error": "",
            "hard_failed": False,
        })
        return src

    def reset_source_after_success(self, source_id: str) -> None:
        src = self.get_source(source_id)
        src["status"] = "ready"
        src["consecutive_fail_count"] = 0
        src["blocked_until_ts"] = 0
        src["blocked_until_iso"] = ""
        src["last_rc"] = 0
        src["last_error"] = ""
        src["hard_failed"] = False
        self.save_state()

    def mark_source_failure(self, source_id: str, rc: int, error: str) -> None:
        src = self.get_source(source_id)
        ts = now_ts()
        blocked_until = ts + self.cfg.cooldown_minutes * 60
        src["status"] = "cooldown"
        src["consecutive_fail_count"] = int(src.get("consecutive_fail_count", 0)) + 1
        src["total_fail_count"] = int(src.get("total_fail_count", 0)) + 1
        src["last_fail_ts"] = ts
        src["last_fail_iso"] = iso_now(ts)
        src["blocked_until_ts"] = blocked_until
        src["blocked_until_iso"] = iso_now(blocked_until)
        src["last_rc"] = int(rc)
        src["last_error"] = error
        if src["consecutive_fail_count"] >= self.cfg.max_fails_per_source:
            src["hard_failed"] = True
            src["status"] = "hard_failed"
        self.save_state()

    def source_blocked_seconds(self, source_id: str) -> int:
        src = self.get_source(source_id)
        if src.get("hard_failed"):
            return 10**9
        until = int(src.get("blocked_until_ts", 0) or 0)
        return max(0, until - now_ts())

    def can_attempt_source(self, source_id: str) -> bool:
        src = self.get_source(source_id)
        if src.get("hard_failed"):
            return False
        return self.source_blocked_seconds(source_id) <= 0

    def ensure_dirs(self) -> int:
        root = self.cfg.root
        paths = [
            root / "books",
            root / "books" / "gutenberg",
            root / "books" / "oapen",
            root / "books" / "oapen" / "meta",
            root / "books" / "oapen" / "pdf",
            root / "books" / "oapen" / "chapters",
            root / "articles",
            root / "articles" / "openalex",
            root / "articles" / "openalex" / "snapshot",
            root / "articles" / "openalex" / "filtered",
            root / "articles" / "pmc",
            root / "articles" / "pmc" / "aws",
            root / "articles" / "pmc" / "aws" / "oa_comm_xml",
            root / "articles" / "pmc" / "aws" / "oa_noncomm_xml",
            root / "articles" / "pmc" / "aws" / "phe_timebound_xml",
            root / "articles" / "pmc" / "aws" / "metadata",
            self.cfg.logdir,
            self.cfg.state_dir,
        ]
        for p in paths:
            p.mkdir(parents=True, exist_ok=True)
        return 0

    def looks_like_html(self, path: Path) -> bool:
        try:
            head = path.read_bytes()[:4096].decode("utf-8", errors="ignore").lstrip().lower()
            return head.startswith("<!doctype html") or head.startswith("<html") or "<html" in head[:512]
        except Exception:
            return False

    def is_valid_oapen_csv(self, path: Path) -> bool:
        if not path.exists() or path.stat().st_size == 0 or self.looks_like_html(path):
            return False
        try:
            first = path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()[0].lower()
        except Exception:
            return False
        return first.startswith("id,") or "bitstream download url" in first or "dc.title" in first

    def http_download_quick(self, url: str, dest: Path, timeout: int = 120, validate: Optional[Callable[[Path], bool]] = None) -> int:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        headers = {"User-Agent": "Mozilla/5.0 (compatible; NoemaForge pipeline)"}
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=timeout) as resp, tmp.open("wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            if tmp.stat().st_size <= 0:
                raise OSError("empty download")
            if validate is not None and not validate(tmp):
                raise ValueError("download validation failed")
            tmp.replace(dest)
            return 0
        except Exception as exc:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            raise RuntimeError(str(exc))

    def do_oapen_metadata(self) -> int:
        csv_path = self.cfg.root / "books" / "oapen" / "meta" / "OAPENLibrary.csv"
        have_old = self.is_valid_oapen_csv(csv_path)
        try:
            self.http_download_quick(
                "https://library.oapen.org/download-export?format=csv",
                csv_path,
                timeout=120,
                validate=self.is_valid_oapen_csv,
            )
            self.log(f"Saved OAPEN metadata: {csv_path}")
            return 0
        except Exception as exc:
            if have_old:
                self.log(f"OAPEN metadata download failed, reusing existing local CSV: {exc}")
                return 0
            self.log(f"OAPEN metadata download failed and no valid local CSV is available: {exc}")
            return 1

    def count_tsv_rows(self, path: Path) -> int:
        if not path.exists():
            return 0
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return max(0, len(lines) - 1)
        except Exception:
            return 0

    def do_oapen_books(self, include_chapters: bool) -> int:
        csv_path = self.cfg.root / "books" / "oapen" / "meta" / "OAPENLibrary.csv"
        if not csv_path.exists():
            self.log(f"OAPEN metadata file not found: {csv_path}")
            return 1
        out = self.cfg.root / "books" / "oapen" / ("chapters" if include_chapters else "pdf")
        script = self.cfg.script_dir / "oapen_bulk_download_safe.py"
        if not script.exists():
            self.log(f"OAPEN downloader script not found: {script}")
            return 1
        cmd = [
            self.python_exe, str(script),
            "--csv", str(csv_path),
            "--out", str(out),
            "--logs", str(self.cfg.logdir),
            "--resume",
            "--delay", str(self.cfg.oapen_delay),
            "--retries", str(self.cfg.oapen_retries),
            "--timeout", str(self.cfg.oapen_timeout),
            "--backoff", str(self.cfg.oapen_backoff),
            "--max-retry-wait", str(self.cfg.oapen_max_retry_wait),
            "--stop-on-first-fail",
        ]
        if include_chapters:
            cmd.append("--include-chapters")
        self.log("Running OAPEN downloader in fail-fast mode...")
        rc = subprocess.run(cmd).returncode
        fail_rows = self.count_tsv_rows(self.cfg.logdir / "oapen_fail.tsv")
        if rc == 0 and fail_rows == 0:
            return 0
        self.log(f"OAPEN step ended with rc={rc}, pending failed rows={fail_rows}")
        return rc if rc != 0 else 2

    def find_aws(self) -> Optional[str]:
        if self.aws_exe and Path(self.aws_exe).exists():
            return self.aws_exe
        exe = shutil.which("aws")
        if exe:
            self.aws_exe = exe
            return exe
        for p in [
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Amazon", "AWSCLIV2", "aws.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Amazon", "AWSCLIV2", "aws.exe"),
        ]:
            if Path(p).exists():
                self.aws_exe = p
                return p
        return None

    def ensure_aws(self) -> Optional[str]:
        exe = self.find_aws()
        if exe:
            return exe
        if not self.cfg.auto_install_aws:
            return None
        msi = Path(tempfile.gettempdir()) / "AWSCLIV2.msi"
        self.log("AWS CLI not found. Downloading installer...")
        try:
            self.http_download_quick("https://awscli.amazonaws.com/AWSCLIV2.msi", msi, timeout=300, validate=None)
        except Exception as exc:
            self.log(f"AWS CLI download failed: {exc}")
            return None
        self.log("Installing AWS CLI v2 silently...")
        rc = subprocess.run(["msiexec.exe", "/i", str(msi), "/qn", "/norestart"]).returncode
        if rc != 0:
            self.log(f"AWS CLI installer returned rc={rc}")
            return None
        return self.find_aws()

    def do_openalex(self) -> int:
        aws = self.ensure_aws()
        if not aws:
            self.log("AWS CLI not found and could not be installed.")
            return 1
        if self.cfg.openalex_mode == "full":
            out = self.cfg.root / "articles" / "openalex" / "snapshot"
            src = "s3://openalex"
            args = [aws, "s3", "sync", src, str(out), "--no-sign-request", "--delete"]
        else:
            out = self.cfg.root / "articles" / "openalex" / "snapshot" / "data" / "works"
            src = "s3://openalex/data/works"
            args = [aws, "s3", "sync", src, str(out), "--no-sign-request", "--delete"]
        self.log(f"Running OpenAlex sync: {src} -> {out}")
        return subprocess.run(args).returncode

    def do_pmc_metadata(self) -> int:
        out = self.cfg.root / "articles" / "pmc" / "aws" / "metadata"
        jobs = [
            ("https://pmc-oa-opendata.s3.amazonaws.com/oa_comm/xml/metadata/csv/oa_comm.filelist.csv", out / "oa_comm.filelist.csv"),
            ("https://pmc-oa-opendata.s3.amazonaws.com/oa_noncomm/xml/metadata/csv/oa_noncomm.filelist.csv", out / "oa_noncomm.filelist.csv"),
            ("https://pmc-oa-opendata.s3.amazonaws.com/phe_timebound/xml/metadata/csv/phe_timebound.filelist.csv", out / "phe_timebound.filelist.csv"),
        ]
        for url, dest in jobs:
            try:
                self.http_download_quick(url, dest, timeout=120, validate=None)
            except Exception as exc:
                if dest.exists() and dest.stat().st_size > 0:
                    self.log(f"PMC metadata download failed for {url}, reusing local file: {exc}")
                    continue
                self.log(f"PMC metadata download failed for {url}: {exc}")
                return 1
        return 0

    def do_pmc_sync(self, suffix: str) -> int:
        aws = self.ensure_aws()
        if not aws:
            self.log("AWS CLI not found and could not be installed.")
            return 1
        if suffix == "oa_comm_xml":
            src = "s3://pmc-oa-opendata/oa_comm/xml/all"
        elif suffix == "oa_noncomm_xml":
            src = "s3://pmc-oa-opendata/oa_noncomm/xml/all"
        elif suffix == "phe_timebound_xml":
            src = "s3://pmc-oa-opendata/phe_timebound/xml/all"
        else:
            self.log(f"Unknown PMC suffix: {suffix}")
            return 1
        out = self.cfg.root / "articles" / "pmc" / "aws" / suffix
        self.log(f"Running PMC sync: {src} -> {out}")
        return subprocess.run([aws, "s3", "sync", src, str(out), "--no-sign-request"]).returncode

    def enabled_tasks(self) -> List[Dict]:
        tasks: List[Dict] = [
            {"id": "00_make_dirs", "title": "Create folder tree", "source": "LOCAL", "func": self.ensure_dirs, "enabled": True},
            {"id": "10_oapen_metadata", "title": "Download OAPEN metadata", "source": "OAPEN", "func": self.do_oapen_metadata, "enabled": self.cfg.run_oapen},
            {"id": "11_oapen_books", "title": "Download OAPEN books (fail-fast resume mode)", "source": "OAPEN", "func": lambda: self.do_oapen_books(False), "enabled": self.cfg.run_oapen},
            {"id": "12_oapen_chapters", "title": "Download OAPEN chapters (optional)", "source": "OAPEN", "func": lambda: self.do_oapen_books(True), "enabled": self.cfg.run_oapen_chapters},
            {"id": "20_openalex", "title": f"Sync OpenAlex snapshot ({self.cfg.openalex_mode})", "source": "OPENALEX", "func": self.do_openalex, "enabled": self.cfg.run_openalex},
            {"id": "30_pmc_metadata", "title": "Download PMC metadata via HTTPS", "source": "PMC_METADATA", "func": self.do_pmc_metadata, "enabled": self.cfg.run_pmc_metadata},
            {"id": "31_pmc_comm", "title": "Sync PMC OA comm XML", "source": "PMC_COMM", "func": lambda: self.do_pmc_sync("oa_comm_xml"), "enabled": self.cfg.run_pmc_comm},
            {"id": "32_pmc_noncomm", "title": "Sync PMC OA noncomm XML", "source": "PMC_NONCOMM", "func": lambda: self.do_pmc_sync("oa_noncomm_xml"), "enabled": self.cfg.run_pmc_noncomm},
            {"id": "33_pmc_phe", "title": "Sync PMC PHE timebound XML", "source": "PMC_PHE", "func": lambda: self.do_pmc_sync("phe_timebound_xml"), "enabled": self.cfg.run_pmc_phe},
        ]
        return [t for t in tasks if t["enabled"]]

    def summarize_sources(self) -> None:
        self.log("")
        self.log("Current source states:")
        for source_id, src in sorted(self.state.get("sources", {}).items()):
            self.log(
                f"  - {source_id}: status={src.get('status')} "
                f"consecutive_fail_count={src.get('consecutive_fail_count',0)} "
                f"blocked_until={src.get('blocked_until_iso','') or '-'}"
            )

    def run(self) -> int:
        self.log("=== Smart library pipeline started ===")
        self.log(f"ROOT={self.cfg.root}")
        self.log(f"SCRIPT_DIR={self.cfg.script_dir}")
        self.log(f"STATE={self.state_path}")
        self.log(f"COOLDOWN_MINUTES={self.cfg.cooldown_minutes}")
        self.log(f"MAX_FAILS_PER_SOURCE={self.cfg.max_fails_per_source}")
        self.log("")
        tasks = self.enabled_tasks()

        # keep existing done markers honored
        for task in tasks:
            self.is_task_done(task["id"])
        self.save_state()

        while True:
            self.state["passes"] = int(self.state.get("passes", 0)) + 1
            current_pass = self.state["passes"]
            self.save_state()
            self.log("")
            self.log(f"=== Pass #{current_pass} started at {iso_now()} ===")

            for task in tasks:
                task_id = task["id"]
                title = task["title"]
                source = task["source"]

                if self.is_task_done(task_id):
                    self.log(f"[SKIP] {title} :: already done")
                    continue

                if source != "LOCAL":
                    src = self.get_source(source)
                    if src.get("hard_failed"):
                        self.log(f"[SKIP] {title} :: source {source} is hard-failed after {src.get('consecutive_fail_count', 0)} consecutive failures")
                        continue
                    wait_s = self.source_blocked_seconds(source)
                    if wait_s > 0:
                        self.log(f"[WAIT] {title} :: source {source} cooling down for another {wait_s}s")
                        continue

                self.log(f"[RUN ] {title}")
                started = now_ts()
                rc = 1
                err_text = ""
                try:
                    rc = int(task["func"]())
                except KeyboardInterrupt:
                    self.log("Interrupted by user.")
                    self.save_state()
                    return 130
                except Exception as exc:
                    rc = 1
                    err_text = repr(exc)
                    self.log(f"[ERR ] {title} :: {err_text}")

                elapsed = now_ts() - started
                if rc == 0:
                    self.mark_task_done(task_id)
                    if source != "LOCAL":
                        self.reset_source_after_success(source)
                    self.log(f"[ OK ] {title} :: {elapsed}s")
                else:
                    if not err_text:
                        err_text = f"rc={rc}"
                    if source != "LOCAL":
                        self.mark_source_failure(source, rc, err_text)
                        src = self.get_source(source)
                        if src.get("hard_failed"):
                            self.log(
                                f"[FAIL] {title} :: source {source} hard-failed "
                                f"after {src.get('consecutive_fail_count')} consecutive failures"
                            )
                        else:
                            self.log(
                                f"[FAIL] {title} :: source {source} paused for {self.cfg.cooldown_minutes} minutes "
                                f"(consecutive_fail_count={src.get('consecutive_fail_count')}, next retry at {src.get('blocked_until_iso')})"
                            )
                    else:
                        self.log(f"[FAIL] {title} :: rc={rc}")
                self.save_state()

            # End-of-pass evaluation
            pending_tasks = [t for t in tasks if not self.is_task_done(t["id"])]
            hard_failed_sources = [
                sid for sid, src in self.state.get("sources", {}).items()
                if src.get("hard_failed") and any(t for t in pending_tasks if t["source"] == sid)
            ]

            self.summarize_sources()

            if not pending_tasks:
                self.log("")
                self.log("=== Pipeline finished successfully ===")
                return 0

            if hard_failed_sources:
                self.log("")
                self.log("=== Pipeline stopped: hard-failed sources remain ===")
                self.log("Hard-failed sources: " + ", ".join(sorted(hard_failed_sources)))
                return 2

            waits: List[int] = []
            ready_exists = False
            for task in pending_tasks:
                source = task["source"]
                if source == "LOCAL":
                    ready_exists = True
                    continue
                wait_s = self.source_blocked_seconds(source)
                if wait_s <= 0:
                    ready_exists = True
                else:
                    waits.append(wait_s)

            if ready_exists:
                self.log("Pending tasks are immediately retryable; starting the next pass now.")
                continue

            sleep_s = min(waits) if waits else self.cfg.cooldown_minutes * 60
            if sleep_s < 0:
                sleep_s = 0
            self.log("")
            self.log(
                f"No source is retryable yet. Sleeping for {sleep_s}s "
                f"until the next source leaves cooldown, then the launcher will continue automatically."
            )
            try:
                time.sleep(sleep_s)
            except KeyboardInterrupt:
                self.log("Interrupted by user during cooldown sleep.")
                self.save_state()
                return 130

def main() -> int:
    cfg = load_config()
    pipeline = Pipeline(cfg)
    return pipeline.run()

if __name__ == "__main__":
    raise SystemExit(main())
