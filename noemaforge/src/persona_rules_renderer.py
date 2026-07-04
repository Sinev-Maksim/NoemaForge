#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/persona_rules_renderer.py
Zone: gui/control-plane
Version: 0.33.0
Created: 2026-07-04
Purpose: Translate structured Persona Rules JSON into operator-readable text and
  schema-safe visual descriptors while preserving raw JSON for audit/debug views.
Inputs: Persona Rules dictionaries from admin_gui_server.persona_rules().
Outputs: Rendered text sections, visual descriptor records and ignored hint names.
Side effects: None.
Tests: python3 -m unittest noemaforge/tests/test_persona_rules_renderer.py -v.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


SUPPORTED_RENDER_HINTS = {"Gauge", "Graph", "Table", "Timeline", "StatusCard"}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _label(key: str) -> str:
    return str(key or "").replace("_", " ").strip().capitalize()


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _bullet_lines(values: Iterable[Any]) -> List[str]:
    lines: List[str] = []
    for value in values:
        if isinstance(value, dict):
            parts = [f"{_label(k)}: {_string(v)}" for k, v in value.items() if k != "raw_persona"]
            if parts:
                lines.append("- " + "; ".join(parts))
        else:
            text = _string(value).strip()
            if text:
                lines.append("- " + text)
    return lines


def _hint_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    hints = payload.get("render_hints")
    if hints is None:
        hints = payload.get("visual_hints")
    records: List[Dict[str, Any]] = []
    for item in _as_list(hints):
        if isinstance(item, str):
            records.append({"type": item})
        elif isinstance(item, dict):
            hint_type = item.get("type") or item.get("kind") or item.get("hint")
            record = dict(item)
            record["type"] = str(hint_type or "")
            records.append(record)
    return records


def _visual_descriptor(record: Dict[str, Any]) -> Dict[str, Any]:
    hint_type = str(record.get("type") or "")
    descriptor = {
        "type": hint_type,
        "title": str(record.get("title") or hint_type),
        "source": str(record.get("source") or "persona_rules"),
    }
    for key in ["value", "max", "unit", "rows", "columns", "points", "events", "status", "label"]:
        if key in record:
            descriptor[key] = record[key]
    return descriptor


def render_persona_rules(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a readable view and optional visual descriptors for Persona Rules."""
    rules = dict(payload or {})
    sections: List[Dict[str, Any]] = []

    overview_rows = [
        ("Persona", rules.get("current_persona")),
        ("Role", rules.get("role")),
        ("Codename", rules.get("codename")),
        ("Description", rules.get("description")),
    ]
    overview = [f"{label}: {_string(value)}" for label, value in overview_rows if _string(value).strip()]
    if overview:
        sections.append({"title": "Persona", "lines": overview})

    for key, title in [
        ("allowed_actions", "Allowed actions"),
        ("output_rules", "Output rules"),
        ("command_routing_rules", "Command routing"),
    ]:
        lines = _bullet_lines(_as_list(rules.get(key)))
        if lines:
            sections.append({"title": title, "lines": lines})

    model_behavior = rules.get("model_behavior") if isinstance(rules.get("model_behavior"), dict) else {}
    if model_behavior:
        sections.append({
            "title": "Model behavior",
            "lines": [f"{_label(key)}: {_string(value)}" for key, value in model_behavior.items()],
        })

    visuals: List[Dict[str, Any]] = []
    ignored: List[str] = []
    for hint in _hint_records(rules):
        hint_type = str(hint.get("type") or "")
        if hint_type in SUPPORTED_RENDER_HINTS:
            visuals.append(_visual_descriptor(hint))
        elif hint_type:
            ignored.append(hint_type)

    if not sections:
        sections.append({"title": "Persona rules", "lines": ["No readable persona rules are available."]})

    text_parts: List[str] = []
    for section in sections:
        text_parts.append(str(section["title"]))
        text_parts.extend(str(line) for line in section.get("lines", []))
        text_parts.append("")

    return {
        "format": "noemaforge.persona-rules.rendered/v1",
        "text": "\n".join(text_parts).strip(),
        "sections": sections,
        "visuals": visuals,
        "ignored_render_hints": ignored,
        "raw_json_available": True,
    }
