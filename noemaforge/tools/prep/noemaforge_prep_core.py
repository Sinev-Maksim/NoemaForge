#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/prep/noemaforge_prep_core.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Cross-platform prep front door for Vault scan, inbox processing, metadata export and firstboot staging.
Inputs: Repo root, Lab/Vault/Library paths and model profile selection.
Outputs: JSON prep reports, metadata summaries and firstboot staging plans.
Side effects: Limited to requested Lab/Vault/Library/output paths.
Tests: noemaforge/tests/test_cross_platform_prep_core_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import process_inbox
import scan_library
import scan_vault


API_VERSION = "noemaforge.cross-platform-prep/v1"
PROFILE_NAMES = ["minimal", "balanced", "writer", "research", "gpu-heavy"]
BUCKET_KINDS = ["models", "adapters", "bundles", "datasets", "mirror_models"]


def nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def posix(path: Path | str) -> str:
    return str(path).replace(os.sep, "/")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_lab_root(repo_root: Path) -> Path:
    return (repo_root.parent / "noemaforge-lab").resolve()


def resolve_repo_root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return PACKAGE_ROOT.resolve()


def resolve_lab_paths(lab_root: Path) -> Dict[str, Path]:
    data = lab_root / "data"
    return {
        "lab_root": lab_root,
        "data_root": data,
        "library_root": data / "Library",
        "vault_root": data / "Vault",
        "workspace_root": data / "Workspace",
        "outbox_root": lab_root / "outbox",
    }


def ensure_lab_dirs(paths: Dict[str, Path]) -> None:
    for key in ["library_root", "vault_root", "workspace_root", "outbox_root"]:
        paths[key].mkdir(parents=True, exist_ok=True)


def _scanner_namespace(**kwargs: Any) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def verify_seed(repo_root: Path) -> Dict[str, Any]:
    required = [
        "tools/prep/process_inbox.py",
        "tools/prep/scan_vault.py",
        "tools/prep/scan_library.py",
        "tools/prep/noemaforge_prep_core.py",
        "configs/model-profiles.json",
        "src/firstboot_orchestrator.py",
        "bin/noemaforge",
    ]
    resolved: List[Dict[str, Any]] = []
    missing: List[str] = []
    for rel in required:
        path = repo_root / rel
        item = {"ref": rel, "path": posix(path), "exists": path.exists()}
        resolved.append(item)
        if not path.exists():
            missing.append(rel)
    return {
        "apiVersion": API_VERSION,
        "kind": "PrepSeedVerification",
        "created_at": nowz(),
        "repo_root": posix(repo_root),
        "ok": not missing,
        "missing": missing,
        "resolved": resolved,
    }


def run_lab(repo_root: Path, lab_root: Path, *, auto_manifest: bool, full_hash: bool) -> Dict[str, Any]:
    paths = resolve_lab_paths(lab_root)
    ensure_lab_dirs(paths)

    inbox_summary = {
        "apiVersion": "noemaforge.inbox/v1",
        "kind": "InboxProcessSummary",
        "created_at": nowz(),
        "results": [
            process_inbox.process_library(str(paths["library_root"])),
            process_inbox.process_vault(str(paths["vault_root"])),
        ],
    }
    outbox = paths["outbox_root"] / "prep"
    write_json(outbox / "inbox_process_summary.json", inbox_summary)

    library_summary = scan_library.scan(
        _scanner_namespace(
            library_root=str(paths["library_root"]),
            sources_dir="sources",
            db_name="library_index.sqlite",
            snapshot_name="library_catalog.seed.json",
            auto_manifest=auto_manifest,
            full_hash=full_hash,
        )
    )
    vault_summary = scan_vault.scan(
        _scanner_namespace(
            vault_root=str(paths["vault_root"]),
            db_name="vault_index.sqlite",
            snapshot_name="model_registry.seed.json",
            auto_manifest=auto_manifest,
            full_hash=full_hash,
        )
    )
    summary = {
        "apiVersion": API_VERSION,
        "kind": "CrossPlatformPrepRun",
        "created_at": nowz(),
        "repo_root": posix(repo_root),
        "lab_root": posix(lab_root),
        "auto_manifest": bool(auto_manifest),
        "full_hash": bool(full_hash),
        "outputs": {
            "inbox_summary": posix(outbox / "inbox_process_summary.json"),
            "library_index": posix(paths["library_root"] / "library_index.sqlite"),
            "library_catalog": posix(paths["library_root"] / "library_catalog.seed.json"),
            "vault_index": posix(paths["vault_root"] / "vault_index.sqlite"),
            "model_registry_seed": posix(paths["vault_root"] / "model_registry.seed.json"),
        },
        "inbox": inbox_summary,
        "library": library_summary,
        "vault": vault_summary,
    }
    write_json(outbox / "cross_platform_prep_run.json", summary)
    return summary


