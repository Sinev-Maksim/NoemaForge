# Recovery/Stability Notes for Debian Trixie

## Current baseline

The 0.29.11 recovery/stability package remains the runtime base. Version 0.32.1 adds a wiki/prelaunch merge layer on top of it.

Known verified context from legacy live-validation host:

- Debian GNU/Linux 13 / Trixie.
- Kernel `6.12.85+deb13-amd64`.
- NVIDIA GeForce RTX 3080 Ti.
- NVIDIA driver `550.163.01`.
- CUDA shown by `nvidia-smi`: `12.4`.
- Secure Boot enabled.
- NoemaForge heavy LLM should not auto-start during boot.

## Operational rules

- Keep GUI/NVIDIA recovery independent from LLM startup.
- Keep Qwen/large GGUF manual/on-demand until delayed/limited start is safe.
- Prefer `noemaforge-llm-stop` before reboot, GUI rescue, or heavy browser use.
- Treat failed firstboot artifacts as forensic data, not as garbage.

## Clean Install Share Readiness

`clean-install-share-readiness-core` makes the clean install with `/mnt/noemaforge-share` a target-evidence gate instead of a local claim. The item stays in `blocked_until_target_clean_install_evidence` until NoemaForge records dry-run/selftest output, an operator-approved host install transcript, canonical share mount state, post-install Trixie preflight, emergency-mode checks and a forensics bundle with a hash.

`share-automount-reboot-readiness-core` narrows the reboot follow-up for that same share path. The item stays in `blocked_until_target_share_reboot_evidence` until the target records the `/mnt/noemaforge-share` fstab line with `nofail` and `x-systemd.automount`, the automount unit state, an operator-approved reboot plan, a changed boot ID, inactive emergency and rescue targets, post-reboot share access and a reviewed archive hash.

The share path must remain canonical at `/mnt/noemaforge-share`, and any fstab or generated systemd mount path must be non-blocking: nofail, automount and a bounded device timeout are part of the evidence shape. Previous install, backup or migration context can be retained only as archive/readonly evidence; it must not become an active runtime root during the clean install. The local validator checks those requirements as policy and documentation structure only, so it does not execute setup, mount, systemd, journal or forensics commands.

## Post-Reboot Validation Archive

`post-reboot-validation-archive-readiness-core` turns the post-reboot validation and wiki patch follow-up into a concrete evidence contract while keeping it open in `blocked_until_target_post_reboot_archive_evidence`. The target bundle must record the post-reboot boot ID, system-running state, failed units, gateway service state, main backend service state, display-manager or GDM state, socket state, operator approval for live smoke, Trixie preflight JSON, ToolProxy live smoke transcript, live selftest transcript, forensics bundle path, journal bundle path, bundle SHA256, redaction manifest and a wiki patch manifest with target evidence references.

`post-reboot-service-health-readiness-core` narrows the service-health slice of that work while keeping it open in `blocked_until_target_post_reboot_service_health_evidence`. The target evidence must record the post-reboot boot ID, system-running state, failed units, gateway service active/status evidence, operator-approved manual start and stop evidence for `noemaforge-llama@main`, ToolProxy service active/status evidence, socket/API smoke output and a forensics archive hash. Local validation checks only the evidence contract, registry entry and documentation trace; it does not run systemd, socket probes, gateway requests, ToolProxy commands or LLM backend commands.

`post-reboot-gpu-gdm-gateway-toolproxy-readiness-core` narrows the composite post-reboot validation row that spans GPU, GDM, gateway and ToolProxy. It keeps the item open in `blocked_until_target_post_reboot_gpu_gdm_gateway_toolproxy_evidence` until the target records boot ID and system state, operator approval, display-manager/GDM and NVIDIA evidence, gateway and ToolProxy service states, gateway and ToolProxy socket smoke evidence, redaction review and a hashed forensics bundle. Local validation checks only the evidence contract, registry entry and documentation trace; it does not run systemd, NVIDIA, gateway, ToolProxy, LLM or archive commands.

`toolproxy-capability-live-smoke-readiness-core` narrows the ToolProxy capability-token live smoke that is not covered by the offline token UX pack. It keeps the item open in `blocked_until_target_toolproxy_capability_live_smoke_evidence` until the target records ToolProxy service and socket baseline, operator approval scoped to issue/verify, live `llm.chat` capability issue output, live verify output, redacted token preview, revocation/post-revocation evidence and a hashed forensics archive. Local validation checks only the evidence contract, registry entry and documentation trace; it does not run ToolProxy, systemd, socket or archive commands.

