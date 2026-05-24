# Code-dev QA sub-team

The code-dev QA sub-team is the review layer for code-producing NoemaForge pipelines. A producer model or role writes the implementation plan or patch, then one or more reviewer roles inspect the result before the next participant receives a handoff. The reviewer set must be producer-distinct so the same role does not approve its own work.

The alpha operating rule keeps reviewers sequential under the single-heavy-LLM lease. This preserves the runtime constraint while still allowing multiple perspectives: one reviewer can focus on correctness, another on integration risk, and another on test coverage when the local model inventory supports it. Each reviewer writes findings into a consensus ledger that separates shared findings from unique findings.

The handoff artifact is as important as the comments. It records the reviewed files, unresolved risks, recommended tests, rollback notes and the next participant context. A downstream tester or integrator should be able to continue from that artifact without rereading raw chat transcripts.
