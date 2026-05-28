#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: prelaunch/tools/common/unified_manifest_downloader.py
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

Existing module notes:
Unified manifest downloader for Windows-friendly local mirroring.

This script reads a runtime manifest derived from the unified project manifest and
downloads as many items as can be automated:
- Hugging Face model repos via snapshot_download
- Hugging Face dataset repos via snapshot_download(repo_type="dataset")
- GGUF model repos via selective hf_hub_download + quant selection
- Piper voices via selective voice subset download
- GitHub repositories via git clone/pull or zip fallback
- Zenodo records via the public records API
- TensorFlow Datasets builders via tensorflow_datasets (optional dependency)
- "web_scrape" items via best-effort discovery of downloadable assets

It keeps the Hugging Face cache separate from user-facing folders and writes
JSON reports that make verify/resume practical.
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import traceback
import sys
import time
import zipfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse

try:
    import requests
except Exception as exc:  # pragma: no cover
    print("This script requires 'requests'. Install with: python -m pip install requests", file=sys.stderr)
    raise

try:
    from huggingface_hub import HfApi, hf_hub_download, snapshot_download
    from huggingface_hub.utils import HfHubHTTPError
except Exception as exc:  # pragma: no cover
    print("This script requires 'huggingface_hub'. Install with: python -m pip install huggingface_hub", file=sys.stderr)
    raise

# Conservative defaults for the user's Windows setup.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT_DIR / "download_targets_runtime_manifest.json"
DEFAULT_VAULT_ROOT = Path(os.environ.get("VAULT_ROOT", r"E:\noemaforge-lab\data\Vault"))
DEFAULT_TARGET_ROOT = DEFAULT_VAULT_ROOT / "download-mirror"
DEFAULT_HF_CACHE = Path(os.environ.get("HF_HUB_CACHE", r"E:\hf-home\hub"))
DEFAULT_TFDS_DATA_DIR = DEFAULT_VAULT_ROOT / "datasets-tfds"
DEFAULT_WEB_DL_DIR = DEFAULT_VAULT_ROOT / "datasets-web"
USER_AGENT = "noemaforge-unified-downloader/2026.04"

REPORT_NAME = "_unified_download_report.json"
MANUAL_QUEUE_NAME = "_manual_queue.csv"
RUNTIME_STATE_NAME = "download_manifest.json"

GGUF_TAGS: Dict[str, List[str]] = {
    "q4": ["Q4_K_M", "Q4_K_S", "Q4_K", "Q4_0", "IQ4_XS", "IQ4_NL", "Q4"],
    "q5": ["Q5_K_M", "Q5_K_S", "Q5_1", "Q5_0", "Q5", "Q4_K_M", "Q4_K_S"],
    "q8": ["Q8_0", "Q8"],
    "f16": ["F16", "BF16", "FP16"],
}
AUX_PATTERNS = ["README*", "LICENSE*", "tokenizer*", "*.json", "*.txt", "*.model", "*.md"]
FILE_LINK_EXTENSIONS = (
    ".zip", ".tar", ".tar.gz", ".tgz", ".gz", ".xz", ".bz2", ".7z", ".rar",
    ".json", ".jsonl", ".csv", ".tsv", ".parquet", ".txt", ".zst",
)

@dataclass
class Args:
    manifest: Path
    target_root: Path
    cache_dir: Path
    tfds_data_dir: Path
    web_download_root: Path
    quant: str
    include_restricted: bool
    include_manual: bool
    verify_only: bool
    dry_run: bool
    force: bool
    checksum: bool
    list_only: bool
    groups: List[str]
    match: Optional[str]
    piper_locale: str
    piper_max_voices: int
    no_git_pull: bool
    skip_tfds: bool


def slugify(s: str) -> str:
    s = s.lower()
    repl = {"φ": "phi", "‑": "-", "–": "-", "—": "-", "→": "-to-", "/": "-", "&": "and"}
    for old, new in repl.items():
        s = s.replace(old, new)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "item"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def human_size(n: Optional[int]) -> str:
    if n is None:
        return "?"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.2f}{unit}"
        size /= 1024.0
    return f"{n}B"


