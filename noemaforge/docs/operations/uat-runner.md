# UAT runner — the one-command UAT button

`noemaforge uat run` performs a full UAT pass as a single command and returns the
evidence as a bundle (not just side effects). It sequentially:

1. **Starts event recording** — into a dedicated event-log dir for the session.
2. **Launches the Admin GUI** — display-safe, pointed at the same event log
   (skip with `--no-gui`; the GUI is exercised on the target host).
3. **Runs every pipeline** in the catalog in turn, saving each run's artifacts
   into the logging folder. A pipeline failure is captured as evidence, not a
   stop — every pipeline produces a recorded response.
4. **Stops the GUI and the event recording**, then writes a self-describing
   bundle.

## Usage

```bash
# clean-venv bootstrap gate before live/functional execution:
python -m pip install -e ".[dev]"
noemaforge uat check

noemaforge uat run --out <logging-dir>
# headless (no GUI), a subset, or a no-side-effect plan:
noemaforge uat run --out <dir> --no-gui --pipelines public_mwp,evolution
noemaforge uat run --out <dir> --dry-run
```

`noemaforge uat check` is read-only. It validates the expected release branch,
clean worktree, `VERSION` files, `pyproject.toml` dev dependency contract,
importability of `pytest`, `yaml` and `jsonschema`, `compileall` for
`noemaforge/src`, pytest collection, docs hygiene and UAT runner help. It does
not launch the GUI, services, model backends, pipelines, downloads or target-host
live checks.

Options: `--out` (defaults to `$UAT_DIR` or a safe temp directory),
`--pipelines a,b` (default: all), `--request TEXT`
(passed to each pipeline), `--timeout N` (per pipeline), `--gui/--no-gui`,
`--dry-run`, `--keep-display` (on by default — display-safety rule).

## Bundle layout (`--out`)

```text
<out>/
  manifest.json        # kind=NoemaForgeUATBundle: per-pipeline status + counts
  summary.md           # human-readable per-pipeline table
  events/events.jsonl  # the recorded event stream (start … stop)
  pipelines/<id>/      # per pipeline: stdout.txt, stderr.txt, run_dir/ (artifacts)
  gui/                 # gui.json + gui.log (when the GUI is launched)
```

Keep the bundle directory **outside** the repository tree (it is run output, not
tracked content). `manifest.json.summary` reports `total / ok / failed /
artifacts`; the printed JSON returns the bundle path.
