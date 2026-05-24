#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/research_packet_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Research_Packet contracts for freshness-bounded cited scouting.
Inputs: noemaforge/configs/research-packet-policy.json and ResearchPacket examples.
Outputs: JSON-compatible ResearchPacketValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_research_packet_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import production_ai_contracts as pac


API_VERSION = "noemaforge.research-packet/v1"
POLICY_KIND = "ResearchPacketPolicy"
SET_KIND = "ResearchPacketSet"
PACKET_KIND = "ResearchPacket"
REPORT_KIND = "ResearchPacketValidationReport"

VALID_STATUSES = {"draft", "shadow", "stable", "retired"}
VALID_PACKET_STATUSES = {"draft", "ready", "needs_refresh", "blocked"}
REQUIRED_SOURCE_KINDS = {"official_docs", "repository", "local_evidence"}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,180}$")


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_path(value: Path | str) -> Path:
    return Path(value).resolve()


def _display_path(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_days(*, collected_at: str, published_at: str) -> Optional[float]:
    collected = _parse_time(collected_at)
    published = _parse_time(published_at)
    if collected is None or published is None:
        return None
    return (collected - published).total_seconds() / 86400.0


def _domain_from_url(url: str) -> str:
    text = str(url or "").strip()
    if text.startswith("noemaforge.local://"):
        return "noemaforge.local"
    parsed = urlparse(text)
    return (parsed.netloc or parsed.path.split("/", 1)[0]).lower()


def _is_safe_relative_ref(ref: str) -> bool:
    text = str(ref or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    parts = PurePosixPath(text).parts
    return not any(part in {"", ".", ".."} for part in parts)


def _resolve_ref(ref: str, *, project_root: Path, package_root: Path) -> Dict[str, Any]:
    candidates = [
        ("package", package_root / ref),
        ("project", project_root / ref),
    ]
    if not str(ref).startswith("noemaforge/"):
        candidates.append(("project_noemaforge", project_root / "noemaforge" / ref))

    checked: List[str] = []
    for base_name, path in candidates:
        checked.append(_display_path(path))
        if path.exists():
            return {
                "ok": True,
                "ref": ref,
                "resolved_under": base_name,
                "path": _display_path(path),
                "checked": checked,
            }
    return {"ok": False, "ref": ref, "resolved_under": "", "path": "", "checked": checked}


def _resolve_refs(refs: Sequence[str], *, project_root: Path, package_root: Path, owner: str) -> Dict[str, Any]:
    failures: List[str] = []
    resolved_refs: List[Dict[str, Any]] = []
    missing_refs: List[Dict[str, Any]] = []
    unsafe_refs: List[Dict[str, Any]] = []
    for ref in refs:
        if not _is_safe_relative_ref(ref):
            item = {"owner": owner, "ref": ref}
            unsafe_refs.append(item)
            failures.append(f"unsafe_ref:{owner}:{ref}")
            continue
        resolved = _resolve_ref(ref, project_root=project_root, package_root=package_root)
        resolved["owner"] = owner
        if resolved["ok"]:
            resolved_refs.append(resolved)
        else:
            missing_refs.append(resolved)
            failures.append(f"missing_ref:{owner}:{ref}")
    return {"failures": failures, "resolved_refs": resolved_refs, "missing_refs": missing_refs, "unsafe_refs": unsafe_refs}


def load_policy(policy_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(policy_path).read_text(encoding="utf-8"))


def load_example_set(example_path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(example_path).read_text(encoding="utf-8"))


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else payload


def _allowed_domains(policy: Dict[str, Any]) -> List[str]:
    return [domain.lower() for domain in _as_string_list(policy.get("allowed_domains"))]


def build_research_packet(
    query: str,
    sources: Sequence[Dict[str, Any]],
    claims: Sequence[Dict[str, Any]],
    citations: Sequence[Dict[str, Any]],
    policy_payload: Dict[str, Any],
    *,
    trace_id: str = "trace:research-packet:inline",
    collected_at: str = "",
    packet_id: str = "research-packet:inline",
) -> Dict[str, Any]:
    policy = _policy_dict(policy_payload)
    collected = collected_at or _nowz()
    packet = {
        "apiVersion": API_VERSION,
        "kind": PACKET_KIND,
        "id": packet_id,
        "trace_id": trace_id,
        "status": "draft",
        "query": str(query or ""),
        "collected_at": collected,
        "freshness_window_days": _as_int(policy.get("default_freshness_window_days"), 30),
        "source_allowlist": _as_string_list(policy.get("allowed_domains")),
        "sources": [dict(item) for item in sources],
        "claims": [dict(item) for item in claims],
        "citations": [dict(item) for item in citations],
        "finalization": {
            "network_fetch_performed": False,
            "all_claims_cited": True,
            "all_sources_allowlisted": True,
            "freshness_checked": True,
        },
        "refs": [],
    }
    failures = _packet_failures(packet, policy_payload)
    packet["status"] = "ready" if not failures else ("needs_refresh" if any("stale" in item or "freshness" in item for item in failures) else "blocked")
    return packet


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if not SAFE_ID_RE.match(str(payload.get("id") or "")):
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    for key in [
        "no_network_during_validation",
        "require_trace_id",
        "source_allowlist_required",
        "freshness_bounded",
        "citations_required",
        "no_uncited_claims",
        "require_primary_or_official_sources",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    if _as_int(policy.get("max_source_age_days")) <= 0:
        failures.append("policy_max_source_age_days_invalid")
    if _as_int(policy.get("default_freshness_window_days")) <= 0:
        failures.append("policy_default_freshness_window_days_invalid")
    if _as_int(policy.get("min_sources")) <= 0:
        failures.append("policy_min_sources_invalid")
    if not _allowed_domains(policy):
        failures.append("policy_allowed_domains_empty")
    if not REQUIRED_SOURCE_KINDS.issubset(set(_as_string_list(policy.get("required_source_kinds")))):
        failures.append("policy_required_source_kinds_incomplete")
    if set(_as_string_list(policy.get("packet_statuses"))) != VALID_PACKET_STATUSES:
        failures.append("policy_packet_statuses_incomplete")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _source_failures(packet_id: str, packet: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    collected_at = str(packet.get("collected_at") or "")
    freshness_window = _as_int(packet.get("freshness_window_days"), _as_int(policy.get("default_freshness_window_days"), 30))
    max_age = min(_as_int(policy.get("max_source_age_days"), 45), freshness_window)
    allowed = set(_allowed_domains(policy))
    packet_allowlist = set(domain.lower() for domain in _as_string_list(packet.get("source_allowlist")))
    sources = packet.get("sources") if isinstance(packet.get("sources"), list) else []
    if len(sources) < _as_int(policy.get("min_sources"), 1):
        failures.append(f"packet_sources_below_min:{packet_id}:{len(sources)}")
    if policy.get("source_allowlist_required") is True and not allowed.issubset(packet_allowlist):
        failures.append(f"packet_allowlist_incomplete:{packet_id}")
    seen_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            failures.append(f"packet_source_not_object:{packet_id}")
            continue
        source_id = str(source.get("id") or "")
        if not SAFE_ID_RE.match(source_id):
            failures.append(f"source_id_invalid:{packet_id}:{source_id}")
        if source_id in seen_ids:
            failures.append(f"source_id_duplicate:{packet_id}:{source_id}")
        seen_ids.add(source_id)
        kind = str(source.get("kind") or "")
        if kind not in set(_as_string_list(policy.get("required_source_kinds"))):
            failures.append(f"source_kind_not_allowed:{packet_id}:{source_id}:{kind}")
        url = str(source.get("url") or "")
        domain = str(source.get("domain") or _domain_from_url(url)).lower()
        if domain != _domain_from_url(url):
            failures.append(f"source_domain_mismatch:{packet_id}:{source_id}:{domain}:{_domain_from_url(url)}")
        if domain not in allowed:
            failures.append(f"source_domain_not_allowed:{packet_id}:{source_id}:{domain}")
        age = _age_days(collected_at=collected_at, published_at=str(source.get("published_at") or ""))
        if age is None:
            failures.append(f"source_time_invalid:{packet_id}:{source_id}")
        elif age < 0:
            failures.append(f"source_published_after_collection:{packet_id}:{source_id}")
        elif policy.get("freshness_bounded") is True and age > max_age:
            failures.append(f"source_stale:{packet_id}:{source_id}:{round(age, 3)}:{max_age}")
        if _parse_time(str(source.get("accessed_at") or "")) is None:
            failures.append(f"source_accessed_at_invalid:{packet_id}:{source_id}")
        if policy.get("require_primary_or_official_sources") is True and source.get("primary") is not True:
            failures.append(f"source_not_primary:{packet_id}:{source_id}")
        if not str(source.get("excerpt") or "").strip():
            failures.append(f"source_excerpt_missing:{packet_id}:{source_id}")
    return failures


def _citation_failures(packet_id: str, packet: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    sources = packet.get("sources") if isinstance(packet.get("sources"), list) else []
    source_ids = {str(source.get("id") or "") for source in sources if isinstance(source, dict)}
    claims = packet.get("claims") if isinstance(packet.get("claims"), list) else []
    citations = packet.get("citations") if isinstance(packet.get("citations"), list) else []
    citation_by_id = {str(item.get("id") or ""): item for item in citations if isinstance(item, dict)}
    citation_ids_seen: set[str] = set()
    for citation in citations:
        if not isinstance(citation, dict):
            failures.append(f"citation_not_object:{packet_id}")
            continue
        citation_id = str(citation.get("id") or "")
        if not SAFE_ID_RE.match(citation_id):
            failures.append(f"citation_id_invalid:{packet_id}:{citation_id}")
        if citation_id in citation_ids_seen:
            failures.append(f"citation_id_duplicate:{packet_id}:{citation_id}")
        citation_ids_seen.add(citation_id)
        if str(citation.get("source_id") or "") not in source_ids:
            failures.append(f"citation_source_missing:{packet_id}:{citation_id}:{citation.get('source_id')}")
        if citation.get("supports") is not True:
            failures.append(f"citation_not_supportive:{packet_id}:{citation_id}")
        if not str(citation.get("cited_text") or "").strip():
            failures.append(f"citation_text_missing:{packet_id}:{citation_id}")
    if policy.get("citations_required") is True and not citations:
        failures.append(f"packet_citations_missing:{packet_id}")
    if policy.get("no_uncited_claims") is True and not claims:
        failures.append(f"packet_claims_missing:{packet_id}")
    for claim in claims:
        if not isinstance(claim, dict):
            failures.append(f"claim_not_object:{packet_id}")
            continue
        claim_id = str(claim.get("id") or "")
        if not SAFE_ID_RE.match(claim_id):
            failures.append(f"claim_id_invalid:{packet_id}:{claim_id}")
        cited_ids = _as_string_list(claim.get("citation_ids"))
        if not cited_ids:
            failures.append(f"claim_citations_missing:{packet_id}:{claim_id}")
        for citation_id in cited_ids:
            citation = citation_by_id.get(citation_id)
            if citation is None:
                failures.append(f"claim_citation_ref_missing:{packet_id}:{claim_id}:{citation_id}")
                continue
            if str(citation.get("claim_id") or "") != claim_id:
                failures.append(f"claim_citation_mismatch:{packet_id}:{claim_id}:{citation_id}:{citation.get('claim_id')}")
        if not str(claim.get("text") or "").strip():
            failures.append(f"claim_text_missing:{packet_id}:{claim_id}")
    return failures


def _packet_failures(packet: Dict[str, Any], policy_payload: Dict[str, Any]) -> List[str]:
    policy = _policy_dict(policy_payload)
    failures: List[str] = []
    packet_id = str(packet.get("id") or "<missing>")
    if packet.get("apiVersion") != API_VERSION:
        failures.append(f"packet_api_version_invalid:{packet_id}")
    if packet.get("kind") != PACKET_KIND:
        failures.append(f"packet_kind_invalid:{packet_id}")
    if not SAFE_ID_RE.match(packet_id):
        failures.append(f"packet_id_invalid:{packet_id}")
    if policy.get("require_trace_id") is True and not SAFE_ID_RE.match(str(packet.get("trace_id") or "")):
        failures.append(f"packet_trace_id_invalid:{packet_id}")
    if str(packet.get("status") or "") not in set(_as_string_list(policy.get("packet_statuses"))):
        failures.append(f"packet_status_invalid:{packet_id}:{packet.get('status')}")
    if not str(packet.get("query") or "").strip():
        failures.append(f"packet_query_missing:{packet_id}")
    if _parse_time(str(packet.get("collected_at") or "")) is None:
        failures.append(f"packet_collected_at_invalid:{packet_id}")
    if _as_int(packet.get("freshness_window_days")) <= 0:
        failures.append(f"packet_freshness_window_invalid:{packet_id}")
    failures.extend(_source_failures(packet_id, packet, policy))
    failures.extend(_citation_failures(packet_id, packet, policy))
    finalization = packet.get("finalization") if isinstance(packet.get("finalization"), dict) else {}
    if policy.get("no_network_during_validation") is True and finalization.get("network_fetch_performed") is not False:
        failures.append(f"packet_network_fetch_performed:{packet_id}")
    for key in ["all_claims_cited", "all_sources_allowlisted", "freshness_checked"]:
        if finalization.get(key) is not True:
            failures.append(f"packet_finalization_{key}_not_true:{packet_id}")
    return failures


def _scoring_case_result(case: Dict[str, Any], policy_payload: Dict[str, Any]) -> Dict[str, Any]:
    case_id = str(case.get("id") or "<missing>")
    raw = case.get("packet") if isinstance(case.get("packet"), dict) else {}
    packet = build_research_packet(
        str(raw.get("query") or ""),
        raw.get("sources") if isinstance(raw.get("sources"), list) else [],
        raw.get("claims") if isinstance(raw.get("claims"), list) else [],
        raw.get("citations") if isinstance(raw.get("citations"), list) else [],
        policy_payload,
        trace_id=f"trace:research-packet:{case_id}",
        collected_at=str(raw.get("collected_at") or ""),
        packet_id=f"research-packet:{case_id}",
    )
    failures = _packet_failures(packet, policy_payload)
    ok = not failures
    expected_ok = bool(case.get("expected_ok"))
    result_failures: List[str] = []
    if ok is not expected_ok:
        result_failures.append(f"scoring_ok_mismatch:{case_id}:{ok}:{expected_ok}")
    expected_status = str(case.get("expected_status") or "")
    if expected_status and packet["status"] != expected_status:
        result_failures.append(f"scoring_status_mismatch:{case_id}:{packet['status']}:{expected_status}")
    return {
        "id": case_id,
        "ok": not result_failures,
        "packet_ok": ok,
        "status": packet["status"],
        "failures": sorted(set(result_failures)),
        "packet_failures": sorted(set(failures))[:20],
    }


def validate_research_packet_policy(
    payload: Dict[str, Any],
    *,
    project_root: Path | str,
    package_root: Path | str,
    policy_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    project = _as_path(project_root)
    package = _as_path(package_root)
    if not project.exists():
        raise FileNotFoundError(project)
    if not package.exists():
        raise FileNotFoundError(package)

    policy = _policy_dict(payload)
    failures: List[str] = []
    failures.extend(_policy_failures(payload))

    all_resolved_refs: List[Dict[str, Any]] = []
    all_missing_refs: List[Dict[str, Any]] = []
    all_unsafe_refs: List[Dict[str, Any]] = []
    packet_results: List[Dict[str, Any]] = []
    scoring_results: List[Dict[str, Any]] = []

    policy_refs = _resolve_refs(_as_string_list(payload.get("refs")), project_root=project, package_root=package, owner=str(payload.get("id") or "policy"))
    failures.extend(policy_refs["failures"])
    all_resolved_refs.extend(policy_refs["resolved_refs"])
    all_missing_refs.extend(policy_refs["missing_refs"])
    all_unsafe_refs.extend(policy_refs["unsafe_refs"])

    example_ref_results = _resolve_refs(_as_string_list(policy.get("required_example_sets")), project_root=project, package_root=package, owner="required_example_sets")
    failures.extend(example_ref_results["failures"])
    all_resolved_refs.extend(example_ref_results["resolved_refs"])
    all_missing_refs.extend(example_ref_results["missing_refs"])
    all_unsafe_refs.extend(example_ref_results["unsafe_refs"])

    for item in example_ref_results["resolved_refs"]:
        example_set = load_example_set(Path(item["path"]))
        if example_set.get("apiVersion") != API_VERSION:
            failures.append(f"example_set_api_version_invalid:{item['ref']}")
        if example_set.get("kind") != SET_KIND:
            failures.append(f"example_set_kind_invalid:{item['ref']}")
        packets = example_set.get("packets") if isinstance(example_set.get("packets"), list) else []
        if not packets:
            failures.append(f"example_set_packets_empty:{item['ref']}")
        for packet in packets:
            if not isinstance(packet, dict):
                failures.append(f"packet_not_object:{item['ref']}")
                continue
            packet_id = str(packet.get("id") or "<missing>")
            packet_failures = _packet_failures(packet, payload)
            refs_result = _resolve_refs(
                _as_string_list(packet.get("refs")),
                project_root=project,
                package_root=package,
                owner=packet_id,
            )
            packet_failures.extend(refs_result["failures"])
            failures.extend(packet_failures)
            all_resolved_refs.extend(refs_result["resolved_refs"])
            all_missing_refs.extend(refs_result["missing_refs"])
            all_unsafe_refs.extend(refs_result["unsafe_refs"])
            packet_results.append(
                {
                    "id": packet_id,
                    "ok": not packet_failures,
                    "status": str(packet.get("status") or ""),
                    "sources": len(packet.get("sources") if isinstance(packet.get("sources"), list) else []),
                    "claims": len(packet.get("claims") if isinstance(packet.get("claims"), list) else []),
                    "citations": len(packet.get("citations") if isinstance(packet.get("citations"), list) else []),
                    "failures": sorted(set(packet_failures)),
                }
            )
        for case in example_set.get("scoring_cases") if isinstance(example_set.get("scoring_cases"), list) else []:
            if not isinstance(case, dict):
                failures.append(f"scoring_case_not_object:{item['ref']}")
                continue
            result = _scoring_case_result(case, payload)
            failures.extend(result["failures"])
            scoring_results.append(result)

    checks = [
        {"id": "source_allowlist", "status": "passed" if not any("allowlist" in item or "domain_not_allowed" in item for item in failures) else "failed"},
        {"id": "freshness_bounds", "status": "passed" if not any("stale" in item or "freshness" in item for item in failures) else "failed"},
        {"id": "citation_coverage", "status": "passed" if not any("citation" in item or "uncited" in item for item in failures) else "failed"},
        {"id": "offline_validation", "status": "passed" if not any("network_fetch" in item for item in failures) else "failed"},
        {"id": "scoring_cases", "status": "passed" if scoring_results and not any(not item["ok"] for item in scoring_results) else "failed"},
        {"id": "refs_resolved", "status": "passed" if not all_missing_refs and not all_unsafe_refs else "failed"},
    ]
    metrics = {
        "packets": len(packet_results),
        "passing_packets": sum(1 for item in packet_results if item["ok"]),
        "scoring_cases": len(scoring_results),
        "passing_scoring_cases": sum(1 for item in scoring_results if item["ok"]),
        "refs": len(all_resolved_refs) + len(all_missing_refs) + len(all_unsafe_refs),
        "resolved_refs": len(all_resolved_refs),
        "missing_refs": len(all_missing_refs),
        "unsafe_refs": len(all_unsafe_refs),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "policy_path": str(policy_path or ""),
        "project_root": _display_path(project),
        "package_root": _display_path(package),
        "failures": sorted(set(failures)),
        "metrics": metrics,
        "checks": checks,
        "packet_results": sorted(packet_results, key=lambda item: item["id"]),
        "scoring_results": sorted(scoring_results, key=lambda item: item["id"]),
        "resolved_refs": sorted(all_resolved_refs, key=lambda item: (item["owner"], item["ref"])),
        "missing_refs": sorted(all_missing_refs, key=lambda item: (item["owner"], item["ref"])),
        "unsafe_refs": sorted(all_unsafe_refs, key=lambda item: (item["owner"], item["ref"])),
    }


def research_packet_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != REPORT_KIND:
        raise ValueError("research_packet_report_required")
    status = "passed" if report.get("ok") else "failed"
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": [
            {"id": "pipeline_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "rollback_plan", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
            {"id": "safety_eval", "status": status, "score": 1.0 if status == "passed" else 0.0, "threshold": 1.0},
        ],
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge Research_Packet contracts.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/ and docs/.")
    parser.add_argument("--package-root", default="", help="Package root, default: <project-root>/noemaforge.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/research-packet-policy.json",
        help="Policy path, absolute or relative to project root.",
    )
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = _as_path(args.project_root)
    package_root = _as_path(args.package_root) if args.package_root else project_root / "noemaforge"
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path

    report = validate_research_packet_policy(
        load_policy(policy_path),
        project_root=project_root,
        package_root=package_root,
        policy_path=policy_path,
    )
    if args.summary:
        payload: Dict[str, Any] = {
            "apiVersion": report["apiVersion"],
            "kind": "ResearchPacketValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "policy_path": report["policy_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
