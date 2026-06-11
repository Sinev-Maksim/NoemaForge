#!/usr/bin/env python3
"""Token diet for model review prompts: strip generated-evidence diff blocks.

Generated evidence files (MANIFEST*/SHA256SUMS* at any path depth) dominate
branch diffs but carry zero review signal — the premerge evidence gate
verifies them bit-exactly. This filter removes their blocks from a unified
diff before it enters a model prompt, prepends an explanatory note, and caps
the remainder defensively.

Reads the diff file in place, writes the filtered diff back, and prints a
machine-readable summary line:

    FILTERED kept=<n> omitted=<n> omitted_kb=<n> evidence_only=<0|1>

Exit code is always 0 on success so callers branch on `evidence_only`.

Usage:
    python ci/filter_review_diff.py <diff-file> [--cap-bytes 204800]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Generated evidence basenames, matched at any path depth so future mirrors
# (e.g. docs/MANIFEST.json) are covered without edits.
# Coupled with noemaforge/tests/test_review_diff_filter.py (EVIDENCE_PATHS):
# extend BOTH together if evidence filenames ever grow beyond MANIFEST*/SHA256SUMS*.
EVIDENCE_BLOCK_RE = re.compile(
    r"^diff --git a/(?:[^ ]*/)?"
    r"(MANIFEST(\.json)?(\.sha256)?|SHA256SUMS(\.sha256)?) ",
    re.M,
)
SPLIT_RE = re.compile(r"(?m)(?=^diff --git )")


def filter_diff(raw: str, cap_bytes: int) -> tuple[str, int, int, int]:
    """Return (filtered_text, kept_blocks, omitted_blocks, omitted_chars)."""
    blocks = SPLIT_RE.split(raw)
    kept: list[str] = []
    omitted = omitted_chars = 0
    for block in blocks:
        if not block.strip():
            continue
        if EVIDENCE_BLOCK_RE.match(block):
            omitted += 1
            omitted_chars += len(block)
        else:
            kept.append(block)

    filtered = "".join(kept)
    if omitted:
        note = (
            f"[NOTE] {omitted} generated evidence file diff(s) omitted "
            f"({omitted_chars // 1024} KB): MANIFEST/SHA256SUMS files are "
            "regenerated artifacts verified bit-exactly by the premerge "
            "evidence gate; do not review them.\n\n"
        )
        filtered = note + filtered
    if len(filtered) > cap_bytes:
        filtered = (
            filtered[:cap_bytes]
            + "\n\n[NOTE] diff truncated for the review prompt; "
            "full diff is in the compare view."
        )
    return filtered, len(kept), omitted, omitted_chars


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diff_file", help="unified diff file, rewritten in place")
    parser.add_argument("--cap-bytes", type=int, default=200 * 1024)
    args = parser.parse_args()

    path = Path(args.diff_file)
    raw = path.read_text(encoding="utf-8", errors="replace")
    filtered, kept, omitted, omitted_chars = filter_diff(raw, args.cap_bytes)
    path.write_text(filtered, encoding="utf-8", newline="\n")
    print(
        f"FILTERED kept={kept} omitted={omitted} "
        f"omitted_kb={omitted_chars // 1024} evidence_only={int(kept == 0)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
