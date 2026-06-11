#!/usr/bin/env python3
"""NoemaForge release-evidence regenerator.

Rebuilds the seven generated evidence files from the **git index** (the clean
staged tree, immune to working-copy cruft and CRLF checkout effects):

    MANIFEST.json                     project active-file manifest
    MANIFEST.json.sha256              hash sidecar
    MANIFEST.sha256                   hash sidecar (legacy name)
    SHA256SUMS                        project per-file hashes
    SHA256SUMS.sha256                 hash sidecar
    noemaforge/checksums/SHA256SUMS   package per-file hashes
    noemaforge/docs/MANIFEST.json     package active-file manifest

Active-file selection comes from the same exclusion policy the verifier uses
(`manifest-checksum-exclusion-policy.json`), so a regen followed by
`manifest_checksum_exclusion_runtime.py --summary --hash-source git-index`
is consistent by construction.

This script is the single source of evidence generation: the premerge gate
runs it before verifying (so PR branches never need to commit regenerated
evidence), and the evidence-refresh workflow runs it after merges to keep the
committed copies on release branches current.

Usage:
    python ci/regen_evidence.py            # regenerate + git add (default)
    python ci/regen_evidence.py --check    # exit 1 if committed copies differ
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "noemaforge" / "src"))
import manifest_checksum_exclusion_runtime as mcer  # noqa: E402

EVIDENCE_FILES = [
    "MANIFEST.json",
    "MANIFEST.json.sha256",
    "MANIFEST.sha256",
    "SHA256SUMS",
    "SHA256SUMS.sha256",
    "noemaforge/checksums/SHA256SUMS",
    "noemaforge/docs/MANIFEST.json",
    "noemaforge/docs/MANIFEST.json.sha256",
]


def _git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=str(REPO), check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _index_hashes() -> dict:
    return mcer._git_index_hashes(REPO)


def _active_sets() -> tuple[list[str], list[str]]:
    policy = mcer.load_policy(
        REPO / "noemaforge/configs/manifest-checksum-exclusion-policy.json")["policy"]
    excluded = set(mcer._as_string_list(policy.get("excluded_dir_names"))
                   or sorted(mcer.DEFAULT_EXCLUDED_DIR_NAMES))
    proj_only = set(mcer._as_string_list(policy.get("project_only_excluded_dir_names")))
    proj_excluded_files = set(mcer._as_string_list(policy.get("project_excluded_file_refs")))

    proj_active: list[str] = []
    pkg_active: list[str] = []
    for rel in sorted(_index_hashes()):
        parts = rel.split("/")
        if any(p in excluded for p in parts):
            continue
        if not (parts[0] in proj_only or rel in proj_excluded_files):
            proj_active.append(rel)
        if parts[0] == "noemaforge" and len(parts) > 1:
            pkg_active.append("/".join(parts[1:]))
    return proj_active, pkg_active


def _write(rel: str, text: str) -> None:
    (REPO / rel).write_text(text, encoding="utf-8", newline="\n")


def _write_manifest(rel: str, files: list[str]) -> None:
    obj = json.loads((REPO / rel).read_text(encoding="utf-8-sig"))
    obj["file_count"] = len(files)
    obj["files"] = files
    _write(rel, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def regenerate() -> tuple[int, int]:
    proj_active, pkg_active = _active_sets()

    # Pass A — manifests (content depends on the active sets only).
    _write_manifest("MANIFEST.json", proj_active)
    _write_manifest("noemaforge/docs/MANIFEST.json", pkg_active)
    _git("add", "MANIFEST.json", "noemaforge/docs/MANIFEST.json")

    # Pass B — manifest hash sidecars (need the index hash of pass A output).
    hashes = _index_hashes()
    _write("MANIFEST.json.sha256", f"{hashes['MANIFEST.json']}  MANIFEST.json\n")
    _write("MANIFEST.sha256", f"{hashes['MANIFEST.json']}  MANIFEST.json\n")
    _write("noemaforge/docs/MANIFEST.json.sha256",
           f"{hashes['noemaforge/docs/MANIFEST.json']}  MANIFEST.json\n")
    _git("add", "MANIFEST.json.sha256", "MANIFEST.sha256",
         "noemaforge/docs/MANIFEST.json.sha256")

    # Pass C — package SHA256SUMS, its sidecar, then project SHA256SUMS.
    hashes = _index_hashes()
    pkg_lines = "".join(f"{hashes['noemaforge/' + r]}  {r}\n"
                        for r in pkg_active if r != "checksums/SHA256SUMS")
    _write("noemaforge/checksums/SHA256SUMS", pkg_lines)
    _git("add", "noemaforge/checksums/SHA256SUMS")

    hashes = _index_hashes()
    _write("SHA256SUMS.sha256",
           f"{hashes['noemaforge/checksums/SHA256SUMS']}  noemaforge/checksums/SHA256SUMS\n")
    _git("add", "SHA256SUMS.sha256")

    hashes = _index_hashes()
    proj_lines = "".join(f"{hashes[r]}  {r}\n"
                         for r in proj_active if r != "SHA256SUMS")
    _write("SHA256SUMS", proj_lines)
    _git("add", "SHA256SUMS")

    return len(proj_active), len(pkg_active)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="regenerate and exit 1 if any committed evidence file changed")
    args = parser.parse_args()

    before = {rel: _index_hashes().get(rel) for rel in EVIDENCE_FILES}
    proj, pkg = regenerate()
    print(f"regen_evidence: proj_active={proj} pkg_active={pkg}")

    if args.check:
        after = _index_hashes()
        stale = [rel for rel in EVIDENCE_FILES if before.get(rel) != after.get(rel)]
        if stale:
            print("regen_evidence: committed evidence is STALE for:")
            for rel in stale:
                print(f"  {rel}")
            return 1
        print("regen_evidence: committed evidence matches the regenerated state")
    return 0


if __name__ == "__main__":
    sys.exit(main())
