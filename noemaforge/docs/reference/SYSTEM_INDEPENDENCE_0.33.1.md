<!--
=== NoemaForge File Header ===
File: noemaforge/docs/reference/SYSTEM_INDEPENDENCE_0.33.1.md
Zone: docs/reference
Version: 0.33.0
Purpose: Audit + phased plan for the 0.33.1 milestone — full system independence
  (NoemaForge runs the same on Linux, macOS and Windows). Inventories the
  platform-specific surface and defines the acceptance matrix.
Notes: Documentation is English-only.
=== End NoemaForge File Header ===
-->

# 0.33.1 — Full system independence (audit + plan)

**Goal:** NoemaForge runs *completely the same* on **Linux (\*nix), macOS and Windows** —
identical behaviour for paths, service/process management, sockets, exec/sandbox,
display-safety and the Admin GUI. Linux-production-only operations (systemd, GDM,
polkit) **degrade gracefully** and are clearly marked `N/A` off Linux, rather than
crashing or silently misbehaving.

**Acceptance:** the artifact-driven **AAT suite** + the full unit-test matrix pass
**identically** on `ubuntu-latest`, `macos-latest`, and `windows-latest` in CI.

## Foundations already in place (0.32.2)

- `platform_paths` migration — runtime state/config/data roots resolve per-OS.
- Sandbox/canary **import-safety** — `try/except` around Unix-only `resource`; host
  fallback when rlimits are unavailable.
- seclog `fcntl` guard + `SEL_DIR` cross-platform resolution.
- `noema` CLI (`start`/`doctor`/`upgrade`) is Python, loopback-only, display-safe.

## Platform-specific surface (scan of `noemaforge/src`, 2026-06-09)

| Surface | Hits / files | Disposition |
|---|---|---|
| Existing platform guards (`os.name`/`sys.platform`/`platform.system`) | 11 / 5 | ✅ keep + extend the pattern |
| Unix-only module imports (`resource`/`fcntl`/`pwd`/`grp`) | 5 / 5 | guard each with `try/except ImportError` + capability flag |
| Unix signals (`SIGKILL`/`SIGTERM`) | 19 / 6 | use `getattr(signal, "SIGKILL", signal.SIGTERM)`; route process-kill through one helper |
| `systemctl` / systemd | 367 / 153 | **biggest item** — most are unit/doc refs; the *code* callers need a service-manager abstraction that degrades off Linux |
| Hardcoded `/run` `/opt` `/var` paths | 208 / 57 | route through `platform_paths`; keep Linux install layout as the Linux default only |
| `AF_UNIX` / `.sock` | 59 / 20 | socket paths via `platform_paths`; verify Win10+ AF_UNIX or fall back to loopback TCP |
| Unix privilege (`runuser`/`polkit`/`pkexec`) | 50 / 2 | abstract escalation; `N/A` with clear messaging off Linux |

## Phased plan

1. **Paths** — extend the `platform_paths` migration to the remaining hardcoded
   `/run|/opt|/var` callers; the Linux FHS layout stays the Linux default only.
2. **Service/process management** — introduce a `service_manager` abstraction:
   Linux→systemd, macOS→launchd/no-op, Windows→no-op/Scheduled-Task; every
   `systemctl(...)` code path goes through it and degrades (never crashes) off Linux.
   Fold in the harvested nits (`role_tournament.py` Linux-only backend-stop; DRY the
   `getattr(signal, "SIGKILL", …)` fallback).
3. **Signals** — confirm every signal use takes the `getattr` fallback; centralize.
4. **Sockets** — AF_UNIX paths via `platform_paths`; loopback-TCP fallback where
   AF_UNIX is unavailable.
5. **Privilege** — escalation behind one interface; `N/A`-with-reason off Linux.
6. **CI parity matrix** — run AAT (`ci/run_acceptance.sh`) + `unittest` on
   `ubuntu/macos/windows-latest`. **Depends on the AAT suite (PR #71) merging.**
   Non-Linux failures are first surfaced *informationally* (non-gating), then promoted
   to gating as each phase lands.

## Out of scope (intentional, `N/A` off Linux)

systemd unit *activation*, GDM/display-manager rescue, NVIDIA/GPU control, polkit
prompts — these are Linux-production operations. The contract is **graceful
degradation + clear `N/A`**, not re-implementing them on macOS/Windows.

## Tracking

Each phase ships as its own `claude/sysindep-*` PR with a clean single-concern diff
and (where testable) AAT/unit coverage proving parity. This doc is the index; update
the table dispositions as phases land.
