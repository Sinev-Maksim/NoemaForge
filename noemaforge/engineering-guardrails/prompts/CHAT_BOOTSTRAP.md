# Paste this into a new NoemaForge/Night Watch chat

Treat `NoemaForge Engineering Guardrails v1` as binding project policy.

Before generating or modifying any package/script:
1. classify the requested stage in the canonical Night Watch pipeline;
2. identify exact base/candidate SHA and allowed side effects;
3. run the guardrail self-check;
4. inspect previously known UAT rake classes before designing a new process boundary;
5. prefer root-cause/generalized repair over a one-off symptom workaround;
6. add a regression/static guard for every new UAT finding.

Hard rules:
- isolated worktree + exact base;
- tests immutable during repair;
- unexpected changes fail closed;
- no remote write/GCP without authorization;
- persona != provider != independent reviewer;
- implementer cannot satisfy own independent review;
- same provider/model fresh session is only local co-check;
- review gate precedes reproducer/cost/GCP;
- `stagnation_limit_per_task=4`;
- `traversal_depth_limit=0` means unlimited;
- `global_iteration_limit=0` means unlimited;
- no unbounded payload in argv;
- all machine text protocol is explicit UTF-8 bytes/files, never host-default encoding;
- capability canaries precede task-budget consumption;
- direct mutation only after mutation canary; otherwise structured proposal + trusted deterministic apply;
- provider/transport failure does not consume product-task stagnation budget;
- terminal state signals the user and creates one evidence archive with SHA-256 and local path/URI;
- every `UAT request findings resolution` has prerequisite and package-fallback tracks.

Use comments for invariants/why/removal conditions, not narration or version history.
Do not declare `MAIN_UAT_COMPLETE=true`; physical Debian-only gates remain separate until actually executed.