def sha256_of_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_token(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def match_tag(filename: str, tag: str) -> bool:
    return normalize_token(tag) in normalize_token(filename)


def read_manifest(path: Path) -> List[Dict[str, Any]]:
    items = json.loads(path.read_text("utf-8"))
    if not isinstance(items, list):
        raise ValueError("Runtime manifest must be a list")
    return [normalize_manifest_item(item) for item in items]


def item_selected(item: Dict[str, Any], args: Args) -> bool:
    if args.groups and "all" not in args.groups:
        group_ok = False
        for g in args.groups:
            if g == "models" and item["kind"] in ("model", "gguf_model"):
                group_ok = True
            elif g == "datasets" and item["kind"] == "dataset":
                group_ok = True
            elif g == "gguf" and item["method"] == "hf_gguf":
                group_ok = True
        if not group_ok:
            return False
    if args.match:
        hay = " ".join([
            item.get("name", ""), item.get("slug", ""), item.get("kind", ""),
            item.get("method", ""), item.get("location", ""), item.get("used_in", ""),
        ]).lower()
        if args.match.lower() not in hay:
            return False
    if item.get("direct_download", "").lower() != "yes" and not args.include_restricted:
        return False
    if item.get("method") == "manual" and not args.include_manual:
        return False
    if item.get("restricted") and not args.include_restricted:
        return False
    return True


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_csv_row(path: Path, fieldnames: Sequence[str], row: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerow(row)


def compare_file(local_path: Path, remote_size: Optional[int], remote_sha256: Optional[str], checksum: bool) -> Tuple[str, str]:
    if not local_path.exists():
        return "missing", "file not found"
    try:
        local_size = local_path.stat().st_size
    except OSError as exc:
        return "error", f"stat failed: {exc}"
    if remote_size is not None and local_size != remote_size:
        return "size_mismatch", f"local {human_size(local_size)} != remote {human_size(remote_size)}"
    if checksum and remote_sha256:
        local_sha = sha256_of_file(local_path)
        if local_sha.lower() != remote_sha256.lower():
            return "hash_mismatch", "sha256 mismatch"
    return "ok", ""


def sync_file(src: Path, dest: Path, force: bool = False) -> str:
    ensure_dir(dest.parent)
    if dest.exists() and not force:
        try:
            if src.stat().st_size == dest.stat().st_size:
                return "kept"
        except OSError:
            pass
    shutil.copy2(src, dest)
    return "copied"


def sync_snapshot(src_root: Path, dest_root: Path, paths: Iterable[str], force: bool = False) -> Dict[str, int]:
    stats = {"copied": 0, "kept": 0}
    for rel in paths:
        src = src_root / rel
        dest = dest_root / rel
        if not src.exists():
            continue
        action = sync_file(src, dest, force=force)
        stats[action] = stats.get(action, 0) + 1
    return stats


def load_runtime_state(dest_dir: Path) -> Dict[str, Any]:
    p = dest_dir / RUNTIME_STATE_NAME
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return {}


def save_runtime_state(dest_dir: Path, payload: Dict[str, Any]) -> None:
    write_json(dest_dir / RUNTIME_STATE_NAME, payload)


def extract_hf_repo(location: str) -> Tuple[Optional[str], Optional[str]]:
    u = urlparse(location)
    parts = [p for p in u.path.split("/") if p]
    if not parts:
        return None, None
    if parts[0] == "datasets":
        if len(parts) >= 3:
            return "dataset", f"{parts[1]}/{parts[2]}"
        return "dataset", None
    if len(parts) >= 2:
        return "model", f"{parts[0]}/{parts[1]}"
    return "model", None


def extract_zenodo_record_id(location: str) -> Optional[str]:
    m = re.search(r"/records?/(\d+)", location)
    return m.group(1) if m else None


def normalize_manifest_item(item: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(item)
    out.setdefault("name", out.get("title") or out.get("slug") or "unnamed")
    if not out.get("slug"):
        out["slug"] = slugify(out["name"])
    location = out.get("location", "") or ""
    method = out.get("method")

    if method in ("hf_model_snapshot", "hf_dataset_snapshot", "hf_gguf", "hf_piper_subset"):
        repo_type_guess, repo_id_guess = extract_hf_repo(location) if location else (None, None)
        if not out.get("repo_id"):
            out["repo_id"] = out.get("hf_repo_id") or out.get("dataset_id") or repo_id_guess
        if method == "hf_dataset_snapshot":
            out["repo_type"] = "dataset"
        elif not out.get("repo_type") and repo_type_guess:
            out["repo_type"] = repo_type_guess

    if method == "zenodo_record" and not out.get("zenodo_record_id"):
        rid = extract_zenodo_record_id(location)
        if rid:
            out["zenodo_record_id"] = rid

    return out


def list_repo_files(api: HfApi, repo_id: str, repo_type: str) -> List[str]:
    return sorted(api.list_repo_files(repo_id=repo_id, repo_type=repo_type))


def get_paths_info(api: HfApi, repo_id: str, repo_type: str, paths: Sequence[str]) -> List[Dict[str, Any]]:
    infos = api.get_paths_info(repo_id=repo_id, repo_type=repo_type, paths=list(paths))
    result = []
    for info in infos:
        path = getattr(info, "path", None)
        size = getattr(info, "size", None)
        lfs = getattr(info, "lfs", None)
        sha256 = None
        if isinstance(lfs, dict):
            sha256 = lfs.get("sha256")
            if size is None:
                size = lfs.get("size")
        else:
            if lfs is not None:
                sha256 = getattr(lfs, "sha256", None)
                if size is None:
                    size = getattr(lfs, "size", None)
        if path is None:
            continue
        result.append({"path": str(path), "size": int(size) if size is not None else None, "sha256": sha256})
    result.sort(key=lambda x: x["path"])
    return result


def select_gguf_paths(gguf_files: Sequence[str], quant: str) -> List[str]:
    if not gguf_files:
        return []
    for tag in GGUF_TAGS[quant]:
        matched = [f for f in gguf_files if match_tag(Path(f).name, tag)]
        if matched:
            return matched
    for broad in ("Q4", "IQ4", "Q5", "Q8", "F16", "BF16"):
        matched = [f for f in gguf_files if broad in normalize_token(Path(f).name)]
        if matched:
            return matched
    return [gguf_files[0]]


def choose_piper_files(api: HfApi, repo_id: str, locale: str, max_voices: int) -> List[str]:
    files = api.list_repo_files(repo_id=repo_id, repo_type="model")
    onnx = [f for f in files if f.lower().endswith(".onnx") and f"/{locale}/" in f.replace("\\", "/")]
    preferred = [f for f in onnx if "medium" in f.lower()] or onnx
    voice_roots: Dict[str, List[str]] = {}
    for f in preferred:
        stem = f[:-5]  # strip .onnx
        voice_roots.setdefault(stem, []).append(f)
    selected_roots = sorted(voice_roots)[:max_voices]
    selected = []
    repo_files = set(files)
    for stem in selected_roots:
        selected.append(stem + ".onnx")
        for extra in (stem + ".onnx.json", stem + ".json", stem + ".md"):
            if extra in repo_files:
                selected.append(extra)
    # add a minimal README/LICENSE
    for pat in ("README*", "LICENSE*"):
        for f in files:
            if fnmatch.fnmatch(Path(f).name, pat):
                selected.append(f)
    dedup = []
    seen = set()
    for p in selected:
        if p in repo_files and p not in seen:
            seen.add(p)
            dedup.append(p)
    return dedup


def http_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def download_url(session: requests.Session, url: str, dest: Path, force: bool = False, timeout: int = 60) -> Dict[str, Any]:
    ensure_dir(dest.parent)
    meta: Dict[str, Any] = {"url": url, "dest": str(dest), "status": "planned"}
    head_size = None
    try:
        r_head = session.head(url, allow_redirects=True, timeout=timeout)
        if r_head.ok:
            cl = r_head.headers.get("Content-Length")
            if cl and cl.isdigit():
                head_size = int(cl)
    except requests.RequestException:
        pass

    if dest.exists() and not force and head_size is not None and dest.stat().st_size == head_size:
        meta["status"] = "kept"
        meta["size"] = head_size
        return meta

    # Resume only for straightforward cases.
    mode = "wb"
    headers: Dict[str, str] = {}
    if dest.exists() and not force and head_size is not None:
        local_size = dest.stat().st_size
        if 0 < local_size < head_size:
            headers["Range"] = f"bytes={local_size}-"
            mode = "ab"
    with session.get(url, stream=True, allow_redirects=True, timeout=timeout, headers=headers) as r:
        r.raise_for_status()
        with dest.open(mode) as f:
            for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
    meta["status"] = "downloaded"
    meta["size"] = dest.stat().st_size if dest.exists() else None
    return meta




def extract_archive_if_needed(archive_path: Path, extract_root: Path, expected_paths: Sequence[str], force: bool = False) -> Dict[str, Any]:
    ensure_dir(extract_root)
    if expected_paths and not force and all((extract_root / p).exists() for p in expected_paths):
        return {"status": "kept", "extracted_root": str(extract_root)}
    try:
        shutil.unpack_archive(str(archive_path), str(extract_root))
        return {"status": "extracted", "extracted_root": str(extract_root)}
    except Exception as exc:
        return {"status": "failed", "error": repr(exc), "archive": str(archive_path)}


def run_tfds_direct_bundle(item: Dict[str, Any], dest_dir: Path, args: Args, bundle: Dict[str, Any]) -> Dict[str, Any]:
    session = http_session()
    raw_dir = dest_dir / 'raw'
    extract_root = dest_dir / 'extracted'
    ensure_dir(raw_dir)
    ensure_dir(extract_root)
    report: Dict[str, Any] = {
        'name': item['name'],
        'method': 'tfds_direct_bundle',
        'tfds_builder': item.get('tfds_builder'),
        'dest': str(dest_dir),
        'raw_dir': str(raw_dir),
        'extract_root': str(extract_root),
    }
    expected_paths = bundle.get('expected_paths', [])
    if args.verify_only:
        ok = all((extract_root / p).exists() for p in expected_paths) if expected_paths else (dest_dir.exists() and any(dest_dir.rglob('*')))
        report['status'] = 'verified' if ok else 'partial'
        report['expected_paths'] = expected_paths
        return report
    if args.dry_run:
        report['status'] = 'planned'
        report['archives'] = [u['filename'] for u in bundle.get('urls', [])]
        report['expected_paths'] = expected_paths
        return report

    file_reports = []
    extract_reports = []
    any_failed = False
    for entry in bundle.get('urls', []):
        url = entry['url']
        filename = entry.get('filename') or Path(urlparse(url).path).name
        archive_path = raw_dir / filename
        dl = download_url(session, url, archive_path, force=args.force)
        file_reports.append(dl)
        if dl.get('status') == 'failed':
            any_failed = True
            continue
        extract_expected = entry.get('extract_expected', [])
        ex = extract_archive_if_needed(archive_path, extract_root, extract_expected, force=args.force)
        ex['filename'] = filename
        extract_reports.append(ex)
        if ex.get('status') == 'failed':
            any_failed = True
    ok = all((extract_root / p).exists() for p in expected_paths) if expected_paths else False
    report['downloads'] = file_reports
    report['extracts'] = extract_reports
    report['expected_paths'] = expected_paths
    if ok and not any_failed:
        report['status'] = 'ok'
    elif ok:
        report['status'] = 'partial'
    else:
        report['status'] = 'failed' if any_failed else 'partial'
    save_runtime_state(dest_dir, {
        'name': item['name'],
        'tfds_builder': item.get('tfds_builder'),
        'bundle': bundle.get('id'),
        'updated_at': now_iso(),
        'expected_paths': expected_paths,
    })
    return report


TFDS_DIRECT_FALLBACKS: Dict[str, Dict[str, Any]] = {
    'coco/2017': {
        'id': 'coco_2017_bundle',
        'urls': [
            {
                'url': 'http://images.cocodataset.org/zips/train2017.zip',
                'filename': 'train2017.zip',
                'extract_expected': ['train2017'],
            },
            {
                'url': 'http://images.cocodataset.org/zips/val2017.zip',
                'filename': 'val2017.zip',
                'extract_expected': ['val2017'],
            },
            {
                'url': 'http://images.cocodataset.org/annotations/annotations_trainval2017.zip',
                'filename': 'annotations_trainval2017.zip',
                'extract_expected': ['annotations'],
            },
        ],
        'expected_paths': ['train2017', 'val2017', 'annotations'],
    },
    'davis': {
        'id': 'davis_2017_480p_bundle',
        'urls': [
            {
                'url': 'https://data.vision.ee.ethz.ch/csergi/share/davis/DAVIS-2017-trainval-480p.zip',
                'filename': 'DAVIS-2017-trainval-480p.zip',
                'extract_expected': ['DAVIS/ImageSets/2017/train.txt', 'DAVIS/ImageSets/2017/val.txt'],
            },
        ],
        'expected_paths': ['DAVIS/ImageSets/2017/train.txt', 'DAVIS/ImageSets/2017/val.txt'],
    },
}


def github_owner_repo(url: str) -> Optional[Tuple[str, str]]:
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


def git_available() -> bool:
    try:
        proc = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=15)
        return proc.returncode == 0
    except Exception:
        return False


def download_github_repo(url: str, dest_dir: Path, force: bool, no_pull: bool, dry_run: bool) -> Dict[str, Any]:
    ensure_dir(dest_dir.parent)
    report: Dict[str, Any] = {"url": url, "dest": str(dest_dir), "status": "planned", "method": "github_repo"}
    if dry_run:
        return report
    if git_available():
        if (dest_dir / ".git").exists():
            if no_pull:
                report["status"] = "kept"
                return report
            proc = subprocess.run(["git", "-C", str(dest_dir), "pull", "--ff-only"], capture_output=True, text=True)
            report["status"] = "updated" if proc.returncode == 0 else "failed"
            report["stdout"] = proc.stdout[-4000:]
            report["stderr"] = proc.stderr[-4000:]
            return report
        if dest_dir.exists() and any(dest_dir.iterdir()) and not force:
            report["status"] = "kept"
            return report
        proc = subprocess.run(["git", "clone", "--depth", "1", url, str(dest_dir)], capture_output=True, text=True)
        report["status"] = "downloaded" if proc.returncode == 0 else "failed"
        report["stdout"] = proc.stdout[-4000:]
        report["stderr"] = proc.stderr[-4000:]
        if proc.returncode == 0:
            return report
        # fall through to zip fallback if clone failed.
    owner_repo = github_owner_repo(url)
    if not owner_repo:
        report["status"] = "failed"
        report["stderr"] = "Could not parse GitHub owner/repo from URL"
        return report
    owner, repo = owner_repo
    session = http_session()
    tmp_zip = dest_dir.parent / f"{repo}.zip"
    for branch in ("main", "master"):
        archive_url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}"
        try:
            dl = download_url(session, archive_url, tmp_zip, force=True)
        except requests.RequestException:
            continue
        shutil.unpack_archive(str(tmp_zip), str(dest_dir.parent))
        extracted = dest_dir.parent / f"{repo}-{branch}"
        if extracted.exists():
            if dest_dir.exists() and force:
                shutil.rmtree(dest_dir)
            if dest_dir.exists() and not force:
                report["status"] = "kept"
            else:
                extracted.rename(dest_dir)
                report["status"] = "downloaded"
            tmp_zip.unlink(missing_ok=True)
            return report
    report["status"] = "failed"
    report["stderr"] = "Git clone and GitHub zip fallback both failed"
    return report


def zenodo_record_files(session: requests.Session, record_id: str) -> List[Dict[str, Any]]:
    api_url = f"https://zenodo.org/api/records/{record_id}"
    r = session.get(api_url, timeout=60)
    r.raise_for_status()
    payload = r.json()
    files = payload.get("files", [])
    result = []
    for f in files:
        key = f.get("key") or f.get("filename")
        url = None
        links = f.get("links") or {}
        for k in ("download", "self", "content"):
            if links.get(k):
                url = links[k]
                break
        size = f.get("size")
        checksum = None
        checksum_field = f.get("checksum")
        if isinstance(checksum_field, str) and checksum_field.startswith("md5:"):
            checksum = checksum_field.split(":", 1)[1]
        result.append({"path": key, "url": url, "size": size, "checksum": checksum})
    return result


def discover_page_links(session: requests.Session, url: str) -> List[str]:
    r = session.get(url, timeout=60)
    r.raise_for_status()
    text = r.text
    hrefs = re.findall(r"""href\s*=\s*['"]([^'"]+)['"]""", text, flags=re.I)
    candidates = []
    for href in hrefs:
        href = unescape(href).strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        full = urljoin(url, href)
        parsed = urlparse(full)
        if parsed.scheme not in ("http", "https"):
            continue
        path_lower = parsed.path.lower()
        if path_lower.endswith(FILE_LINK_EXTENSIONS) or any(k in full.lower() for k in ("download", "zenodo.org/records/", "huggingface.co/", "github.com/")):
            candidates.append(full)
    # Preserve order, dedupe.
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def resolve_web_candidate_method(url: str) -> Tuple[str, Dict[str, Any]]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "huggingface.co" in host:
        repo_type, repo_id = extract_hf_repo(url)
        if repo_id:
            method = "hf_dataset_snapshot" if repo_type == "dataset" else "hf_model_snapshot"
            if "gguf" in url.lower():
                method = "hf_gguf"
            return method, {"repo_type": repo_type, "repo_id": repo_id}
    # Use exact equality or endswith(".<domain>") so that attacker-controlled
    # hostnames like "evil.github.com.attacker.com" are not misclassified
    # (CWE-20 incomplete URL sanitization).
    if host == "github.com" or host.endswith(".github.com"):
        return "github_repo", {"github_url": url}
    if host == "zenodo.org" or host.endswith(".zenodo.org"):
        m = re.search(r"/records/(\d+)", url)
        if m:
            return "zenodo_record", {"zenodo_record_id": m.group(1)}
    return "direct_url", {"direct_url": url}


def hf_snapshot_expected(api: HfApi, repo_id: str, repo_type: str) -> List[Dict[str, Any]]:
    files = api.list_repo_files(repo_id=repo_id, repo_type=repo_type)
    return get_paths_info(api, repo_id=repo_id, repo_type=repo_type, paths=files)


def verify_expected(dest_dir: Path, remote_files: Sequence[Dict[str, Any]], checksum: bool) -> Dict[str, Any]:
    statuses = []
    missing = []
    bad = []
    for info in remote_files:
        rel = info["path"]
        status, reason = compare_file(dest_dir / rel, info.get("size"), info.get("sha256"), checksum)
        statuses.append({"path": rel, "status": status, "reason": reason, "size": info.get("size")})
        if status == "missing":
            missing.append(rel)
        elif status != "ok":
            bad.append(rel)
    return {
        "ok": sum(1 for s in statuses if s["status"] == "ok"),
        "missing": missing,
        "bad": bad,
        "files": statuses,
    }


def hf_download_and_sync_snapshot(item: Dict[str, Any], dest_dir: Path, args: Args, api: HfApi) -> Dict[str, Any]:
    repo_id = item.get("repo_id")
    repo_type = item.get("repo_type") or ("dataset" if item["method"] == "hf_dataset_snapshot" else "model")
    report: Dict[str, Any] = {"name": item["name"], "method": item["method"], "repo_id": repo_id, "dest": str(dest_dir)}
    if not repo_id:
        report["status"] = "failed"
        report["error"] = "No repo_id set in manifest and could not infer one from location"
        return report
    if args.dry_run:
        try:
            remote_files = hf_snapshot_expected(api, repo_id=repo_id, repo_type=repo_type)
        except Exception as exc:
            report["status"] = "error"
            report["error"] = str(exc)
            return report
        verify = verify_expected(dest_dir, remote_files, checksum=args.checksum)
        report["status"] = "planned"
        report["remote_files"] = len(remote_files)
        report["ok"] = verify["ok"]
        report["missing"] = len(verify["missing"])
        report["bad"] = len(verify["bad"])
        return report

    try:
        snapshot_path = Path(snapshot_download(
            repo_id=repo_id,
            repo_type=repo_type,
            cache_dir=str(args.cache_dir),
            resume_download=True,
            force_download=args.force,
        ))
        remote_files = hf_snapshot_expected(api, repo_id=repo_id, repo_type=repo_type)
        rel_paths = [f["path"] for f in remote_files]
        sync_stats = sync_snapshot(snapshot_path, dest_dir, rel_paths, force=args.force)
        verify = verify_expected(dest_dir, remote_files, checksum=args.checksum)
        save_runtime_state(dest_dir, {
            "name": item["name"],
            "repo_id": repo_id,
            "repo_type": repo_type,
            "updated_at": now_iso(),
            "remote_file_count": len(remote_files),
        })
        report.update({
            "status": "ok" if not verify["missing"] and not verify["bad"] else "partial",
            "remote_files": len(remote_files),
            "copied": sync_stats.get("copied", 0),
            "kept": sync_stats.get("kept", 0),
            "ok": verify["ok"],
            "missing": len(verify["missing"]),
            "bad": len(verify["bad"]),
        })
        if args.verify_only:
            report["status"] = "verified" if not verify["missing"] and not verify["bad"] else "partial"
        return report
    except HfHubHTTPError as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
        return report


def hf_download_and_sync_gguf(item: Dict[str, Any], dest_dir: Path, args: Args, api: HfApi) -> Dict[str, Any]:
    repo_id = item.get("repo_id")
    report: Dict[str, Any] = {"name": item["name"], "method": item["method"], "repo_id": repo_id, "dest": str(dest_dir), "quant": args.quant}
    if not repo_id:
        report["status"] = "failed"
        report["error"] = "No repo_id set in manifest and could not infer one from location"
        return report
    try:
        repo_files = api.list_repo_files(repo_id=repo_id, repo_type="model")
        gguf_files = sorted([f for f in repo_files if f.lower().endswith(".gguf")])
        selected = select_gguf_paths(gguf_files, args.quant)
        selected_aux = []
        for pat in AUX_PATTERNS:
            for f in repo_files:
                if fnmatch.fnmatch(Path(f).name, pat):
                    selected_aux.append(f)
        selected_paths = []
        seen = set()
        for p in list(selected) + selected_aux:
            if p not in seen:
                seen.add(p)
                selected_paths.append(p)
        remote_files = get_paths_info(api, repo_id=repo_id, repo_type="model", paths=selected_paths)
        verify = verify_expected(dest_dir, remote_files, checksum=args.checksum)
        if args.dry_run or args.verify_only:
            report.update({
                "status": "planned" if args.dry_run else ("verified" if not verify["missing"] and not verify["bad"] else "partial"),
                "selected_files": [Path(p).name for p in selected],
                "remote_files": len(remote_files),
                "ok": verify["ok"],
                "missing": len(verify["missing"]),
                "bad": len(verify["bad"]),
            })
            return report

        copied = kept = 0
        for rel in selected_paths:
            src = Path(hf_hub_download(
                repo_id=repo_id,
                filename=rel,
                repo_type="model",
                cache_dir=str(args.cache_dir),
                force_download=args.force,
                resume_download=True,
            ))
            action = sync_file(src, dest_dir / rel, force=args.force)
            copied += int(action == "copied")
            kept += int(action == "kept")
        verify = verify_expected(dest_dir, remote_files, checksum=args.checksum)
        save_runtime_state(dest_dir, {
            "name": item["name"], "repo_id": repo_id, "repo_type": "model",
            "updated_at": now_iso(), "selected_files": selected_paths,
        })
        report.update({
            "status": "ok" if not verify["missing"] and not verify["bad"] else "partial",
            "selected_files": [Path(p).name for p in selected],
            "remote_files": len(remote_files),
            "copied": copied,
            "kept": kept,
            "ok": verify["ok"],
            "missing": len(verify["missing"]),
            "bad": len(verify["bad"]),
        })
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
        return report


def hf_download_and_sync_piper(item: Dict[str, Any], dest_dir: Path, args: Args, api: HfApi) -> Dict[str, Any]:
    repo_id = item.get("repo_id")
    report: Dict[str, Any] = {"name": item["name"], "method": item["method"], "repo_id": repo_id, "dest": str(dest_dir)}
    if not repo_id:
        report["status"] = "failed"
        report["error"] = "No repo_id set in manifest and could not infer one from location"
        return report
    try:
        selected_paths = choose_piper_files(api, repo_id=repo_id, locale=args.piper_locale, max_voices=args.piper_max_voices)
        remote_files = get_paths_info(api, repo_id=repo_id, repo_type="model", paths=selected_paths)
        verify = verify_expected(dest_dir, remote_files, checksum=args.checksum)
        if args.dry_run or args.verify_only:
            report.update({
                "status": "planned" if args.dry_run else ("verified" if not verify["missing"] and not verify["bad"] else "partial"),
                "selected_files": selected_paths,
                "remote_files": len(remote_files),
                "ok": verify["ok"],
                "missing": len(verify["missing"]),
                "bad": len(verify["bad"]),
            })
            return report
        copied = kept = 0
        for rel in selected_paths:
            src = Path(hf_hub_download(
                repo_id=repo_id,
                filename=rel,
                repo_type="model",
                cache_dir=str(args.cache_dir),
                force_download=args.force,
                resume_download=True,
            ))
            action = sync_file(src, dest_dir / rel, force=args.force)
            copied += int(action == "copied")
            kept += int(action == "kept")
        verify = verify_expected(dest_dir, remote_files, checksum=args.checksum)
        save_runtime_state(dest_dir, {
            "name": item["name"], "repo_id": repo_id, "repo_type": "model",
            "updated_at": now_iso(), "selected_files": selected_paths,
        })
        report.update({
            "status": "ok" if not verify["missing"] and not verify["bad"] else "partial",
            "selected_files": selected_paths,
            "remote_files": len(remote_files),
            "copied": copied,
            "kept": kept,
            "ok": verify["ok"],
            "missing": len(verify["missing"]),
            "bad": len(verify["bad"]),
        })
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
        return report


def run_tfds_builder(item: Dict[str, Any], dest_dir: Path, args: Args) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "name": item["name"], "method": item["method"], "tfds_builder": item.get("tfds_builder"), "dest": str(dest_dir)
    }
    builder_name = item.get("tfds_builder")
    if not builder_name:
        report["status"] = "failed"
        report["error"] = "No tfds_builder set in manifest"
        return report
    fallback = TFDS_DIRECT_FALLBACKS.get(builder_name)
    if fallback:
        return run_tfds_direct_bundle(item, dest_dir, args, fallback)
    if args.skip_tfds:
        report["status"] = "skipped"
        report["reason"] = "TFDS disabled by --skip-tfds"
        return report
    try:
        import tensorflow as tf  # type: ignore  # noqa: F401
    except Exception:
        report["status"] = "skipped_missing_dependency"
        report["error"] = "TensorFlow is not installed in this env. Install with: python -m pip install tensorflow"
        report["hint"] = "On native Windows, current TensorFlow packages are CPU-only; use WSL2 for official GPU support."
        return report
    try:
        import tensorflow_datasets as tfds  # type: ignore
    except Exception:
        report["status"] = "skipped_missing_dependency"
        report["error"] = "tensorflow_datasets is not installed. Install with: python -m pip install tensorflow-datasets"
        return report
    ensure_dir(args.tfds_data_dir)
    try:
        builder = tfds.builder(builder_name, data_dir=str(args.tfds_data_dir))
        data_path = Path(str(getattr(builder, "data_path", args.tfds_data_dir / slugify(builder_name))))
        if args.verify_only:
            report["status"] = "verified" if data_path.exists() and any(data_path.rglob("*")) else "partial"
            report["data_path"] = str(data_path)
            return report
        if args.dry_run:
            report["status"] = "planned"
            report["data_path"] = str(data_path)
            return report
        builder.download_and_prepare()
        report["status"] = "ok"
        report["data_path"] = str(data_path)
        save_runtime_state(dest_dir, {
            "name": item["name"], "tfds_builder": builder_name, "updated_at": now_iso(), "data_path": str(data_path),
        })
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
        return report


