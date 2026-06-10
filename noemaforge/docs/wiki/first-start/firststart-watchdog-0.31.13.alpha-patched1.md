# NoemaForge 0.32.1 — first-start watchdog and hang fix

> **Status: historical snapshot (0.31.13.alpha-patched1 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Tracking: `NFG-FIX-0.32.1-firststart-watchdog`

Status: implemented in `0.32.1`.

## Source finding

legacy live-validation host diagnostic bundle `noemaforge_03113_firststart_hang_20260511-150449.tar.gz` showed that `sudo noemaforge first-start --normal --dry-run --show-candidates` remained in role-tournament for multiple hours while a single `llama-server-cuda` backend consumed high CPU/RAM.

Observed symptoms:

- `firstboot_orchestrator.py` ran for more than 3.5 hours.
- `llama-server-cuda` stayed active under `noemaforge-llama@...service`.
- Active models included names with `uncensored` / `aggressive` markers.
- `firstboot-status.json` mixed current `role_tournament/running` fields with stale previous `request_id`, `results`, `finished_at` and `ok=true` fields.
- `role_tournament` only wrote final results, so operators could not see the current role/model/task while a run was in progress.

## Implemented fixes

1. **Hard per-candidate watchdog**
   - `NOEMAFORGE_TOURNAMENT_PER_MODEL_TIMEOUT` now bounds each model candidate.
   - Default: fast=120s, normal=300s, full/full_composite=600s.

2. **Hard total tournament watchdog**
   - `NOEMAFORGE_TOURNAMENT_TOTAL_TIMEOUT` bounds the whole run.
   - Default: fast=600s, normal=1800s, full/full_composite=7200s.

3. **Streaming progress artifacts**
   - `/var/lib/noemaforge/bootstrap/role-tournament-progress.json`
   - `/var/lib/noemaforge/bootstrap/role-tournament-progress.jsonl`
   - `/var/lib/noemaforge/bootstrap/model-run-records.json`

4. **Backend cleanup**
   - active backends are tracked and cleaned via atexit/SIGTERM/SIGINT handlers;
   - `stop_gguf_backend()` now uses systemd stop/kill plus process fallback by backend socket path;
   - stale sockets are removed after stop.

5. **Default safety-name filter**
   - model names/paths containing markers such as `uncensored`, `aggressive`, `jailbreak`, `abliterated`, `nsfw`, `no-guard` or `no-censor` are excluded from default first-start.
   - Override only by explicit operator choice: `--include-unverified` or `NOEMAFORGE_TOURNAMENT_INCLUDE_UNVERIFIED=1`.

6. **Fresh status writes**
   - `firstboot_status.write_status()` no longer merges with previous status documents.
   - `mark_started()` emits `run_id` and `pid`.
   - This prevents stale previous success artifacts from appearing in the current running status.

7. **Operator knobs**

```bash
sudo noemaforge first-start --normal --dry-run --show-candidates   --per-model-timeout 180   --total-timeout 1200

sudo noemaforge first-start --fast --dry-run --show-candidates   --per-model-timeout 90   --total-timeout 600
```

Optional explicit unsafe/unverified inclusion:

```bash
sudo noemaforge first-start --normal --dry-run --show-candidates --include-unverified
```

## Expected behavior after the fix

`first-start --normal --dry-run --show-candidates` should no longer remain indefinitely on one model. If a model exceeds its budget, it is marked with one of:

- `per_model_timeout`
- `total_timeout`
- `warmup_failed`
- `default_safety_filter`

and the tournament moves on or finishes boundedly.

## Remaining validation

This fix was syntax/smoke-tested in the package sandbox. Full measured tournament validation still belongs on legacy live-validation host because it requires the mounted Vault, ModelStore, systemd units and actual model runtimes.
