# Guided scenario — the canonical demo path

One polished, end-to-end walkthrough of NoemaForge: **install → dashboard → pipeline draft →
approval gate → artifact download → selftest trend → forensics bundle.** Each step shows the exact
command, what you should see, and where the governance boundary sits. It is display-safe and
operator-gated throughout: nothing privileged or GPU happens without your approval.

> **Screenshots/gifs:** image slots are reserved below as HTML comments so this page renders
> cleanly today. To produce the gif/screenshot set, run the steps on a live host and drop captures
> into `noemaforge/docs/showcase/assets/` (suggested names noted per step), then uncomment the
> matching `![…]` line. See [Capturing the assets](#capturing-the-assets).

---

## 0. Install (≈3 min)

```bash
# From the release package (target host):
sudo ./setup.sh --mode host --model-profile minimal --with-share /mnt/noemaforge-share
# or validate first, non-destructively:
./setup.sh --mode vm --dry-run --selftest
```

You should see a `NoemaForge <version> setup plan` with the safety invariants
(`max_active_llms=1`, `heavy_llm_autostart=manual_only`). No heavy backend is started.

<!-- ![Install plan](assets/00-install.png) -->

## 1. Readiness + one-button start (≈1 min)

```bash
noema doctor          # read-only readiness (Python, paths, policies/schemas, backends)
noema start           # ensures local dirs, launches the localhost Admin GUI, opens the browser
#                       → http://127.0.0.1:8765/   (Windows: tools\windows\run_admin_gui.ps1)
```

`noema start` refuses a non-loopback host and starts no GPU/model work — it brings up only the
localhost control plane.

<!-- ![doctor + start](assets/01-doctor-start.png) -->

## 2. The dashboard

Open `http://127.0.0.1:8765/`. You land on the control plane: a session header, the job/event
timeline, model-selection modes, and the pipeline panel. Everything here *plans*; it does not
execute privilege.

<!-- ![Admin dashboard](assets/02-dashboard.png) -->

## 3. Draft a pipeline

In the pipeline panel, draft a pipeline (e.g. the `research` flow). The draft is a **plan**: it
lists the stages, the roles, and the capability requirements — but it does not run yet.

<!-- ![Pipeline draft](assets/03-pipeline-draft.png) -->

## 4. The approval gate

A privileged or heavy step is surfaced as an **explicit, reviewable plan + the exact command to
run** — it never auto-applies. Model selection / first-start always carries `--keep-display`:

```bash
sudo noemaforge first-start --normal --keep-display --show-candidates
```

This is the boundary in action: see
[“What cannot happen automatically”](../security/TRUST_BOUNDARIES.md#what-cannot-happen-automatically).

<!-- ![Approval gate](assets/04-approval-gate.png) -->

## 5. Open / download an artifact

Completed jobs produce artifacts (plans, decisions, model-run records). Open one from the job
timeline and download it. Artifacts are content-addressed and listed in the run’s evidence.

<!-- ![Artifact download](assets/05-artifact.png) -->

## 6. Selftest trend

Run the smoke / selftest surface and view the trend — health over time, not a single point:

```bash
noemaforge smoke            # backend/gateway liveness + health
# the dashboard shows the selftest/health trend panel
```

<!-- ![Selftest trend](assets/06-selftest-trend.png) -->

## 7. Forensics bundle

Collect a diagnostics/forensics bundle for the run (event log slice, job/session metadata,
rollback record) — the same evidence the release pipeline publishes:

```bash
sudo noemaforge first-start diagnostics     # operator-run diagnostics bundle
# release-wide acceptance evidence is published by the publish-evidence workflow (one-click download)
```

<!-- ![Forensics bundle](assets/07-forensics.png) -->

---

## What this demonstrates

- **Operator-in-the-loop** — every privileged/GPU step was an explicit, approved command.
- **Plan-then-apply** — pipelines and model selection are plans first.
- **Auditable + reversible** — jobs/events/artifacts are persisted; epochs are rollback-able.
- **Verifiable** — the same evidence is downloadable from CI (see
  [`../ci/PIPELINE.md`](../ci/PIPELINE.md) → `publish-evidence`).

## Capturing the assets

To produce the short gif/screenshot set referenced above:
1. Run steps 0–7 on a live host with the Admin GUI open.
2. Capture each numbered step (a screen recorder for a single end-to-end gif works well).
3. Save into `noemaforge/docs/showcase/assets/` using the `NN-name.png` names noted per step
   (e.g. `02-dashboard.png`), or a single `walkthrough.gif`.
4. Uncomment the matching `![…]` lines here and link the gif from the README dashboard section.

Display-safety reminder: any capture that involves model selection / GPU must use `--keep-display`.
