# NoemaForge 0.32.1 — full composite real launch

> **Status: historical snapshot (0.32.1 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Status: alpha-prep runbook.

This page records the NoemaForge live findings that led to patched10 and the safe procedure for a real full-composite launch.

## What changed in patched10

- Runtime safety gate checks structured runtime fields only: artifact paths, realpaths, model ids, backend ids, staged model sources and ModelStore records.
- Free-form model answers, prompts and eval explanations are no longer blocking runtime-safety evidence.
- Mentions such as `0003-of-0005` inside an eval answer are stored as warning-only text mentions.
- `_canonical_noemaforge_path()` maps legacy `/mnt/brainos-share/brainos-lab` targets to `/mnt/noemaforge-share/noemaforge-lab` when the canonical target exists.
- The previous false positive `blocked_runtime_safety` from model-generated explanations is fixed.

## Required preflight before real apply

```bash
sudo noemaforge trixie-preflight --json
NOEMAFORGE_PIPELINE_STATE=/var/lib/noemaforge/pipelines noemaforge pipeline validate
systemctl status noemaforge-llm-gateway.service --no-pager -l
systemctl cat noemaforge-llama@.service
```

Check sockets:

```bash
sudo systemctl start noemaforge-llm-gateway.service
ss -xlpn | grep -E '/run/(brainos|noemaforge)/llm/gateway.sock' || true

sudo systemctl stop noemaforge-llama@main.service 2>/dev/null || true
sudo rm -f /run/noemaforge/llm/backends/main.sock
sudo systemctl start noemaforge-llama@main.service
sleep 25
find /run/noemaforge/llm/backends -maxdepth 1 -type s -ls 2>/dev/null || true
sudo systemctl stop noemaforge-llama@main.service 2>/dev/null || true
```

## Real full-composite launch

Default safe pool, all runnable models, no top limit:

```bash
sudo noemaforge first-start   --full_composite 0   --show-candidates   --show-compositions   --clear-model-health   --per-model-timeout 240   --total-timeout 7200
```

Including unverified models is high-risk and requires explicit confirmation:

```bash
sudo noemaforge first-start   --full_composite 0   --show-candidates   --show-compositions   --clear-model-health   --include-unverified   --yes-i-understand-unverified-risk   --per-model-timeout 240   --total-timeout 7200
```

## Stop and return to GUI

```bash
sudo systemctl stop noemaforge-first-start.service 2>/dev/null || true
sudo pkill -TERM -f 'firstboot_orchestrator.py|role_tournament.py|noemaforge-first-launch|llama-server|noemaforge-llama-start' || true
sudo noemaforge first-start abort 2>/dev/null || true
sudo systemctl set-default graphical.target
sudo systemctl start --no-block display-manager.service 2>/dev/null || true
sudo systemctl start --no-block gdm.service 2>/dev/null || true
sudo systemctl isolate --no-block graphical.target
```

---

_Provenance: extracted 2026-06-10 from the consolidated wiki dump (`WIKI.md`) into a standalone article; the dump is retired._
