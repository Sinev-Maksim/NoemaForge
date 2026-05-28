# NoemaForge 0.30.0 MVP operator guide

Onboarding ladder boundary: README.md is the 5-minute overview, docs/QUICKSTART_VM.md is the first-success VM path, docs/SETUP_MODES.md explains host/VM/docker-dev/macOS-dev differences, and docs/PRODUCTION_INSTALL_TRIXIE.md is only entered after quickstart validation; primary docs do not lead with Windows lab workflow.

Enter this guide after `docs/onboarding/PRODUCTION_INSTALL_TRIXIE.md` or a successful VM dry run, not as the first setup document.

## Safe day-one loop

```bash
noemaforge status
noemaforge profiles recommend
noemaforge pipeline catalog
noemaforge pipeline run public_mwp --request "operator onboarding"
noemaforge pipeline dashboard-state --out /tmp/noemaforge-dashboard-state.json
```

## Start/stop runtime

```bash
sudo noemaforge safe-start --wait --restart
noemaforge smoke --debug
sudo noemaforge pause --wait
```

## Ask the local model without curl

```bash
noemaforge chat --role admin --once "Ответь одним словом: OK"
noemaforge interpret "systemctl --failed --no-pager"
```

## Support bundle

```bash
sudo noemaforge forensics --dry-run
sudo noemaforge forensics
```

The bundle excludes model weights, Vault contents, browser profiles, and obvious token/secret paths.

## Pipelines

A NoemaForge pipeline is a sequence of stage context packets and auditable artifacts. It is designed for switchable LLMs, not multiple simultaneous heavy models.

```bash
noemaforge pipeline run evolution --task-id fix-001 --project noemaforge --request "fix operator CLI"
noemaforge pipeline summary <run_id>
noemaforge pipeline next <run_id>
noemaforge pipeline artifact add <run_id> --stage intake --type markdown --path outputs/fix.md --meta summary="implementation note"
noemaforge pipeline export <run_id>
```
