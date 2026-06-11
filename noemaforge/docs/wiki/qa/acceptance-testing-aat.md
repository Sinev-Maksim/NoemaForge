# Acceptance testing — the artifact-driven AAT suite

The AAT suite proves the **evidence chain**, not just the code: every
acceptance case ends in a saved, verifiable artifact bundle under `results/`
(with `summary.json` and a SHA256 manifest), so a verdict can always be traced
back to bytes. The canonical spec is
`noemaforge/docs/quality/AAT_SUITE.md`; this page is the maintained overview.

## Tiers

**CI tier (shipped).** Runs in GitHub Actions on every push/PR via
`.github/workflows/acceptance.yml` (`ci/run_acceptance.sh` →
`ci/acceptance_runner.py` + pytest). Gating cases:

| Case | Proves |
|---|---|
| `checksum_validation` | release MANIFEST/SHA256SUMS are internally consistent |
| `telemetry_privacy` | privacy filter strips planted secrets/paths from stored artifacts |
| `capability_tokens` | minted ToolProxy token verifies; revoked/expired/tampered are rejected |
| `toolproxy_isolation` | gateway is unix-socket-only; exec allowlist bounded, deny-by-default |
| `signed_manifest_verification` | release provenance policy mandates signatures; subject records well-formed |
| `contract_epoch_immutability` | canonical epoch hash is stable without an explicit revision |

plus best-effort `install_dry_run`.

**Nightly/security tier (shipped).** OpenSSF Scorecard
(`.github/workflows/scorecard.yml`) publishes supply-chain posture nightly.

**Target tier (pending).** Cases that need the production target host:
`no_hidden_autostart` (install+boot snapshot diff shows no unexpected LLM or
media processes) and `model_warmup_modes` (heavy warmup only after explicit
action), plus live ToolProxy smoke and cosign/attestation verification.

**LLM tier (pending).** Cases that need a live model: `grounded_summary`,
`safe_refusal_boundary`, `toolproxy_event_explainer`,
`epoch_diff_interpreter`, `cost_ceiling_guard`.

**GUI tier (planned, from UAT).** The all-pipeline test/demo mode (defect
register U-004): one control runs every available pipeline in safe test mode
with small built-in prompts and exports a summary report (pipeline, case,
status, artifact, error, duration, persona). This is the operator-visible
face of the suite.

## Relationship to UAT

AAT automates what the manual UAT campaign proved by hand. The 2026-06-08/10
target-host UAT (migration, clean install, full-composite first-start, Admin
GUI) is recorded under `docs/uat/` at the project root, with the canonical
defect register feeding the fixpack backlog. As target-tier cases land, the
manual steps they cover shrink to spot checks.

## Running locally

```bash
bash ci/run_acceptance.sh results/
python -m pytest ci/acceptance -q
```

The harness exits non-zero when a gating case fails; pending tiers are
reported but do not gate until implemented.
