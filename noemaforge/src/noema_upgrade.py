#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/noema_upgrade.py
Zone: runtime/upgrade
Version: 0.33.0
Created: 2026-06-07
Modified: 2026-06-07
Purpose: Plan and apply an in-place NoemaForge version upgrade by replacing install-tree files
  from an extracted incoming release, while GUARANTEEING that user/machine state is never lost.
  Safety invariants: (1) nothing is ever deleted; (2) protected paths (context.md, and anything
  under data/memory/sessions/secrets/vault/state/logs, plus token/secret/key files) are never
  overwritten; (3) only managed code/doc extensions are replaced; (4) dry-run is the default.
Inputs: a current install root; an extracted incoming-release root; optional extra preserve globs.
Outputs: a structured upgrade plan (replace/add/preserve/skip) and, with --apply, the actions taken.
Side effects: read-only in plan/dry-run; copies incoming files into the install root only on --apply.
Tests: python3 -m unittest noemaforge/tests/test_noema_upgrade.py
Notes: Code comments are English-only. This module performs NO GPU/model/display actions and never
  removes files, so it is display-safe and data-safe by construction.
=== End NoemaForge File Header ===

Design: NoemaForge separates the install root (code/docs — upgraded here) from the data root
(machine state — never part of an upgrade, resolved separately by platform_paths). This planner
additionally protects named state that may live inside the install tree.
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

# Hard cap on a downloaded release archive (defends against a hostile/oversized response).
DEFAULT_MAX_ARCHIVE_BYTES = 500 * 1024 * 1024

# Managed extensions: the only files an upgrade is allowed to overwrite in place.
REPLACE_SUFFIXES = {
    ".py", ".sh", ".md", ".yaml", ".yml", ".json", ".html", ".css", ".js",
    ".txt", ".service", ".cfg", ".ini", ".toml", ".rego",
}

# Directory components whose entire subtree is user/machine state — never touched.
PRESERVE_DIR_PARTS = {
    ".git", "data", "memory", "sessions", "secrets", "tokens", "vault", "state",
    "logs", "var", "__pycache__",
}
# Exact protected basenames (machine state / secrets that may sit in the install tree).
PRESERVE_NAMES = {"context.md", "token", "secret", "credentials", "id_rsa", ".env"}
# Protected suffixes (local overrides, keys, env, token/secret material).
# NOTE: matched on the full suffix only — a release file such as
# ``capability-token.schema.json`` is NOT a secret and stays upgradable.
PRESERVE_SUFFIXES = {".local", ".key", ".pem", ".env", ".token", ".secret", ".credentials"}


def _is_protected(rel_parts: Sequence[str]) -> bool:
    """True if a path (given as relative parts) is user/machine state that must never be
    overwritten or deleted by an upgrade. Protection is by directory subtree, exact basename,
    or sensitive suffix — never by loose substring, so normal code/schema files are upgradable."""
    if any(part in PRESERVE_DIR_PARTS for part in rel_parts):
        return True
    name = rel_parts[-1] if rel_parts else ""
    if name in PRESERVE_NAMES:
        return True
    if Path(name).suffix in PRESERVE_SUFFIXES:
        return True
    return False


def _rel_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file():
            yield p.relative_to(root)