def run_zenodo_record(item: Dict[str, Any], dest_dir: Path, args: Args) -> Dict[str, Any]:
    session = http_session()
    record_id = item.get("zenodo_record_id")
    report: Dict[str, Any] = {"name": item["name"], "method": item["method"], "record_id": record_id, "dest": str(dest_dir)}
    if not record_id:
        report["status"] = "failed"
        report["error"] = "No zenodo_record_id set in manifest and could not infer one from location"
        return report
    try:
        files = zenodo_record_files(session, record_id)
        report["remote_files"] = len(files)
        missing = 0
        bad = 0
        for f in files:
            status, _ = compare_file(dest_dir / f["path"], f.get("size"), None, False)
            if status == "missing":
                missing += 1
            elif status != "ok":
                bad += 1
        if args.dry_run or args.verify_only:
            report["status"] = "planned" if args.dry_run else ("verified" if not missing and not bad else "partial")
            report["missing"] = missing
            report["bad"] = bad
            return report
        downloaded = kept = 0
        for f in files:
            meta = download_url(session, f["url"], dest_dir / f["path"], force=args.force)
            if meta["status"] == "downloaded":
                downloaded += 1
            elif meta["status"] == "kept":
                kept += 1
        save_runtime_state(dest_dir, {
            "name": item["name"], "record_id": record_id, "updated_at": now_iso(), "remote_files": len(files),
        })
        report["status"] = "ok"
        report["downloaded"] = downloaded
        report["kept"] = kept
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
        return report


