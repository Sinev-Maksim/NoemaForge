# Code and Commenting Standard

## Code
1. Separate pure policy/routing logic from provider/process/filesystem adapters.
2. Keep external side effects behind narrow typed boundaries.
3. Use explicit enums/typed states instead of overloaded booleans such as “ready”.
4. A process exit code is not proof of semantic success or mutation success.
5. Treat stdout/stderr/exit/status/mutation as separate evidence dimensions.
6. No unbounded payloads in command-line arguments.
7. No host-default encoding for machine protocol text.
8. Use native filesystem objects for containment/security checks; serialize only at the external boundary.
9. Fail closed on unexpected mutations, stale SHA bindings, missing mandatory reviewer capabilities, and unknown paid-execution cost.
10. Never weaken existing tests to make a candidate pass.

## Comments
Comments explain **why an invariant exists**, not what an obvious line does.

Good:
```text
# UAT request findings resolution NW-UAT-WIN-047:
# Write UTF-8 bytes directly because Windows PowerShell host encodings are not
# a stable machine-protocol boundary. Remove only when the provider adapter has
# a tested versioned binary transport contract.
```

Bad:
```text
# Write prompt to stdin.
$stream.Write(...)
```

For a workaround comment, include:
- finding ID;
- invariant/root cause;
- removal condition.

Version history belongs in CHANGELOG/README/evidence, not normal source comments.

Security-boundary code needs a comment stating what must remain true after refactoring.
