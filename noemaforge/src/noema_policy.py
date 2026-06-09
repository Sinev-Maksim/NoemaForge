#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/noema_policy.py
Zone: runtime/cli
Version: 0.33.0
Created: 2026-06-08
Modified: 2026-06-08
Purpose: `noema policy test` — validate the ToolProxy/release policy files
  (noemaforge/policies/*.rego) against their security CONTRACT without requiring an external
  policy engine. This is a stdlib structural validator (not a full Rego evaluator): it guards the
  deny-by-default invariant and each known policy's required rules, so a regression like flipping
  `default allow := false` to `true` fails CI. A full OPA-based evaluator is a separate, optional
  dependency decision (this module does not introduce one).
Inputs: package root (default: this install).
Outputs: per-policy results + overall ok; exit 0 only when every contract holds.
Side effects: read-only filesystem scan.
Tests: python3 -m unittest noemaforge/tests/test_noema_policy.py
Notes: Code comments are English-only. Display-safe: read-only, no GPU/model/display actions.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_PKG_ROOT = Path(__file__).resolve().parents[1]  # noemaforge/

# Decision rules that MUST default to false (deny-by-default / fail-closed).
DENY_BY_DEFAULT_RULES = {"allow", "publishable", "permit", "grant", "authorize", "admit"}

# Per-policy contract: required package + the decision rule that must exist and default to false.
KNOWN_CONTRACTS: Dict[str, Dict[str, str]] = {
    "toolproxy.rego": {"package": "noemaforge.toolproxy", "deny_default": "allow"},
    "release.rego": {"package": "noemaforge.release", "deny_default": "publishable"},
}

_PACKAGE_RE = re.compile(r"^\s*package\s+([A-Za-z0-9_.]+)", re.MULTILINE)
# Matches `default <name> := <value>` (Rego v1) and `default <name> = <value>`.
_DEFAULT_RE = re.compile(r"(?m)^\s*default\s+([A-Za-z_][A-Za-z0-9_]*)\s*:?=\s*([A-Za-z0-9_\"']+)")


def check_policy(path: Path) -> Dict[str, Any]:
    """Validate one .rego file against the deny-by-default contract (+ known-policy contract)."""
    name = path.name
    violations: List[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"file": f"policies/{name}", "ok": False, "violations": [f"unreadable: {exc}"]}

    pkg_match = _PACKAGE_RE.search(text)
    package = pkg_match.group(1) if pkg_match else None
    if package is None:
        violations.append("missing `package` declaration")

    defaults = {m.group(1): m.group(2) for m in _DEFAULT_RE.finditer(text)}
    for rule, value in defaults.items():
        if rule in DENY_BY_DEFAULT_RULES and value != "false":
            violations.append(
                f"deny-by-default violated: `default {rule} := {value}` (must be `false`)")

    contract = KNOWN_CONTRACTS.get(name)
    if contract:
        if package != contract["package"]:
            violations.append(
                f"package must be `{contract['package']}`, got `{package}`")
        dd = contract["deny_default"]
        if dd not in defaults:
            violations.append(f"missing required `default {dd} := false`")
        elif defaults[dd] != "false":
            violations.append(f"`default {dd}` must be `false`, got `{defaults[dd]}`")

    return {
        "file": f"policies/{name}",
        "package": package,
        "defaults": defaults,
        "known_contract": contract is not None,
        "violations": violations,
        "ok": not violations,
    }


def check_policies(root: Optional[Path] = None) -> Dict[str, Any]:
    """Validate every policy under <root>/policies. Returns ok + per-policy results.

    Also fails if a known-contract policy file is missing entirely.
    """
    root = Path(root) if root else _PKG_ROOT
    pdir = root / "policies"
    results: List[Dict[str, Any]] = []
    missing: List[str] = []

    found = {p.name for p in pdir.glob("*.rego")} if pdir.is_dir() else set()
    for required in KNOWN_CONTRACTS:
        if required not in found:
            missing.append(required)

    if pdir.is_dir():
        for p in sorted(pdir.glob("*.rego")):
            results.append(check_policy(p))

    ok = not missing and all(r["ok"] for r in results) and bool(results)
    return {
        "ok": ok,
        "policy_dir": str(pdir),
        "checked": len(results),
        "missing_required": missing,
        "policies": results,
    }


def format_human(report: Dict[str, Any]) -> str:
    lines = [f"noema policy test — {report['checked']} policy file(s) in {report['policy_dir']}"]
    for m in report["missing_required"]:
        lines.append(f"  [FAIL] required policy missing: {m}")
    for r in report["policies"]:
        if r["ok"]:
            lines.append(f"  [OK]   {r['file']} (package {r.get('package')})")
        else:
            for v in r["violations"]:
                lines.append(f"  [FAIL] {r['file']}: {v}")
    lines.append("OVERALL: PASS" if report["ok"] else "OVERALL: FAIL")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="noema policy",
        description="Validate ToolProxy/release policies against the deny-by-default contract. "
                    "Read-only; display-safe. Stdlib structural validator (not a Rego engine).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_test = sub.add_parser("test", help="validate the policy files; exit 0 only if all pass")
    p_test.add_argument("--root", default=None, help="package root (default: this install)")
    p_test.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = check_policies(Path(args.root) if args.root else None)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_human(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
