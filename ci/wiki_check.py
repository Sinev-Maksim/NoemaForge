#!/usr/bin/env python3
"""NoemaForge wiki integrity gate.

The canonical wiki is ``noemaforge/docs/wiki/``: one standalone article per
page under a category folder, indexed from the hub ``WIKI.md``. This check
keeps the tree coherent so the wiki can be trusted as release evidence and
auto-published to the GitHub Wiki on merge.

Checks (CI mode, default):

1. hub index freshness — the generated evergreen/archive sections between the
   ``wiki-index`` markers in WIKI.md match the current tree;
2. hub coverage — every wiki page is referenced from WIKI.md;
3. link integrity — every relative Markdown link in every wiki page resolves
   to an existing file inside the repository;
4. no consolidated dumps — pages must not contain ``## Fragment N:`` headers
   (dump files are retired; see the Deep Research Integration Policy).

Maintenance mode: ``--write-index`` regenerates the marker sections in
WIKI.md in place (run it after adding/removing pages, then commit).

Usage:
    python ci/wiki_check.py                # CI gate, exit 1 on violations
    python ci/wiki_check.py --write-index  # refresh hub index sections
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIKI = REPO / "noemaforge" / "docs" / "wiki"
HUB = WIKI / "WIKI.md"

HISTORICAL_BANNER = "Status: historical snapshot"
FRAGMENT_RE = re.compile(r"^## Fragment \d+: ", re.M)
# inline links: [text](target) — tolerate titles, skip images by stripping '!'
LINK_RE = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
MARKERS = {
    "evergreen": ("<!-- wiki-index:evergreen:start -->", "<!-- wiki-index:evergreen:end -->"),
    "archive": ("<!-- wiki-index:archive:start -->", "<!-- wiki-index:archive:end -->"),
}


def wiki_pages() -> list[Path]:
    # Sort by the posix relpath string: Path ordering is case-insensitive on
    # Windows but case-sensitive on Linux, which made the generated hub index
    # platform-dependent (stale on CI when written locally).
    return sorted(WIKI.rglob("*.md"), key=lambda p: p.relative_to(WIKI).as_posix())


def rel(p: Path) -> str:
    return p.relative_to(WIKI).as_posix()


def page_title(p: Path) -> str:
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return p.stem


def is_historical(p: Path) -> bool:
    return HISTORICAL_BANNER in p.read_text(encoding="utf-8", errors="replace")


def hub_mentioned_targets(hub_text: str) -> set[str]:
    return {m.group(1).split("#", 1)[0] for m in LINK_RE.finditer(hub_text)}


def build_index_sections() -> dict[str, str]:
    hub_text = HUB.read_text(encoding="utf-8")
    manual = hub_text.split(MARKERS["evergreen"][0], 1)[0]
    manual_targets = hub_mentioned_targets(manual)

    evergreen: list[tuple[str, str]] = []
    archive: dict[str, list[tuple[str, str]]] = {}
    for p in wiki_pages():
        r = rel(p)
        if r in {"WIKI.md", "README.md"}:
            continue
        category = r.split("/", 1)[0] if "/" in r else "(root)"
        if is_historical(p):
            archive.setdefault(category, []).append((r, page_title(p)))
        elif r not in manual_targets:
            evergreen.append((r, page_title(p)))

    ev_lines = [f"- [{title}]({r})" for r, title in evergreen]
    era_re = re.compile(r"-(0\.\d+\.[0-9a-zA-Z.\-]*?)\.md$|-(02914)\.md$")
    ar_lines: list[str] = []
    for category in sorted(archive):
        ar_lines.append(f"\n### {category}\n")
        for r, title in sorted(archive[category]):
            m = era_re.search(r)
            era = f" — `{m.group(1) or m.group(2)}`" if m else ""
            ar_lines.append(f"- [{title}]({r}){era}")
    return {
        "evergreen": "\n".join(ev_lines) + "\n",
        "archive": "\n".join(ar_lines).lstrip("\n") + "\n",
    }


def splice(text: str, section: str, body: str) -> str:
    start, end = MARKERS[section]
    if start not in text or end not in text:
        raise SystemExit(f"wiki_check: marker pair for {section!r} missing in WIKI.md")
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    return f"{head}{start}\n{body}{end}{tail}"


def check_links(failures: list[str]) -> None:
    for p in wiki_pages():
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in LINK_RE.finditer(text):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#", "/")):
                continue
            path = target.split("#", 1)[0]
            if not path:
                continue
            resolved = (p.parent / path).resolve()
            if not resolved.exists():
                failures.append(f"broken_link:{rel(p)}:{target}")
            else:
                try:
                    resolved.relative_to(REPO)
                except ValueError:
                    failures.append(f"link_escapes_repo:{rel(p)}:{target}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-index", action="store_true",
                        help="regenerate the hub index sections in place")
    args = parser.parse_args()

    sections = build_index_sections()
    hub_text = HUB.read_text(encoding="utf-8")

    if args.write_index:
        new = hub_text
        for name, body in sections.items():
            new = splice(new, name, body)
        HUB.write_text(new, encoding="utf-8", newline="\n")
        print("wiki_check: hub index sections regenerated")
        return 0

    failures: list[str] = []

    expected = hub_text
    for name, body in sections.items():
        expected = splice(expected, name, body)
    if expected != hub_text:
        failures.append("hub_index_stale: run `python ci/wiki_check.py --write-index` and commit")

    mentioned = hub_mentioned_targets(hub_text)
    for p in wiki_pages():
        r = rel(p)
        if r in {"WIKI.md", "README.md"}:
            continue
        if r not in mentioned:
            failures.append(f"page_not_in_hub:{r}")

    check_links(failures)

    for p in wiki_pages():
        if FRAGMENT_RE.search(p.read_text(encoding="utf-8", errors="replace")):
            failures.append(f"consolidated_dump_forbidden:{rel(p)}")

    if failures:
        print("wiki_check: FAIL")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"wiki_check: OK ({len(wiki_pages())} pages, hub index fresh, links resolve)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
