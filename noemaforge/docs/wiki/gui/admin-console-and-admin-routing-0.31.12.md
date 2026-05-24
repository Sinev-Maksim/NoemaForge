# Admin Console and Admin Routing — 0.31.12

NoemaForge `0.31.12` adds a local Admin GUI control-plane on top of the pipeline dashboard.

## Operator contract

- `noemaforge gui console start` starts the localhost Admin GUI/API.
- The GUI does **not** start a text LLM, media backend, camera or microphone.
- The default Admin message is `Привет!`; typo greeting `Првиет!` is also recognized and can be sent from the browser.
- Every executable GUI action maps to a local NoemaForge command and returns JSON in the page.
- `Turn off GUI` calls `/api/shutdown` and stops the local GUI server.

## Local API

The server is `noemaforge/src/admin_gui_server.py` and serves the existing dashboard assets plus:

- `GET /api/health`
- `GET /api/state`
- `POST /api/admin/message`
- `POST /api/pipeline/run`
- `POST /api/pipeline/approve`
- `POST /api/pipeline/advance`
- `POST /api/admin/modify-pipeline`
- `POST /api/dev-team/run`
- `POST /api/dev-team/write-file`
- `POST /api/dev-team/replace`
- `POST /api/dev-team/set-version`
- `POST /api/model-evolution/run`
- `POST /api/shutdown`

## Admin routing

`noemaforge admin route --json --message TEXT` classifies requests into concrete pipeline IDs.

Examples:

```bash
noemaforge admin message --message 'Првиет!' --json
noemaforge admin message --execute --message 'Привет!' --json
noemaforge admin message --execute --prepare-media --message 'создай музыку для intro' --json
noemaforge admin message --execute --message 'доработай код через dev team' --json
noemaforge admin message --execute --message 'эволюция модели для dev роли' --json
```

Routes currently include:

- greeting → `dashboard_operator_console`
- code/dev/release-fix → `dev_pipeline_member_cells`
- music → `music_generation`
- voice → `voice_generation`
- photo/image generation → `photo_generation`
- video → `video_generation`
- camera masks → `camera_mask_bridge`
- image metadata/VLM planning → `image_analysis`
- model evolution → `model_evolution`
- release prep → `release_prep`

## Safety boundaries

The GUI is a control-plane. It launches pipeline records and planning runtimes, but it does not silently run heavy model backends. Media generation remains explicit-only until a backend adapter is selected by the operator.


## In-browser Dev Team edits

The dashboard includes a `Dev Team direct edits` card. It can create a patch proposal or, when the explicit apply checkbox is selected, call the same local helpers as the CLI:

```bash
noemaforge dev-team write-file --project REPO --path FILE --content TEXT --apply --json
noemaforge dev-team replace --project REPO --path FILE --old OLD --new NEW --apply --json
noemaforge dev-team set-version --project REPO --version 0.31.13 --apply
```

Each direct write records diff metadata and, when replacing an existing file, a backup path.

## Verified GUI-local flow

Sandbox verification covered `/api/health` → Admin message `Првиет!` → routed `music_generation` pipeline action → `/api/model-evolution/run` → `/api/shutdown`. All responses stay inside the local GUI/API surface.

## Target replay evidence contract

`final-gui-scenario-replay-readiness-core` keeps the final Admin GUI replay in `blocked_until_target_final_gui_scenario_replay_evidence` until the real NoemaForge target captures a reviewed transcript. The required replay uses `polished_admin_gui_guided_scenario` and must archive target baseline, operator approval, Admin GUI start/health, greeting transcript, routed pipeline launch, Dev Team action, model-evolution action, full transcript, artifact hash manifest, redaction review, archive SHA256 and the version-bump guard record. The local validator only checks policy, registry, example and documentation shape; it does not start the GUI, browser, pipelines, Dev Team, model-evolution or archive commands.
