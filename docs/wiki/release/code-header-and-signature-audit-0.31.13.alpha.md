# NoemaForge 0.32.1 code-header and signature audit

Version: `0.32.1`  
Created: 2026-05-14  
Modified: 2026-05-14

## Purpose

This page records the release rule for code-file headers, checksum signatures and English-only code comments in the alpha archive.

## Header contract

Every active code, script, UI, helper and service-unit file must include a `NoemaForge File Header` describing:

- file path;
- zone;
- version;
- created date;
- modified date;
- purpose;
- inputs;
- outputs;
- side effects;
- tests;
- English-only code-comment policy.

## Comment language policy

Code comments and generated code headers are English-only. User-facing text may be localized through `docs/i18n/*` or locale JSON files.

## Verification

The corrected alpha archive was audited for:

```text
missing code headers: 0
non-English code comments: 0
setup selftest: PASS
python syntax: PASS
shell syntax: PASS
manifest/checksum regeneration: PASS
```

## Notes

Historical documentation can mention previous versions for release history. Active runtime metadata must remain `0.32.1`.
