# NoemaForge 0.32.1 manifest completeness

> **Status: historical snapshot (0.31.13.alpha-patched1 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Version: `0.32.1`  
Created: 2026-05-14  
Modified: 2026-05-14

## Covered discussion areas

The release manifest and TODO/Wiki set covers the following areas discussed during pre-alpha and alpha preparation:

- NoemaForge rebrand and canonical paths;
- GUI state persistence and backend-owned conversations;
- persona portraits and deterministic fallback avatars;
- SR/SSR review inbox for backend messages and artifacts;
- first-start modes: fast, normal, full and full_composite;
- model health registry, failed-model exclusion and continuation planning;
- epoch visualization and apply request flow;
- hardware, runtime and product telemetry;
- staged CPU/GPU runtime policy;
- task queue, inactivity timer and bounded improvement depth;
- Dev Team fallback to latest seed self-optimization when the backlog is empty;
- full pipeline catalog, media/video/mask pipelines, diagram/stats views and draft-only new-pipeline flow;
- Edge/TinyML/OTA backlog;
- local-first smart-home control backlog with privacy-first data flow;
- emergency recovery, nofail automount and GUI restoration.

## Alpha boundary

Some items are intentionally `draft_only` or `roadmap_only` in alpha. They are described in contracts and TODO but do not perform hidden privileged actions.

## Verification rule

`MANIFEST.json`, `MANIFEST_0.32.1.json`, `SHA256SUMS`, and `SHA256SUMS_0.32.1` are regenerated after all corrections and before packaging.
