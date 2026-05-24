# NoemaForge 0.31.13.alpha-patched1: live runtime and model-selection fixes

## Context

This patch records the live legacy live-validation host validation findings after the NoemaForge rename and the first `patched6` dry-run model-selection attempts.

Observed blockers:

- `gui-rescue` and `gui_rescue` aliases were not consistently action aliases.
- `safe-start` could return `5/NOTINSTALLED` when core systemd units were missing.
- `noemaforge-llm-gateway` still had legacy socket defaults in the binary in earlier builds.
- `llama-server` wrapper still delegated through legacy backend paths in earlier builds.
- `noemaforge-llama@.service` was missing on the target host, so every model was marked `systemctl_start_failed:5`.
- ModelStore symlinks could still point to legacy share paths and trigger misleading `artifact_missing` errors.
- `patched6` treated per-model budget exhaustion after valid role scores as a global `failed_runtime`, invalidating good partial measurements.

## Patched7 decisions

### Runtime infrastructure must fail as infrastructure

If model backend infrastructure is missing or systemd reports a common startup failure such as `systemctl_start_failed:5`, the tournament writes:

```text
runtime-infrastructure-failure.json
```

and does not mark every model as bad.

### Partial valid model results are retained

If a model starts, passes warmup, and produces valid role scores, then later exhausts its per-model budget, it is marked:

```text
partial_valid_budget_exhausted
```

The model is not globally excluded from selection. Already measured role scores remain eligible. Unfinished roles remain unstaffed until another candidate fills them.

### Mandatory-core roles are evaluated first

The first-start tournament now prioritizes the alpha kernel roles:

```text
operator.admin/administrator
system.guard/surgeon
dev.work/solution_architect
writing.story/writer
```

Optional roles are evaluated after mandatory core roles.

### Installer runtime fixes

The installer now installs core units:

```text
noemaforge-llm-gateway.service
noemaforge-toolproxy.service
noemaforge-memsentinel.service
noemaforge-llama@.service
```

It also creates setup markers:

```text
/var/lib/noemaforge/.sys/setup.done
/var/lib/noemaforge/.sys/setup-state.json
```

and creates writable state directories for operator/runtime checks.

### NoemaForge runtime paths

Runtime defaults now use:

```text
/run/noemaforge/llm/gateway.sock
/run/noemaforge/llm/backends/main.sock
/opt/noemaforge/bin/llama-server
```

Legacy share migration is supported during install by bind/symlink migration when the old share is still the physical mount.

## Alpha validation gate

Before applying a first epoch:

```bash
sudo noemaforge first-start --normal --dry-run --show-candidates --per-model-timeout 180 --total-timeout 1200
```

The epoch must not be applied unless:

- `runtime-infrastructure-failure.json` is absent;
- `role-candidate-map.filtered.json` has selected mandatory core roles;
- failed-runtime models are excluded;
- partial-valid models retain only their successful role scores;
- `systemctl --failed` is clean or failures are documented as non-blocking.

