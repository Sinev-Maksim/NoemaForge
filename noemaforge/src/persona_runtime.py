#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/persona_runtime.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Manage NoemaForge personas, portraits and activation state.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Existing module notes:
NoemaForge persona/codename runtime.

Minimal stdlib-only layer for:
- role codename lookup;
- activation context packet creation;
- stateful portrait evolution.

It is deliberately not a multi-agent runner. It records which persona context is
active for the operator and keeps the one-active-LLM invariant intact.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import xml.etree.ElementTree as ET
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_PERSONA_STATE", "/var/lib/noemaforge/personas"))
SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_id(value: str) -> str:
    return SAFE_RE.sub("_", value).strip("_") or "persona"


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_catalog(root: Path) -> Dict[str, Any]:
    path = root / "configs" / "persona-catalog.json"
    if not path.exists():
        raise SystemExit(f"missing persona catalog: {path}")
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def load_state(state: Path) -> Dict[str, Any]:
    path = state / "persona_state.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
    return {"version": "0.30.19", "active": None, "generations": {}, "events": []}


def save_state(state_dir: Path, data: Dict[str, Any]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(state_dir / "persona_state.json", dumps(data) + "\n")


def normalize(v: str) -> str:
    return v.casefold().replace("ё", "е")


def resolve(catalog: Dict[str, Any], query: str) -> tuple[str, Dict[str, Any]]:
    personas = catalog.get("personas") or {}
    q = normalize(query)
    for role, spec in personas.items():
        if normalize(role) == q or normalize(spec.get("codename", "")) == q or normalize(safe_id(role.replace("/", "_"))) == q:
            return role, spec
    hits = [(role, spec) for role, spec in personas.items() if q in normalize(role) or q in normalize(spec.get("codename", ""))]
    if len(hits) == 1:
        return hits[0]
    raise SystemExit("unknown or ambiguous persona: " + query)


def color_for(seed: str, salt: int = 0) -> str:
    return "#" + hashlib.sha256((seed + str(salt)).encode()).hexdigest()[:6]


def xml_escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def portrait_svg(role: str, codename: str, generation: int, reason: str = "") -> str:
    c1 = color_for(role, generation)
    c2 = color_for(role, generation + 11)
    c3 = color_for(role, generation + 23)
    initials = "".join([p[0] for p in codename.replace("-", " ").split()[:2]]).upper()[:2]
    reason_text = xml_escape(reason or "evolution")[:80]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="NoemaForge persona {xml_escape(codename)} generation {generation}">
  <defs>
    <radialGradient id="g" cx="38%" cy="24%" r="82%"><stop offset="0" stop-color="{c2}"/><stop offset="0.72" stop-color="{c1}"/><stop offset="1" stop-color="#05070b"/></radialGradient>
  </defs>
  <rect width="512" height="512" rx="48" fill="#05070b"/>
  <circle cx="256" cy="218" r="176" fill="url(#g)" opacity="0.94"/>
  <path d="M110 384c36-74 84-110 146-110s110 36 146 110" fill="none" stroke="{c3}" stroke-width="24" stroke-linecap="round" opacity="0.84"/>
  <path d="M160 178c48-58 120-68 182-24" fill="none" stroke="#e8eef7" stroke-opacity="0.40" stroke-width="15" stroke-linecap="round"/>
  <circle cx="204" cy="224" r="18" fill="#e8eef7" opacity="0.88"/>
  <circle cx="312" cy="224" r="18" fill="#e8eef7" opacity="0.88"/>
  <path d="M214 298c38 28 76 28 114 0" fill="none" stroke="#e8eef7" stroke-opacity="0.56" stroke-width="12" stroke-linecap="round"/>
  <text x="256" y="448" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="40" font-weight="700" fill="#e8eef7">{xml_escape(initials)}</text>
  <text x="256" y="480" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="16" fill="#9aa8bb">gen {generation} · {reason_text}</text>
</svg>'''


def cmd_list(args: argparse.Namespace) -> None:
    catalog = load_catalog(Path(args.root))
    personas = catalog.get("personas") or {}
    if args.json:
        print(dumps(personas))
        return
    for role, spec in sorted(personas.items()):
        print(f"{role}\t{spec.get('codename')}\t{spec.get('portrait')}")


def activation_packet(state_dir: Path, role: str, spec: Dict[str, Any], generation: int, reason: str) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    pid = safe_id(role.replace("/", "_"))
    path = state_dir / f"persona_{pid}_activation_context.md"
    content = f"""# NoemaForge Persona Activation Context

- role_key: `{role}`
- codename: `{spec.get('codename')}`
- generation: `{generation}`
- activated_at: `{nowz()}`
- llm_mode: `switchable`
- max_active_llms: `1`
- reason: {reason or 'operator activation'}

## Contract

This persona is a context, not a concurrently running agent. Use the active LLM only, write handoff notes as markdown, and preserve safety policy boundaries.

## Portrait

{spec.get('portrait')}
"""
    atomic_write_text(path, content)
    return path


def cmd_activate(args: argparse.Namespace) -> None:
    root = Path(args.root)
    state_dir = Path(args.state)
    catalog = load_catalog(root)
    role, spec = resolve(catalog, args.persona)
    state = load_state(state_dir)
    generation = int((state.get("generations") or {}).get(role, spec.get("default_generation", 0)))
    packet = activation_packet(state_dir, role, spec, generation, args.reason or "")
    state["active"] = {
        "role_key": role,
        "codename": spec.get("codename"),
        "generation": generation,
        "activated_at": nowz(),
        "packet": str(packet),
    }
    state.setdefault("events", []).append({
        "ts": nowz(), "event": "activate", "role_key": role,
        "codename": spec.get("codename"), "generation": generation,
    })
    save_state(state_dir, state)
    print(dumps({
        "ok": True,
        "active": state["active"],
        "portrait": spec.get("portrait"),
        "context_packet": str(packet),
        "invariant": {"max_active_llms": 1},
    }))


def cmd_evolve(args: argparse.Namespace) -> None:
    root = Path(args.root)
    state_dir = Path(args.state)
    catalog = load_catalog(root)
    role, spec = resolve(catalog, args.persona)
    state = load_state(state_dir)
    generations = state.setdefault("generations", {})
    generation = int(generations.get(role, spec.get("default_generation", 0))) + 1
    generations[role] = generation
    out_dir = state_dir / "portraits"
    out_dir.mkdir(parents=True, exist_ok=True)
    pid = safe_id(role.replace("/", "_"))
    out = out_dir / f"{pid}_gen{generation}.svg"
    atomic_write_text(out, portrait_svg(role, spec.get("codename", "persona"), generation, args.reason or "evolution"))
    state.setdefault("events", []).append({
        "ts": nowz(), "event": "evolve", "role_key": role,
        "codename": spec.get("codename"), "generation": generation,
        "portrait": str(out), "reason": args.reason or "",
    })
    if (state.get("active") or {}).get("role_key") == role:
        state["active"]["generation"] = generation
        state["active"]["portrait"] = str(out)
        state["active"]["evolved_at"] = nowz()
    save_state(state_dir, state)
    print(dumps({
        "ok": True,
        "role_key": role,
        "codename": spec.get("codename"),
        "generation": generation,
        "portrait": str(out),
        "reason": args.reason or "",
    }))


def cmd_active(args: argparse.Namespace) -> None:
    root = Path(args.root)
    state_dir = Path(args.state)
    catalog = load_catalog(root)
    state = load_state(state_dir)
    active = state.get("active")
    if not active:
        doc = {"ok": True, "active": None, "next": "noemaforge persona activate Бехтерев --reason operator_review"}
    else:
        role = active.get("role_key")
        spec = (catalog.get("personas") or {}).get(role, {})
        doc = {"ok": True, "active": {**spec, **active}, "state": str(state_dir / "persona_state.json")}
    if args.json:
        print(dumps(doc))
        return
    if not doc.get("active"):
        print("no active persona")
        print(doc["next"])
        return
    a = doc["active"]
    print(f"{a.get('role_key')}	{a.get('codename')}	gen={a.get('generation')}	portrait={a.get('portrait')}")


def cmd_show(args: argparse.Namespace) -> None:
    catalog = load_catalog(Path(args.root))
    role, spec = resolve(catalog, args.persona)
    doc = {"ok": True, "role_key": role, **spec}
    if args.json:
        print(dumps(doc))
        return
    print(f"role_key: {role}")
    print(f"codename: {spec.get('codename')}")
    print(f"portrait: {spec.get('portrait')}")
    print(f"system_prompt_hint: {spec.get('system_prompt_hint')}")


def cmd_validate(args: argparse.Namespace) -> None:
    root = Path(args.root)
    catalog = load_catalog(root)
    problems = []
    seen = set()
    for role, spec in (catalog.get("personas") or {}).items():
        cn = spec.get("codename")
        if not cn:
            problems.append(f"{role}: missing codename")
        if cn in seen:
            problems.append(f"duplicate codename: {cn}")
        seen.add(cn)
        portrait = root / spec.get("portrait", "")
        if not portrait.exists():
            problems.append(f"{role}: missing portrait {portrait}")
        else:
            try:
                ET.fromstring(portrait.read_text(encoding="utf-8", errors="replace"))
            except Exception as exc:
                problems.append(f"{role}: invalid SVG portrait {portrait}: {exc}")
        if (spec.get("safety") or {}).get("max_active_llms") != 1:
            problems.append(f"{role}: max_active_llms must be 1")
    print(dumps({"ok": not problems, "persona_count": len(catalog.get("personas") or {}), "problems": problems}))
    if problems:
        raise SystemExit(1)


def cmd_lineage(args: argparse.Namespace) -> None:
    state_dir = Path(args.state)
    catalog = load_catalog(Path(args.root))
    state = load_state(state_dir)
    events = state.get("events") or []
    if args.persona:
        role, spec = resolve(catalog, args.persona)
        events = [e for e in events if e.get("role_key") == role]
    doc = {
        "ok": True,
        "state": str(state_dir / "persona_state.json"),
        "active": state.get("active"),
        "events": events[-int(args.limit):],
        "generation_count": len(state.get("generations") or {}),
    }
    if args.json:
        print(dumps(doc)); return
    active = doc.get("active") or {}
    print(f"active: {active.get('role_key', 'none')} {active.get('codename', '')} gen={active.get('generation', '-')}")
    for e in doc["events"]:
        print(f"{e.get('ts')}\t{e.get('event')}\t{e.get('role_key')}\tgen={e.get('generation')}\t{e.get('reason','')}")


def cmd_export(args: argparse.Namespace) -> None:
    state_dir = Path(args.state)
    catalog = load_catalog(Path(args.root))
    state = load_state(state_dir)
    out = Path(args.out or state_dir / "persona_export.json")
    doc = {"exported_at": nowz(), "catalog_version": catalog.get("version"), "state": state}
    atomic_write_text(out, dumps(doc) + "\n")
    print(dumps({"ok": True, "out": str(out), "active": state.get("active")}))



def cmd_doctor(args: argparse.Namespace) -> None:
    root = Path(args.root)
    state_dir = Path(args.state)
    catalog = load_catalog(root)
    state = load_state(state_dir)
    personas = catalog.get("personas") or {}
    problems = []
    warnings = []
    active = state.get("active") or {}
    if active and active.get("role_key") not in personas:
        problems.append(f"active persona not in catalog: {active.get('role_key')}")
    for role, spec in personas.items():
        portrait = spec.get("portrait")
        if not portrait or not (root / portrait).exists():
            problems.append(f"{role}: missing portrait {portrait}")
    if not active:
        warnings.append("no active persona; use noemaforge persona activate Бехтерев")
    result = {
        "ok": not problems,
        "persona_count": len(personas),
        "active": active or None,
        "state": str(state_dir),
        "warnings": warnings,
        "problems": problems,
        "next_safe_action": "noemaforge persona activate Бехтерев" if not active else f"noemaforge persona show {active.get('codename')}",
        "invariant": {"max_active_llms": 1, "mode": "switchable"},
    }
    print(dumps(result))
    if problems:
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="noemaforge persona")
    p.add_argument("--root", default=str(DEFAULT_ROOT))
    p.add_argument("--state", default=str(DEFAULT_STATE))
    sub = p.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("list")
    lp.add_argument("--json", action="store_true")
    lp.set_defaults(func=cmd_list)
    active = sub.add_parser("active")
    active.add_argument("--json", action="store_true")
    active.set_defaults(func=cmd_active)
    show = sub.add_parser("show")
    show.add_argument("persona")
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=cmd_show)
    ap = sub.add_parser("activate")
    ap.add_argument("persona")
    ap.add_argument("--reason", default="")
    ap.set_defaults(func=cmd_activate)
    ep = sub.add_parser("evolve")
    ep.add_argument("persona")
    ep.add_argument("--reason", default="")
    ep.set_defaults(func=cmd_evolve)
    lin = sub.add_parser("lineage")
    lin.add_argument("persona", nargs="?")
    lin.add_argument("--limit", type=int, default=20)
    lin.add_argument("--json", action="store_true")
    lin.set_defaults(func=cmd_lineage)
    ex = sub.add_parser("export")
    ex.add_argument("--out")
    ex.set_defaults(func=cmd_export)
    vp = sub.add_parser("validate")
    vp.set_defaults(func=cmd_validate)
    doc = sub.add_parser("doctor")
    doc.set_defaults(func=cmd_doctor)
    return p


def normalize_global_argv(argv: Optional[list[str]]) -> list[str]:
    items = list(sys.argv[1:] if argv is None else argv)
    global_opts = []
    rest = []
    i = 0
    while i < len(items):
        if items[i] in {"--root", "--state"} and i + 1 < len(items):
            global_opts.extend([items[i], items[i + 1]])
            i += 2
        else:
            rest.append(items[i])
            i += 1
    return global_opts + rest


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(normalize_global_argv(argv))
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
