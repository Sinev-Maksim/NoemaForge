# Pipeline: code_dev_qa_subteam

Stages:

1. intake
2. producer_context
3. reviewer_selection
4. static_scan
5. reviewer_a_analysis
6. reviewer_b_analysis
7. consensus_merge
8. test_plan
9. handoff_to_tester

Command surface:

```bash
noemaforge qa code team --producer <model> --json
noemaforge qa code run --project <path> --producer <model> --json
```

The pipeline is deliberately single-LLM-safe: reviewers are executed sequentially by default, even if the plan models the analysis as a logical sub-team.
