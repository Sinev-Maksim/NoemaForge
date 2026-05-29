#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/toolvault.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/toolvault.py
# Purpose: Provide the module 'toolvault'.
# Invoked by / imported from:
#   - src/bundles.py
#   - src/knowledge/embedding_worker.py
#   - src/knowledge_maintainer.py
#   - src/localgateway.py
#   - src/localgw_connectors/octoprint.py
#   - src/nids_lite.py
#   - src/offline_apt.py
#   - src/plugin_runner.py
#   - src/prestart.py
#   - src/webgateway.py
# Public API / entry functions:
#   - sha256_file
#   - load_yaml
#   - dump_yaml
#   - vault_paths
#   - trust_paths
#   - bundle_paths
#   - ensure_signing_keypair
#   - time_nowz
#   - load_trusted_keys
#   - sign_manifest_inplace
#   - verify_manifest_signature
#   - verify_bundle_attestation
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/toolvault, noemaforge.supplychain/v1
#   - Imports: __future__, base64, hashlib, json, os, tarfile, typing, yaml
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""toolvault.py (v0.19.0)

Minimal ToolVault helpers + supply-chain attestation.

ToolVault is the offline supply-chain anchor for:
  - bundle tools/plugins (artifacts pinned by sha256 + manifest)
  - optional offline apt repos / driver vault in future

Design goals:
  - boring, auditable, deterministic
  - deny-by-default for un-attested tools
  - keep signature support optional (prefer/require/off)

Signature model
---------------
We support an Ed25519 signature embedded inside the bundle manifest:

  signing:
    key_id: toolvault-local-<fingerprint>
    algorithm: ed25519
    sig_b64: <base64>

The signed payload is the canonical JSON form of the manifest *without* the
"signing" field.

Trusted public keys live under ToolVault trust directory.
Private key is generated locally (pre-start) and never exposed to roles.

IMPORTANT:
- sha256 pinning is still required for high/critical tools.
- signature is a defense-in-depth layer to catch tampering and to make
  supply-chain approvals explicit.