def plan_upgrade(
    current_root: Path,
    incoming_root: Path,
    *,
    preserve_globs: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Classify every incoming file into replace / add / preserve / skip_unmanaged.

    Never schedules a delete. Protected paths are reported under ``preserve`` and are never
    overwritten even when the incoming release ships a different version of them.
    """
    current_root = Path(current_root)
    incoming_root = Path(incoming_root)
    preserve_globs = list(preserve_globs or [])

    replace: List[str] = []
    add: List[str] = []
    preserve: List[str] = []
    skip_unmanaged: List[str] = []

    for rel in _rel_files(incoming_root):
        rel_posix = rel.as_posix()
        parts = rel.parts
        protected = _is_protected(parts) or any(rel.match(g) for g in preserve_globs)
        exists = (current_root / rel).is_file()

        if protected:
            # Never overwrite protected state, whether or not it exists in current.
            preserve.append(rel_posix)
            continue
        if exists:
            if rel.suffix in REPLACE_SUFFIXES:
                replace.append(rel_posix)
            else:
                skip_unmanaged.append(rel_posix)
        else:
            add.append(rel_posix)

    # Files that exist only in the current install are KEPT (upgrade never deletes).
    current_only = sorted(
        rel.as_posix() for rel in _rel_files(current_root)
        if not (incoming_root / rel).exists()
    )

    return {
        "current_root": str(current_root),
        "incoming_root": str(incoming_root),
        "replace": sorted(replace),
        "add": sorted(add),
        "preserve": sorted(preserve),
        "skip_unmanaged": sorted(skip_unmanaged),
        "kept_current_only": current_only,
        "summary": {
            "replace": len(replace),
            "add": len(add),
            "preserve": len(preserve),
            "skip_unmanaged": len(skip_unmanaged),
            "kept_current_only": len(current_only),
        },
    }


def apply_plan(plan: Dict[str, Any], *, dry_run: bool = True) -> Dict[str, Any]:
    """Apply replace + add actions from a plan. Dry-run by default: pass dry_run=False to write.

    Only copies incoming → current for the ``replace`` and ``add`` lists. Never touches the
    ``preserve`` / ``skip_unmanaged`` / ``kept_current_only`` sets, and never deletes anything.
    """
    current_root = Path(plan["current_root"])
    incoming_root = Path(plan["incoming_root"])
    applied: List[str] = []
    for rel in list(plan["replace"]) + list(plan["add"]):
        src = incoming_root / rel
        dst = current_root / rel
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        applied.append(rel)
    return {
        "dry_run": dry_run,
        "applied": sorted(applied),
        "applied_count": len(applied),
        "preserved_count": len(plan["preserve"]),
    }


def format_plan(plan: Dict[str, Any]) -> str:
    s = plan["summary"]
    lines = [
        f"NoemaForge upgrade plan: {plan['incoming_root']} -> {plan['current_root']}",
        f"  replace={s['replace']} add={s['add']} preserve={s['preserve']} "
        f"skip_unmanaged={s['skip_unmanaged']} kept_current_only={s['kept_current_only']}",
        "  (upgrade never deletes; protected user/machine state is never overwritten)",
    ]
    for rel in plan["preserve"][:10]:
        lines.append(f"  [preserve] {rel}")
    if len(plan["preserve"]) > 10:
        lines.append(f"  [preserve] … +{len(plan['preserve']) - 10} more")
    return "\n".join(lines)


# ── GitHub-native fetch (resolve + fail-safe archive download + safe extract) ──────────
#
# A "Fetcher" is any callable url -> bytes; the default uses urllib. Injecting it keeps the
# network layer deterministically testable and lets callers add proxies/auth.
Fetcher = Callable[[str], bytes]


def _default_fetcher(url: str, *, max_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "NoemaForge-upgrade",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req) as resp:  # noqa: S310 - https GitHub URLs only
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"archive exceeds size cap ({max_bytes} bytes)")
    return data


def resolve_release(repo: str, version: Optional[str] = None, *,
                    fetcher: Optional[Fetcher] = None) -> Dict[str, str]:
    """Resolve a GitHub release to a tag + downloadable tarball URL.

    ``version`` None resolves the repo's latest release; otherwise the given tag is used.
    Network access goes through *fetcher* (injectable for tests). GitHub-native, with the
    codeload tarball as the fail-safe archive source.
    """
    fetch = fetcher or _default_fetcher
    if "/" not in repo:
        raise ValueError("repo must be 'owner/name'")
    if version is None:
        meta = json.loads(fetch(f"https://api.github.com/repos/{repo}/releases/latest").decode("utf-8"))
        tag = meta.get("tag_name")
        if not tag:
            raise ValueError("latest release has no tag_name")
        version = str(tag)
    archive_url = f"https://api.github.com/repos/{repo}/tarball/{version}"
    return {"version": version, "archive_url": archive_url, "kind": "tar"}


def _is_within(base: Path, target: Path) -> bool:
    try:
        base_r = base.resolve()
        target_r = target.resolve()
    except OSError:
        return False
    return base_r == target_r or base_r in target_r.parents


def _safe_members_tar(tf: tarfile.TarFile, dest: Path):
    for m in tf.getmembers():
        # Reject symlinks/hardlinks/devices and any path escaping dest (zip-slip / tar-slip).
        if m.issym() or m.islnk() or m.isdev():
            raise ValueError(f"unsafe archive member type: {m.name}")
        if m.name.startswith("/") or ".." in Path(m.name).parts:
            raise ValueError(f"unsafe archive member path: {m.name}")
        if not _is_within(dest, dest / m.name):
            raise ValueError(f"archive member escapes destination: {m.name}")
        yield m


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path):
    for name in zf.namelist():
        if name.startswith("/") or ".." in Path(name).parts or not _is_within(dest, dest / name):
            raise ValueError(f"unsafe archive member path: {name}")
    zf.extractall(dest)


def fetch_and_extract(archive_url: str, dest: Path, *, fetcher: Optional[Fetcher] = None,
                      max_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES) -> Path:
    """Download an archive and extract it under *dest*, guarding against path traversal.

    Returns the extracted top-level directory (GitHub archives nest everything under a single
    ``owner-repo-sha/`` folder). Never writes outside *dest*; never follows archive symlinks.
    """
    fetch = fetcher or (lambda u: _default_fetcher(u, max_bytes=max_bytes))
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    blob = fetch(archive_url)
    if len(blob) > max_bytes:
        raise ValueError(f"archive exceeds size cap ({max_bytes} bytes)")

    bio = io.BytesIO(blob)
    if zipfile.is_zipfile(bio):
        bio.seek(0)
        with zipfile.ZipFile(bio) as zf:
            _safe_extract_zip(zf, dest)
    else:
        bio.seek(0)
        with tarfile.open(fileobj=bio, mode="r:*") as tf:
            tf.extractall(dest, members=list(_safe_members_tar(tf, dest)), filter="data")

    entries = [p for p in dest.iterdir() if p.is_dir()]
    return entries[0] if len(entries) == 1 else dest


def run_upgrade(current_root: Path, repo: str, *, version: Optional[str] = None,
                manifest_name: str = "release-manifest.json", apply: bool = False,
                allow_unverified: bool = False, preserve_globs: Optional[Sequence[str]] = None,
                fetcher: Optional[Fetcher] = None, dest: Optional[Path] = None) -> Dict[str, Any]:
    """End-to-end in-place upgrade: fetch a GitHub release -> verify its signed manifest ->
    plan -> apply (dry-run by default).

    Aborts BEFORE planning/applying if the release manifest fails verification (or is absent and
    --allow-unverified was not given), so an unverified release is never installed. Display-safe:
    file operations only (no GPU/model/display); never deletes or overwrites protected state.
    """
    import tempfile
    current_root = Path(current_root)
    if dest is None:
        dest = tempfile.mkdtemp(prefix="noema-upgrade-")

    rel = resolve_release(repo, version, fetcher=fetcher)
    incoming = fetch_and_extract(rel["archive_url"], Path(dest), fetcher=fetcher)

    # Verify the signed release manifest before touching the install.
    verified: Optional[bool] = None
    manifest_path = Path(incoming) / manifest_name
    if manifest_path.is_file():
        import noema_release
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {"ok": False, "stage": "verify", "version": rel["version"],
                    "verify_errors": [f"unreadable manifest: {exc}"], "incoming": str(incoming)}
        vres = noema_release.verify_manifest(manifest, Path(incoming))
        verified = bool(vres.get("ok"))
        if not verified:
            return {"ok": False, "stage": "verify", "version": rel["version"],
                    "verify_errors": vres.get("errors", []), "incoming": str(incoming)}
    elif not allow_unverified:
        return {"ok": False, "stage": "verify", "version": rel["version"],
                "verify_errors": [f"no {manifest_name} in release; pass --allow-unverified to proceed"],
                "incoming": str(incoming)}

    plan = plan_upgrade(current_root, Path(incoming), preserve_globs=preserve_globs)
    result = apply_plan(plan, dry_run=not apply)
    return {"ok": True, "stage": "apply" if apply else "plan", "version": rel["version"],
            "verified": verified, "plan_summary": plan["summary"], "result": result,
            "incoming": str(incoming)}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="noema upgrade",
        description="Plan/apply an in-place upgrade, preserving user/machine state. "
                    "Display-safe: performs no GPU/model/display actions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "apply"):
        sp = sub.add_parser(name, help=f"{name} an upgrade")
        sp.add_argument("--current", required=True, help="current install root")
        sp.add_argument("--incoming", required=True, help="extracted incoming-release root")
        sp.add_argument("--preserve", action="append", default=[],
                        help="extra glob (relative) to protect; repeatable")
        sp.add_argument("--json", action="store_true")
        if name == "apply":
            sp.add_argument("--apply", action="store_true",
                            help="actually write changes (default is dry-run)")

    p_fetch = sub.add_parser("fetch", help="download + extract a GitHub release for upgrade")
    p_fetch.add_argument("--repo", required=True, help="GitHub 'owner/name'")
    p_fetch.add_argument("--version", default=None, help="tag to fetch (default: latest release)")
    p_fetch.add_argument("--dest", required=True, help="directory to extract into")
    p_fetch.add_argument("--json", action="store_true")

    p_run = sub.add_parser("run", help="fetch + verify + plan + apply an upgrade end-to-end")
    p_run.add_argument("--current", required=True, help="current install root")
    p_run.add_argument("--repo", required=True, help="GitHub 'owner/name'")
    p_run.add_argument("--version", default=None, help="tag to fetch (default: latest release)")
    p_run.add_argument("--manifest-name", default="release-manifest.json")
    p_run.add_argument("--apply", action="store_true", help="write changes (default is dry-run)")
    p_run.add_argument("--allow-unverified", action="store_true",
                       help="proceed even if the release ships no signed manifest (UNSAFE)")
    p_run.add_argument("--preserve", action="append", default=[])
    p_run.add_argument("--dest", default=None, help="extract dir (default: a temp dir)")
    p_run.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            res = run_upgrade(Path(args.current), args.repo, version=args.version,
                              manifest_name=args.manifest_name, apply=args.apply,
                              allow_unverified=args.allow_unverified,
                              preserve_globs=args.preserve,
                              dest=Path(args.dest) if args.dest else None)
        except (OSError, ValueError, urllib.error.URLError,
                tarfile.TarError, zipfile.BadZipFile) as exc:
            print(f"FAIL: upgrade failed: {exc}")
            return 1
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif not res["ok"]:
            print(f"FAIL [{res['stage']}]: " + "; ".join(res.get("verify_errors", [])))
        else:
            s = res["plan_summary"]
            mode = "APPLIED" if args.apply else "DRY-RUN (no changes written; pass --apply)"
            print(f"upgrade {args.repo}@{res['version']} verified={res['verified']} -> {mode}: "
                  f"replace={s['replace']} add={s['add']} preserve={s['preserve']}")
        return 0 if res["ok"] else 1

    if args.command == "fetch":
        try:
            rel = resolve_release(args.repo, args.version)
            root = fetch_and_extract(rel["archive_url"], Path(args.dest))
        except (OSError, ValueError, urllib.error.URLError,
                tarfile.TarError, zipfile.BadZipFile) as exc:
            # Corrupt / non-archive responses surface as a clean FAIL, not a traceback.
            print(f"FAIL: fetch failed: {exc}")
            return 1
        if args.json:
            print(json.dumps({"version": rel["version"], "extracted_root": str(root)},
                             indent=2, ensure_ascii=False))
        else:
            print(f"fetched {args.repo}@{rel['version']} -> {root}")
        return 0

    plan = plan_upgrade(Path(args.current), Path(args.incoming), preserve_globs=args.preserve)

    if args.command == "plan":
        print(json.dumps(plan, indent=2, ensure_ascii=False) if args.json else format_plan(plan))
        return 0

    # apply
    result = apply_plan(plan, dry_run=not args.apply)
    if args.json:
        print(json.dumps({"plan": plan["summary"], "result": result}, indent=2, ensure_ascii=False))
    else:
        print(format_plan(plan))
        mode = "APPLIED" if not result["dry_run"] else "DRY-RUN (no changes written; pass --apply)"
        print(f"  {mode}: {result['applied_count']} files, {result['preserved_count']} preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
