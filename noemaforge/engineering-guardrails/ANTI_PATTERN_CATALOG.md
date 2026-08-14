# Repeated Rake Catalogue

| Class | Examples | General prevention |
|---|---|---|
| Native argv corruption | Python `-c` split, long Codex prompt in argv | single process adapter; argv integrity tests; unbounded payload forbidden |
| Host encoding leakage | Codex stdin invalid UTF-8 with Cyrillic | raw UTF-8 bytes; Unicode round-trip canary |
| Parse ≠ runtime | PowerShell inline `if` passed parser then failed on PS5.1 | PS5.1 runtime compatibility fixture |
| Process success ≠ capability | Codex exit 0 but mutation impossible | mutation canary + typed dimensions |
| Provider failure misread as product failure | proposal transport consumed task attempts | preflight before task budget; separate infrastructure accounting |
| Platform serialization leak | `logs\escape.log` in external warning key | native filesystem path internally, POSIX at serialization boundary |
| Warning promoted to failure | Git LF→CRLF stderr | typed stderr classifier |
| Diagnostic wrapper itself broken | CMD/PowerShell escaping | generated wrapper lint + location-independent diagnostic |
| Documentation line interpreted as CMD | raw prose in `.cmd` | CMD syntax/static lint |
| Persona masquerades as independent reviewer | same engine under multiple personas | `independence_key` on actual engine/model/session |
| Review bypass | downstream continued after blocked review | mechanical short-circuit regression |
| Fallback becomes a second fragile system | portable/runtime/provider fallback untested | fallback canary + same contract tests as primary path |
