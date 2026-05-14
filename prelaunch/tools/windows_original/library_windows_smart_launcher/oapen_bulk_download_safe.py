#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: prelaunch/tools/windows_original/library_windows_smart_launcher/oapen_bulk_download_safe.py
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

Existing module notes:
Conservative OAPEN bulk downloader for the official OAPEN CSV export.

Hotfix goals:
- Works with the classic OAPEN CSV that has BITSTREAM Download URL columns.
- Also works with CSV variants that embed bitstream links in other metadata fields.
- Detects accidental HTML downloads and prints a clearer error.
- Keeps slow, resume-safe, retrying downloads to reduce 429s.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

csv.field_size_limit(50 * 1024 * 1024)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
DOC_EXTS = (".pdf", ".epub", ".mobi", ".azw3")
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
URL_RE = re.compile(r"https?://[^\s\"'<>|]+", re.IGNORECASE)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def safe_print(*args, **kwargs) -> None:
    print(*args, **kwargs, flush=True)


def split_candidate_urls(raw: str) -> List[str]:
    raw = str(raw or "")
    if not raw.strip():
        return []

    parts: List[str] = []
    for piece in raw.split("||"):
        piece = piece.strip()
        if not piece:
            continue
        found = URL_RE.findall(piece)
        if found:
            parts.extend(found)
        elif piece.startswith(("http://", "https://")):
            parts.append(piece)
    return parts


def title_from_row(row: Dict[str, str], row_num: int) -> str:
    candidates = [
        row.get("dc.title"),
        row.get("dc.title[en]"),
        row.get("title"),
        row.get("publication_title"),
    ]
    for item in candidates:
        item = (item or "").strip()
        if item:
            return item
    return f"row_{row_num}"


def looks_like_chapter(title: str, row: Dict[str, str]) -> bool:
    lower = (title or "").strip().lower()
    if lower.startswith("chapter "):
        return True

    for key in ("collection", "item type", "dc.type", "oapen.chapternumber"):
        val = (row.get(key) or "").strip().lower()
        if val in {"chapter", "chapters"}:
            return True
        if key == "oapen.chapternumber" and val:
            return True
    return False


def is_obvious_image_url(url: str) -> bool:
    path = unquote(urlparse(url).path).lower()
    name = os.path.basename(path)
    if not name:
        return True

    if any(name.endswith(ext) for ext in IMAGE_EXTS):
        return True

    image_markers = (
        ".pdf.jpg",
        ".epub.jpg",
        ".mobi.jpg",
        ".azw3.jpg",
        "_cover.jpg",
        "/download.jpg",
    )
    return any(marker in path for marker in image_markers)


def score_document_url(url: str) -> Optional[int]:
    if is_obvious_image_url(url):
        return None

    path = unquote(urlparse(url).path).lower()
    name = os.path.basename(path)
    if not name:
        return None

    if name.endswith(".pdf") or ".pdf?" in url.lower() or ".pdf&" in url.lower():
        return 300
    if ".pdf" in name:
        return 250
    if name.endswith(".epub") or ".epub?" in url.lower() or ".epub&" in url.lower():
        return 200
    if ".epub" in name:
        return 150
    if name.endswith(".mobi") or ".mobi?" in url.lower() or ".mobi&" in url.lower():
        return 120
    if ".mobi" in name:
        return 100
    if name.endswith(".azw3") or ".azw3?" in url.lower() or ".azw3&" in url.lower():
        return 90
    if ".azw3" in name:
        return 80

    # Fallback: treat bitstream URLs as possible documents even if the extension is hidden.
    if "/bitstream/" in path:
        return 40
    return None


def looks_like_download_field(name: str) -> bool:
    n = (name or "").strip().lower()
    if not n:
        return False
    return any(
        key in n
        for key in (
            "bitstream download url",
            "download url",
            "download link",
            "fulltext",
            "full text",
            "bitstream",
            "file url",
            "resource url",
            "open access url",
            "pdf url",
            "epub url",
            "identifier.uri",
            "identifier.url",
        )
    )


