# Provider Bootstrap and Budget-Safe Validation for Pipeline v47

Status: target-host operator runbook  
Budget policy: use existing subscriptions and explicitly free tiers; no new
purchase or automatic overage.

This runbook records the current BigBro-BOS state and the next safe validation
steps. It contains no credentials and must not be used as proof that a provider
is integrated until the requested evidence is captured.

## 1. Kimi Code / Kimi K3

### Current state

- Kimi Code `0.28.1` is installed.
- Device OAuth completed far enough to reach the models endpoint.
- The endpoint rejected the account because active membership benefits could
  not be verified.
- The Kimi UI explicitly offered a membership upgrade.

### Decision

Do not upgrade and do not retry in a loop. Mark the provider:

```text
provider=moonshot
surface=kimi-code
state=blocked_membership
retry_after=owner_policy_change
```

The CLI may remain installed for later capability probes. Do not store device
codes, cookies, or OAuth material in the repository or evidence reports.

### Next no-cost step

No K3 execution is currently available through this account. Implement the
adapter's blocked-state detection and continue with other providers. Re-probe
only after the owner explicitly reports that account entitlement changed.

## 2. Google Antigravity with Google AI Plus

### Current state

- Antigravity CLI `1.1.4` is installed at `~/.local/bin/agy`.
- The owner reports Google AI Plus, not Google AI Pro.
- A successful first-launch/login/model/quota transcript has not yet been
  captured.

Google currently gives baseline Antigravity access to individual accounts.
Higher Antigravity quota is specifically documented for AI Pro and Ultra.
Therefore Plus must be treated as baseline access until the CLI reports exact
quota.

### Step-by-step probe

1. Open a fresh shell.
2. Create a disposable source export with no `.git` directory.
3. Start `agy` from that export.
4. Complete first-launch login and workspace trust.
5. Open `/usage` or `/quota` and capture only model/quota names and refresh
   information.
6. Open `/config` or settings and set AI-credit overages to `Never`.
7. Reject every mutation request during the first run.
8. Ask for a read-only architecture and release-risk review.
9. Save a sanitized transcript with provider, model, quota class, duration, and
   zero changed files.

Do not assume Plus grants Pro quotas. Do not enable credit overages.

## 3. Hermes Agent free path

### Current state

- Hermes Agent `0.18.2` is installed in the dedicated Hermes home.
- Nous Portal OAuth succeeded.
- `tencent/hy3:free` completed a basic chat.
- `stepfun/step-3.7-flash:free` was also listed.
- The terminal backend remained `local`.
- Bundled skills were synchronized automatically.
- GitHub token, web-search providers, browser engine, and Skills Hub were not
  configured.

### Safety action before repository use

The current local terminal backend is not approved for NoemaForge mutation.

1. Keep the existing installation as a lab profile.
2. Run `hermes setup terminal`.
3. Select a containerized backend before any repository task.
4. Keep approvals manual.
5. Do not configure GitHub credentials or GitHub Skills Hub.
6. Do not install the messaging gateway or unattended cron.
7. Inventory and hash bundled skills; enable only an allowlisted subset for the
   test profile.
8. Disable persistent memory/skill creation for the first pipeline benchmark
   where the setup mode permits it.
9. Use a disposable repository export without `.git`.
10. Run one read-only task, then one bounded write task in a disposable copy.
11. Record model, free tag, context use, tool calls, changed files, duration,
    and quota/limit response.

Free tags are runtime catalog state, not a permanent guarantee. The provider
adapter must pause cleanly when a free model disappears or its quota is
exhausted.

### Initial Hermes role

Hermes is an acceleration/reference harness, not the NoemaForge control plane.
Use it for:

- bounded subagent experiments;
- skills and routing pattern evaluation;
- cross-family review;
- provider fallback tests.

Do not let it merge, push, mutate the control checkout, or approve its own
output.

## 4. Ollama local provider

### Current state

- Ollama client `0.32.1` is installed.
- The installer created and enabled `ollama.service`.
- The client reported that it could not connect to a running instance.
- NVIDIA GPU was detected.

### Diagnosis sequence

Run, in order:

```bash
sudo systemctl status ollama --no-pager -l
sudo journalctl -u ollama -n 200 --no-pager
sudo systemctl restart ollama
curl -fsS http://127.0.0.1:11434/api/version
ollama -v
```

If the service still fails, capture the unit, environment, logs, port state,
and NVIDIA access before changing configuration. Do not download a model until
the API health probe passes.

### First local benchmark

After service health:

1. choose one model that fits the RTX 3080 Ti 12 GB budget;
2. keep only one heavy model loaded;
3. test schema-constrained classification and summarization first;
4. capture VRAM, latency, context size, and structured-output quality;
5. do not use a local model for final release decisions until independently
   reviewed.

## 5. Provider evidence contract

Every provider capability probe must emit:

- provider and model identifiers;
- client/CLI version;
- authentication class without secrets;
- free/subscription/baseline quota class;
- exact capabilities observed;
- context/output limits when reported;
- tool and mutation policy;
- elapsed time and terminal result;
- changed-file count;
- provider-limit or membership failure classification;
- sanitized artifact hashes.

Installation success alone is not a provider PASS.
