#!/usr/bin/env python3
"""NoemaForge wiki publisher.

Renders the canonical wiki tree (``noemaforge/docs/wiki/``) into a flat page
set suitable for the GitHub Wiki (which addresses pages by file basename):

- ``WIKI.md`` becomes ``Home.md``;
- other root pages keep their basename;
- ``<category>/<page>.md`` becomes ``<category>--<page>.md`` (stable, unique,
  groups alphabetically by category in the page list);
- relative links between wiki pages are rewritten to flat page names (no
  ``.md``), links to other repository files become absolute GitHub blob URLs;
- ``_Sidebar.md`` (hub + categories) and ``_Footer.md`` are generated.

The destination directory's ``*.md`` files are replaced atomically per run, so
the GitHub Wiki checkout stays an exact mirror of the canonical tree.

Usage:
    python ci/wiki_publish.py --dest <dir> [--repo-url URL] [--branch main]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIKI = REPO / "noemaforge" / "docs" / "wiki"
LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)(\s+\"[^\"]*\")?\)")


def flat_name(rel: str) -> str:
    if rel == "WIKI.md":
        return "Home.md"
    return rel.replace("/", "--")


def page_map() -> dict[Path, str]:
    return {p: flat_name(p.relative_to(WIKI).as_posix()) for p in sorted(WIKI.rglob("*.md"))}


def rewrite_links(text: str, src: Path, names: dict[Path, str], repo_url: str, branch: str) -> str:
    def repl(m: re.Match) -> str:
        bang, label, target, title = m.group(1), m.group(2), m.group(3), m.group(4) or ""
        if target.startswith(("http://", "https://", "mailto:", "#", "/")):
            return m.group(0)
        path, _, anchor = target.partition("#")
        if not path:
            return m.group(0)
        resolved = (src.parent / path).resolve()
        suffix = f"#{anchor}" if anchor else ""
        if resolved in names:
            page = names[resolved][:-3]  # strip .md
            return f"{bang}[{label}]({page}{suffix}{title})"
        try:
            rel = resolved.relative_to(REPO).as_posix()
        except ValueError:
            return m.group(0)
        return f"{bang}[{label}]({repo_url}/blob/{branch}/{rel}{suffix}{title})"

    return LINK_RE.sub(repl, text)


def build_sidebar(names: dict[Path, str]) -> str:
    lines = ["### NoemaForge wiki", "", "- [Home](Home)", ""]
    categories: dict[str, list[tuple[str, str]]] = {}
    for p, flat in names.items():
        rel = p.relative_to(WIKI).as_posix()
        if rel == "WIKI.md":
            continue
        category = rel.split("/", 1)[0] if "/" in rel else "(root)"
        categories.setdefault(category, []).append((flat[:-3], p.stem))
    for category in sorted(categories):
        lines.append(f"**{category}**")
        lines.extend(f"- [{stem}]({page})" for page, stem in sorted(categories[category]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", required=True, help="output directory (e.g. a wiki.git checkout)")
    parser.add_argument("--repo-url", default="https://github.com/Sinev-Maksim/NoemaForge")
    parser.add_argument("--branch", default="main", help="branch for repo blob links")
    args = parser.parse_args()

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    names = page_map()
    if not names:
        print("wiki_publish: no pages found", file=sys.stderr)
        return 1

    for old in dest.glob("*.md"):
        old.unlink()

    for p, flat in names.items():
        text = p.read_text(encoding="utf-8", errors="replace")
        text = rewrite_links(text, p, {k.resolve(): v for k, v in names.items()}, args.repo_url, args.branch)
        (dest / flat).write_text(text, encoding="utf-8", newline="\n")

    (dest / "_Sidebar.md").write_text(build_sidebar(names), encoding="utf-8", newline="\n")
    (dest / "_Footer.md").write_text(
        f"_Generated from [`noemaforge/docs/wiki/`]({args.repo_url}/tree/{args.branch}/noemaforge/docs/wiki)"
        " — edit there, not here. Published by `ci/wiki_publish.py`._\n",
        encoding="utf-8", newline="\n",
    )
    print(f"wiki_publish: wrote {len(names)} pages + _Sidebar + _Footer to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
