# NoemaForge production install - Debian Trixie after quickstart

Onboarding ladder boundary: README.md is the 5-minute overview, docs/QUICKSTART_VM.md is the first-success VM path, docs/SETUP_MODES.md explains host/VM/docker-dev/macOS-dev differences, and docs/PRODUCTION_INSTALL_TRIXIE.md is only entered after quickstart validation; primary docs do not lead with Windows lab workflow.

Use this page only after `docs/onboarding/QUICKSTART_VM.md` passes on an Ubuntu/Debian VM or equivalent no-risk validation host.

## Prerequisites

- `./setup.sh --mode vm --dry-run --selftest` completed without failures.
- `docs/SETUP_MODES.md` was reviewed and host mode was chosen intentionally.
- The operator has a local data root and, if needed, an existing Vault/share path.
- Heavy LLM backends remain manual-only; setup does not auto-download models.

## Install

```bash
sudo ./setup.sh --mode host --model-profile minimal --with-share /mnt/noemaforge-share
```

For a custom data root:

```bash
sudo ./setup.sh --mode host --model-profile minimal --data-root /var/lib/noemaforge --with-share /mnt/noemaforge-share
```

## Verify

```bash
noemaforge help
noemaforge profiles recommend
noemaforge first-start progress --status /var/lib/noemaforge/firstboot/status.json
sudo noemaforge trixie-preflight --json
noemaforge pipeline validate --json
```

The installer installs `/opt/noemaforge` as a root-owned immutable payload:
directories are `0755`, regular files are `0644`, and files listed in
`/opt/noemaforge/tools/prep/executable_manifest.txt` are `0755`. Mutable runtime
state belongs under `/var/lib/noemaforge`, `/run/noemaforge`, or the documented
share/modelstore paths, not under `/opt/noemaforge`.

For a `runtime_only` re-entry, validate the selected profile rather than the main
backend profile:

```bash
sudo noemaforge safe-start --wait --llm-profile=runtime_only
noemaforge smoke --profile runtime_only --debug
noemaforge mvp-smoke --json
```

`runtime_only` starts gateway and ToolProxy only. A missing
`/run/noemaforge/llm/backends/main.sock` is expected in this profile and must be
reported as an expected skip, not as an install failure.

`safe-start` starts services for the current session by default. It does not
persistently enable gateway, ToolProxy, manager timers, or the main backend unless
the operator supplies an explicit persistence flag such as `--persist-services`
or changes policy with `noemaforge boot-mode`.

If `mvp-smoke --json` fails, inspect `state` in the JSON output. Failed checks
include command metadata plus `stdout_path`, `stderr_path`, and `report_path`
under `state/checks/<check_id>/`.

## Clean Install Evidence Gate

`clean-install-share-readiness-core` keeps the clean install with `/mnt/noemaforge-share` in `blocked_until_target_clean_install_evidence` until the target host records an install transcript, dry-run/selftest output, canonical share mount evidence, post-install preflight, emergency-mode guard and forensics archive. The local prelaunch validator checks only that evidence shape and documentation trace; it does not run setup, mount, systemd or forensics commands.

For the live target pass, keep `/mnt/noemaforge-share` as the share root, verify the fstab or systemd mount path uses non-blocking nofail/automount semantics, and archive the command outputs before closing the TODO. Previous install or migration context may appear only as archive/readonly evidence, not as an active runtime root.

## Next

Continue with `docs/onboarding/MVP_OPERATOR_GUIDE.md` for day-one operator commands and recovery habits.
