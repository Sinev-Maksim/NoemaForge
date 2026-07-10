# NoemaForge 0.33.0 Codex runner status

- timestamp: 2026-07-10T02:13:59+01:00
- repo: /home/cat/src/NoemaForge
- branch: codex/0.33.0-prod-ready-loop
- base: release/0.33.0-dev
- work_branch: codex/0.33.0-prod-ready-loop
- umbrella_issue: #221

## Git status

```text
 M install_noemaforge_mvp.sh
 M noemaforge/bin/noemaforge
 M noemaforge/bin/noemaforge-llama-start
 M noemaforge/configs/pipeline-teams.json
 M noemaforge/docs/TODO.md
 M noemaforge/docs/onboarding/MVP_OPERATOR_GUIDE.md
 M noemaforge/docs/onboarding/PRODUCTION_INSTALL_TRIXIE.md
 M noemaforge/docs/operations/operator-runbook.md
 M noemaforge/src/pipeline_runtime.py
 M noemaforge/systemd/dropins/noemaforge-autostart-gui.service.d/10-safe-gui-delay.conf
 M noemaforge/systemd/dropins/noemaforge-llama@.service.d/40-socket-perms.conf
 M noemaforge/systemd/dropins/noemaforge-llm-backends-manager.service.d/50-single-active-manager.conf
 M noemaforge/systemd/dropins/noemaforge-toolproxy.service.d/05-sel-perms.conf
 M noemaforge/systemd/dropins/noemaforge-toolproxy.service.d/10-root-preflight.conf
 M noemaforge/systemd/noemaforge-autostart-gui.service
 M noemaforge/systemd/noemaforge-autostart-gui.timer
 M noemaforge/systemd/noemaforge-autostart-wogui.service
 M noemaforge/systemd/noemaforge-llama@.service
 M noemaforge/systemd/noemaforge-llm-gateway.service
 M noemaforge/systemd/noemaforge-memsentinel.service
 M noemaforge/systemd/noemaforge-shutdown-stop.service
 M noemaforge/systemd/noemaforge-toolproxy.service
 M noemaforge/tests/test_pipeline_runtime_public_mwp.py
 M noemaforge/tools/ops/noemaforge-op-chatgpt-light.sh
 M noemaforge/tools/ops/noemaforge-op-common.sh
 M noemaforge/tools/ops/noemaforge-op-gui-rescue.sh
 M noemaforge/tools/ops/noemaforge-op-gui-status.sh
 M noemaforge/tools/ops/noemaforge-op-health.sh
 M noemaforge/tools/ops/noemaforge-op-llm-memory-override.sh
 M noemaforge/tools/ops/noemaforge-op-llm-stop.sh
 M noemaforge/tools/ops/noemaforge-op-manager.sh
 M noemaforge/tools/ops/noemaforge-op-nvidia-preflight.sh
 M noemaforge/tools/ops/noemaforge-op-safe-mode.sh
 M noemaforge/tools/ops/noemaforge-op-safe-start.sh
 M noemaforge/tools/ops/noemaforge-op-smoke.sh
 M noemaforge/tools/ops/noemaforge-op-start-llm-safe.sh
 M noemaforge/tools/prep/archive-firstboot-baseline.sh
 M noemaforge/tools/prep/noemaforge-av-readiness.sh
 M noemaforge/tools/prep/noemaforge-consistency-audit.sh
 M noemaforge/tools/prep/noemaforge-dashboard.sh
 M noemaforge/tools/prep/noemaforge-first-launch.sh
 M noemaforge/tools/prep/noemaforge-first-run-audit.sh
 M noemaforge/tools/prep/noemaforge-firstboot-from-share.sh
 M noemaforge/tools/prep/noemaforge-firstboot-smoke.sh
 M noemaforge/tools/prep/noemaforge-forensic-bundle.sh
 M noemaforge/tools/prep/noemaforge-forensics-bundle.sh
 M noemaforge/tools/prep/noemaforge-gui-diagnose.sh
 M noemaforge/tools/prep/noemaforge-gui-prepare.sh
 M noemaforge/tools/prep/noemaforge-gui-recover-minimal.sh
 M noemaforge/tools/prep/noemaforge-gui-start.sh
 M noemaforge/tools/prep/noemaforge-headless.sh
 M noemaforge/tools/prep/noemaforge-multimodal.sh
 M noemaforge/tools/prep/noemaforge-mvp-smoke.sh
 M noemaforge/tools/prep/noemaforge-persona-gui.sh
 M noemaforge/tools/prep/noemaforge-recursion-audit.sh
 M noemaforge/tools/prep/noemaforge-trixie-preflight.sh
 M noemaforge/tools/prep/noemaforge-version-audit.sh
 M noemaforge/tools/prep/run_check.sh
 M noemaforge/tools/prep/run_firstboot.sh
 M noemaforge/tools/prep/run_lab.sh
 M noemaforge/tools/prep/run_verify.sh
?? .codex/tasks/
?? noemaforge/tests/test_033_prod_ready_install_reentry.py
?? run_claude_033_fable5_merge_checker_loop.sh
?? run_codex_033_prod_ready_loop.sh
```

## Latest commits

```text
71285d9 Document 0.33.0 pre-release candidate state
269c539 Merge pull request #211 from Sinev-Maksim/codex/ux-197-per-message-run-mode-20260705T103624Z
0f880d6 Resolve #211 after 0.33.0 UX merges
bc58eb5 Merge pull request #210 from Sinev-Maksim/codex/ux-195-locale-aware-admin-pipeline-20260705T102349Z
2a98f80 Resolve #210 after 0.33.0 UX merges
4125541 Merge pull request #209 from Sinev-Maksim/codex/ux-193-status-timer-cadence-20260705T101714Z
ce5ad0f Resolve #209 after 0.33.0 UX merges
765776f Merge pull request #207 from Sinev-Maksim/codex/ux-192-default-task-state-20260704T173835Z
f430e42 Merge pull request #206 from Sinev-Maksim/codex/ux-191-product-metrics-degraded-20260704T173242Z
e94cb57 Merge pull request #205 from Sinev-Maksim/codex/ux-187-hw-sw-card-metadata-20260704T172657Z
```
