# Epoch Card Target Readiness

The Epoch Card readiness gate defines the evidence required before NoemaForge may generate a current Epoch Card from target model selection. It is not a substitute for running model selection on the target machine. The local contract only verifies that the required evidence shape is strict enough to prevent a synthetic or aspirational card from being presented as current runtime truth.

An Epoch Card needs the selected model, role map, staffing state, scorecards, rollback plan, and approval evidence. Hashes are required for selected-model artifacts, scorecards, and approval records so the card can be tied back to concrete target evidence. Redaction and documentation trace are required before the card can be shared or archived.

The gate intentionally blocks card generation when target model-selection evidence is missing. This keeps the active TODO item open until the target machine produces a successful model-selection decision, scorecard bundle, role assignment map, rollback manifest, and operator approval record.

The executable contract is `epoch-card-target-readiness-core` in `noemaforge/configs/epoch-card-target-readiness.json`. The local validator in `helpers/epoch_card_target_readiness.mjs` checks ready and blocked sample cases without starting model selection, touching target services, or generating a release artifact.
