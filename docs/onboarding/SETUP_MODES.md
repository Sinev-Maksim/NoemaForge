# NoemaForge setup modes

Setup default path boundary: The blessed onboarding path is release unpack or git clone, then root ./setup.sh in VM mode first, then host install only by explicit operator choice; Windows helpers are optional side tools and are never required for the canonical path.

Setup mode boundary: Linux host mode uses native services and local paths, macOS dev mode is non-privileged validation and light workflows, VM mode is the recommended no-risk onboarding path, and docker-dev is development/test only, not the full production NoemaForge path.

Onboarding ladder boundary: README.md is the 5-minute overview, docs/QUICKSTART_VM.md is the first-success VM path, docs/SETUP_MODES.md explains host/VM/docker-dev/macOS-dev differences, and docs/PRODUCTION_INSTALL_TRIXIE.md is only entered after quickstart validation; primary docs do not lead with Windows lab workflow.

## VM mode

Recommended first public path. It validates the package and lets the operator learn commands without risking the host.

```bash
./setup.sh --mode vm --dry-run --selftest
```

## Host mode

Installs CLI, helpers, docs, and safe defaults to the local Linux host. It does not auto-start heavy LLMs.

```bash
sudo ./setup.sh --mode host --model-profile minimal
```

## Docker-dev mode

Development/test mode only. It is useful for syntax checks and alternate-root installs, not for a production NoemaForge runtime.

```bash
./setup.sh --mode docker-dev --dry-run --selftest
```

## macOS-dev mode

Non-privileged validation mode. NoemaForge production services are Linux/systemd-oriented; macOS mode is for repository validation and light workflow checks.

```bash
./setup.sh --mode macos-dev --dry-run --selftest
```

## Model profiles

```bash
noemaforge profiles list
noemaforge profiles recommend
```

All profiles keep `max_active_llms=1`.

After `docs/onboarding/QUICKSTART_VM.md` passes and host mode is chosen intentionally, continue to `docs/onboarding/PRODUCTION_INSTALL_TRIXIE.md`.
