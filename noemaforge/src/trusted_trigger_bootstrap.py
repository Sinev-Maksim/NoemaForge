#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/trusted_trigger_bootstrap.py
Zone: gui/control-plane
Version: 0.33.0
Created: 2026-07-24
Modified: 2026-07-24
Purpose: Exchange a launcher-owned one-time capability for the process-local Admin GUI owner-session cookie.
Inputs: Private token file path from launcher environment plus observed localhost HTTP metadata.
Outputs: HttpOnly SameSite owner-session cookie or fail-closed denial.
Side effects: Consumes and deletes the launcher token file; updates only in-memory session capability state.
Tests: noemaforge/tests/test_trusted_trigger_integration.py
Notes: Ordinary localhost GET requests never mint authority; the token is delivered in a URL fragment and POSTed same-origin.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import hmac
import ipaddress
import os
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from trusted_trigger_integration import TrustedTriggerIntegration


def _text(value: Any) -> str:
    return str(value or "").strip()


def _header(headers: Mapping[str, Any], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() == target:
            return _text(value)
    return ""


def _loopback_host(value: str) -> bool:
    host = _text(value).lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _host_header_is_loopback(value: str) -> bool:
    try:
        parsed = urlparse("//" + _text(value))
    except ValueError:
        return False
    return _loopback_host(parsed.hostname or "")


def _origin_is_loopback_or_absent(value: str) -> bool:
    text = _text(value)
    if not text:
        return True
    try:
        parsed = urlparse(text)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and _loopback_host(parsed.hostname or "")


def _client_is_loopback(client_address: Sequence[Any]) -> bool:
    if not client_address:
        return False
    return _loopback_host(_text(client_address[0]))


def load_owner_bootstrap_token_from_env() -> str:
    """Read and remove a launcher-owned regular file with mode 0600 or stricter."""
    raw_path = os.environ.pop("NOEMAFORGE_OWNER_BOOTSTRAP_TOKEN_FILE", "").strip()
    if not raw_path:
        return ""
    path = Path(raw_path)
    descriptor = None
    try:
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if not nofollow and path.is_symlink():
            return ""
        descriptor = os.open(path, os.O_RDONLY | nofollow)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            return ""
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            return ""
        if stat.S_IMODE(info.st_mode) & 0o077:
            return ""
        if info.st_size < 32 or info.st_size > 512:
            return ""
        payload = os.read(descriptor, 513)
        if len(payload) > 512:
            return ""
        token = payload.decode("utf-8").strip()
        return token if 32 <= len(token) <= 512 else ""
    except (OSError, UnicodeError):
        return ""
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


class LauncherTrustedTriggerIntegration(TrustedTriggerIntegration):
    """Existing trigger evaluator plus a one-use launcher bootstrap boundary."""

    def __init__(self, *args: Any, owner_bootstrap_token: str = "", **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._launcher_bootstrap_token = _text(owner_bootstrap_token)

    def consume_owner_bootstrap_token(
        self,
        supplied: str,
        session_id: str,
        *,
        headers: Mapping[str, Any],
        client_address: Sequence[Any],
    ) -> str:
        valid_transport = (
            _client_is_loopback(client_address)
            and _host_header_is_loopback(_header(headers, "Host"))
            and _origin_is_loopback_or_absent(_header(headers, "Origin"))
        )
        expected = self._launcher_bootstrap_token
        candidate = _text(supplied)
        if not valid_transport or not expected or not candidate:
            return ""
        if not hmac.compare_digest(candidate, expected):
            return ""
        self._launcher_bootstrap_token = ""
        issuer = getattr(self, "owner_session_cookie_header", None)
        if not callable(issuer):
            issuer = getattr(self, "_issue_owner_session_cookie", None)
        return issuer(session_id) if callable(issuer) else ""
