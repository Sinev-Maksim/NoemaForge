# Repository hardening (public repo)

NoemaForge is a public repository with an autonomous CI pipeline and a
**self-hosted runner on the maintainer's own machine**. That combination raises
the stakes: a weak branch or Actions posture is not just untidy, it is an attack
surface. This page records the protections in force and why. The branch rulesets
live as code under `.github/rulesets/` and are (re)applied with
`ci/apply_rulesets.sh`; nothing here is click-only state that can silently drift.

## Branch protection (rulesets)

| Branch | Rules | Rationale |
|---|---|---|
| `main` | block deletion · block force-push (non-fast-forward) · require pull request · require status checks (`Quality gate`, `Acceptance suite`) | Released history is immutable: no direct push, no rewrite, no delete; every change is a green PR. |
| `release/**` | block deletion · block force-push | The integration lines accept direct pushes (merge bursts + the evidence-refresh bot) but can never be rewritten or removed. |
| `claude/**`, `codex/**` | none | Throwaway feature branches; force-push is the normal workflow there. |

**No bypass actors.** The rules apply to everyone, including repository admins and
any access token. This is deliberate: the goal is to prevent force-push / deletion
*including* via a compromised token or an accidental `git push --force`. A genuine
history rewrite requires temporarily and explicitly disabling the ruleset in
Settings — friction that belongs in front of a destructive, irreversible action.

`required_approving_review_count` is `0` because the project is currently
single-maintainer (who cannot approve their own PR); the PR + green-checks
requirement still forces every `main` change through CI rather than a direct push.

## Self-hosted runner safety

The Codex review job runs on the self-hosted `BIGBRO-WIN` runner, which holds the
maintainer's Codex credentials. Three independent guards keep untrusted code off
it:

1. The autonomous-pipeline workflow has **no `pull_request` / `pull_request_target`
   trigger** — it fires only on `push` to `claude/**` / `codex/**`, and a fork
   cannot push to this repository's branches.
2. The job `if:` requires `github.event_name == 'push'` — explicit, and it survives
   a future accidental trigger addition.
3. The job `if:` also pins `github.actor` to the maintainer, so even an added
   collaborator's push does not execute on the personal machine.

The review step itself runs `codex exec -s read-only` and has **no `GITHUB_TOKEN`
in its environment** (the token is granted only to the two steps that call the
GitHub API), so the model process holds no write capability.

## Supply chain

- Every GitHub Action is **pinned to a full commit SHA** (tags kept as comments);
  Dependabot (`github-actions`, weekly) keeps the pins current.
- Workflow `GITHUB_TOKEN` defaults to read-only; write scope is granted per-job
  only where needed.
- Dependabot checks the root Python metadata (`pip`) and SHA-pinned GitHub
  Actions weekly. Updates are grouped, bounded, and require normal review; no
  dependency update is auto-merged. There is no `npm` ecosystem entry because
  the repository has no Node package manifest or lock file.
- `.github/workflows/semgrep.yml` runs Semgrep CE `1.166.0` with the official
  rules repository pinned at commit
  `d41fb34cf74466e2878af5f268ebf54466a04541`. It loads only the checked-out
  Python, JavaScript, TypeScript, and Go rule directories, disables registry
  metrics, and uploads `ERROR` findings as the `semgrep-ce` SARIF category.
- GitHub CodeQL default setup is the authoritative CodeQL lane. An advanced
  `codeql.yml` is intentionally absent because GitHub rejects advanced-setup
  SARIF uploads while default setup is enabled. Direct alert-count access was
  unavailable during this change, so no current open-alert count is claimed.
- Code Scanning findings are triaged before promotion to an issue. False
  positives are dismissed only with repository-specific rationale recorded in
  Code Scanning; issue creation remains manual to avoid permission expansion,
  duplicate alerts, and fork or Dependabot PR failures.
- Release evidence is generated and verified in CI (`ci/regen_evidence.py`); the
  committed copies on release branches are maintained by `evidence-refresh.yml`.

## Operator settings (GitHub UI, maintainer-applied)

A few protections live in repo Settings rather than in code and are applied by the
maintainer:

- **Actions → Fork pull request workflows**: require approval for outside
  contributors before any workflow runs.
- **Code security**: enable secret scanning + push protection (free for public
  repos) and private vulnerability reporting.
- Optionally **Actions → Allowed actions**: restrict to selected / verified
  creators, and enforce repository-level SHA-pinning.