def run_web_scrape(item: Dict[str, Any], dest_dir: Path, args: Args) -> Dict[str, Any]:
    session = http_session()
    report: Dict[str, Any] = {"name": item["name"], "method": item["method"], "url": item["location"], "dest": str(dest_dir)}
    try:
        links = discover_page_links(session, item["location"])
        report["discovered_links"] = links[:25]
        if not links:
            report["status"] = "manual"
            report["reason"] = "No downloadable links discovered on page"
            return report
        if args.dry_run:
            report["status"] = "planned"
            return report
        if args.verify_only:
            report["status"] = "verified" if dest_dir.exists() and any(dest_dir.rglob("*")) else "partial"
            return report

        # Try the first reasonable candidate.
        successes = 0
        for link in links:
            method, extra = resolve_web_candidate_method(link)
            tmp_item = dict(item)
            tmp_item.update(extra)
            tmp_item["method"] = method
            if method == "github_repo":
                sub = download_github_repo(link, dest_dir, force=args.force, no_pull=args.no_git_pull, dry_run=False)
            elif method in ("hf_model_snapshot", "hf_dataset_snapshot", "hf_gguf"):
                if method == "hf_gguf":
                    sub = hf_download_and_sync_gguf(tmp_item, dest_dir, args, HfApi())
                else:
                    sub = hf_download_and_sync_snapshot(tmp_item, dest_dir, args, HfApi())
            elif method == "zenodo_record":
                sub = run_zenodo_record(tmp_item, dest_dir, args)
            elif method == "direct_url":
                filename = Path(urlparse(link).path).name or "download.bin"
                sub = download_url(session, link, dest_dir / filename, force=args.force)
            else:
                continue
            if sub.get("status") in ("ok", "downloaded", "updated", "kept", "partial"):
                successes += 1
                report.setdefault("subreports", []).append(sub)
                if method != "direct_url":
                    break
        report["status"] = "ok" if successes else "manual"
        if not successes:
            report["reason"] = "Candidates discovered but none downloaded successfully"
        save_runtime_state(dest_dir, {"name": item["name"], "updated_at": now_iso(), "links": links[:50]})
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
        return report


