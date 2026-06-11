# NoemaForge 0.32.1 — full composite real launch

> **Status: historical snapshot (0.31.13.alpha-patched1 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Status: alpha-prep runbook.

This page records the legacy live-validation host live findings that led to patched10 and the safe procedure for a real full-composite launch.

## Readiness contract

`target-live-validation-readiness-core` defines the offline readiness gate for this runbook. Its policy keeps the real NVIDIA/GDM/LLM task in `blocked_until_target_machine_evidence` state until a target NoemaForge machine produces archived evidence for trixie preflight, display-manager/GDM health, NVIDIA driver state, gateway socket state, manual main backend smoke, ToolProxy live-LLM smoke, GUI rescue recovery and the final evidence bundle. The local validator only checks the manifest, documentation refs and safety controls; it does not execute `systemctl`, `nvidia-smi`, socket probes or live LLM commands.

`full-composite-target-run-readiness-core` defines the specific patched10 full-composite evidence gate. It keeps the run in `blocked_until_target_full_composite_evidence` until the target host records a patched10 install baseline, `sudo noemaforge trixie-preflight --json`, pipeline validation, the operator-approved `--full_composite 0` command plan, run transcript, first-start summary artifacts, GUI/display recovery evidence and a forensics bundle with a hash. Local validation checks only policy and documentation structure; it does not run first-start, systemd, GUI recovery or forensics commands.

`full-composite-ssh-readiness-core` defines the SSH-assisted version of that evidence gate. It keeps the SSH run in `blocked_until_target_ssh_evidence` until the target host records SSH service/listener state, an operator-approved known-host access plan with no stored credentials, an SSH-observed `--full_composite 0` run transcript, abort/display recovery over SSH and a redacted archive with hashes. Local validation checks the evidence shape only; it does not open SSH sessions.

`nologin-recovery-readiness-core` defines the recovery-specific gate for `/run/nologin`. It keeps the recovery confirmation in `blocked_until_target_nologin_recovery_evidence` until the target host records pre-recovery state, approved abort cleanup, post-recovery absence of `/run/nologin`, active display-manager or GDM state and a reviewed forensics archive. Local validation checks only the evidence contract and does not run recovery commands.

`emergency-gui-recovery-readiness-core` defines the Debian Trixie emergency GUI recovery gate. It keeps the display-manager alias check in `blocked_until_target_emergency_gui_recovery_evidence` until the target host records display-manager and GDM baseline state, approved `pause --wait` and `gui-rescue --wait` transcripts, display-manager alias-to-GDM evidence, post-rescue absence of `/run/nologin` and a reviewed archive hash. Local validation checks only the evidence contract and does not call systemd or recovery commands.

`share-automount-reboot-readiness-core` defines the share reboot gate. It keeps the automount confirmation in `blocked_until_target_share_reboot_evidence` until the target host records the nofail/automount fstab baseline, an approved reboot plan, post-reboot inactive emergency/rescue targets, share access through `/mnt/noemaforge-share` and a reviewed archive hash. Local validation checks only the evidence contract and does not reboot or mount anything.

## What changed in patched10

- Runtime safety gate checks structured runtime fields only: artifact paths, realpaths, model ids, backend ids, staged model sources and ModelStore records.
- Free-form model answers, prompts and eval explanations are no longer blocking runtime-safety evidence.
- Mentions such as `0003-of-0005` inside an eval answer are stored as warning-only text mentions.
- `_canonical_noemaforge_path()` maps legacy `/mnt/brainos-share/brainos-lab` targets to `/mnt/noemaforge-share/noemaforge-lab` when the canonical target exists.
- The previous false positive `blocked_runtime_safety` from model-generated explanations is fixed.

## Evidence gates before closure

The TODO for the real patched10 full-composite run remains open until these target artifacts exist:

- install/version baseline showing patched10 or later and no `/run/nologin` block;
- trixie preflight JSON, pipeline validation output and gateway service state;
- operator-approved `sudo noemaforge first-start --full_composite 0 --show-candidates --show-compositions --clear-model-health --per-model-timeout 240 --total-timeout 7200`;
- run transcript with TTY status updates;
- `candidate-selection-plan.json`, `role-candidate-map.json`, `model-run-records.json`, `rollback_plan.json` and `composite-selection-plan.json`;
- display-manager or GDM recovery state after abort/cleanup;
- forensics bundle path, SHA256 and redaction manifest.

For the SSH-assisted follow-up, the evidence bundle must also include SSH service state, listen socket, known-host fingerprint, operator-approved SSH identity, batch-mode probe result, SSH session transcript, abort/recovery transcript and a redaction note confirming that no credentials were archived.

For the `/run/nologin` recovery follow-up, the evidence bundle must include the pre-recovery `/run/nologin` probe, `systemctl get-default`, display-manager or GDM state, abort cleanup result, post-recovery `/run/nologin` absence, graphical target state and the forensics bundle hash.

For the share automount reboot follow-up, the evidence bundle must include the fstab share line, `nofail` and `x-systemd.automount` options, automount unit state, operator-approved reboot plan, changed boot ID, emergency and rescue target state, failed unit list, post-reboot share access and the forensics bundle hash.

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
