# NoemaForge 0.31.13.alpha HOW2START

## 1. Stop runtime before installation

Keep the Debian display manager running. Stop NoemaForge runtime services and stale sockets:

```bash
sudo noemaforge first-start abort 2>/dev/null || true
sudo systemctl stop noemaforge-first-start.service noemaforge-llm-gateway.service noemaforge-toolproxy.service noemaforge-memsentinel.service 2>/dev/null || true
systemctl list-units --type=service --all 'noemaforge-llama@*.service' --no-legend | awk '{print $1}' | xargs -r sudo systemctl stop
noemaforge dashboard stop 2>/dev/null || true
sudo rm -f /run/noemaforge/llm/gateway.sock /run/noemaforge/llm/backends/*.sock /run/brainos/llm/gateway.sock /run/brainos/llm/backends/*.sock
sudo systemctl daemon-reload
sudo systemctl reset-failed
```

## 2. Install

```bash
cd ~/Downloads
sha256sum -c noemaforge_0.31.13.alpha_prelaunch.tar.gz.sha256
rm -rf noemaforge_0.31.13.alpha_prelaunch
tar -xzf noemaforge_0.31.13.alpha_prelaunch.tar.gz
cd noemaforge_0.31.13.alpha_prelaunch
./setup.sh --mode vm --dry-run --selftest
sudo ./setup.sh --mode host --model-profile minimal --with-share /mnt/noemaforge-share
hash -r
```

## 3. Validate

```bash
noemaforge version
noemaforge version-audit --json
noemaforge consistency-audit --json
sudo noemaforge trixie-preflight --json
NOEMAFORGE_PIPELINE_STATE=/var/lib/noemaforge/pipelines noemaforge pipeline validate
systemctl get-default
systemctl --failed --no-pager
```

## 4. Start GUI

```bash
noemaforge dashboard stop 2>/dev/null || true
noemaforge gui console start --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

## 5. First-start candidate review

Use dry-run before any real full/composite run:

```bash
sudo noemaforge first-start --normal --dry-run --show-candidates --per-model-timeout 240 --total-timeout 1200
noemaforge first-start summary --latest
```

A heavy real run should be monitored from a terminal and can be aborted safely:

```bash
NOEMAFORGE_FIRST_START_TTY_STATUS_INTERVAL=10 sudo noemaforge first-start --full_composite 4 --show-candidates --show-compositions --per-model-timeout 240 --total-timeout 7200
sudo noemaforge first-start abort
```

## 6. Recovery

```bash
sudo noemaforge emergency-recover
```

The recovery path restores `graphical.target`, starts the display manager with `--no-block`, removes `/run/nologin` when appropriate and avoids using high-level headless wrappers as the first rescue step.

## Legacy compact quickstart merged from HOW2START_0.31.13.alpha.md

```bash
cd ~/Downloads
sha256sum -c noemaforge_0.31.13.alpha_prelaunch.tar.gz.sha256
rm -rf noemaforge_0.31.13.alpha_prelaunch
tar -xzf noemaforge_0.31.13.alpha_prelaunch.tar.gz
cd noemaforge_0.31.13.alpha_prelaunch
./setup.sh --mode vm --dry-run --selftest
sudo ./setup.sh --mode host --model-profile minimal --with-share /mnt/noemaforge-share
hash -r
noemaforge version
noemaforge version-audit --json
noemaforge consistency-audit --json
noemaforge gui console start --port 8765
```

Open `http://127.0.0.1:8765/`.
