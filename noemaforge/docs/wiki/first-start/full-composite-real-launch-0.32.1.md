# NoemaForge 0.32.2 — full composite real launch

Status: readiness-gated runbook.

This page records the target-machine evidence contracts that must be satisfied before the full
composite real launch on the NoemaForge host is considered complete.

## Readiness contracts

Each item below is `blocked_until_target_*_evidence` and will not be closed until the
NoemaForge host produces and archives the corresponding evidence bundle.

### Full-composite target run

`full-composite-target-run-readiness-core` keeps the patched10 full-composite run in
`blocked_until_target_full_composite_evidence` state. Required: patched10 install baseline,
target preflight, operator-approved `--full_composite 0` plan, run transcript, first-start
summary artifacts, display/abort recovery evidence and a forensics archive.

### Full-composite SSH run

`full-composite-ssh-readiness-core` keeps the SSH-assisted full-composite run in
`blocked_until_target_ssh_evidence` state. Required: SSH service and listener evidence,
operator-approved known-host access plan, SSH-observed transcript, SSH abort/display recovery
and a redacted forensics archive.

### Live target validation

`target-live-validation-readiness-core` keeps NVIDIA/GDM/LLM validation in
`blocked_until_target_machine_evidence` state. Required: trixie-preflight, display-manager/GDM,
NVIDIA, gateway socket, manual main-backend, ToolProxy live-LLM, GUI rescue and evidence-archive
checks. The local validator has no live command execution path.

### Emergency GUI recovery

`emergency-gui-recovery-readiness-core` keeps the Trixie emergency GUI recovery validation in
`blocked_until_target_emergency_gui_recovery_evidence` state. Required: display-manager and
GDM baseline, operator-approved `pause --wait` and `gui-rescue --wait` transcripts,
display-manager alias-to-GDM evidence, post-rescue `/run/nologin` absence and a forensics archive.

### No-login recovery

`nologin-recovery-readiness-core` keeps the `/run/nologin` recovery confirmation in
`blocked_until_target_nologin_recovery_evidence` state. Required: pre-recovery nologin and
display baseline, operator-approved abort cleanup, post-recovery `/run/nologin` absence,
display-manager or GDM active state and a forensics archive.

### Share automount reboot

`share-automount-reboot-readiness-core` keeps the share automount reboot guard in
`blocked_until_target_share_reboot_evidence` state. Required: fstab and automount unit evidence
for `/mnt/noemaforge-share`, operator-approved reboot evidence, post-reboot emergency and rescue
target state, post-reboot share access and a forensics archive.

## None of these run locally

All validators above are offline-only. They check policy, example, registry and docs shape. They
do not execute systemd, sudo, recovery, LLM, gateway, SSH or archive commands on the local machine.

## What changed from 0.31.13 alpha to 0.32.2

- All six readiness contracts are now explicit `eval-pack` entries in `unified-registry.json`.
- Each contract has a schema, a typed runtime and documented evidence requirements.
- The blocked state is machine-readable and tracked in the registry `metadata.todo_state` field.
