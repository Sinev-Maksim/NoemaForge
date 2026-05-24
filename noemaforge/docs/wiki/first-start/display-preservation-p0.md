# NoemaForge 0.31.13.alpha-patched1 display-preservation P0 fix

## Purpose

This page records the P0 safety rule added after a real model-selection run caused local monitor blackout / display-manager handoff failures.

## Rule

First-start and model-selection must preserve the local Debian GUI/display-manager by default.

Display stop is permitted only when all of the following are true:

1. the operator explicitly passes `--soft-headless`;
2. the operator also passes `--allow-display-stop` or `--allow-headless-display-stop`;
3. the command is not a GUI-triggered hidden job;
4. recovery/abort remains available.

## Safe defaults

```text
sudo noemaforge first-start --full_composite 4 --keep-display
sudo noemaforge first-start --full_composite 4 --dry-run --keep-display
```

## Unsafe opt-in

```text
sudo noemaforge first-start --full_composite 4 --soft-headless --allow-display-stop
```

This path is intentionally not used by the GUI.

## GUI continuation behavior

`Continue model selection` creates a job/plan and exposes progress and suggested commands. It does not start a privileged real selection process from the browser. Its safe command is dry-run and keep-display by default; a real command is shown separately for operator-approved terminal execution.

## Tests

- `bash -n noemaforge/bin/noemaforge`
- `bash -n noemaforge/tools/prep/noemaforge-first-launch.sh`
- `noemaforge first-start --help` shows display-stop opt-in rules
- GUI `/api/model-selection/continue` returns commands containing `--keep-display`
