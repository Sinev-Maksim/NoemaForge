#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/noema_release.py
Zone: runtime/release
Version: 0.33.0
Created: 2026-06-07
Modified: 2026-06-07
Purpose: Implement the verifiable release-manifest contract ("noema release pack" / "verify").
  `pack` builds a release manifest (schema: noemaforge/schemas/release-manifest.schema.json) by
  hashing every artifact under a root; `verify` validates a manifest's structure and confirms
  every artifact's SHA-256 matches the file on disk. A release is GO only when verify passes.
Inputs: a release root directory; a manifest dict/file; version + contract_epoch for pack.
Outputs: a manifest dict/JSON (pack); a structured verification result + exit code (verify).
Side effects: read-only for verify; pack only writes the manifest file when --out is given.
Tests: python3 -m unittest noemaforge/tests/test_noema_release.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Stdlib-only (hashlib/json/argparse) so release verification works on a bare host with no extra
dependencies, on the Linux target and the Windows/macOS control hosts alike.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

API_VERSION = "noemaforge.release-manifest/v1"
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

# Names never included in a release manifest (VCS / bytecode caches).
_EXCLUDED_DIR_NAMES = {".git", "__pycache__"}
_EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path, *, chunk_size: int = 1 << 20) -> str:
    """Return the hex SHA-256 of a file, streamed so large artifacts stay memory-bounded."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_artifact_files(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        parts = p.relative_to(root).parts
        if any(part in _EXCLUDED_DIR_NAMES for part in parts):
            continue
        if p.suffix in _EXCLUDED_SUFFIXES:
            continue
        yield p


def build_manifest(
    root: Path,
    *,
    version: str,
    contract_epoch: str,
    channel: Optional[str] = None,
    manifest_name: str = "release-manifest.json",
) -> Dict[str, Any]:
    """Build a release manifest by hashing every artifact under *root*.

    Paths are stored POSIX-relative to *root* for cross-platform stability. The output
    manifest file (``manifest_name``) is excluded if it already exists under root.
    """
    root = Path(root)
    artifacts: List[Dict[str, Any]] = []
    for p in _iter_artifact_files(root):
        rel = p.relative_to(root).as_posix()
        if rel == manifest_name:
            continue
        artifacts.append({"path": rel, "sha256": sha256_file(p), "bytes": p.stat().st_size})

    manifest: Dict[str, Any] = {
        "apiVersion": API_VERSION,
        "version": version,
        "contract_epoch": contract_epoch,
        "generated_at": _nowz(),
        "artifacts": artifacts,
    }
    if channel:
        manifest["channel"] = channel
    return manifest


def verify_manifest(
    manifest: Dict[str, Any],
    root: Path,
    *,
    require_signature: bool = False,
) -> Dict[str, Any]:
    """Verify a manifest's structure and every artifact's SHA-256 against files under *root*.

    Returns a structured result; ``ok`` is True only when there are zero errors. Read-only.
    """
    root = Path(root)
    errors: List[str] = []
    warnings: List[str] = []

    # Structural checks against the contract.
    if manifest.get("apiVersion") != API_VERSION:
        errors.append(f"apiVersion must be {API_VERSION!r}, got {manifest.get('apiVersion')!r}")
    version = manifest.get("version")
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        errors.append(f"version missing or malformed: {version!r}")
    if not manifest.get("contract_epoch"):
        errors.append("contract_epoch is required")
    if not manifest.get("generated_at"):
        errors.append("generated_at is required")

    artifacts = manifest.get("artifacts")
    checked = 0
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts must be a non-empty list")
        artifacts = []

    seen_paths: set = set()
    for i, art in enumerate(artifacts):
        if not isinstance(art, dict):
            errors.append(f"artifact[{i}] is not an object")
            continue
        path = art.get("path")
        digest = art.get("sha256")
        if not path or not isinstance(path, str):
            errors.append(f"artifact[{i}] missing path")
            continue
        if path in seen_paths:
            errors.append(f"duplicate artifact path: {path}")
        seen_paths.add(path)
        if not isinstance(digest, str) or not _SHA256_RE.match(digest):
            errors.append(f"{path}: sha256 missing or malformed")
            continue
        # Reject path traversal / absolute paths before touching the filesystem.
        target = (root / path)
        try:
            resolved = target.resolve()
            if root.resolve() not in resolved.parents and resolved != root.resolve():
                errors.append(f"{path}: resolves outside the release root")
                continue
        except OSError:
            errors.append(f"{path}: cannot resolve path")
            continue
        if not target.is_file():
            errors.append(f"{path}: listed in manifest but missing on disk")
            continue
        actual = sha256_file(target)
        checked += 1
        if actual != digest:
            errors.append(f"{path}: sha256 mismatch (manifest {digest[:12]}…, disk {actual[:12]}…)")
        else:
            bytes_expected = art.get("bytes")
            if isinstance(bytes_expected, int) and bytes_expected != target.stat().st_size:
                warnings.append(f"{path}: bytes mismatch (manifest {bytes_expected}, disk {target.stat().st_size})")

    # Signature handling: presence-only in 0.33.0 (full crypto verification is a later increment).
    signature = manifest.get("signature")
    if require_signature and not signature:
        errors.append("signature required but absent")
    elif signature:
        warnings.append("signature present but not cryptographically verified in this release")

    return {
        "ok": not errors,
        "version": version,
        "contract_epoch": manifest.get("contract_epoch"),
        "artifact_count": len(artifacts),
        "checked": checked,
        "errors": errors,
        "warnings": warnings,
    }


def format_human(result: Dict[str, Any]) -> str:
    lines = [
        f"NoemaForge release verify - version {result.get('version') or 'unknown'} "
        f"epoch {result.get('contract_epoch') or 'unknown'}",
        f"  artifacts: {result.get('artifact_count', 0)} listed, {result.get('checked', 0)} hashed",
    ]
    for w in result.get("warnings", []):
        lines.append(f"  [WARN] {w}")
    for e in result.get("errors", []):
        lines.append(f"  [FAIL] {e}")
    lines.append("OVERALL: VERIFIED" if result.get("ok") else "OVERALL: FAILED")
    return "\n".join(lines)


def _load_manifest(path: str) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    return data


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="noema release",
                                     description="Build and verify NoemaForge release manifests.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pack = sub.add_parser("pack", help="build a release manifest by hashing artifacts under --root")
    p_pack.add_argument("--root", required=True)
    p_pack.add_argument("--version", required=True)
    p_pack.add_argument("--contract-epoch", required=True)
    p_pack.add_argument("--channel", default=None)
    p_pack.add_argument("--out", default=None, help="write manifest JSON here (default: stdout)")

    p_verify = sub.add_parser("verify", help="verify a manifest's structure and artifact hashes")
    p_verify.add_argument("manifest")
    p_verify.add_argument("--root", required=True)
    p_verify.add_argument("--require-signature", action="store_true")
    p_verify.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "pack":
        manifest = build_manifest(Path(args.root), version=args.version,
                                  contract_epoch=args.contract_epoch, channel=args.channel)
        text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {args.out} ({len(manifest['artifacts'])} artifacts)")
        else:
            sys.stdout.write(text)
        return 0

    # verify
    try:
        manifest = _load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read manifest {args.manifest}: {exc}")
        return 1
    result = verify_manifest(manifest, Path(args.root), require_signature=args.require_signature)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_human(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
