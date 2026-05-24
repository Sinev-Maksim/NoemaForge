# Persona Portraits and Dashboard — 0.31.12

`0.31.12` keeps persona portrait validation and upgrades the dashboard from static-only to a local Admin GUI/API.

## Checks

```bash
noemaforge persona gui-status --json
noemaforge dashboard state
noemaforge gui console start
```

The dashboard still displays:

- active persona codename;
- SVG portrait;
- current pipeline lifecycle;
- artifacts/events;
- next operator actions.

New Admin controls allow routing text requests, launching pipelines, triggering dev-team/model-evolution runtimes and shutting down the GUI from the page.

## Final replay dashboard evidence

`final-gui-scenario-replay-readiness-core` keeps the dashboard portion of the final public replay in `blocked_until_target_final_gui_scenario_replay_evidence`. The target run must capture the selected `polished_admin_gui_guided_scenario`, visible Admin GUI start/health, greeting transcript, route responses, screenshots or session refs, full transcript, artifact hash manifest, redaction record and archive SHA256 before the version-bump follow-up can close. Local validation remains dry and evidence-oriented; it never opens the dashboard or starts GUI actions.
