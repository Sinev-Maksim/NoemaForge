#!/usr/bin/env python3
"""NoemaForge release-evidence generator (pre-release only).

Generates the eight release-evidence files from the **working tree** — the same
source the verifier enumerates (`manifest_checksum_exclusion_runtime._active_files`
walks the filesystem) — so a regen followed by
`manifest_checksum_exclusion_runtime.py --summary --hash-source working-tree`
is consistent by construction:

    MANIFEST.json                     project active-file manifest
    MANIFEST.json.sha256              hash sidecar
    MANIFEST.sha256                   hash sidecar (legacy name)
    SHA256SUMS                        project per-file hashes
    SHA256SUMS.sha256                 hash sidecar
    noemaforge/checksums/SHA256SUMS   package per-file hashes
    noemaforge/docs/MANIFEST.json     package active-file manifest
    noemaforge/docs/MANIFEST.json.sha256  hash sidecar

These files are NOT tracked (gitignored) and are produced ONLY at pre-release by
`publish-evidence.yml` (owner directive 2026-06-14); they are not committed,
checked or merged on dev/PR/release branches. The schema-only manifest metadata
(apiVersion/kind/notes) lives in `ci/evidence-templates/*.template.json`; the
version-bearing fields (runtime_base_version/docs_overlay_version/package_name/
version) are derived from the release SoT (`release.json`) every run so they
never drift; file_count/files/generated_at and the volatile per-file hashes are
computed here from the working-tree contents.

Bootstrap: the manifests/checksums are self-referential (each lists the others),
so the eight files are first created as empty placeholders — so the active-file
enumeration includes them — then written with real content in dependency order
(manifests → manifest sidecars → package SHA256SUMS → its sidecar → project
SHA256SUMS, which lists everything else but excludes itself).

Usage:
    python ci/regen_evidence.py            # generate the evidence files on disk
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "noemaforge" / "src"))
import manifest_checksum_exclusion_runtime as mcer  # noqa: E402

TEMPLATES = REPO / "ci" / "evidence-templates"

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


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write(rel: str, text: str) -> None:
    (REPO / rel).write_text(text, encoding="utf-8", newline="\n")


def _ensure_placeholders() -> None:
    """Create empty evidence files so the active-set enumeration includes them
    (the manifests are self-referential — they list each other)."""
    for rel in EVIDENCE_FILES:
        p = REPO / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("", encoding="utf-8")


def _active_sets() -> tuple[list[str], list[str]]:
    """Active project/package file sets via the SAME enumerator the verifier uses
    (working-tree walk), so the generated manifests match verification exactly."""
    policy = mcer.load_policy(
        REPO / "noemaforge/configs/manifest-checksum-exclusion-policy.json")["policy"]
    excluded = mcer._as_string_list(policy.get("excluded_dir_names")) or sorted(mcer.DEFAULT_EXCLUDED_DIR_NAMES)
    proj_only = mcer._as_string_list(policy.get("project_only_excluded_dir_names"))
    proj_excluded_files = mcer._as_string_list(policy.get("project_excluded_file_refs"))

    proj_active = sorted(mcer._relative_set(
        REPO,
        mcer._active_files(REPO, excluded,
                           root_only_excluded_dir_names=proj_only,
                           excluded_file_refs=proj_excluded_files),
    ))
    pkg_root = REPO / "noemaforge"
    pkg_active = sorted(mcer._relative_set(pkg_root, mcer._active_files(pkg_root, excluded)))
    return proj_active, pkg_active


def _release_metadata() -> dict[str, str]:
    """Version-bearing manifest fields, derived from the release SoT (release.json)
    every run so the manifests never drift from the release surface. release.json
    carries the *promoted release baseline* (the version-QA gate asserts manifest
    metadata == release.json), which is deliberately distinct from the runtime
    RUNTIME_VERSION until the version promotion completes across all surfaces."""
    rj = json.loads((REPO / "release.json").read_text(encoding="utf-8-sig"))
    version = str(rj["version"])
    package = str(rj.get("package") or f"noemaforge_{version}_prelaunch")
    return {
        "runtime_base_version": version,
        "docs_overlay_version": version,
        "package_name": package,
        "version": version,
    }


def _write_manifest(rel: str, files: list[str], template_rel: str,
                    version_fields: dict[str, str]) -> None:
    # Evidence is untracked, so the manifest never pre-exists on a clean release
    # tree — seed the schema-only metadata (apiVersion/kind/notes) from the
    # committed template, then inject the version fields derived from release.json.
    obj = json.loads((TEMPLATES / template_rel).read_text(encoding="utf-8-sig"))
    for key in obj:
        if key in version_fields:
            obj[key] = version_fields[key]
    obj["generated_at"] = _now_iso()
    obj["file_count"] = len(files)
    obj["files"] = files
    _write(rel, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def regenerate() -> tuple[int, int]:
    _ensure_placeholders()
    proj_active, pkg_active = _active_sets()
    version_fields = _release_metadata()

    # 1. manifests — active SET (file names) + version fields from release.json.
    _write_manifest("MANIFEST.json", proj_active, "MANIFEST.template.json", version_fields)
    _write_manifest("noemaforge/docs/MANIFEST.json", pkg_active,
                    "docs-MANIFEST.template.json", version_fields)

    # 2. manifest hash sidecars — hash the (now final) manifests from disk.
    mh = _sha256_file(REPO / "MANIFEST.json")
    _write("MANIFEST.json.sha256", f"{mh}  MANIFEST.json\n")
    _write("MANIFEST.sha256", f"{mh}  MANIFEST.json\n")
    dh = _sha256_file(REPO / "noemaforge/docs/MANIFEST.json")
    _write("noemaforge/docs/MANIFEST.json.sha256", f"{dh}  MANIFEST.json\n")

    # 3. package SHA256SUMS — per-file working-tree hashes of the package active
    #    set (excludes itself); all referenced files are now final.
    pkg_root = REPO / "noemaforge"
    pkg_lines = "".join(
        f"{_sha256_file(pkg_root / r)}  {r}\n"
        for r in pkg_active if r != "checksums/SHA256SUMS"
    )
    _write("noemaforge/checksums/SHA256SUMS", pkg_lines)

    # 4. its sidecar.
    _write("SHA256SUMS.sha256",
           f"{_sha256_file(REPO / 'noemaforge/checksums/SHA256SUMS')}  noemaforge/checksums/SHA256SUMS\n")

    # 5. project SHA256SUMS last — lists every project active file except itself;
    #    nothing hashes it, so it closes the dependency order.
    proj_lines = "".join(
        f"{_sha256_file(REPO / r)}  {r}\n"
        for r in proj_active if r != "SHA256SUMS"
    )
    _write("SHA256SUMS", proj_lines)

    return len(proj_active), len(pkg_active)


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    proj, pkg = regenerate()
    print(f"regen_evidence: generated evidence (proj_active={proj} pkg_active={pkg})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
