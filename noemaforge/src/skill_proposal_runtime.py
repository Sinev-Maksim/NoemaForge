#!/usr/bin/env python3
"""
NoemaForge quarantine-only SKILL.md proposal parser.

This parser treats imported skill files as untrusted text. It extracts a small
proposal record for SSR/QA review, but it never registers, executes, imports, or
activates the skill.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from noemaforge_version import RUNTIME_VERSION


API_VERSION = "noemaforge.skill-proposal/v1"
PROPOSAL_KIND = "SkillProposal"
MAX_SKILL_BYTES = 65536
MAX_FRONTMATTER_LINES = 160
MAX_SECTIONS = 32
MAX_INSTRUCTION_CHARS = 32768
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _slug(text: str, *, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(text or "").strip()).strip("-._")
    if not value:
        value = fallback
    if not re.match(r"^[A-Za-z0-9]", value):
        value = f"skill-{value}"
    return value[:128]


def _as_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        raw = [value]
    items: List[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
    return items


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [part.strip().strip("\"'") for part in inner.split(",") if part.strip()]
    return text.strip("\"'")


def _parse_frontmatter_block(lines: List[str]) -> Tuple[Dict[str, Any], List[str]]:
    frontmatter: Dict[str, Any] = {}
    failures: List[str] = []
    pending_key = ""
    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        list_match = re.match(r"^\s*-\s+(.+?)\s*$", line)
        if list_match and pending_key:
            frontmatter.setdefault(pending_key, []).append(_parse_scalar(list_match.group(1)))
            continue
        if line[:1].isspace():
            failures.append("frontmatter_nested_mapping_unsupported")
            continue
        if ":" not in line:
            failures.append("frontmatter_line_invalid")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if not re.match(r"^[A-Za-z0-9_.-]{1,80}$", key):
            failures.append(f"frontmatter_key_invalid:{key}")
            pending_key = ""
            continue
        parsed = _parse_scalar(value)
        frontmatter[key] = parsed
        pending_key = key if parsed == "" else ""
        if pending_key:
            frontmatter[pending_key] = []
    return frontmatter, failures


def split_frontmatter(text: str) -> Tuple[Dict[str, Any], str, List[str]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, []
    limit = min(len(lines), MAX_FRONTMATTER_LINES + 2)
    for index in range(1, limit):
        if lines[index].strip() == "---":
            frontmatter, failures = _parse_frontmatter_block(lines[1:index])
            body = "\n".join(lines[index + 1 :])
            return frontmatter, body, failures
    return {}, text, ["frontmatter_closing_delimiter_missing"]


def extract_sections(body: str) -> Tuple[List[Dict[str, str]], List[str]]:
    sections: List[Dict[str, str]] = []
    failures: List[str] = []
    current_title = "Instructions"
    current_lines: List[str] = []
    for line in body.splitlines():
        match = HEADING_RE.match(line)
        if match:
            sections.append({"title": current_title, "body": "\n".join(current_lines).strip()})
            current_title = match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)
    sections.append({"title": current_title, "body": "\n".join(current_lines).strip()})
    sections = [section for section in sections if section["title"] or section["body"]]
    if len(sections) > MAX_SECTIONS:
        failures.append("section_count_exceeds_limit")
        sections = sections[:MAX_SECTIONS]
    return sections, failures


def build_skill_proposal_from_text(text: str, *, source_uri: str = "SKILL.md") -> Dict[str, Any]:
    failures: List[str] = []
    warnings: List[str] = []
    byte_count = len(text.encode("utf-8", errors="replace"))
    digest = _sha256_text(text)
    if byte_count > MAX_SKILL_BYTES:
        failures.append("skill_md_exceeds_size_limit")
        text = text.encode("utf-8", errors="replace")[:MAX_SKILL_BYTES].decode("utf-8", errors="replace")
    frontmatter, body, frontmatter_failures = split_frontmatter(text)
    failures.extend(frontmatter_failures)
    sections, section_failures = extract_sections(body)
    failures.extend(section_failures)
    instructions = body.strip()
    if len(instructions) > MAX_INSTRUCTION_CHARS:
        warnings.append("instructions_truncated")
        instructions = instructions[:MAX_INSTRUCTION_CHARS]

    declared_id = str(frontmatter.get("id") or frontmatter.get("name") or frontmatter.get("title") or "").strip()
    proposal_id = _slug(declared_id, fallback=f"skill-{digest[:12]}")
    if not SAFE_ID_RE.match(proposal_id):
        failures.append("proposal_id_invalid")
        proposal_id = f"skill-{digest[:12]}"

    requested_tools = _as_string_list(
        frontmatter.get("requested_tools")
        if "requested_tools" in frontmatter
        else frontmatter.get("tools")
    )
    requested_permissions = _as_string_list(
        frontmatter.get("requested_permissions")
        if "requested_permissions" in frontmatter
        else frontmatter.get("permissions")
    )
    if not requested_tools:
        warnings.append("requested_tools_empty")
    if not requested_permissions:
        warnings.append("requested_permissions_empty")

    return {
        "apiVersion": API_VERSION,
        "kind": PROPOSAL_KIND,
        "version": RUNTIME_VERSION,
        "created_at": _nowz(),
        "ok": not failures,
        "proposal_id": proposal_id,
        "import_mode": "quarantine_only",
        "activation_state": "quarantined",
        "decision": "quarantined",
        "ssr_status": "pending",
        "qa_status": "pending",
        "failures": failures,
        "warnings": warnings,
        "source": {
            "uri": str(source_uri or "SKILL.md"),
            "sha256": digest,
            "bytes": byte_count,
        },
        "parsed_skill": {
            "id": declared_id,
            "title": str(frontmatter.get("title") or frontmatter.get("name") or proposal_id).strip(),
            "description": str(frontmatter.get("description") or "").strip(),
            "frontmatter": frontmatter,
            "instructions": instructions,
            "sections": sections,
        },
        "requested_tools": requested_tools,
        "requested_permissions": requested_permissions,
        "safety": {
            "no_code_execution": True,
            "no_active_registration": True,
            "requires_ssr_review": True,
            "requires_qa_review": True,
            "requires_epoch_before_activation": True,
        },
    }


def build_skill_proposal_from_path(path: Path | str) -> Dict[str, Any]:
    skill_path = Path(path)
    text = skill_path.read_text(encoding="utf-8-sig")
    return build_skill_proposal_from_text(text, source_uri=str(skill_path))


def write_quarantine_proposal(proposal: Dict[str, Any], quarantine_root: Path | str) -> Path:
    root = Path(quarantine_root)
    proposal_id = _slug(str(proposal.get("proposal_id") or ""), fallback="skill-proposal")
    digest = str(proposal.get("source", {}).get("sha256") or "unknown")[:12]
    out_dir = root / "skill_proposals"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{proposal_id}__{digest}.json"
    out_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse an untrusted SKILL.md into a quarantine-only SkillProposal.")
    parser.add_argument("skill_md", help="Path to an untrusted SKILL.md file")
    parser.add_argument("--quarantine-root", help="Directory where the proposal JSON should be written")
    args = parser.parse_args(argv)
    proposal = build_skill_proposal_from_path(args.skill_md)
    if args.quarantine_root:
        proposal["artifact_path"] = str(write_quarantine_proposal(proposal, args.quarantine_root))
    print(json.dumps(proposal, ensure_ascii=False, sort_keys=True))
    return 0 if proposal.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
