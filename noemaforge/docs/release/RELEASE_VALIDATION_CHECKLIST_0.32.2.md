# NoemaForge 0.32.2 Release Validation Checklist

## P0 local static gates

```bash
noemaforge version-audit --strict-all --expected 0.32.2
python3 -m py_compile $(find noemaforge/src -name '*.py')
find . -name '*.sh' -type f -exec bash -n {} \;
```

## P0 target-machine gates

- [ ] GUI remains active during install and dry-run first-start.
- [ ] Admin chat replies conversationally to smalltalk/help without launching a pipeline.
- [ ] Mode switch persists and is visible after refresh.
- [ ] Continue model selection creates one job and duplicate clicks return the same job.
- [ ] Re-inventory Vault returns either a successful job or a clear privileged fallback command.
- [ ] Page refresh restores message history and active job state.
- [ ] Job stop/cancel returns a visible state and does not leave stale active jobs.
- [ ] Gateway, ToolProxy and main llama backend smoke tests pass or return clear blocked status.

## P0 failure bundle

If a target gate fails, collect:

```bash
systemctl --failed --no-pager
systemctl status display-manager.service gdm.service --no-pager -l
journalctl -b -p warning --no-pager | tail -300
dmesg -T | tail -300
find /var/lib/noemaforge -maxdepth 3 -type f | sort | tail -200
```
