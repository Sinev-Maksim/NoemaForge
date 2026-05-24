# Roadmap / TODO crosswalk — 0.29.14

## Merge decision

`0.29.14` is not a runtime feature release. It is a prelaunch knowledge/tooling merge release. It consolidates:

- 0.32.1 wiki/prelaunch package,
- new tool-gap summary,
- public marketing package,
- metrics/evaluation research,
- 0.29.11 verified recovery/stability context,
- additional plus-docs archive.

## Crosswalk

| Stream | Current state | 0.29.14 action | Next action |
|---|---|---|---|
| Recovery/stability | Verified 0.29.11 base exists | Preserved and documented | Convert rescue commands into checked installers |
| Wiki/knowledge base | Created in 0.32.1 | Extended with marketing/tools/metrics | Add mkdocs or GitHub Pages index |
| Tool inventory | Fragmented across chats | Merged into tool-gap matrix | Turn into issue backlog |
| Prelaunch tools | Windows tools present | Added source copies and Unix wrappers | Test on Trixie/macOS |
| Public launch | Separate marketing.md | Added public wiki page | Finalize license/pricing/contribution docs |
| Evolve roadmap | Existing v2 verified | Kept as roadmap source | Add priority tags and owner fields |
| Metrics | Research text added | Added eval/observability summary | Implement JSON schemas and dashboards |
| LLM manager | Risky autostart | Safety rule reinforced | Implement resource-aware delayed start |
| ToolProxy/caps | Known open item | Kept as blocker | Solve capability token issuance |

## Release rule

Until manager policy is safe, NoemaForge must preserve this invariant:

> GUI and NVIDIA first. Heavy LLMs only by explicit manual command.
