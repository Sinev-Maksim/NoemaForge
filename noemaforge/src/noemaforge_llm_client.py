#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/noemaforge_llm_client.py
# Zone: operator/ux
# Purpose: Minimal OpenAI-compatible LLM client over NoemaForge Unix sockets.
# Safety: network only to local Unix sockets; no command execution.
# === End NoemaForge File Header ===

import json
import os
import socket
from dataclasses import dataclass
from typing import Any


@dataclass
class UnixHTTPResponse:
    status: int
    headers: dict[str, str]
    body: bytes


def unix_http_json(sock_path: str, method: str, path: str, payload: dict[str, Any] | None = None, timeout: float = 120.0) -> dict[str, Any] | str:
    body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = (
        f"{method} {path} HTTP/1.1\r\n"
        "Host: localhost\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("utf-8") + body

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(sock_path)
        s.sendall(req)
        chunks: list[bytes] = []
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        s.close()
    raw = b"".join(chunks)
    if b"\r\n\r\n" not in raw:
        text = raw.decode("utf-8", "replace")
        try:
            return json.loads(text)
        except Exception:
            return text
    head, resp_body = raw.split(b"\r\n\r\n", 1)
    status_line = head.splitlines()[0].decode("utf-8", "replace")
    try:
        status = int(status_line.split()[1])
    except Exception:
        status = 0
    text = resp_body.decode("utf-8", "replace")
    if status < 200 or status >= 300:
        raise RuntimeError(f"HTTP {status}: {text[:1000]}")
    try:
        return json.loads(text)
    except Exception:
        return text


def gateway_chat(messages: list[dict[str, str]], model: str = "main", max_tokens: int = 768, temperature: float = 0.2, sock_path: str | None = None, extra: dict[str, Any] | None = None, timeout: float = 180.0) -> dict[str, Any]:
    sock = sock_path or os.environ.get("NOEMAFORGE_GATEWAY_SOCKET", "/run/noemaforge/llm/gateway.sock")
    payload: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    if extra:
        payload.update(extra)
    result = unix_http_json(sock, "POST", "/v1/chat/completions", payload, timeout=timeout)
    if not isinstance(result, dict):
        raise RuntimeError(f"non-json gateway response: {result!r}")
    return result


def content_from_chat_response(resp: dict[str, Any]) -> str:
    return str((((resp.get("choices") or [{}])[0]).get("message") or {}).get("content") or "")
