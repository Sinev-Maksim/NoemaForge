# Project identity

- Product: **NoemaForge** — local-first AI OS, privacy-first, runs on the production target host (Debian 13 Trixie, GNOME/GDM, RTX 3080 Ti).
- Repo: https://github.com/Sinev-Maksim/NoemaForge
- **Working base branch: `release/0.33.0-dev`** (0.32.2 and 0.33.0 are shipped to `main`; never commit to `main` directly).
- Version source of truth: `VERSION` file, bridged by `noemaforge/src/noemaforge_version.py`. `RUNTIME_VERSION =` is assigned **only** there; no version literals elsewhere.

# Where work comes from (canonical sources)

- `noemaforge/docs/TODO.md` — the canonical TODO: accepted optimization decisions (A/B/C/E), UAT fixpack items, 0.33.x roadmap, review-harvest backlog.
- `docs/ROADMAP.md` — milestone roadmap (0.33.0 GUI fixpack → 0.33.1 system independence → 0.33.2 hybrid LLM).
- `docs/uat/DEFECT-REGISTER-0.32.2.md` — canonical defect register (D-001…D-010, U-001…U-005, R/S/O items) driving the fixpack.
- `Claude_stats.md` — model-routing protocol + per-task stats (model, time, tokens, review fixes). Update it for every task.

# Language

- **All GitHub-facing text is English-only**: PR titles/bodies, comments, reviews, commit messages (imperative, concise). Chat with the owner is Russian.
- Code, file names, CLI commands: English.

# Workflow per task

1. Branch off fresh base: `git fetch origin && git checkout -b claude/<slug> origin/release/0.33.0-dev`.
2. Route the task per `Claude_stats.md` (S→Haiku, M→Sonnet, L→Opus, XL→Fable orchestrates); record a stats row with real token/time numbers.
3. Implement; verify before committing:
   - `python -m py_compile` on changed `.py`; YAML/JSON parse on changed configs; `bash -n` on changed `.sh` (use `C:\Program Files\Git\bin\bash.exe` on this machine).
   - Targeted pytest for touched areas; gates in a **pristine worktree** (`git worktree add`): `ci/wiki_check.py`, `docs_hygiene_runtime.py`, pytest.
4. Commit in small logical chunks; end commit messages with the Claude co-author line.
5. Push, open PR to `release/0.33.0-dev` with label `codex-review`, post `@coderabbitai review`.
6. Process review verdicts: fix Codex/CodeRabbit blockers; apply or TODO-log every `## Optimizations` item **before merge**; count review-fix rounds in stats.
7. The human merges. After base advances, re-sweep open branches if CI asks for it.

# Evidence lifecycle (A1 — IMPORTANT, replaces the old regen ritual)

- **Do NOT regenerate or commit MANIFEST/SHA256SUMS on task branches.** The premerge gate and acceptance workflow run `ci/regen_evidence.py` themselves (regen-then-verify); `evidence-refresh.yml` auto-commits refreshed evidence on `release/**` after merges; `.gitattributes` (`merge=ours`) keeps merges conflict-free on those files.
- Release archives/tags still carry exact committed evidence — produced by the refresh workflow, not by hand.

# CI surface

- `premerge-quality.yml` — py_compile, versions vs SoT, JSON/YAML, no caches, bash -n, evidence regen-then-verify, wiki integrity (`ci/wiki_check.py`), docs hygiene (step 11).
- `acceptance.yml` — artifact-driven AAT suite (regen step first).
- `autonomous-pipeline.yml` — validate-claude-push + Codex CLI review on the self-hosted Windows runner (enforced read-only sandbox; pre-flight digest supplies validation results; English-only output; evidence-stripped token-lean diff).
- `evidence-refresh.yml`, `wiki-sync.yml` (auto-publish wiki to GitHub Wiki on main), `p0-status-ledger.yml`, `scorecard.yml` (nightly).

# Docs and wiki

- Canonical trees live under the package root: `noemaforge/docs/**` (incl. the wiki at `noemaforge/docs/wiki/` — one article per page, indexed from `WIKI.md`; regenerate the hub index with `python ci/wiki_check.py --write-index` after adding pages).
- Forbidden strings in active files: see `noemaforge/configs/docs-hygiene-policy.json` → `forbidden_active_text` (legacy host name, legacy public-docs paths, stale-content marker). Never write them out.
- When behavior changes, update the affected maintained wiki article in the same PR.

# Display safety — production target host

- Every command that starts model selection or heavy GPU work MUST keep the display alive (`--keep-display` semantics). Stopping a display manager requires an explicit operator opt-in flag. Default stop helpers preserve the graphical desktop.

# Hard rules (never violate)

- No production GitHub Release without explicit human GO + target-host validation evidence.
- `noema upgrade` never removes/overwrites user or machine state.
- No `.pyc`/`__pycache__` in git; no new external runtime deps without discussion (runtime stays stdlib-only; optional extras live in `pyproject.toml`).
- Do not mark a task complete unless compile + targeted tests pass.
- Self-modification stays lab-only behind Pipeline_RFC + explicit approval.
