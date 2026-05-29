#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/i18n_runtime.py
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

Existing module notes:
Small NoemaForge i18n helper for user-facing GUI/CLI strings.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

SUPPORTED_LOCALES = ["en", "ru", "uk", "es", "de", "pt", "it", "zh-CN", "ja", "ko"]
ALIASES = {
    "pt-PT": "pt", "pt_PT": "pt", "pt-BR": "pt", "pt_BR": "pt",
    "zh": "zh-CN", "zh_CN": "zh-CN", "zh-Hans": "zh-CN", "zh_Hans": "zh-CN",
    "ua": "uk", "uk-UA": "uk", "uk_UA": "uk",
    "ru-RU": "ru", "ru_RU": "ru", "en-US": "en", "en_US": "en", "en-GB": "en", "en_GB": "en",
    "es-ES": "es", "es_ES": "es", "de-DE": "de", "de_DE": "de", "it-IT": "it", "it_IT": "it",
    "ja-JP": "ja", "ja_JP": "ja", "ko-KR": "ko", "ko_KR": "ko",
}


def normalize_locale(value: str | None = None) -> str:
    raw = value or os.environ.get("NOEMAFORGE_LANG") or os.environ.get("LC_ALL") or os.environ.get("LANG") or "en"
    raw = str(raw).split(".", 1)[0].strip() or "en"
    raw = ALIASES.get(raw, raw)
    if raw in SUPPORTED_LOCALES:
        return raw
    base = raw.split("-", 1)[0].split("_", 1)[0]
    return ALIASES.get(base, base if base in SUPPORTED_LOCALES else "en")


def load_messages(root: Path, locale: str | None = None) -> Dict[str, str]:
    loc = normalize_locale(locale)
    base = root / "configs" / "locales"
    messages: Dict[str, str] = {}
    for name in ["en", loc]:
        path = base / f"{name}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                messages.update({str(k): str(v) for k, v in data.items()})
        except Exception:
            continue
    return messages


def tr(root: Path, key: str, default: str = "", locale: str | None = None, **kwargs: Any) -> str:
    msg = load_messages(root, locale).get(key, default or key)
    try:
        return msg.format(**kwargs)
    except Exception:
        return msg
