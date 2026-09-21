# Night Watch Recovery / Resume Procedure

**Purpose:** resume work after chat loss, agent loss, machine interruption, or incomplete WIP.

## Mandatory resume order

1. Checkout `night-watch`.
2. Read:
   - `NIGHT_WATCH_DEVELOPMENT_RULES.md`;
   - `NIGHT_WATCH_STATUS.md`;
   - `NIGHT_WATCH_CONTEXT.md`;
   - `NIGHT_WATCH_RECHECK_2026-09-21.md`;
   - this file.
3. Verify the exact NoemaForge base and release hashes before trusting old review/evidence.
4. Use only the recovered exact frozen v3.8.5 installer whose outer SHA-256 is:
   `6adbcabac444c393cb40b7f4cb495b6a78d410c2adefe2ce81cbd74aad3dbd5d`.
5. The nested sealed release must have SHA-256:
   `16e11736e5241e310b56f84acdd3a71e1d95b9a27f3a29d9ee26f221b45e371c`.
6. Do not substitute reports, a similar ZIP, or an older target log for these exact bytes.
7. Clean-extract before every qualification rerun; never reuse a working extraction that was touched by ad-hoc tests.
8. Preserve installer/preflight/run logs from the real target-host run and bind them to the outer SHA above.
9. Perform remote independent exact-SHA review / CodeRabbit when required.
10. Only after external gates and human GO may promotion/merge/release proceed.

## Recovered artifact locations

ChatGPT Library durable copy:

`/NightWatch-Recovered/NightWatch-Agent-Self-Heal.zip`

Historical source copy:

`/ОС_ИИ/NightWatch-Agent-Self-Heal(20260916-194020).zip`

The binary itself is not duplicated into normal Git history; GitHub stores the exact hash, status, evidence index, and recovery procedure.

## Target-shell note

The frozen v3.8.5 CMD launchers invoke `powershell.exe`.

On current Windows, that normally resolves to Windows PowerShell 5.1 even when the OS is Windows 10/11. The release was deliberately compatible with PowerShell 5.1+.

If the runtime requirement changes to **PowerShell 7 specifically**, create and qualify a new release identity. Do not alter the recovered v3.8.5 bytes in place.

## WIP durability

Before any risky next iteration or session end:

- update canonical Markdown if understanding/status changed;
- commit code/evidence/docs that are materially useful;
- push to `night-watch`;
- mark incomplete commits `unstable, saved for context`.

Never leave the only recoverable copy in a chat, local temp directory, unpushed worktree, or assistant memory.