"""


import base64
import hashlib
import json
import os
import tarfile
from typing import Any, Dict, Optional, Tuple

import yaml


# === NoemaForge Autodoc Function Header ===
# Function: sha256_file(path: str)
# Purpose: Implement the routine 'sha256 file'.
# Inputs:
#   - path: str
# Called by:
#   - src/knowledge_maintainer.py
#   - src/offline_apt.py
#   - src/webgateway.py
#   - tools/prep/scan_library.py
#   - tools/prep/scan_vault.py
# Calls:
#   - sha256, hexdigest, open, iter, update, read
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - chunk, f, h
# === End NoemaForge Autodoc Function Header ===
def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: load_yaml(path: str)
# Purpose: Implement the routine 'load yaml'.
# Inputs:
#   - path: str
# Called by:
#   - src/bundles.py
#   - src/knowledge/embedding_worker.py
#   - src/knowledge_maintainer.py
#   - src/localgateway.py
#   - src/localgw_connectors/octoprint.py
#   - src/nids_lite.py
#   - src/plugin_runner.py
#   - src/webgateway.py
# Calls:
#   - open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# === NoemaForge Autodoc Function Header ===
# Function: dump_yaml(obj: Dict[str, Any], path: str)
# Purpose: Implement the routine 'dump yaml'.
# Inputs:
#   - obj: Dict[str, Any]
#   - path: str
# Called by:
#   - src/webgateway.py
# Calls:
#   - makedirs, dirname, open, safe_dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def dump_yaml(obj: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True)


# === NoemaForge Autodoc Function Header ===
# Function: vault_paths(policy: Dict[str, Any])
# Purpose: Implement the routine 'vault paths'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - src/webgateway.py
# Calls:
#   - str, isinstance, get, join
# Returns / emits: Tuple[str, str, str]
# Key locals:
#   - artifacts, manifests, root, tv
# === End NoemaForge Autodoc Function Header ===
def vault_paths(policy: Dict[str, Any]) -> Tuple[str, str, str]:
    tv = (policy.get("tool_vault") or {}) if isinstance(policy, dict) else {}
    root = str(tv.get("root") or "/var/lib/noemaforge/toolvault")
    manifests = str(tv.get("manifests_dir") or os.path.join(root, "manifests"))
    artifacts = str(tv.get("artifacts_dir") or os.path.join(root, "artifacts"))
    return root, manifests, artifacts


# === NoemaForge Autodoc Function Header ===
# Function: trust_paths(policy: Dict[str, Any])
# Purpose: Implement the routine 'trust paths'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, isinstance, join, get
# Returns / emits: Tuple[str, str, str]
# Key locals:
#   - keys_file, priv_file, root, trust_dir, tv
# === End NoemaForge Autodoc Function Header ===
def trust_paths(policy: Dict[str, Any]) -> Tuple[str, str, str]:
    tv = (policy.get("tool_vault") or {}) if isinstance(policy, dict) else {}
    root = str(tv.get("root") or "/var/lib/noemaforge/toolvault")
    trust_dir = str(tv.get("trust_dir") or os.path.join(root, "trust"))
    keys_file = str(tv.get("trusted_keys_file") or "trusted_keys.json")
    priv_file = str(tv.get("signing_key_file") or "toolvault_signing_ed25519.pem")
    return trust_dir, os.path.join(trust_dir, keys_file), os.path.join(trust_dir, priv_file)


# === NoemaForge Autodoc Function Header ===
# Function: bundle_paths(policy: Dict[str, Any], bundle_id: str, manifest_path: str = '', artifact_sha256: str = '', artifact_path: str = '')
# Purpose: Implement the routine 'bundle paths'.
# Inputs:
#   - policy: Dict[str, Any]
#   - bundle_id: str
#   - manifest_path: str = ''
#   - artifact_sha256: str = ''
#   - artifact_path: str = ''
# Called by:
#   - src/bundles.py
#   - src/plugin_runner.py
#   - src/prestart.py
# Calls:
#   - vault_paths, strip, join
# Returns / emits: Tuple[str, str]
# Key locals:
#   - ap, mp
# === End NoemaForge Autodoc Function Header ===
def bundle_paths(
    *,
    policy: Dict[str, Any],
    bundle_id: str,
    manifest_path: str = "",
    artifact_sha256: str = "",
    artifact_path: str = "",
) -> Tuple[str, str]:
    _root, manifests, artifacts = vault_paths(policy)
    mp = manifest_path.strip() or os.path.join(manifests, f"{bundle_id}.yaml")
    ap = artifact_path.strip()
    if not ap and artifact_sha256.strip():
        ap = os.path.join(artifacts, artifact_sha256.strip())
    return mp, ap


# ----------------------
# Signature support
# ----------------------


# === NoemaForge Autodoc Function Header ===
# Function: _canonical_manifest_bytes(mf: Dict[str, Any])
# Purpose: Implement the routine ' canonical manifest bytes'.
# Inputs:
#   - mf: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - dict, pop, dumps, encode
# Returns / emits: bytes
# Side effects:
#   - serializes structured data
# Key locals:
#   - mf2, s
# === End NoemaForge Autodoc Function Header ===
def _canonical_manifest_bytes(mf: Dict[str, Any]) -> bytes:
    mf2 = dict(mf or {})
    mf2.pop("signing", None)
    # stable order, no whitespace
    s = json.dumps(mf2, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return s.encode("utf-8")


# === NoemaForge Autodoc Function Header ===
# Function: _key_id_from_public_bytes(pub: bytes)
# Purpose: Implement the routine ' key id from public bytes'.
# Inputs:
#   - pub: bytes
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - hexdigest, sha256
# Returns / emits: str
# Key locals:
#   - fp
# === End NoemaForge Autodoc Function Header ===
def _key_id_from_public_bytes(pub: bytes) -> str:
    fp = hashlib.sha256(pub).hexdigest()[:16]
    return f"toolvault-local-{fp}"


# === NoemaForge Autodoc Function Header ===
# Function: ensure_signing_keypair(policy: Dict[str, Any])
# Purpose: Ensure ToolVault signing keypair exists.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - trust_paths, makedirs, exists, isinstance, get, generate, public_key, public_bytes, _key_id_from_public_bytes, private_bytes, decode, append
# Returns / emits: Dict[str, Any]
# Side effects:
#   - creates directories
#   - appends to logs or files
# Key locals:
#   - f, k, keys, keys_obj, kid, pem, pk, pub_b64, pub_bytes, sk
# === End NoemaForge Autodoc Function Header ===
def ensure_signing_keypair(policy: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure ToolVault signing keypair exists.

    Returns key info: {ok, key_id, public_key_b64, created}
    """

    trust_dir, keys_path, priv_path = trust_paths(policy)
    os.makedirs(trust_dir, exist_ok=True)

    # Load existing keys
    keys_obj: Dict[str, Any] = {}
    if os.path.exists(keys_path):
        try:
            keys_obj = json.loads(open(keys_path, "r", encoding="utf-8").read() or "{}")
        except Exception:
            keys_obj = {}

    keys = keys_obj.get("keys") if isinstance(keys_obj, dict) else None
    if not isinstance(keys, list):
        keys = []

    # If private key exists and a matching public key is already trusted, just return
    if os.path.exists(priv_path) and keys:
        # return the first toolvault-local key
        for k in keys:
            if not isinstance(k, dict):
                continue
            kid = str(k.get("key_id") or "")
            if kid.startswith("toolvault-local-"):
                return {"ok": True, "key_id": kid, "public_key_b64": str(k.get("public_key_b64") or ""), "created": False}

    # Generate new Ed25519 key pair
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        sk = Ed25519PrivateKey.generate()
        pk = sk.public_key()
        pub_bytes = pk.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        kid = _key_id_from_public_bytes(pub_bytes)

        # Write private key (PEM)
        pem = sk.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        with open(priv_path, "wb") as f:
            f.write(pem)
        try:
            os.chmod(priv_path, 0o600)
        except Exception:
            pass

        pub_b64 = base64.b64encode(pub_bytes).decode("ascii")

        keys.append({"key_id": kid, "algorithm": "ed25519", "public_key_b64": pub_b64, "created_at": time_nowz()})
        keys_obj = {
            "apiVersion": "noemaforge.supplychain/v1",
            "kind": "TrustedKeys",
            "keys": keys,
        }
        with open(keys_path, "w", encoding="utf-8") as f:
            json.dump(keys_obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        try:
            os.chmod(keys_path, 0o644)
        except Exception:
            pass

        return {"ok": True, "key_id": kid, "public_key_b64": pub_b64, "created": True, "keys_path": keys_path}
    except Exception as e:
        return {"ok": False, "error": f"keygen_failed:{e!r}"}


# === NoemaForge Autodoc Function Header ===
# Function: time_nowz()
# Purpose: Implement the routine 'time nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strftime, gmtime
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def time_nowz() -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# === NoemaForge Autodoc Function Header ===
# Function: load_trusted_keys(policy: Dict[str, Any])
# Purpose: Return mapping key_id -> raw public key bytes.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - trust_paths, exists, loads, isinstance, get, strip, lower, b64decode, read, str, open
# Returns / emits: Dict[str, bytes]
# Side effects:
#   - reads or writes files
# Key locals:
#   - alg, b64, k, keys, kid, obj, out
# === End NoemaForge Autodoc Function Header ===
def load_trusted_keys(policy: Dict[str, Any]) -> Dict[str, bytes]:
    """Return mapping key_id -> raw public key bytes."""

    _trust_dir, keys_path, _priv_path = trust_paths(policy)
    if not os.path.exists(keys_path):
        return {}
    try:
        obj = json.loads(open(keys_path, "r", encoding="utf-8").read() or "{}")
    except Exception:
        return {}

    keys = obj.get("keys") if isinstance(obj, dict) else None
    if not isinstance(keys, list):
        return {}

    out: Dict[str, bytes] = {}
    for k in keys:
        if not isinstance(k, dict):
            continue
        kid = str(k.get("key_id") or "").strip()
        alg = str(k.get("algorithm") or "").strip().lower()
        b64 = str(k.get("public_key_b64") or "").strip()
        if not kid or alg != "ed25519" or not b64:
            continue
        try:
            out[kid] = base64.b64decode(b64)
        except Exception:
            continue
    return out


# === NoemaForge Autodoc Function Header ===
# Function: sign_manifest_inplace(manifest_path: str, policy: Dict[str, Any])
# Purpose: Sign a manifest with the local ToolVault signing key.
# Inputs:
#   - manifest_path: str
#   - policy: Dict[str, Any]
# Called by:
#   - src/webgateway.py
# Calls:
#   - ensure_signing_keypair, str, trust_paths, load_yaml, _canonical_manifest_bytes, get, exists, load_pem_private_key, sign, decode, dump_yaml, read
# Returns / emits: Tuple[bool, str]
# Side effects:
#   - serializes structured data
# Key locals:
#   - kid, kinfo, mf, payload, sig, sig_b64, sk
# === End NoemaForge Autodoc Function Header ===
def sign_manifest_inplace(manifest_path: str, policy: Dict[str, Any]) -> Tuple[bool, str]:
    """Sign a manifest with the local ToolVault signing key.

    This is expected to be called during pre-start promotion from quarantine.
    """

    if not manifest_path or not os.path.exists(manifest_path):
        return False, "manifest_missing"

    # ensure local key exists
    kinfo = ensure_signing_keypair(policy)
    if not kinfo.get("ok"):
        return False, "signing_key_missing"

    kid = str(kinfo.get("key_id") or "")
    _trust_dir, _keys_path, priv_path = trust_paths(policy)
    if not os.path.exists(priv_path):
        return False, "private_key_missing"

    mf = load_yaml(manifest_path)
    payload = _canonical_manifest_bytes(mf)

    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        sk = serialization.load_pem_private_key(open(priv_path, "rb").read(), password=None)
        if not isinstance(sk, Ed25519PrivateKey):
            return False, "wrong_private_key_type"
        sig = sk.sign(payload)
        sig_b64 = base64.b64encode(sig).decode("ascii")
        mf["signing"] = {"key_id": kid, "algorithm": "ed25519", "sig_b64": sig_b64}
        dump_yaml(mf, manifest_path)
        return True, "signed"
    except Exception as e:
        return False, f"sign_failed:{e!r}"


# === NoemaForge Autodoc Function Header ===
# Function: verify_manifest_signature(manifest_path: str, policy: Dict[str, Any], mode: str = 'prefer')
# Purpose: Verify embedded manifest signature.
# Inputs:
#   - manifest_path: str
#   - policy: Dict[str, Any]
#   - mode: str = 'prefer'
# Called by:
#   - src/prestart.py
# Calls:
#   - lower, load_yaml, get, strip, load_trusted_keys, _canonical_manifest_bytes, isinstance, b64decode, from_public_bytes, verify, exists, str
# Returns / emits: Tuple[bool, str]
# Key locals:
#   - alg, kid, mf, mode, payload, pk, pub, s, sig, sig_b64, tkeys
# === End NoemaForge Autodoc Function Header ===
def verify_manifest_signature(manifest_path: str, policy: Dict[str, Any], mode: str = "prefer") -> Tuple[bool, str]:
    """Verify embedded manifest signature.

    mode:
      - off: skip
      - prefer: warn on missing/invalid signature (return ok)
      - require: missing/invalid signature -> fail
    """

    mode = str(mode or "prefer").strip().lower()
    if mode in ("off", "disabled", "false", "0", "no"):
        return True, "signature_off"

    if not manifest_path or not os.path.exists(manifest_path):
        return False, "manifest_missing"

    mf = load_yaml(manifest_path)
    s = mf.get("signing")
    if not isinstance(s, dict):
        return (True, "signature_missing") if mode == "prefer" else (False, "signature_missing")

    kid = str(s.get("key_id") or "").strip()
    alg = str(s.get("algorithm") or "").strip().lower()
    sig_b64 = str(s.get("sig_b64") or "").strip()

    if not kid or alg != "ed25519" or not sig_b64:
        return (True, "signature_incomplete") if mode == "prefer" else (False, "signature_incomplete")

    tkeys = load_trusted_keys(policy)
    pub = tkeys.get(kid)
    if not pub:
        return (True, "untrusted_key") if mode == "prefer" else (False, "untrusted_key")

    try:
        sig = base64.b64decode(sig_b64)
    except Exception:
        return (True, "sig_decode_failed") if mode == "prefer" else (False, "sig_decode_failed")

    payload = _canonical_manifest_bytes(mf)

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        pk = Ed25519PublicKey.from_public_bytes(pub)
        pk.verify(sig, payload)
        return True, "signature_ok"
    except Exception:
        return (True, "signature_invalid") if mode == "prefer" else (False, "signature_invalid")


# ----------------------
# Attestation verification
# ----------------------


# === NoemaForge Autodoc Function Header ===
# Function: _signature_mode(policy: Dict[str, Any])
# Purpose: Implement the routine ' signature mode'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, get, str
# Returns / emits: str
# Key locals:
#   - sig
# === End NoemaForge Autodoc Function Header ===
def _signature_mode(policy: Dict[str, Any]) -> str:
    try:
        sig = (((policy.get("attestation") or {}).get("bundle") or {}).get("signature") or {})
        if isinstance(sig, dict):
            return str(sig.get("mode") or "prefer")
    except Exception:
        pass
    return "prefer"


# === NoemaForge Autodoc Function Header ===
# Function: verify_bundle_attestation(policy: Optional[Dict[str, Any]] = None, manifest_path: str, expected_manifest_sha256: str, artifact_path: str, expected_artifact_sha256: str)
# Purpose: Implement the routine 'verify bundle attestation'.
# Inputs:
#   - policy: Optional[Dict[str, Any]] = None
#   - manifest_path: str
#   - expected_manifest_sha256: str
#   - artifact_path: str
#   - expected_artifact_sha256: str
# Called by:
#   - src/bundles.py
#   - src/plugin_runner.py
# Calls:
#   - sha256_file, verify_manifest_signature, exists, _signature_mode
# Returns / emits: Tuple[bool, str]
# Key locals:
#   - got, got2
# === End NoemaForge Autodoc Function Header ===
def verify_bundle_attestation(
    *,
    policy: Optional[Dict[str, Any]] = None,
    manifest_path: str,
    expected_manifest_sha256: str,
    artifact_path: str,
    expected_artifact_sha256: str,
) -> Tuple[bool, str]:
    if not manifest_path or not os.path.exists(manifest_path):
        return False, "manifest_missing"
    if expected_manifest_sha256:
        got = sha256_file(manifest_path)
        if got != expected_manifest_sha256:
            return False, "manifest_sha_mismatch"

    if not artifact_path or not os.path.exists(artifact_path):
        return False, "artifact_missing"
    if expected_artifact_sha256:
        got2 = sha256_file(artifact_path)
        if got2 != expected_artifact_sha256:
            return False, "artifact_sha_mismatch"

    # Optional signature verification (defense-in-depth)
    if policy is not None:
        ok_sig, r_sig = verify_manifest_signature(manifest_path, policy, mode=_signature_mode(policy))
        if not ok_sig:
            return False, f"{r_sig}"

    return True, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: installed_plugins_root(policy: Dict[str, Any])
# Purpose: Implement the routine 'installed plugins root'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - vault_paths, join
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def installed_plugins_root(policy: Dict[str, Any]) -> str:
    root, _m, _a = vault_paths(policy)
    return os.path.join(root, "installed", "plugins")


# === NoemaForge Autodoc Function Header ===
# Function: installed_plugin_dir(policy: Dict[str, Any], plugin_id: str, artifact_sha256: str)
# Purpose: Implement the routine 'installed plugin dir'.
# Inputs:
#   - policy: Dict[str, Any]
#   - plugin_id: str
#   - artifact_sha256: str
# Called by:
#   - src/plugin_runner.py
# Calls:
#   - join, installed_plugins_root
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def installed_plugin_dir(policy: Dict[str, Any], plugin_id: str, artifact_sha256: str) -> str:
    return os.path.join(installed_plugins_root(policy), plugin_id, artifact_sha256)


# === NoemaForge Autodoc Function Header ===
# Function: prepare_plugin_bundle(policy: Dict[str, Any], plugin_id: str, bundle_id: str, manifest_path: str, artifact_path: str, expected_manifest_sha256: str, expected_artifact_sha256: str)
# Purpose: Extract a plugin bundle to installed dir (idempotent).
# Inputs:
#   - policy: Dict[str, Any]
#   - plugin_id: str
#   - bundle_id: str
#   - manifest_path: str
#   - artifact_path: str
#   - expected_manifest_sha256: str
#   - expected_artifact_sha256: str
# Called by:
#   - src/bundles.py
#   - src/plugin_runner.py
#   - src/prestart.py
# Calls:
#   - verify_bundle_attestation, installed_plugin_dir, makedirs, load_yaml, lower, isdir, exists, join, strip, open, getmembers, extractall
# Returns / emits: Tuple[bool, str, Optional[str]]
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - f, fmt, m, mf, name, out_dir, tf
# === End NoemaForge Autodoc Function Header ===
def prepare_plugin_bundle(
    *,
    policy: Dict[str, Any],
    plugin_id: str,
    bundle_id: str,
    manifest_path: str,
    artifact_path: str,
    expected_manifest_sha256: str,
    expected_artifact_sha256: str,
) -> Tuple[bool, str, Optional[str]]:
    """Extract a plugin bundle to installed dir (idempotent).

    Returns: (ok, reason, installed_dir)
    """
    ok, r = verify_bundle_attestation(
        policy=policy,
        manifest_path=manifest_path,
        expected_manifest_sha256=expected_manifest_sha256,
        artifact_path=artifact_path,
        expected_artifact_sha256=expected_artifact_sha256,
    )
    if not ok:
        return False, r, None

    out_dir = installed_plugin_dir(policy, plugin_id, expected_artifact_sha256)
    if os.path.isdir(out_dir) and os.path.exists(os.path.join(out_dir, ".installed")):
        return True, "already_prepared", out_dir

    os.makedirs(out_dir, exist_ok=True)

    # Detect format from manifest (default tar.gz)
    mf = load_yaml(manifest_path)
    fmt = str(mf.get("artifact_format") or "tar.gz").strip().lower()
    if fmt not in ("tar.gz", "tgz"):
        return False, f"unsupported_format:{fmt}", None

    try:
        with tarfile.open(artifact_path, "r:gz") as tf:
            # Minimal path traversal defense
            for m in tf.getmembers():
                name = m.name
                if name.startswith("/") or ".." in name.split("/"):
                    raise RuntimeError("unsafe_tar_path")
            tf.extractall(out_dir)
        with open(os.path.join(out_dir, ".installed"), "w", encoding="utf-8") as f:
            f.write(f"bundle_id={bundle_id}\n")
            f.write(f"plugin_id={plugin_id}\n")
            f.write(f"artifact_sha256={expected_artifact_sha256}\n")
            f.write(f"manifest_sha256={expected_manifest_sha256}\n")
        return True, "prepared", out_dir
    except Exception as e:
        return False, f"extract_failed:{e!r}", None
