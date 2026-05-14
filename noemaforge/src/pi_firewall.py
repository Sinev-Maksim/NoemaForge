#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/pi_firewall.py
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
# File: src/pi_firewall.py
# Purpose: Detect and scrub prompt-injection style content before promotion into trusted flows.
# Invoked by / imported from:
#   - src/glove_agent.py
#   - tools/prep/scan_tabs.py
#   - tools/prep/scan_tg.py
# Public API / entry functions:
#   - class Hit
#   - scan_text
#   - redact_instruction_like_lines
#   - scan_and_scrub
#   - is_clean
# Inputs:
#   - Imports: __future__, re, dataclasses, typing
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""pi_firewall.py (v0.25.1)

Prompt-Injection Firewall (deterministic).

Goal
----
When ingesting *untrusted* external content (web pages, RSS items, emails,
Telegram exports, etc.) we must assume the content may contain instructions
crafted to subvert an agent.

This module provides a **deterministic** scanner + scrubber that:
  - detects likely instruction / tool-exfil patterns
  - can redact suspicious lines/spans
  - emits an explanation suitable for audit/quarantine

Important
---------
This is not a perfect classifier. It is intentionally conservative:
"false positive" means "requires review".

The primary safety objective is:
  - Do not let untrusted content become *instructions*.
  - Prefer dropping/redacting instruction-like text.

New in v0.25.1
---------------
- Adds a small "windowed" scan that can catch instructions split across
  adjacent lines (common in indirect prompt injection).
- Report now includes:
    - bad_lines: explicit set of 1-based line numbers that should be redacted
    - window_hits: matches that were found only in cross-line windows
- Adds scan_and_scrub(): pre-scan -> redact -> post-scan.

Design notes
------------
- We keep *line mapping* as the primary mechanism to support safe redaction.
- Window scanning marks whole involved lines as suspicious, but avoids
  verbatim quoting by redacting rather than copying.
