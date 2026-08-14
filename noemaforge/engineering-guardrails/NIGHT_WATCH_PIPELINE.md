# Canonical Night Watch Pipeline

```text
finding
→ Night Watch work item
→ Codex minimal fix
→ deterministic local check
→ affected independent review / required CodeRabbit
→ review gate
    BLOCK => stop downstream
→ reproducer
    proves base FAIL / candidate PASS / negative control expected
→ Google/Gemini cost estimate on immutable execution plan
→ budget route using max credible estimate
    <= $1 and fits       => auto-start + notice
    >$1 <=$10 and fits   => auto-start + prominent notice
    >$10 <$100 and fits  => approval required; yield
    >=$100 or no fit     => decompose if effective remaining >=$10
                            otherwise hard stop
→ GCP whole gate when execution_required=true
→ Codex reads formal result
→ next iteration
```

Additional invariants:
- `estimated_max_usd == 0` does not mean execution is unnecessary.
- Approval binds candidate SHA, review-envelope SHA, reproducer SHA, execution-plan SHA, cost-estimate SHA, and max approved cost.
- Effective remaining budget includes actual spend + reservations.
- Candidate SHA changes invalidate only affected reviews.
- Markdown-only changes require an independent co-check; CodeRabbit is mandatory only when policy/history makes it affected.