def bucket_roots(vault_root: Path) -> Dict[str, List[Path]]:
    top = [path for path in vault_root.iterdir() if path.is_dir()] if vault_root.exists() else []
    roots: Dict[str, List[Path]] = {
        "models": sorted([path for path in top if path.name.lower().startswith("models")]),
        "adapters": sorted([path for path in top if path.name.lower().startswith("adapters")]),
        "bundles": sorted([path for path in top if path.name.lower().startswith("bundles")]),
        "datasets": sorted([path for path in top if path.name.lower().startswith("datasets")]),
        "mirror_models": [],
    }
    mirror = vault_root / "download-mirror"
    if mirror.exists():
        roots["mirror_models"] = sorted([path for path in mirror.iterdir() if path.is_dir() and path.name.lower().startswith("models")])
    return roots


def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted([path for path in root.rglob("*") if path.is_file()])


def rel_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def proposed_inbox_dest(vault_root: Path, rel_in: str) -> str:
    rel = rel_in.replace("\\", "/")
    top = rel.split("/", 1)[0].lower() if rel else ""
    if top.startswith(("models", "adapters", "bundles")) or top in {"datasets", "manifests"}:
        return rel
    ext = Path(rel).suffix.lower()
    base = Path(rel).name.lower()
    if ext == ".gguf":
        return f"{'models-gguf' if (vault_root / 'models-gguf').is_dir() else 'models'}/inbox/{rel}"
    if ext in {".safetensors", ".bin", ".pt", ".pth", ".onnx"}:
        return f"models/inbox/{rel}"
    if ext in {".zip", ".tar", ".tgz", ".gz"}:
        return f"bundles/inbox/{rel}"
    if ext in {".json", ".yml", ".yaml"} and "manifest" in base:
        return f"manifests/inbox/{rel}"
    return f"misc/inbox/{rel}"


