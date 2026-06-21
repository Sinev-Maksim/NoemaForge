# Pipeline dashboard — 0.33.0 features

Reference page for all GUI features shipped in the 0.33.0 fixpack. For the
overall GUI verdict see [Admin GUI current state](admin-gui-current-state.md).

## Architecture snapshot

The Admin GUI is a single-page app (`noemaforge/templates/pipeline-dashboard/`)
served by `noemaforge/src/admin_gui_server.py` (now split into per-domain route
modules under `admin_gui_routes/`). Frontend code is vanilla ES2020+ JavaScript
(`app.js` ~3.5k lines); no build step, no npm. All user-content paths use
`textContent` or DOM APIs — no innerHTML with unescaped data.

## Feature map (0.33.0)

### Artifact cards (U-001/U-005)

After every pipeline run completes the GUI renders one inline card per artifact
into the chat thread. Cards expose:

- Human-readable title and description from the artifact metadata
- `open_url` / `preview_url` / `download_url` links where available
- `open_command` shown as a code snippet for terminal artifacts

Implementation: `app.js` `_artifactChatCard()`, `postArtifactsToChat()`. API:
`GET /api/pipeline/run/<id>/artifacts`.

### Pending indicator (U-002)

Every admin-send request now shows a spinner bubble while the response is
in-flight. An `ok: false` from the server renders an error card with the
server's message instead of silently dropping the reply. Implementation:
`app.js` `_addPendingBubble()`, `sendAdmin()`.

### Pipeline progress panel (D-007)

Launching a pipeline inserts a progress bubble with the run's stage list,
live status icons (pending / running / done / failed), and elapsed time. The
panel auto-polls `GET /api/pipeline/run/<id>/status` until the run settles.
Implementation: `app.js` `renderPipelineRunPanel()`.

### Pipeline confirm dialog (D-005)

The launch confirm button opens an editable in-GUI dialog (replaces the
browser-native `prompt()`). The operator can review and adjust the
pipeline-id before confirming. After confirmation the pipeline-id is echoed
into chat as a system line. Implementation: `index.html` `#pipeline-confirm`,
`app.js` `_confirmPipelineId`.

### Glossary answers (D-003)

When the Admin responds with a known system state keyword
(`degraded_selected`, `selected=1`, `needs_privilege`, …) the GUI annotates
it with a deterministic tooltip/badge from the built-in glossary rather than
forwarding to the model. Implementation: `admin_gui_server.py`
`_glossary_lookup()`.

### Persona selector (U-003)

A `<select>` in the topbar lists all available personas. Selecting one calls
`POST /api/persona/switch`; the switch is logged into chat as a system line,
and the topbar badge updates. A "Return to Admin" button appears in the chat
thread after every switch. Implementation: `app.js` `_loadPersonaSelect()`,
`switchPersona()`, `_addReturnToAdminLine()`.

### Pipeline persona greeting (D-009)

When a pipeline launches, the pipeline's associated persona codename (from
`pipeline_catalog_api.py` `_pipeline_persona()`) is prepended to the first
chat line so the operator knows which persona is driving the run.

### Repeat-launch guard (D-010)

Re-launching the same pipeline within 60 seconds triggers a warning dialog
(`#pipeline-confirm-continue`). The operator must explicitly click "Launch
anyway" to override. The guard uses an in-memory `_launchHistory` Map so it
survives page focus loss but not reload. Implementation: `app.js`.

### Epoch panel readability (D-002)

The epoch panel now shows human-readable staffing labels (`_STAFFING_LABELS`
map) with hover tooltips for each model slot, and a `_humanStaffingState()`
helper that converts raw epoch JSON into operator-friendly prose. Plan state
no longer goes stale after the first load. Implementation: `app.js`
`renderEpoch()`.

### Iteration depth notice (D-008)

When any of the depth controls (`depth-steps`, `depth-minutes`,
`depth-until-stop`) is set to a non-default value, a yellow notice banner
(`.depth-notice` in the chat toolbar) appears and the Send button label
changes to reflect the active budget. The notice is also refreshed on locale
switch and on startup. Implementation: `app.js` `_updateDepthNotice()`,
`style.css`.

### Hardware gauges and metrics cards (D-001/D-004)

Telemetry cards (`/api/telemetry`, `/api/metrics`) now render as human-readable
label-value rows with colour-coded gauges for CPU/GPU/RAM utilisation. Raw JSON
fallback is removed. Implementation: `app.js` metrics-card section.

### SVG pipeline diagram (D-006)

The pipeline info modal includes a "Show diagram" button that renders the
pipeline's stage graph as an SVG (built via `createElementNS` — no external
library) rather than raw JSON. Stages are laid out left-to-right with arrows.
Implementation: `app.js` `showPipelineDiagram()`.

## API surface (new/changed in 0.33.0)

| Endpoint | Change |
|---|---|
| `GET /api/pipeline/run/<id>/status` | New — pipeline run status poll |
| `GET /api/pipeline/run/<id>/artifacts` | New — artifact list for a run |
| `POST /api/persona/switch` | New — switch active persona |
| `GET /api/pipeline/<id>/diagram` | New — stage graph data for SVG render |

## Known gaps (post-0.33.0 / P2)

See [Admin GUI current state — Known remaining gaps](admin-gui-current-state.md#known-remaining-gaps-p2--post-0330).