"""


import re
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Hit:
    kind: str
    line_no: int
    span: Tuple[int, int]
    evidence: str
    weight: int


_RE_LIST: List[Tuple[str, re.Pattern, int]] = []


# === NoemaForge Autodoc Function Header ===
# Function: _rx(kind: str, pat: str, weight: int)
# Purpose: Implement the routine ' rx'.
# Inputs:
#   - kind: str
#   - pat: str
#   - weight: int
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - append, compile, int
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# === End NoemaForge Autodoc Function Header ===
def _rx(kind: str, pat: str, weight: int) -> None:
    # NOTE: we intentionally avoid DOTALL for line-level scanning.
    _RE_LIST.append((kind, re.compile(pat, re.IGNORECASE | re.MULTILINE), int(weight)))


# Core instruction override patterns
_rx(
    "override_instructions",
    r"\b(ignore|disregard|forget)\b.{0,80}\b(previous|prior|above)\b.{0,40}\b(instruction|message|prompt|rules)\b",
    10,
)
_rx("system_prompt", r"\b(system|developer)\s*(prompt|message)\b", 8)
_rx("role_play", r"\byou\s+are\s+(chatgpt|an\s+assistant|a\s+model)\b", 5)
_rx("do_not_reveal", r"\b(do\s+not|don't)\b.{0,40}\b(reveal|disclose|tell|mention|share)\b", 6)
_rx("jailbreak", r"\b(jailbreak|prompt\s*inject|prompt\s*injection)\b", 4)

# Tool / execution / data exfil patterns
_rx("tool_call", r"\b(tool\s*call|function\s*call|call\s+the\s+tool)\b", 8)
_rx("exec_cmd", r"\b(run|execute)\b.{0,40}\b(command|shell|bash|powershell|cmd\.exe)\b", 8)
_rx(
    "exfiltrate",
    r"\b(exfiltrat|leak|steal|send|post|upload)\w*\b.{0,80}\b(token|key|secret|password|cookie|oauth|session)\b",
    10,
)
_rx("write_persist", r"\b(save|store|persist|write|append)\b.{0,60}\b(memory|database|disk|file|vault|registry|rules|policy)\b", 7)

# Common delimiter tricks
_rx("prompt_block", r"\b(begin|end)\b.{0,20}\b(system|developer|assistant)\b.{0,20}\b(prompt|message)\b", 7)
_rx("yaml_role", r"^(system|developer|assistant)\s*:\s*", 6)

# Base64-ish blobs (often used to smuggle instructions)
_rx("base64_blob", r"\b[A-Za-z0-9+/]{80,}={0,2}\b", 3)


# === NoemaForge Autodoc Function Header ===
# Function: _short(s: str, n: int = 140)
# Purpose: Implement the routine ' short'.
# Inputs:
#   - s: str
#   - n: int = 140
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, len, max
# Returns / emits: str
# Key locals:
#   - s2
# === End NoemaForge Autodoc Function Header ===
def _short(s: str, n: int = 140) -> str:
    s2 = (s or "").strip()
    if len(s2) <= n:
        return s2
    return s2[: max(0, n - 3)] + "..."


# === NoemaForge Autodoc Function Header ===
# Function: scan_text(text: str, source: str = '', max_hits: int = 200, window_lines: int = 3)
# Purpose: Scan text and return a structured risk report.
# Inputs:
#   - text: str
#   - source: str = ''
#   - max_hits: int = 200
#   - window_lines: int = 3
# Called by:
#   - tools/prep/scan_tabs.py
#   - tools/prep/scan_tg.py
# Calls:
#   - enumerate, splitlines, max, range, sum, str, int, sorted, strip, search, span, _short
# Returns / emits: Dict
# Key locals:
#   - already, bad_lines, ev, h, hits, k, kinds_by_line, line_range, lines, ln_no, m, norm
# === End NoemaForge Autodoc Function Header ===
def scan_text(
    text: str,
    *,
    source: str = "",
    max_hits: int = 200,
    window_lines: int = 3,
) -> Dict:
    """Scan text and return a structured risk report.

    - The primary scan is line-based.
    - A secondary "window" scan can catch cross-line injections.

    `bad_lines` is the authoritative set of lines to redact.
    """

    t = text or ""
    hits: List[Hit] = []

    lines = t.splitlines() or [t]

    # 1) Line-based scanning
    for i, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        for kind, rx, w in _RE_LIST:
            m = rx.search(line)
            if not m:
                continue
            s, e = m.span()
            ev = _short(line[s:e], 120)
            hits.append(Hit(kind=kind, line_no=i, span=(s, e), evidence=ev, weight=w))
            if len(hits) >= max_hits:
                break
        if len(hits) >= max_hits:
            break

    bad_lines = {h.line_no for h in hits if h.line_no > 0}

    # 2) Windowed scanning (detect instructions split across adjacent lines)
    window_hits: List[Dict[str, object]] = []
    if int(window_lines) >= 2 and len(lines) >= 2 and len(hits) < max_hits:
        wN = max(2, min(int(window_lines), 6))

        # Pre-index: kinds already found per line.
        kinds_by_line: Dict[int, set] = {}
        for h in hits:
            kinds_by_line.setdefault(h.line_no, set()).add(h.kind)

        for start in range(0, len(lines)):
            win = lines[start : start + wN]
            if len(win) < 2:
                break
            norm = " ".join([ln.strip() for ln in win if ln.strip()])
            if not norm:
                continue
            if len(norm) > 10_000:
                norm = norm[:10_000]

            line_range = range(start + 1, start + 1 + len(win))

            for kind, rx, w in _RE_LIST:
                # Some patterns are explicitly line-anchored; window scan is not meaningful.
                if kind in ("yaml_role", "base64_blob"):
                    continue

                # If any line already had this kind, skip (avoid double counting).
                already = False
                for ln_no in line_range:
                    if kind in (kinds_by_line.get(ln_no) or set()):
                        already = True
                        break
                if already:
                    continue

                m = rx.search(norm)
                if not m:
                    continue

                ev = _short(norm[m.start() : m.end()], 120)
                window_hits.append(
                    {
                        "kind": kind,
                        "start_line": start + 1,
                        "end_line": start + len(win),
                        "evidence": ev,
                        "weight": int(w),
                    }
                )
                for ln_no in line_range:
                    bad_lines.add(int(ln_no))

                if len(hits) + len(window_hits) >= max_hits:
                    break

            if len(hits) + len(window_hits) >= max_hits:
                break

    # Score / severity
    score = sum(h.weight for h in hits) + sum(int(x.get("weight") or 0) for x in window_hits)
    severity = "none"
    if score >= 20:
        severity = "high"
    elif score >= 10:
        severity = "medium"
    elif score >= 4:
        severity = "low"

    reasons: Dict[str, int] = {}
    for h in hits:
        reasons[h.kind] = reasons.get(h.kind, 0) + 1
    for wh in window_hits:
        k = str(wh.get("kind") or "")
        if k:
            reasons[k] = reasons.get(k, 0) + 1

    return {
        "source": source,
        "score": int(score),
        "severity": severity,
        "bad_lines": sorted(int(x) for x in bad_lines if int(x) > 0),
        "hits": [
            {
                "kind": h.kind,
                "line_no": h.line_no,
                "span": [h.span[0], h.span[1]],
                "evidence": h.evidence,
                "weight": h.weight,
            }
            for h in hits
        ],
        "window_hits": window_hits,
        "reasons": reasons,
    }


# === NoemaForge Autodoc Function Header ===
# Function: redact_instruction_like_lines(text: str, report: Dict)
# Purpose: Redact entire lines that contain suspicious patterns.
# Inputs:
#   - text: str
#   - report: Dict
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, get, enumerate, join, splitlines, append, int
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - bad_lines, out_lines, t
# === End NoemaForge Autodoc Function Header ===
def redact_instruction_like_lines(text: str, report: Dict) -> str:
    """Redact entire lines that contain suspicious patterns.

    This avoids *verbatim quoting* of injection payloads.

    NOTE: Prefer using report['bad_lines'] if present (v0.25.1+).
    """

    t = text or ""
    if not report:
        return t

    bad_lines: set = set()
    if report.get("bad_lines"):
        try:
            bad_lines = {int(x) for x in (report.get("bad_lines") or []) if int(x) > 0}
        except Exception:
            bad_lines = set()
    if not bad_lines and report.get("hits"):
        try:
            bad_lines = {int(h.get("line_no") or 0) for h in (report.get("hits") or []) if int(h.get("line_no") or 0) > 0}
        except Exception:
            bad_lines = set()

    if not bad_lines:
        return t

    out_lines: List[str] = []
    for i, line in enumerate(t.splitlines(), start=1):
        if i in bad_lines:
            out_lines.append("[REDACTED: potential prompt injection]")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


# === NoemaForge Autodoc Function Header ===
# Function: scan_and_scrub(text: str, source: str = '')
# Purpose: Convenience helper: scan -> redact -> scan again.
# Inputs:
#   - text: str
#   - source: str = ''
# Called by:
#   - tools/prep/scan_tg.py
# Calls:
#   - scan_text, redact_instruction_like_lines
# Returns / emits: Dict[str, object]
# Key locals:
#   - post, pre, scrubbed
# === End NoemaForge Autodoc Function Header ===
def scan_and_scrub(text: str, *, source: str = "") -> Dict[str, object]:
    """Convenience helper: scan -> redact -> scan again."""

    pre = scan_text(text or "", source=source)
    scrubbed = redact_instruction_like_lines(text or "", pre)
    post = scan_text(scrubbed or "", source=(source + ":post") if source else "post")
    return {"scrubbed_text": scrubbed, "pre": pre, "post": post}


# === NoemaForge Autodoc Function Header ===
# Function: is_clean(report: Dict, max_severity: str = 'low')
# Purpose: Return True if report severity <= max_severity.
# Inputs:
#   - report: Dict
#   - max_severity: str = 'low'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, get, strip, str
# Returns / emits: bool
# Key locals:
#   - order, sev
# === End NoemaForge Autodoc Function Header ===
def is_clean(report: Dict, *, max_severity: str = "low") -> bool:
    """Return True if report severity <= max_severity."""

    order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    sev = str((report or {}).get("severity") or "none").strip().lower()
    return order.get(sev, 3) <= order.get(max_severity, 1)
