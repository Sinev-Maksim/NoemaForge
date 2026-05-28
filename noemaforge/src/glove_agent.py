#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/glove_agent.py
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
# File: src/glove_agent.py
# Purpose: Provide the module 'glove_agent'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - main
# Inputs:
#   - --incident-dir
#   - --out
#   - --profile
#   - --languages
#   - Common path inputs: .//item, .git/hooks
#   - Imports: __future__, argparse, datetime, hashlib, io, json, os, re
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""glove_agent.py (v0.11.0)

Glove = one-shot, amnesic analysis worker.

This script is intended to be executed inside a sandbox backend.
Inputs:
- incident snapshot directory (RO): incident.json, file_meta.json, role_context.json
- optional payload.bin (RO): WebGateway / other incident evidence payload
Output:
- glove_report.json into an output directory (RW)
- optional side artifacts in the same output directory (RW), copied by glove_runner to
  stable names in incident dir (best-effort):
    - sanitized.txt (for rss_sanitize/web_sanitize)
    - payload_inventory.json (for git_scan/package_inspect)

No network. No long-term memory.
"""


import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import tarfile
import zipfile
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

try:
    import xml.etree.ElementTree as ET
except Exception:  # pragma: no cover
    ET = None  # type: ignore


try:
    # Deterministic PI scanner/scrubber.
    from pi_firewall import scan_text as _pi_scan_text, redact_instruction_like_lines as _pi_redact_lines
except Exception:  # pragma: no cover
    _pi_scan_text = None
    _pi_redact_lines = None


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
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _load_json(path: str)
# Purpose: Implement the routine ' load json'.
# Inputs:
#   - path: str
# Called by:
#   - src/noemaforge_core.py
#   - src/fixture_bundle.py
#   - src/model_installer_plan.py
#   - src/model_registry.py
#   - src/model_router.py
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
#   - src/team_installer_plan.py
# Calls:
#   - load, open
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# === End NoemaForge Autodoc Function Header ===
def _load_json(path: str) -> Dict[str, Any]:
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_file(path: str, max_bytes: int = 50000000)
# Purpose: Implement the routine ' sha256 file'.
# Inputs:
#   - path: str
#   - max_bytes: int = 50000000
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/casebase.py
#   - src/doctor.py
#   - src/localgw_uplink_agent.py
#   - src/model_registry.py
#   - src/pipelines/finance_budget.py
#   - src/prestart.py
# Calls:
#   - sha256, hexdigest, open, read, update, len
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - chunk, f, h, total
# === End NoemaForge Autodoc Function Header ===
def _sha256_file(path: str, max_bytes: int = 50_000_000) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            total = 0
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
                total += len(chunk)
                if total >= max_bytes:
                    break
    except Exception:
        return ""
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _read_payload_bytes(path: str, max_bytes: int = 5000000)
# Purpose: Implement the routine ' read payload bytes'.
# Inputs:
#   - path: str
#   - max_bytes: int = 5000000
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, read
# Returns / emits: bytes
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _read_payload_bytes(path: str, max_bytes: int = 5_000_000) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read(max_bytes)
    except Exception:
        return b""


# === NoemaForge Autodoc Function Header ===
# Function: _suspicious_text_signals(text: str)
# Purpose: Implement the routine ' suspicious text signals'.
# Inputs:
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, items, append, strip
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - hits, patterns, t, tok
# === End NoemaForge Autodoc Function Header ===
def _suspicious_text_signals(text: str) -> List[str]:
    t = (text or "").lower()
    hits: List[str] = []
    patterns = {
        "prompt_injection": [
            "ignore previous",
            "system prompt",
            "developer message",
            "you are now",
            "act as",
            "do not follow",
            "exfiltrate",
            "leak",
            "secret",
        ],
        "shell_rce": [
            "curl ",
            "wget ",
            "nc ",
            "bash -c",
            "python -c",
            "powershell",
        ],
        "data_exfil": [
            "~/.ssh",
            "/etc/shadow",
            "id_rsa",
            "token",
            "oauth",
            "api key",
        ],
    }
    for k, toks in patterns.items():
        for tok in toks:
            if tok in t:
                hits.append(f"{k}:{tok.strip()}")
                break
    return hits


# === NoemaForge Autodoc Function Header ===
# Function: _extract_payload_text(incident: Dict[str, Any])
# Purpose: Implement the routine ' extract payload text'.
# Inputs:
#   - incident: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - items, join, get, isinstance, append, len, dumps
# Returns / emits: str
# Side effects:
#   - serializes structured data
#   - appends to logs or files
# Key locals:
#   - args, parts, req
# === End NoemaForge Autodoc Function Header ===
def _extract_payload_text(incident: Dict[str, Any]) -> str:
    # Best-effort extraction of any textual content inside request args
    req = incident.get("request") or {}
    args = req.get("args") or {}
    parts: List[str] = []
    for k, v in args.items():
        if isinstance(v, str) and len(v) < 50_000:
            parts.append(f"{k}={v}")
        if isinstance(v, list):
            try:
                parts.append(f"{k}={json.dumps(v, ensure_ascii=False)[:5000]}")
            except Exception:
                pass
        if isinstance(v, dict):
            try:
                parts.append(f"{k}={json.dumps(v, ensure_ascii=False)[:5000]}")
            except Exception:
                pass
    return "\n".join(parts)


# === NoemaForge Autodoc Function Header ===
# Function: _risk_score(incident: Dict[str, Any], signals: List[str])
# Purpose: Implement the routine ' risk score'.
# Inputs:
#   - incident: Dict[str, Any]
#   - signals: List[str]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, any, min, startswith, get
# Returns / emits: int
# Key locals:
#   - action, reason, score
# === End NoemaForge Autodoc Function Header ===
def _risk_score(incident: Dict[str, Any], signals: List[str]) -> int:
    reason = str(incident.get("reason") or "")
    action = str(incident.get("action") or "")

    score = 10
    if reason in ("epoch_mismatch", "issued_to_mismatch", "cap_missing"):
        score += 30
    if reason.startswith("fs:") or reason.startswith("db:"):
        score += 10
    if action in ("exec.run",):
        score += 20
    if any(s.startswith("data_exfil") for s in signals):
        score += 25
    if any(s.startswith("shell_rce") for s in signals):
        score += 20
    if any(s.startswith("prompt_injection") for s in signals):
        score += 15

    return min(100, score)


# === NoemaForge Autodoc Function Header ===
# Function: _analysis_pass(language: str, base: Dict[str, Any])
# Purpose: Implement the routine ' analysis pass'.
# Inputs:
#   - language: str
#   - base: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _analysis_pass(language: str, base: Dict[str, Any]) -> Dict[str, Any]:
    # In MVP we keep it structured. Later, an actual SLM can generate language-specific
    # passes and we can compare divergences.
    return {
        "language": language,
        "profile": base.get("profile") or "generic",
        "summary": base.get("summary") or "",
        "signals": base.get("signals") or [],
        "risk_score": base.get("risk_score") or 0,
        "recommendations": base.get("recommendations") or [],
        "notes": [
            "Glove pass is template-based in the seed kit. Future: run multiple SLM passes per language and diff conclusions.",
        ],
    }


# === NoemaForge Autodoc Function Header ===
# Function: _profile_recommendations(profile: str, signals: List[str])
# Purpose: Implement the routine ' profile recommendations'.
# Inputs:
#   - profile: str
#   - signals: List[str]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, append, any, lower, startswith
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - p, recs
# === End NoemaForge Autodoc Function Header ===
def _profile_recommendations(profile: str, signals: List[str]) -> List[str]:
    p = (profile or "generic").lower().strip()
    recs: List[str] = []

    if p in ("web_sanitize", "rss_sanitize"):
        recs.append("Treat HTML/RSS content as an attack surface: keep it quarantined; sanitize before indexing.")
        recs.append("Strip any 'instructions' embedded in content; keep only quoted evidence + metadata.")
        if any(s.startswith("prompt_injection") for s in signals):
            recs.append("Add/strengthen indirect prompt-injection fixtures for web/rss ingestion.")

    elif p in ("net_inspect", "lan_forensics"):
        recs.append("Prefer device identity beyond SSID: pin device_uids; watch for drift (MAC/IP changes).")
        recs.append("If unknown devices appear, keep LAN session in quarantine and require human approval.")
        recs.append("Capture minimal network snapshot (neigh table / ARP) as evidence in SEL/WORM.")

    elif p in ("package_inspect", "apt_inspect"):
        recs.append("Prefer signed repositories over ad-hoc package downloads.")
        recs.append("Verify package origin/pinning: repo domain allowlist + sha256 pinning + (future) signature checks.")
        recs.append("Treat maintainer scripts as high-risk. If installing, require a canary VM run that exercises install/uninstall.")

    elif p in ("git_scan", "repo_scan"):
        recs.append("Pin git refs (tag/commit) and avoid floating branches for supply-chain inputs.")
        recs.append("Scan for build/install scripts and CI workflows that could execute code unexpectedly.")
        recs.append("Prefer quarantine -> glove -> ToolVault import; never pipe repo content directly into executors.")

    else:
        recs.append("Keep incident immutable; review through sterile glove; avoid loosening policies by default.")

    return recs


# === NoemaForge Autodoc Function Header ===
# Function: _strip_html(text: str)
# Purpose: Implement the routine ' strip html'.
# Inputs:
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sub, replace, join, strip, append, pop, split
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - blank, lines, ln, out, t
# === End NoemaForge Autodoc Function Header ===
class _TextExtractingHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        t = (tag or "").lower()
        if t in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if t == "br":
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = (tag or "").lower()
        if t in {"script", "style"}:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return
        if t in {"p", "div", "li", "ul", "ol", "section", "article", "header", "footer"} or re.fullmatch(r"h\d", t):
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data:
            self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def _strip_html(text: str) -> str:
    t = text or ""
    parser = _TextExtractingHTMLParser()
    parser.feed(t)
    parser.close()
    t = parser.get_text()
    # Normalize whitespace but preserve newlines.
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in t.split("\n")]
    # Drop empty lines at ends, collapse repeated blanks.
    out: List[str] = []
    blank = 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        out.append(ln)
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


# === NoemaForge Autodoc Function Header ===
# Function: _article_extract(html_text: str)
# Purpose: Best-effort readable text extraction.
# Inputs:
#   - html_text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _strip_html, extract, Document, summary, strip, str
# Returns / emits: str
# Key locals:
#   - doc, h, out, summary_html
# === End NoemaForge Autodoc Function Header ===
def _article_extract(html_text: str) -> str:
    """Best-effort readable text extraction.

    Prefers trafilatura/readability-lxml if present, otherwise falls back to
    conservative HTML stripping.
    """
    h = html_text or ""
    # Try trafilatura
    try:
        import trafilatura  # type: ignore

        out = trafilatura.extract(
            h,
            include_tables=True,
            include_comments=False,
            include_links=False,
            favor_precision=True,
        )
        if out and str(out).strip():
            return str(out).strip()
    except Exception:
        pass

    # Try readability-lxml
    try:
        from readability import Document  # type: ignore

        doc = Document(h)
        summary_html = doc.summary(html_partial=True)
        if summary_html and str(summary_html).strip():
            return _strip_html(str(summary_html))
    except Exception:
        pass

    return _strip_html(h)


# === NoemaForge Autodoc Function Header ===
# Function: _pi_scan_and_scrub(text: str, source: str)
# Purpose: Implement the routine ' pi scan and scrub'.
# Inputs:
#   - text: str
#   - source: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _pi_scan_text, _pi_redact_lines
# Returns / emits: Tuple[str, Dict[str, Any]]
# Key locals:
#   - rep, scrubbed
# === End NoemaForge Autodoc Function Header ===
def _pi_scan_and_scrub(text: str, *, source: str) -> Tuple[str, Dict[str, Any]]:
    if _pi_scan_text is None or _pi_redact_lines is None:
        return (text or ""), {"source": source, "score": 0, "severity": "none", "hits": [], "reasons": {"pi_firewall_missing": 1}}
    rep = _pi_scan_text(text or "", source=source)
    scrubbed = _pi_redact_lines(text or "", rep)
    return scrubbed, rep


# === NoemaForge Autodoc Function Header ===
# Function: _extract_rss_items(xml_text: str, max_items: int = 50)
# Purpose: Implement the routine ' extract rss items'.
# Inputs:
#   - xml_text: str
#   - max_items: int = 50
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - extend, strip, set, _strip_html, fromstring, findall, _txt, add, append, find, join, itertext
# Returns / emits: Tuple[str, List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - desc, it, items, le, link, links, links2, out_lines, parts, plain, pub, root
# === End NoemaForge Autodoc Function Header ===
def _extract_rss_items(xml_text: str, max_items: int = 50) -> Tuple[str, List[str]]:
    links: List[str] = []
    if ET is None:
        plain = _strip_html(xml_text)
        return plain, links

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        plain = _strip_html(xml_text)
        # best-effort link extract
        links = re.findall(r"https?://[^\s'\"]+", xml_text)[:200]
        return plain, links

    # RSS/Atom are messy; do a forgiving walk.
    out_lines: List[str] = []
    items: List[ET.Element] = []

    # RSS: //item
    items.extend(root.findall('.//item'))
    # Atom: //entry
    items.extend(root.findall('.//{http://www.w3.org/2005/Atom}entry'))
    items = items[:max_items]

    # === NoemaForge Autodoc Function Header ===
    # Function: _txt(el: Optional[ET.Element])
    # Purpose: Implement the routine ' txt'.
    # Inputs:
    #   - el: Optional[ET.Element]
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - strip, join, itertext
    # Returns / emits: str
    # === End NoemaForge Autodoc Function Header ===
    def _txt(el: Optional[ET.Element]) -> str:
        if el is None:
            return ""
        return ("".join(el.itertext()) or "").strip()

    for it in items:
        title = _txt(it.find('title')) or _txt(it.find('{http://www.w3.org/2005/Atom}title'))
        link = ""
        # RSS link
        link = _txt(it.find('link'))
        # Atom link attribute
        if not link:
            le = it.find('{http://www.w3.org/2005/Atom}link')
            if le is not None:
                link = (le.attrib.get('href') or '').strip()
        pub = _txt(it.find('pubDate')) or _txt(it.find('{http://www.w3.org/2005/Atom}updated'))
        desc = _txt(it.find('description')) or _txt(it.find('{http://www.w3.org/2005/Atom}summary'))

        if link:
            links.append(link)

        parts = []
        if title:
            parts.append(f"TITLE: {title}")
        if pub:
            parts.append(f"DATE: {pub}")
        if link:
            parts.append(f"LINK: {link}")
        if desc:
            parts.append(f"TEXT: {_strip_html(desc)}")

        if parts:
            out_lines.append("\n".join(parts))
            out_lines.append("---")

    plain = "\n".join(out_lines).strip()
    if not plain:
        plain = _strip_html(xml_text)
        links = re.findall(r"https?://[^\s'\"]+", xml_text)[:200]

    # Dedup links
    seen = set()
    links2: List[str] = []
    for u in links:
        if u in seen:
            continue
        seen.add(u)
        links2.append(u)
    return plain, links2


# === NoemaForge Autodoc Function Header ===
# Function: _guess_payload_kind(sample: bytes)
# Purpose: Implement the routine ' guess payload kind'.
# Inputs:
#   - sample: bytes
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - startswith, decode, lower
# Returns / emits: str
# Key locals:
#   - s
# === End NoemaForge Autodoc Function Header ===
def _guess_payload_kind(sample: bytes) -> str:
    if not sample:
        return "missing"
    if sample.startswith(b"!<arch>\n"):
        return "ar"
    if sample.startswith(b"\x1f\x8b\x08"):
        return "gzip"
    if sample.startswith(b"PK\x03\x04"):
        return "zip"
    # crude text check
    try:
        s = sample.decode("utf-8")
        if "<rss" in s.lower() or "<feed" in s.lower():
            return "xml"
        if "<html" in s.lower() or "<!doctype html" in s.lower():
            return "html"
        return "text"
    except Exception:
        return "binary"


# === NoemaForge Autodoc Function Header ===
# Function: _ar_list_members(path: str, max_members: int = 50)
# Purpose: Implement the routine ' ar list members'.
# Inputs:
#   - path: str
#   - max_members: int = 50
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, read, seek, tell, strip, append, len, int, decode
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - f, hdr, magic, n, name, off, out, size, size_s, total
# === End NoemaForge Autodoc Function Header ===
def _ar_list_members(path: str, max_members: int = 50) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        with open(path, "rb") as f:
            magic = f.read(8)
            if magic != b"!<arch>\n":
                return out
            f.seek(0, os.SEEK_END)
            total = f.tell()
            off = 8
            n = 0
            while off + 60 <= total and n < max_members:
                f.seek(off)
                hdr = f.read(60)
                if len(hdr) < 60:
                    break
                name = hdr[0:16].decode("utf-8", "ignore").strip()
                size_s = hdr[48:58].decode("ascii", "ignore").strip()
                try:
                    size = int(size_s)
                except Exception:
                    size = 0
                out.append({"name": name, "size": size})
                off = off + 60 + size
                if off % 2 == 1:
                    off += 1
                n += 1
    except Exception:
        return out
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _tar_inventory(path: str, max_members: int = 400)
# Purpose: Implement the routine ' tar inventory'.
# Inputs:
#   - path: str
#   - max_members: int = 400
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, getmembers, min, append, len, lower, endswith, startswith, split
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - bins, inv, low, m, members, n, suspicious, tf
# === End NoemaForge Autodoc Function Header ===
def _tar_inventory(path: str, max_members: int = 400) -> Dict[str, Any]:
    inv: Dict[str, Any] = {"format": "tar", "total_members": 0, "suspicious": [], "binaries": [], "notes": []}
    try:
        with tarfile.open(path, "r:*") as tf:
            members = tf.getmembers()
            inv["total_members"] = min(len(members), max_members)
            suspicious: List[str] = []
            bins: List[str] = []
            for m in members[:max_members]:
                n = m.name
                # path traversal indicators
                if n.startswith("/") or ".." in n.split("/"):
                    suspicious.append(f"path_traversal:{n}")
                # suspicious dirs
                low = n.lower()
                if "/.git/hooks" in low or low.endswith(".git/hooks"):
                    suspicious.append(f"git_hooks:{n}")
                if low.endswith(".sh") or low.endswith(".ps1"):
                    suspicious.append(f"script:{n}")
                if low.endswith((".exe", ".dll", ".so", ".dylib")):
                    bins.append(n)
            inv["suspicious"] = suspicious[:200]
            inv["binaries"] = bins[:200]
    except Exception as e:
        inv["notes"].append(f"tar_open_failed:{e!r}")
    return inv


# === NoemaForge Autodoc Function Header ===
# Function: _zip_inventory(path: str, max_members: int = 400)
# Purpose: Implement the routine ' zip inventory'.
# Inputs:
#   - path: str
#   - max_members: int = 400
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - ZipFile, namelist, min, append, len, lower, endswith, startswith, split
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - bins, inv, low, n, names, suspicious, zf
# === End NoemaForge Autodoc Function Header ===
def _zip_inventory(path: str, max_members: int = 400) -> Dict[str, Any]:
    inv: Dict[str, Any] = {"format": "zip", "total_members": 0, "suspicious": [], "binaries": [], "notes": []}
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            inv["total_members"] = min(len(names), max_members)
            suspicious: List[str] = []
            bins: List[str] = []
            for n in names[:max_members]:
                low = n.lower()
                if n.startswith("/") or ".." in n.split("/"):
                    suspicious.append(f"path_traversal:{n}")
                if "/.git/hooks" in low or low.endswith(".git/hooks"):
                    suspicious.append(f"git_hooks:{n}")
                if low.endswith(".sh") or low.endswith(".ps1"):
                    suspicious.append(f"script:{n}")
                if low.endswith((".exe", ".dll", ".so", ".dylib")):
                    bins.append(n)
            inv["suspicious"] = suspicious[:200]
            inv["binaries"] = bins[:200]
    except Exception as e:
        inv["notes"].append(f"zip_open_failed:{e!r}")
    return inv


# === NoemaForge Autodoc Function Header ===
# Function: main()
# Purpose: Implement the routine 'main'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - bootstrap/microvm/noemaforge-microvm-run.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/brainui.py
#   - src/canary_runner.py
#   - src/doctor.py
#   - src/dream_cycle.py
# Calls:
#   - ArgumentParser, add_argument, parse_args, abspath, dirname, _load_json, _extract_payload_text, _suspicious_text_signals, _risk_score, strip, extend, join
# Returns / emits: int
# Key locals:
#   - ap, args, art_fps, base, f, file_meta, fn, idir, incident, inv, inv2, inv_path
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--incident-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--profile", default="generic")
    ap.add_argument("--languages", default="ru,en")
    args = ap.parse_args()

    idir = os.path.abspath(args.incident_dir)
    out_path = os.path.abspath(args.out)
    out_dir = os.path.dirname(out_path)
    langs = [x.strip() for x in str(args.languages).split(",") if x.strip()]

    incident = _load_json(os.path.join(idir, "incident.json"))
    file_meta = _load_json(os.path.join(idir, "file_meta.json"))
    role_ctx = _load_json(os.path.join(idir, "role_context.json"))
    webgw_meta = _load_json(os.path.join(idir, "webgw_meta.json"))

    payload_text = _extract_payload_text(incident)
    signals = _suspicious_text_signals(payload_text)

    score = _risk_score(incident, signals)

    profile = str(getattr(args, "profile", "generic") or "generic").strip()

    summary = (
        f"Quarantine incident {incident.get('incident_id')} on action={incident.get('action')} reason={incident.get('reason')}. "
        f"Detected {len(signals)} suspicious signal(s). Risk score={score}/100."
    )

    recs: List[str] = []
    if score >= 70:
        recs.append("Treat as high-risk: keep incident immutable; review in sterile glove; do not loosen policies.")
        recs.append("Search for indirect prompt injection in sources (email/web/docs).")
        recs.append("If exec was attempted, verify allowed_bins and ensure sandbox backend is available (bwrap/podman).")
    elif score >= 40:
        recs.append("Treat as medium-risk: review incident; check file_meta and request args for leakage attempts.")
        recs.append("Consider adding/adjusting security fixtures / arg_rules to catch similar patterns earlier.")
    else:
        recs.append("Low-risk quarantine: likely policy mismatch or benign denied path. Still log and trend.")

    # Add profile-specific guidance.
    recs.extend(_profile_recommendations(profile, signals))

    # Compute small fingerprints for artifacts
    art_fps: Dict[str, str] = {}
    for fn in ("incident.json", "file_meta.json", "role_context.json", "webgw_meta.json"):
        p = os.path.join(idir, fn)
        if os.path.exists(p):
            art_fps[fn] = _sha256_file(p)

    # Payload analysis (best-effort)
    payload_path = os.path.join(idir, "payload.bin")
    payload_kind = "missing"
    payload_sha = ""
    payload_sample = b""
    outputs: Dict[str, Any] = {}

    if os.path.exists(payload_path) and os.path.isfile(payload_path):
        payload_sample = _read_payload_bytes(payload_path, max_bytes=2_000_000)
        payload_kind = _guess_payload_kind(payload_sample)
        # keep this bounded
        payload_sha = _sha256_file(payload_path, max_bytes=50_000_000)

    # Profile-specific side outputs
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        pass

    prof = profile.lower()
    if prof in ("web_sanitize", "rss_sanitize", "web_readable", "article_extract") and payload_sample:
        try:
            txt = payload_sample.decode("utf-8", errors="ignore")
            links: List[str] = []

            if prof == "rss_sanitize":
                plain, links = _extract_rss_items(txt)
            elif prof in ("web_readable", "article_extract"):
                plain = _article_extract(txt)
                links = re.findall(r"https?://[^\s'\"]+", txt)[:500]
            else:
                # web_sanitize: conservative stripping only
                plain = _strip_html(txt)
                links = re.findall(r"https?://[^\s'\"]+", txt)[:500]

            plain2, pi_rep = _pi_scan_and_scrub(plain, source=f"glove:{prof}")

            sani_path = os.path.join(out_dir, "sanitized.txt")
            with open(sani_path, "w", encoding="utf-8") as f:
                f.write(plain2)

            meta_path = os.path.join(out_dir, "sanitized_meta.json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "ts": _nowz(),
                        "profile": prof,
                        "links": links[:200],
                        "bytes_in": len(payload_sample),
                        "chars_out": len(plain2),
                        "pi_firewall": {
                            "score": pi_rep.get("score"),
                            "severity": pi_rep.get("severity"),
                            "reasons": pi_rep.get("reasons"),
                            "hit_count": len(pi_rep.get("hits") or []),
                        },
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            pi_path = os.path.join(out_dir, "pi_report.json")
            with open(pi_path, "w", encoding="utf-8") as f:
                json.dump(pi_rep, f, ensure_ascii=False, indent=2)

            outputs["sanitized_text"] = os.path.basename(sani_path)
            outputs["sanitized_meta"] = os.path.basename(meta_path)
            outputs["pi_report"] = os.path.basename(pi_path)
            outputs["pi_severity"] = str(pi_rep.get("severity") or "none")
        except Exception as e:
            outputs["sanitized_error"] = repr(e)

    if profile.lower() in ("git_scan", "repo_scan") and os.path.exists(payload_path):
        inv: Dict[str, Any] = {"ts": _nowz(), "payload_kind": payload_kind, "payload_sha256": payload_sha, "webgw_meta": webgw_meta}
        if payload_kind == "gzip":
            inv["inventory"] = _tar_inventory(payload_path)
        elif payload_kind == "zip":
            inv["inventory"] = _zip_inventory(payload_path)
        else:
            inv["inventory"] = {"format": payload_kind, "notes": ["no_archive_inventory"]}
        inv_path = os.path.join(out_dir, "payload_inventory.json")
        try:
            with open(inv_path, "w", encoding="utf-8") as f:
                json.dump(inv, f, ensure_ascii=False, indent=2)
            outputs["payload_inventory"] = os.path.basename(inv_path)
        except Exception as e:
            outputs["inventory_error"] = repr(e)

    if profile.lower() in ("package_inspect", "apt_inspect") and os.path.exists(payload_path):
        inv2: Dict[str, Any] = {"ts": _nowz(), "payload_kind": payload_kind, "payload_sha256": payload_sha, "webgw_meta": webgw_meta}
        if payload_kind == "ar":
            inv2["ar_members"] = _ar_list_members(payload_path)
        else:
            inv2["notes"] = ["payload_not_ar_archive"]
        inv_path2 = os.path.join(out_dir, "payload_inventory.json")
        try:
            with open(inv_path2, "w", encoding="utf-8") as f:
                json.dump(inv2, f, ensure_ascii=False, indent=2)
            outputs["payload_inventory"] = os.path.basename(inv_path2)
        except Exception as e:
            outputs["inventory_error"] = repr(e)

    base: Dict[str, Any] = {
        "glove_version": "0.25.1",
        "ts": _nowz(),
        "amnesic": True,
        "profile": profile,
        "incident_id": incident.get("incident_id"),
        "trace_id": incident.get("trace_id"),
        "action": incident.get("action"),
        "reason": incident.get("reason"),
        "risk_score": score,
        "signals": signals,
        "summary": summary,
        "recommendations": recs,
        "artifact_fingerprints": art_fps,
        "files": (file_meta.get("files") or []),
        "role_context_present": bool(role_ctx),
        "webgw_meta_present": bool(webgw_meta),
        "payload": {
            "present": bool(payload_sample),
            "kind": payload_kind,
            "sha256": payload_sha,
            "sample_bytes": len(payload_sample),
        },
        "outputs": outputs,
    }

    passes = [_analysis_pass(lang, base) for lang in (langs or ["ru"]) ]

    report = {
        "schema_version": "v1",
        "kind": "GloveReport",
        "base": base,
        "analysis_passes": passes,
        "deltas": {
            "language_divergence": "unknown",
            "notes": [
                "In v0.10.8, divergence is not computed (template passes).",
                "Future: run SLM passes per language and compute structured diffs.",
            ],
        },
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