def run_manual(item: Dict[str, Any], dest_dir: Path, args: Args) -> Dict[str, Any]:
    ensure_dir(dest_dir.parent)
    report = {"name": item["name"], "method": "manual", "status": "manual", "url": item["location"], "dest": str(dest_dir)}
    note = [
        f"Name: {item['name']}",
        f"URL: {item['location']}",
        f"Reason: manual / registration / unsupported direct automation",
        f"Generated at: {now_iso()}",
    ]
    if not args.dry_run and args.include_manual:
        ensure_dir(dest_dir)
        (dest_dir / "README.txt").write_text("\n".join(note), encoding="utf-8")
    return report


def summarize_counts(reports: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in reports:
        counts[r.get("status", "unknown")] = counts.get(r.get("status", "unknown"), 0) + 1
    return counts


def handle_item(item: Dict[str, Any], args: Args, api: HfApi) -> Dict[str, Any]:
    dest_dir = args.target_root / item["target_rel"]
    method = item["method"]
    if method == "hf_model_snapshot" or method == "hf_dataset_snapshot":
        return hf_download_and_sync_snapshot(item, dest_dir, args, api)
    if method == "hf_gguf":
        return hf_download_and_sync_gguf(item, dest_dir, args, api)
    if method == "hf_piper_subset":
        return hf_download_and_sync_piper(item, dest_dir, args, api)
    if method == "github_repo":
        return download_github_repo(item["location"], dest_dir, force=args.force, no_pull=args.no_git_pull, dry_run=args.dry_run)
    if method == "zenodo_record":
        return run_zenodo_record(item, dest_dir, args)
    if method == "tfds":
        return run_tfds_builder(item, dest_dir, args)
    if method == "web_scrape":
        return run_web_scrape(item, dest_dir, args)
    if method == "manual":
        return run_manual(item, dest_dir, args)
    return {"name": item["name"], "method": method, "status": "failed", "error": f"Unknown method: {method}"}


def parse_args(argv: Optional[Sequence[str]] = None) -> Args:
    p = argparse.ArgumentParser(description="Unified downloader for the NoemaForge manifest.")
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--target-root", type=Path, default=DEFAULT_TARGET_ROOT)
    p.add_argument("--cache-dir", type=Path, default=DEFAULT_HF_CACHE)
    p.add_argument("--tfds-data-dir", type=Path, default=DEFAULT_TFDS_DATA_DIR)
    p.add_argument("--web-download-root", type=Path, default=DEFAULT_WEB_DL_DIR)
    p.add_argument("--quant", choices=sorted(GGUF_TAGS), default="q4")
    p.add_argument("--include-restricted", action="store_true", help="Attempt gated or non-direct items when the manifest marks them restricted.")
    p.add_argument("--include-manual", action="store_true", help="Emit local README stubs for manual items.")
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="Force re-download / overwrite when supported.")
    p.add_argument("--checksum", action="store_true", help="Use SHA-256 checks when remote metadata provides them.")
    p.add_argument("--list", dest="list_only", action="store_true")
    p.add_argument("--groups", nargs="*", default=["all"], help="Subset: all models datasets gguf")
    p.add_argument("--match", help="Case-insensitive substring filter over name/method/url.")
    p.add_argument("--piper-locale", default="en_US")
    p.add_argument("--piper-max-voices", type=int, default=2)
    p.add_argument("--no-git-pull", action="store_true", help="Keep existing git clones instead of pulling updates.")
    p.add_argument("--skip-tfds", action="store_true", help="Skip TensorFlow Datasets items instead of marking them failed when TensorFlow is unavailable.")
    ns = p.parse_args(argv)
    return Args(
        manifest=ns.manifest,
        target_root=ns.target_root,
        cache_dir=ns.cache_dir,
        tfds_data_dir=ns.tfds_data_dir,
        web_download_root=ns.web_download_root,
        quant=ns.quant,
        include_restricted=ns.include_restricted,
        include_manual=ns.include_manual,
        verify_only=ns.verify_only,
        dry_run=ns.dry_run,
        force=ns.force,
        checksum=ns.checksum,
        list_only=ns.list_only,
        groups=ns.groups,
        match=ns.match,
        piper_locale=ns.piper_locale,
        piper_max_voices=ns.piper_max_voices,
        no_git_pull=ns.no_git_pull,
        skip_tfds=ns.skip_tfds,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    items = read_manifest(args.manifest)
    selected = [item for item in items if item_selected(item, args)]

    if args.list_only:
        print(f"Manifest: {args.manifest}")
        print(f"Selected items: {len(selected)}")
        for item in selected:
            marker = "restricted" if item.get("restricted") else "open"
            print(f"- {item['kind']:10s} {item['slug']:35s} {item['method']:20s} {marker:10s} {item['name']}")
        return 0

    ensure_dir(args.target_root)
    ensure_dir(args.cache_dir)
    report_path = args.target_root / REPORT_NAME
    manual_csv = args.target_root / MANUAL_QUEUE_NAME

    api = HfApi()
    reports: List[Dict[str, Any]] = []
    for item in selected:
        print(f"[{item['method']}] {item['name']}")
        try:
            rep = handle_item(item, args, api)
        except Exception as exc:
            rep = {"status": "failed", "error": repr(exc), "traceback": traceback.format_exc(limit=5)}
        rep["name"] = item["name"]
        rep["slug"] = item["slug"]
        rep["kind"] = item["kind"]
        rep["location"] = item["location"]
        rep["timestamp"] = now_iso()
        reports.append(rep)
        print(f"  -> {rep.get('status')}")

    payload = {
        "generated_at": now_iso(),
        "manifest": str(args.manifest),
        "target_root": str(args.target_root),
        "cache_dir": str(args.cache_dir),
        "tfds_data_dir": str(args.tfds_data_dir),
        "selected_count": len(selected),
        "summary": summarize_counts(reports),
        "reports": reports,
    }
    write_json(report_path, payload)

    manual_rows = []
    for item in items:
        if item["method"] == "manual" or item.get("restricted"):
            manual_rows.append({
                "slug": item["slug"], "name": item["name"], "method": item["method"],
                "restricted": item.get("restricted", False), "location": item["location"],
                "direct_download": item.get("direct_download"), "notes": item.get("notes", ""),
            })
    if manual_rows:
        fieldnames = list(manual_rows[0].keys())
        if manual_csv.exists():
            manual_csv.unlink()
        for row in manual_rows:
            append_csv_row(manual_csv, fieldnames, row)

    print(f"Report written to: {report_path}")
    if manual_rows:
        print(f"Manual/restricted queue: {manual_csv}")
    print("Summary:", payload["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