def file_record(root: Path, path: Path, *, include_hashes: bool) -> Dict[str, Any]:
    stat = path.stat()
    item: Dict[str, Any] = {
        "rel": rel_posix(root, path),
        "name": path.name,
        "size": int(stat.st_size),
        "ext": path.suffix.lower(),
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    if include_hashes:
        import hashlib

        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        item["sha256"] = h.hexdigest()
    return item


def export_vault_metadata(repo_root: Path, vault_root: Path, out_dir: Path, *, run_scan_vault: bool, full_hash: bool) -> Dict[str, Any]:
    if not vault_root.exists():
        raise FileNotFoundError(f"Vault root not found: {vault_root}")
    out_dir.mkdir(parents=True, exist_ok=True)
    if run_scan_vault:
        scan_vault.scan(
            _scanner_namespace(
                vault_root=str(vault_root),
                db_name="vault_index.sqlite",
                snapshot_name="model_registry.seed.json",
                auto_manifest=True,
                full_hash=full_hash,
            )
        )

    roots = bucket_roots(vault_root)
    inbox_root = vault_root / "inbox"
    inbox_preview = [
        {
            "rel": rel_posix(inbox_root, path),
            "proposed_dest": proposed_inbox_dest(vault_root, rel_posix(inbox_root, path)),
            "size": int(path.stat().st_size),
            "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        for path in iter_files(inbox_root)
    ] if inbox_root.exists() else []

    counts: Dict[str, int] = {}
    inventory: Dict[str, List[Dict[str, Any]]] = {}
    for kind in BUCKET_KINDS:
        inventory[kind] = []
        for root in roots[kind]:
            files = [file_record(root, path, include_hashes=full_hash) for path in iter_files(root)]
            inventory[kind].append({"root": posix(root.resolve()), "file_count": len(files), "files": files})
            counts[f"{kind}:{root.name}"] = len(files)

    summary = {
        "apiVersion": "noemaforge.disk_e_metadata/v1",
        "generated_at": nowz(),
        "repo_root": posix(repo_root),
        "vault_root": posix(vault_root.resolve()),
        "bucket_roots": {kind: [posix(path.resolve()) for path in roots[kind]] for kind in BUCKET_KINDS},
        "special_paths": {
            "queue": posix(vault_root / "_queue"),
            "inbox": posix(inbox_root),
            "manifests": posix(vault_root / "manifests"),
            "download_mirror": posix(vault_root / "download-mirror"),
            "hf_home": posix(vault_root / "hf-home"),
        },
        "counts": counts,
        "inbox_preview": inbox_preview,
        "inventory": inventory,
    }
    write_json(out_dir / "vault.disk_e.metadata.json", summary)
    write_text_summary(out_dir / "vault.disk_e.summary.txt", summary)
    write_roots_csv(out_dir / "vault.disk_e.roots.csv", summary)
    return summary


def write_text_summary(path: Path, summary: Dict[str, Any]) -> None:
    lines = [f"Generated: {summary.get('generated_at')}", f"VaultRoot : {summary.get('vault_root')}", "", "Bucket roots:"]
    for kind, roots in (summary.get("bucket_roots") or {}).items():
        for root in roots:
            lines.append(f"  [{kind}] {root}")
    lines.extend(["", "Counts:"])
    for key, value in sorted((summary.get("counts") or {}).items()):
        lines.append(f"  {key} = {value}")
    lines.extend(["", "Inbox preview:"])
    for row in (summary.get("inbox_preview") or [])[:200]:
        lines.append(f"  {row.get('rel')} -> {row.get('proposed_dest')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_roots_csv(path: Path, summary: Dict[str, Any]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["kind", "root", "file_count"])
        writer.writeheader()
        for kind, roots in (summary.get("bucket_roots") or {}).items():
            for root in roots:
                writer.writerow({"kind": kind, "root": root, "file_count": (summary.get("counts") or {}).get(f"{kind}:{Path(root).name}", 0)})


def compare_metadata(repo_root: Path, real_vault_root: Path, lab_vault_root: Path, out_dir: Path, *, run_scan_vault: bool) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for label, root in [("real", real_vault_root), ("lab", lab_vault_root)]:
        if run_scan_vault and root.exists():
            scan_vault.scan(_scanner_namespace(vault_root=str(root), db_name="vault_index.sqlite", snapshot_name="model_registry.seed.json", auto_manifest=True, full_hash=False))
        roots = bucket_roots(root)
        counts = {f"{kind}:{path.name}": len(list(iter_files(path))) for kind in BUCKET_KINDS for path in roots[kind]}
        records.append(
            {
                "label": label,
                "exists": root.exists(),
                "vault_root": posix(root),
                "bucket_roots": {kind: [posix(path) for path in roots[kind]] for kind in BUCKET_KINDS},
                "counts": counts,
                "has_models_gguf": (root / "models-gguf").exists(),
                "has_download_mirror": (root / "download-mirror").exists(),
            }
        )
    doc = {
        "apiVersion": "noemaforge.disk_e_compare/v1",
        "generated_at": nowz(),
        "repo_root": posix(repo_root),
        "compared": records,
        "recommendation": "Prefer real Vault when it exists; otherwise stage from lab Vault.",
    }
    write_json(out_dir / "vault.disk_e.compare.json", doc)
    lines = [f"Generated: {doc['generated_at']}", ""]
    for record in records:
        lines.append(f"[{record['label']}] VaultRoot : {record['vault_root']}")
        lines.append(f"  exists              : {record['exists']}")
        lines.append(f"  has models-gguf     : {record['has_models_gguf']}")
        lines.append(f"  has download-mirror : {record['has_download_mirror']}")
    (out_dir / "vault.disk_e.compare.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return doc


def firstboot_stage(repo_root: Path, lab_root: Path, *, model_profile: str, auto_manifest: bool, dry_run: bool) -> Dict[str, Any]:
    paths = resolve_lab_paths(lab_root)
    if not dry_run:
        run_lab(repo_root, lab_root, auto_manifest=auto_manifest, full_hash=False)
    outbox = paths["outbox_root"] / "prep"
    outbox.mkdir(parents=True, exist_ok=True)
    vault_root = paths["vault_root"]
    plan = {
        "apiVersion": API_VERSION,
        "kind": "FirstbootStagingPlan",
        "created_at": nowz(),
        "repo_root": posix(repo_root),
        "lab_root": posix(lab_root),
        "vault_root": posix(vault_root),
        "model_profile": model_profile,
        "dry_run": bool(dry_run),
        "manual_command": f"sudo bash {posix(repo_root / 'tools/prep/noemaforge-firstboot-from-share.sh')} --vault-root {posix(vault_root)} --model-profile {model_profile}",
        "staging_artifacts": {
            "vault_index": posix(vault_root / "vault_index.sqlite"),
            "model_registry_seed": posix(vault_root / "model_registry.seed.json"),
            "inbox_summary": posix(outbox / "inbox_process_summary.json"),
        },
        "windows_required": False,
        "auto_download": False,
    }
    write_json(outbox / "firstboot_staging_plan.json", plan)
    return plan


def check(repo_root: Path) -> Dict[str, Any]:
    seed = verify_seed(repo_root)
    scripts = [
        repo_root / "tools/prep/noemaforge_prep_core.py",
        repo_root / "tools/prep/scan_vault.py",
        repo_root / "tools/prep/process_inbox.py",
        repo_root / "tools/prep/scan_library.py",
    ]
    missing = [posix(path) for path in scripts if not path.exists()]
    return {
        "apiVersion": API_VERSION,
        "kind": "PrepCoreCheck",
        "created_at": nowz(),
        "ok": seed["ok"] and not missing,
        "seed": seed,
        "python_sources": [posix(path) for path in scripts],
        "missing": missing,
    }


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", default="", help="Path to the NoemaForge package root.")


def add_lab_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--lab-root", default="", help="Path to noemaforge-lab root.")
    parser.add_argument("--auto-manifest", action="store_true")
    parser.add_argument("--full-hash", action="store_true")


def emit(payload: Dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok", True) is not False else 1


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NoemaForge cross-platform prep core")
    sub = ap.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify-seed")
    add_common(p_verify)

    p_check = sub.add_parser("check")
    add_common(p_check)

    p_lab = sub.add_parser("lab")
    add_common(p_lab)
    add_lab_args(p_lab)

    p_firstboot = sub.add_parser("firstboot")
    add_common(p_firstboot)
    add_lab_args(p_firstboot)
    p_firstboot.add_argument("--model-profile", default="minimal", choices=PROFILE_NAMES)
    p_firstboot.add_argument("--dry-run", action="store_true")

    p_meta = sub.add_parser("export-vault-metadata")
    add_common(p_meta)
    p_meta.add_argument("--vault-root", required=True)
    p_meta.add_argument("--out-dir", required=True)
    p_meta.add_argument("--run-scan-vault", action="store_true")
    p_meta.add_argument("--full-hash", action="store_true")

    p_compare = sub.add_parser("export-compare-metadata")
    add_common(p_compare)
    p_compare.add_argument("--real-vault-root", required=True)
    p_compare.add_argument("--lab-vault-root", required=True)
    p_compare.add_argument("--out-dir", required=True)
    p_compare.add_argument("--run-scan-vault", action="store_true")

    args = ap.parse_args(argv)
    repo_root = resolve_repo_root(args.repo_root)
    lab_root = Path(getattr(args, "lab_root", "") or default_lab_root(repo_root)).expanduser().resolve()

    if args.command == "verify-seed":
        return emit(verify_seed(repo_root))
    if args.command == "check":
        return emit(check(repo_root))
    if args.command == "lab":
        return emit(run_lab(repo_root, lab_root, auto_manifest=bool(args.auto_manifest), full_hash=bool(args.full_hash)))
    if args.command == "firstboot":
        return emit(firstboot_stage(repo_root, lab_root, model_profile=args.model_profile, auto_manifest=bool(args.auto_manifest), dry_run=bool(args.dry_run)))
    if args.command == "export-vault-metadata":
        return emit(export_vault_metadata(repo_root, Path(args.vault_root).expanduser().resolve(), Path(args.out_dir).expanduser().resolve(), run_scan_vault=bool(args.run_scan_vault), full_hash=bool(args.full_hash)))
    if args.command == "export-compare-metadata":
        return emit(compare_metadata(repo_root, Path(args.real_vault_root).expanduser().resolve(), Path(args.lab_vault_root).expanduser().resolve(), Path(args.out_dir).expanduser().resolve(), run_scan_vault=bool(args.run_scan_vault)))
    ap.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
