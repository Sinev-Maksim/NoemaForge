# NoemaForge 0.32.1 quickstart - first-success VM path

This is the recommended first public-MWP path.

Onboarding ladder boundary: README.md is the 5-minute overview, docs/QUICKSTART_VM.md is the first-success VM path, docs/SETUP_MODES.md explains host/VM/docker-dev/macOS-dev differences, and docs/PRODUCTION_INSTALL_TRIXIE.md is only entered after quickstart validation; primary docs do not lead with Windows lab workflow.

Setup default path boundary: The blessed onboarding path is release unpack or git clone, then root ./setup.sh in VM mode first, then host install only by explicit operator choice; Windows helpers are optional side tools and are never required for the canonical path.

## 1. Validate the package

```bash
./setup.sh --mode vm --dry-run --selftest
```

Expected outcome: no install, no service start, no model download.

## 2. Inspect safe model profile

```bash
NOEMAFORGE_ROOT="$PWD/noemaforge" noemaforge/bin/noemaforge profiles recommend
NOEMAFORGE_ROOT="$PWD/noemaforge" noemaforge/bin/noemaforge profiles list
```

## 3. Validate pipelines

```bash
NOEMAFORGE_ROOT="$PWD/noemaforge" noemaforge/bin/noemaforge pipeline validate --state /tmp/noemaforge-pipelines
NOEMAFORGE_ROOT="$PWD/noemaforge" noemaforge/bin/noemaforge pipeline run public_mwp \
  --state /tmp/noemaforge-pipelines \
  --task-id first-run \
  --project local \
  --request "first public-MWP run"
```

## 4. Host install after validation

Read `docs/onboarding/SETUP_MODES.md` first. Continue to `docs/onboarding/PRODUCTION_INSTALL_TRIXIE.md` only after this quickstart validation passes.

```bash
sudo ./setup.sh --mode host --model-profile minimal
```

Then:

```bash
noemaforge help
noemaforge profiles recommend
sudo noemaforge stop --dry-run
noemaforge pipeline validate
sudo noemaforge trixie-preflight --json
```

## 5. Manual runtime start only when ready

```bash
sudo noemaforge safe-start --wait --restart
noemaforge smoke --debug
```

Stop/pause:

```bash
sudo noemaforge pause --wait
```