`toolproxy-live-llm-smoke-readiness-core` narrows the live ToolProxy socket plus `llm.chat` smoke path that uses `noemaforge toolproxy smoke --live-llm`. It keeps the item open in `blocked_until_target_toolproxy_live_llm_smoke_evidence` until the target records ToolProxy service/socket baseline, operator approval, `llm.chat` capability binding, live smoke JSON, LLM chat result, model identity, token revocation/post-revocation evidence, redaction proof and a hashed forensics archive. Local validation checks only the evidence contract, registry entry and documentation trace; it does not run ToolProxy, systemd, socket, LLM, revoke or archive commands.

`gateway-main-live-smoke-readiness-core` narrows the gateway plus `noemaforge-llama@main` smoke path into the target-only sequence that must be reviewed before closure. It keeps the item open in `blocked_until_target_gateway_main_live_smoke_evidence` until the target records gateway and main-backend service/socket baseline, operator approval, manual main-backend start transcript, gateway socket/status output, gateway smoke transcript, chat completion transcript, backend stop state and a hashed redacted archive. Local validation checks only the evidence contract, registry entry and documentation trace; it does not run systemd, socket probes, gateway commands, chat commands or LLM backend commands.

`trixie-preflight-target-readiness-core` narrows the target preflight line that feeds these post-reboot checks while keeping it open in `blocked_until_target_trixie_preflight_evidence`. The target evidence must record operator approval for the read-only `sudo noemaforge trixie-preflight --json` run, parseable JSON output, Debian release and kernel baseline, secure-boot state, llama-server dependency surface, gateway and ToolProxy socket state and a reviewed archive hash. Local validation checks only the evidence contract, registry entry and documentation trace; it does not run sudo, preflight, systemd, socket probes or remediation commands.

`failure-forensics-bundle-readiness-core` narrows the post-failure support bundle path while keeping it open in `blocked_until_target_failure_forensics_bundle_evidence`. The target evidence must record the failure surface, failure timestamp, operator approval, dry-run transcript, real `sudo noemaforge forensics` transcript, bundle path, SHA256, file inventory, redaction manifest, secret scan summary, runtime log excerpts and a reviewed findings or follow-up record. Local validation checks only the evidence contract, registry entry and documentation trace; it does not run sudo, forensics, journal, systemd or upload commands.

`target-gui-recovery-path-readiness-core` narrows the target-hardware recovery path into the exact ordered sequence `sudo noemaforge pause --wait` followed by `sudo noemaforge gui-rescue --wait`, while keeping it open in `blocked_until_target_gui_recovery_path_evidence`. The target evidence must record display-manager/GDM and graphical target baseline state, operator approval, pause transcript, GUI rescue transcript, proof that pause preceded rescue, post-rescue display state, `/run/nologin` absence, archive hash and inspection follow-up. Local validation checks only the evidence contract, registry entry and documentation trace; it does not run sudo, recovery, systemd or archive commands.

`systemd-gdm-nvidia-live-validation-readiness-core` narrows the direct systemd/GDM/NVIDIA live validation that remains after the broader target-live gate. It keeps the item open in `blocked_until_target_systemd_gdm_nvidia_live_validation_evidence` until the target records boot ID, system-running and failed-unit state, operator approval, display-manager/GDM and graphical target state, NVIDIA driver, GPU, module and memory signal, secure-boot state, kernel driver logs, `/run/nologin` absence, seat recovery evidence and a hashed redacted archive. Local validation checks only the evidence contract, registry entry and documentation trace; it does not run systemd, GDM, NVIDIA, journal, loginctl or archive commands.

The wiki patch is a review artifact, not an automatic target mutation. It should summarize the target evidence, reference the archived logs by hash, and update canonical docs only after operator review. The local readiness validator proves that this evidence shape, registry attachment and documentation trace exist, but it does not run `systemctl`, `journalctl`, live LLM smoke, forensics or wiki patch creation commands.

## Existing helper set

The base package already contains helpers such as:

- `noemaforge-llm-stop`
- `gui-status`
- `gui-rescue`
- `noemaforge-health`
- `noemaforge-start-llm-safe`
- `noemaforge-reboot-safe`
- `noemaforge-toolproxy-diag`

## Integration with TODO

0.32.1 does not apply runtime changes automatically. It adds prelaunch documentation and helper wrappers for Trixie/macOS so the next implementation pass can convert stable notes into tested installer logic.