def collect_candidate_urls(row: Dict[str, str], fieldnames: Sequence[str]) -> Tuple[List[str], List[str]]:
    urls: List[str] = []
    used_fields: List[str] = []
    seen = set()

    preferred_fields = [h for h in fieldnames if h and looks_like_download_field(h)]

    for field in preferred_fields:
        raw = row.get(field) or ""
        found = split_candidate_urls(raw)
        if not found:
            continue
        used_fields.append(field)
        for url in found:
            if url not in seen:
                seen.add(url)
                urls.append(url)

    if urls:
        return urls, used_fields

    # Fallback: scan every cell for explicit URLs. This is needed for some OAPEN/MEMO CSV variants.
    for field in fieldnames:
        raw = row.get(field) or ""
        if not raw:
            continue
        found = split_candidate_urls(raw)
        for url in found:
            lower = url.lower()
            path = unquote(urlparse(url).path).lower()
            if (
                "/bitstream/" in path
                or any(ext in lower for ext in DOC_EXTS)
            ):
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
                    if field not in used_fields:
                        used_fields.append(field)

    return urls, used_fields


def choose_best_url(row: Dict[str, str], fieldnames: Sequence[str]) -> Tuple[Optional[str], List[str]]:
    raw_candidates, used_fields = collect_candidate_urls(row, fieldnames)

    candidates: List[Tuple[int, str]] = []
    for url in raw_candidates:
        score = score_document_url(url)
        if score is not None:
            candidates.append((score, url))

    if not candidates:
        return None, used_fields

    candidates.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    return candidates[0][1], used_fields


def looks_like_html_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(4096).decode("utf-8", errors="ignore").lstrip().lower()
    except Exception:
        return False

    return head.startswith("<!doctype html") or head.startswith("<html") or "<html" in head[:512]


def iter_items(csv_path: Path, include_chapters: bool) -> Iterable[Tuple[str, str]]:
    if looks_like_html_file(csv_path):
        raise ValueError(
            "The metadata file looks like HTML, not CSV. Redownload OAPENLibrary.csv and try again."
        )

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(16384)
        handle.seek(0)

        if not sample.strip():
            raise ValueError("CSV file is empty")

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except Exception:
            dialect = csv.excel

        reader = csv.DictReader(handle, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("CSV has no headers")

        preview_headers = ", ".join(reader.fieldnames[:12])
        detected_download_headers = [h for h in reader.fieldnames if looks_like_download_field(h)]
        if detected_download_headers:
            safe_print(f"Detected URL columns: {', '.join(detected_download_headers[:8])}")
        else:
            safe_print(f"No explicit URL columns found. Fallback scanning is enabled. Header preview: {preview_headers}")

        yielded = 0
        rows_seen = 0
        for row_num, row in enumerate(reader, start=2):
            rows_seen += 1
            title = title_from_row(row, row_num)

            if not include_chapters and looks_like_chapter(title, row):
                continue

            best_url, _used_fields = choose_best_url(row, reader.fieldnames)
            if best_url:
                yielded += 1
                yield title, best_url

        if rows_seen == 0:
            raise ValueError("CSV has headers but no data rows")
        if yielded == 0:
            raise ValueError(
                "Could not find any usable document URLs in the CSV. "
                f"Header preview: {preview_headers}"
            )


def sanitize_root(root: str) -> str:
    root = re.sub(r'[<>:"/\\|?*]+', "_", root)
    root = root.strip(" .")
    if not root:
        root = "file"
    if len(root) > 140:
        root = root[:140]
    return root


def filename_from_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    name = os.path.basename(path) or "file"

    root, ext = os.path.splitext(name)
    if ext.lower() in IMAGE_EXTS:
        inner_root, inner_ext = os.path.splitext(root)
        if inner_ext:
            root, ext = inner_root, inner_ext

    lower_name = name.lower()
    if not ext or ext.lower() not in DOC_EXTS:
        if ".pdf" in lower_name:
            ext = ".pdf"
        elif ".epub" in lower_name:
            ext = ".epub"
        elif ".mobi" in lower_name:
            ext = ".mobi"
        elif ".azw3" in lower_name:
            ext = ".azw3"
        else:
            ext = ".bin"

    root = sanitize_root(root)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{root}__{digest}{ext}"


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    return None


def ensure_nonempty_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(str(path))
    if path.stat().st_size <= 0:
        raise OSError("empty file")


def download_one(
    title: str,
    url: str,
    out_dir: Path,
    resume: bool,
    retries: int,
    timeout: int,
    backoff: float,
    max_retry_wait: float,
) -> Tuple[str, str, str]:
    dest = out_dir / filename_from_url(url)

    if dest.exists() and resume and dest.stat().st_size > 0:
        return title, "skip", str(dest)

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; NoemaForge-Lab OAPEN downloader)",
        "Referer": "https://library.oapen.org/",
        "Accept": "*/*",
    }

    last_error = "unknown error"
    for attempt in range(1, max(1, retries) + 1):
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=timeout) as response, dest.open("wb") as fout:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    fout.write(chunk)

            ensure_nonempty_file(dest)
            return title, "ok", str(dest)

        except HTTPError as exc:
            code = getattr(exc, "code", None)
            last_error = f"HTTP {code}: {exc.reason}" if code else repr(exc)

            if code in RETRYABLE_STATUS and attempt < retries:
                retry_after = parse_retry_after(exc.headers.get("Retry-After"))
                if retry_after is not None and retry_after > max_retry_wait:
                    last_error = (
                        f"HTTP {code}: {exc.reason}; Retry-After={retry_after:.1f}s exceeds cap {max_retry_wait:.1f}s"
                    )
                else:
                    wait_s = retry_after if retry_after is not None else (backoff ** (attempt - 1)) + random.uniform(0.2, 1.2)
                    wait_s = min(wait_s, max_retry_wait)
                    safe_print(f"      retry {attempt}/{retries - 1} after {wait_s:.1f}s :: {title} :: {last_error}")
                    time.sleep(wait_s)
                    continue

        except URLError as exc:
            last_error = str(exc.reason) if hasattr(exc, "reason") else repr(exc)
            if attempt < retries:
                wait_s = (backoff ** (attempt - 1)) + random.uniform(0.2, 1.2)
                safe_print(f"      retry {attempt}/{retries - 1} after {wait_s:.1f}s :: {title} :: {last_error}")
                time.sleep(wait_s)
                continue

        except Exception as exc:
            last_error = repr(exc)
            if attempt < retries:
                wait_s = (backoff ** (attempt - 1)) + random.uniform(0.2, 1.2)
                safe_print(f"      retry {attempt}/{retries - 1} after {wait_s:.1f}s :: {title} :: {last_error}")
                time.sleep(wait_s)
                continue

        break

    try:
        if dest.exists():
            dest.unlink()
    except OSError:
        pass

    return title, "fail", f"{url} :: {last_error}"


