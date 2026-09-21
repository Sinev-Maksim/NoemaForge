# Night Watch Recovery / Resume Procedure

**Purpose:** resume work after chat loss, agent loss, machine interruption, or incomplete WIP.

## Mandatory resume order

1. Checkout `night-watch`.
2. Read:
   - `NIGHT_WATCH_DEVELOPMENT_RULES.md`;
   - `NIGHT_WATCH_STATUS.md`;
   - `NIGHT_WATCH_CONTEXT.md`;
   - this file.
3. Verify the exact NoemaForge base and any candidate/release hashes before trusting old review/evidence.
4. Recover the exact frozen v3.8.5 bytes when source-level/replay work is required:
   - outer SHA-256: `6adbcabac444c393cb40b7f4cb495b6a78d410c2adefe2ce81cbd74aad3dbd5d`;
   - inner SHA-256: `16e11736e5241e310b56f84acdd3a71e1d95b9a27f3a29d9ee26f221b45e371c`.
5. Do not substitute reports, a similar ZIP, or an older target log for the exact frozen bytes.
6. If the exact artifact is available, extract cleanly and rerun deterministic qualification before making a new release claim.
7. Run the exact final frozen candidate on a real Windows PowerShell 5.1 target and preserve the host preflight/installer/runtime evidence.
8. Perform remote independent exact-SHA review / CodeRabbit when required.
9. Only after external gates and human GO may promotion/merge/release proceed.

## If exact frozen bytes are unavailable

Treat source-level rerun as **BLOCKED_BY_ARTIFACT_AVAILABILITY**, not as a product failure and not as evidence that prior qualification failed.

Persist the availability finding and continue all other safe evidence/documentation work.

## WIP durability

Before any risky next iteration or session end:

- update canonical Markdown if understanding/status changed;
- commit code/evidence/docs that are materially useful;
- push to `night-watch`;
- mark incomplete commits `unstable, saved for context`.

Never leave the only recoverable copy in a chat, local temp directory, unpushed worktree, or assistant memory.
