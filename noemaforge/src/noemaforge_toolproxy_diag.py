#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/noemaforge_toolproxy_diag.py
# Zone: operator/ux
# Purpose: Diagnose ToolProxy socket, policy, capability tokens and optional llm.chat path.
# Safety: diagnostics and short-lived token management only; live socket calls are explicit.
# === End NoemaForge File Header ===

import argparse
import datetime as dt
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from platform_paths import DEFAULT_PATHS as _pp


def _toolproxy_socket_default(paths: Any = _pp) -> str:
    socket_path = paths.toolproxy_socket
    if callable(socket_path):
        socket_path = socket_path()
    return str(socket_path)


DEFAULT_TOKENS_DIR = os.environ.get("NOEMAFORGE_CAP_TOKENS_DIR", str(_pp.data_root / ".sys/cap_tokens"))
DEFAULT_SOCKET = os.environ.get("NOEMAFORGE_TOOLPROXY_SOCKET", _toolproxy_socket_default())


def sh(cmd: list[str], timeout: int = 20) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    except Exception as e:
        return f"ERROR: {e}\n"


def stat_path(path: str) -> str:
    try:
        return subprocess.check_output(
            ["stat", "-c", "%A %a %U:%G %F %n", path],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
    except Exception:
        return ""


def jprint(doc: dict[str, Any], pretty: bool = True) -> None:
    print(json.dumps(doc, ensure_ascii=False, indent=2 if pretty else None, sort_keys=False))


def send_toolproxy(req: dict[str, Any], sock_path: str = DEFAULT_SOCKET, timeout: float = 180) -> dict[str, Any]:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(sock_path)
        s.sendall(json.dumps(req, ensure_ascii=False).encode("utf-8"))
        s.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            data = s.recv(65536)
            if not data:
                break
            chunks.append(data)
    finally:
        s.close()
    raw = b"".join(chunks).decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except Exception:
        return {"ok": False, "error": "non_json_toolproxy_response", "raw": raw[:2000]}


def build_toolproxy_request(
    *,
    action: str,
    token: str,
    role: str,
    project_id: str,
    run_id: str,
    stream_id: str,
    args: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    return {
        "action": str(action),
        "token": str(token),
        "args": args or {},
        "meta": {
            "role": str(role),
            "project_id": str(project_id),
            "run_id": str(run_id),
            "stream_id": str(stream_id),
            "trace_id": str(trace_id or ""),
        },
    }


def probe_toolproxy(sock_path: str = DEFAULT_SOCKET, timeout: float = 5.0) -> dict[str, Any]:
    req = build_toolproxy_request(
        action="operator.status",
        token="toolproxy-probe.invalid",
        role="operator",
        project_id="noemaforge-toolproxy-probe",
        run_id="probe",
        stream_id="dev.work",
        trace_id="toolproxy-probe",
    )
    try:
        response = send_toolproxy(req, sock_path=sock_path, timeout=timeout)
    except Exception as exc:
        return {
            "ok": False,
            "probe": "native_json_over_unix_socket",
            "socket": sock_path,
            "error": str(exc),
        }
    reason = str(response.get("error") or response.get("reason") or "")
    denied = response.get("ok") is False and reason in {"denied", "invalid_token", "unknown_token", "cap_missing"}
    return {
        "ok": bool(denied),
        "probe": "native_json_over_unix_socket",
        "socket": sock_path,
        "expected": "structured_denial_for_invalid_capability_token",
        "response": response,
    }


def _import_caps():
    root = os.environ.get("NOEMAFORGE_ROOT")
    preferred = []
    if root:
        preferred.append(str(Path(root) / "src"))
    preferred.append(str(Path(__file__).resolve().parent))
    for c in reversed([p for p in preferred if p]):
        if c in sys.path:
            sys.path.remove(c)
        sys.path.insert(0, c)
    opt_src = "/opt/noemaforge/src"
    if opt_src not in sys.path:
        sys.path.append(opt_src)
    import caps  # type: ignore
    return caps


def issue_token_value(tokens_dir: str, action: str, ttl_sec: int, role: str, project_id: str, run_id: str, trace_id: str | None = None) -> str:
    caps = _import_caps()
    return caps.issue_token(
        tokens_dir,
        issued_to={"role": role, "project_id": project_id, "run_id": run_id},
        caps=[{"action": action}],
        ttl_sec=int(ttl_sec),
        trace_id=trace_id or "toolproxy-token-" + str(int(time.time())),
    )


def issue_test_token(tokens_dir: str = DEFAULT_TOKENS_DIR) -> str:
    return issue_token_value(tokens_dir, "llm.chat", 300, "architect", "noemaforge-toolproxy-diag", "diag", "toolproxy-diag-" + str(int(time.time())))


def test_llm_chat(tokens_dir: str = DEFAULT_TOKENS_DIR, sock_path: str = DEFAULT_SOCKET) -> dict[str, Any]:
    token = issue_test_token(tokens_dir)
    trace_id = "toolproxy-diag-" + str(int(time.time()))
    req = build_toolproxy_request(
        action="llm.chat",
        token=token,
        role="architect",
        project_id="noemaforge-toolproxy-diag",
        run_id="diag",
        stream_id="dev.work",
        trace_id=trace_id,
        args={
            "model": "main",
            "messages": [{"role": "user", "content": "Return exactly: OK"}],
            "max_tokens": 8,
            "temperature": 0,
        },
    )
    res = send_toolproxy(req, sock_path=sock_path)
    res["trace_id_sent"] = trace_id
    res["token_prefix"] = token.split(".")[0] + ".***" if "." in token else token[:16] + "***"
    return res


def diag_report(test_llm: bool = False, tokens_dir: str = DEFAULT_TOKENS_DIR, sock_path: str = DEFAULT_SOCKET) -> dict[str, Any]:
    report: dict[str, Any] = {
        "socket": stat_path(sock_path),
        "service_active": sh(["systemctl", "is-active", "noemaforge-toolproxy.service"]).strip(),
        "service_enabled": sh(["systemctl", "is-enabled", "noemaforge-toolproxy.service"]).strip(),
        "sel_dir": stat_path("/var/lib/noemaforge/sel"),
        "sel_segments_dir": stat_path("/var/lib/noemaforge/sel/segments"),
        "cap_tokens_dir": stat_path(tokens_dir),
        "tool_registry": stat_path("/opt/noemaforge/configs/tool-registry.yaml"),
        "tool_policy": stat_path("/opt/noemaforge/configs/tool-policy.yaml"),
        "recent_errors": sh(["bash", "-lc", "journalctl -u noemaforge-toolproxy.service -n 80 -l --no-pager | grep -Ei 'TOOLPROXY|PermissionError|llm_gateway|cap_missing|tool_unknown|policy|deny|error' || true"], timeout=20),
    }
    if test_llm:
        try:
            report["llm_chat_test"] = test_llm_chat(tokens_dir, sock_path=sock_path)
        except Exception as e:
            report["llm_chat_test"] = {"ok": False, "error": str(e)}
    return report


def token_list(tokens_dir: str) -> dict[str, Any]:
    root = Path(tokens_dir)
    items: list[dict[str, Any]] = []
    if root.is_dir():
        for path in sorted(root.glob("*.json")):
            try:
                rec = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except Exception as exc:
                items.append({"file": str(path), "ok": False, "error": str(exc)})
                continue
            safe = {k: rec.get(k) for k in ["token_id", "issued_to", "epoch_id", "expires_at", "caps", "trace_id", "issued_at"]}
            safe["file"] = str(path)
            safe["ok"] = True
            items.append(safe)
    return {"ok": True, "tokens_dir": str(root), "count": len(items), "items": items}


def token_revoke(tokens_dir: str, token_id: str) -> dict[str, Any]:
    tid = token_id.split(".", 1)[0].strip()
    path = Path(tokens_dir) / f"{tid}.json"
    if not path.exists():
        return {"ok": False, "token_id": tid, "error": "not_found", "path": str(path)}
    revoked_dir = Path(tokens_dir) / "revoked"
    revoked_dir.mkdir(parents=True, exist_ok=True)
    target = revoked_dir / f"{tid}.{int(time.time())}.json"
    os.replace(path, target)
    return {"ok": True, "token_id": tid, "revoked_to": str(target)}


def token_verify(tokens_dir: str, token: str) -> dict[str, Any]:
    caps = _import_caps()
    ok, rec, reason = caps.verify_token(tokens_dir, token)
    safe: dict[str, Any] | None = None
    if rec:
        safe = {k: rec.get(k) for k in ["token_id", "issued_to", "epoch_id", "expires_at", "caps", "trace_id", "issued_at"]}
    return {"ok": bool(ok), "reason": reason, "record": safe}


def token_cmd(ns: argparse.Namespace) -> int:
    if ns.token_action == "issue":
        token = issue_token_value(ns.tokens_dir, ns.action, ns.ttl, ns.role, ns.project_id, ns.run_id, ns.trace_id)
        tid = token.split(".", 1)[0]
        doc = {"ok": True, "token_id": tid, "token": token if ns.show_secret else tid + ".***", "tokens_dir": ns.tokens_dir, "ttl_sec": ns.ttl, "action": ns.action, "issued_to": {"role": ns.role, "project_id": ns.project_id, "run_id": ns.run_id}}
        jprint(doc)
        return 0
    if ns.token_action == "list":
        jprint(token_list(ns.tokens_dir))
        return 0
    if ns.token_action == "revoke":
        doc = token_revoke(ns.tokens_dir, ns.token_id)
        jprint(doc)
        return 0 if doc.get("ok") else 1
    if ns.token_action == "verify":
        doc = token_verify(ns.tokens_dir, ns.token)
        jprint(doc)
        return 0 if doc.get("ok") else 1
    if ns.token_action == "cleanup":
        caps = _import_caps()
        removed = caps.cleanup_expired(ns.tokens_dir, keep_days=ns.keep_days)
        jprint({"ok": True, "tokens_dir": ns.tokens_dir, "removed": removed, "keep_days": ns.keep_days})
        return 0
    raise SystemExit(f"unknown token action: {ns.token_action}")


def smoke_cmd(ns: argparse.Namespace) -> int:
    problems: list[str] = []
    try:
        token = issue_token_value(ns.tokens_dir, ns.action, ns.ttl, ns.role, ns.project_id, ns.run_id)
        verify = token_verify(ns.tokens_dir, token)
        if not verify.get("ok"):
            problems.append("issued token did not verify")
    except Exception as exc:
        token = ""
        verify = {"ok": False, "error": str(exc)}
        problems.append(f"token issue/verify failed: {exc}")
    live = None
    if ns.live_llm:
        try:
            live = test_llm_chat(ns.tokens_dir, sock_path=ns.socket)
            if not live.get("ok"):
                problems.append("live llm.chat returned ok=false")
        except Exception as exc:
            live = {"ok": False, "error": str(exc)}
            problems.append(f"live llm.chat failed: {exc}")
    doc = {"ok": not problems, "tokens_dir": ns.tokens_dir, "token_prefix": token.split(".", 1)[0] + ".***" if token else None, "verify": verify, "live_llm": live, "problems": problems}
    jprint(doc)
    return 0 if not problems else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Diagnose NoemaForge ToolProxy and capability tokens")
    ap.add_argument("--json", action="store_true", help="kept for backward compatibility; JSON is default for new subcommands")
    ap.add_argument("--test-llm", action="store_true", help="legacy diag option: issue a short-lived token and test llm.chat")
    sub = ap.add_subparsers(dest="cmd")

    diag = sub.add_parser("diag")
    diag.add_argument("--json", action="store_true", help="kept for compatibility; diag output is JSON for subcommands")
    diag.add_argument("--test-llm", action="store_true")
    diag.add_argument("--tokens-dir", default=DEFAULT_TOKENS_DIR)
    diag.add_argument("--socket", default=DEFAULT_SOCKET)

    token = sub.add_parser("token")
    token.add_argument("--tokens-dir", default=DEFAULT_TOKENS_DIR)
    tsub = token.add_subparsers(dest="token_action", required=True)
    issue = tsub.add_parser("issue")
    issue.add_argument("--tokens-dir", default=DEFAULT_TOKENS_DIR)
    issue.add_argument("--action", default="llm.chat")
    issue.add_argument("--ttl", type=int, default=600)
    issue.add_argument("--role", default="operator")
    issue.add_argument("--project-id", default="noemaforge")
    issue.add_argument("--run-id", default="manual")
    issue.add_argument("--trace-id")
    issue.add_argument("--show-secret", action="store_true", help="print full bearer token; otherwise only token id is shown")
    issue.set_defaults(func=token_cmd)
    listp = tsub.add_parser("list")
    listp.add_argument("--tokens-dir", default=DEFAULT_TOKENS_DIR)
    listp.set_defaults(func=token_cmd)
    revoke = tsub.add_parser("revoke")
    revoke.add_argument("token_id")
    revoke.add_argument("--tokens-dir", default=DEFAULT_TOKENS_DIR)
    revoke.set_defaults(func=token_cmd)
    verify = tsub.add_parser("verify")
    verify.add_argument("token")
    verify.add_argument("--tokens-dir", default=DEFAULT_TOKENS_DIR)
    verify.set_defaults(func=token_cmd)
    cleanup = tsub.add_parser("cleanup")
    cleanup.add_argument("--tokens-dir", default=DEFAULT_TOKENS_DIR)
    cleanup.add_argument("--keep-days", type=int, default=7)
    cleanup.set_defaults(func=token_cmd)

    smoke = sub.add_parser("smoke")
    smoke.add_argument("--tokens-dir", default=DEFAULT_TOKENS_DIR)
    smoke.add_argument("--action", default="llm.chat")
    smoke.add_argument("--ttl", type=int, default=120)
    smoke.add_argument("--role", default="operator")
    smoke.add_argument("--project-id", default="noemaforge-toolproxy-smoke")
    smoke.add_argument("--run-id", default="smoke")
    smoke.add_argument("--live-llm", action="store_true", help="also call live ToolProxy llm.chat; requires running services")
    smoke.add_argument("--socket", default=DEFAULT_SOCKET)
    smoke.set_defaults(func=smoke_cmd)
    probe = sub.add_parser("probe")
    probe.add_argument("--socket", default=DEFAULT_SOCKET)
    probe.add_argument("--timeout", type=float, default=5.0)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    ns = ap.parse_args(argv)
    if getattr(ns, "cmd", None) == "token":
        # argparse stores common options on the token namespace; child action defaults hold func.
        return ns.func(ns)
    if getattr(ns, "cmd", None) == "smoke":
        return ns.func(ns)
    if getattr(ns, "cmd", None) == "probe":
        doc = probe_toolproxy(ns.socket, ns.timeout)
        jprint(doc)
        return 0 if doc.get("ok") else 1
    if getattr(ns, "cmd", None) == "diag":
        report = diag_report(bool(ns.test_llm), ns.tokens_dir, sock_path=ns.socket)
    else:
        report = diag_report(bool(getattr(ns, "test_llm", False)), DEFAULT_TOKENS_DIR)
    if getattr(ns, "json", False) or getattr(ns, "cmd", None):
        jprint(report)
    else:
        print("=== NoemaForge ToolProxy diagnostics ===")
        for k in ["socket", "service_active", "service_enabled", "sel_dir", "sel_segments_dir", "cap_tokens_dir", "tool_registry", "tool_policy"]:
            print(f"{k}: {report[k]}")
        if report.get("llm_chat_test") is not None:
            print("\n=== llm.chat test ===")
            jprint(report.get("llm_chat_test") or {})
        print("\n=== recent errors ===")
        print(str(report["recent_errors"]).rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