def write_tsv(path: Path, rows: Sequence[Tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("title\tvalue\n")
        for title, value in rows:
            safe_title = str(title).replace("\t", " ").replace("\r", " ").replace("\n", " ")
            safe_value = str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")
            handle.write(f"{safe_title}\t{safe_value}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--logs", type=Path, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--retries", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--backoff", type=float, default=2.0)
    ap.add_argument("--include-chapters", action="store_true")
    ap.add_argument("--stop-on-first-fail", action="store_true")
    ap.add_argument("--max-retry-wait", type=float, default=30.0)
    args = ap.parse_args()

    if not args.csv.exists():
        safe_print(f"CSV not found: {args.csv}")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    if args.logs is None:
        args.logs = args.out.parent.parent / "logs"
    args.logs.mkdir(parents=True, exist_ok=True)

    ok_rows: List[Tuple[str, str]] = []
    skip_rows: List[Tuple[str, str]] = []
    fail_rows: List[Tuple[str, str]] = []

    items = list(iter_items(args.csv, include_chapters=args.include_chapters))
    total = len(items)
    if total == 0:
        safe_print("No downloadable items found.")
        return 1

    safe_print(f"Queue size: {total}")

    for idx, (title, url) in enumerate(items, start=1):
        status_title = title.replace("\r", " ").replace("\n", " ")
        status_title = status_title[:140]
        safe_print(f"[{idx}/{total}] {status_title}")
        title2, status, value = download_one(
            title=title,
            url=url,
            out_dir=args.out,
            resume=args.resume,
            retries=max(1, args.retries),
            timeout=max(10, args.timeout),
            backoff=max(1.1, args.backoff),
            max_retry_wait=max(0.0, args.max_retry_wait),
        )

        if status == "ok":
            ok_rows.append((title2, value))
        elif status == "skip":
            skip_rows.append((title2, value))
        else:
            fail_rows.append((title2, value))
            safe_print(f"      FAIL :: {value}")
            if args.stop_on_first_fail:
                safe_print("      stop-on-first-fail is enabled; pausing this source for the launcher to retry later.")
                break

        time.sleep(max(0.0, args.delay))

    write_tsv(args.logs / "oapen_ok.tsv", ok_rows)
    write_tsv(args.logs / "oapen_skip.tsv", skip_rows)
    write_tsv(args.logs / "oapen_fail.tsv", fail_rows)

    safe_print(
        f"Done. downloaded={len(ok_rows)} skipped={len(skip_rows)} failed={len(fail_rows)}"
    )
    if fail_rows:
        return 2
    return 0 if (len(ok_rows) + len(skip_rows)) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
