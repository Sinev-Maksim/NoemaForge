# SmartHome Privacy Evaluation Gate

The SmartHome privacy evaluation gate turns the local-first SmartHome backlog into an executable privacy contract. It does not enable live adapters, scan a home network, or claim target-machine runtime success. It validates the static controls that must be present before SmartHome automation can move from roadmap planning to target evidence.

The gate requires every device to declare a source class of `trusted`, `simulated`, or `unverified`. Unknown source states fail closed so operator-facing automation can distinguish trusted devices from simulated fixtures and unverified hardware. Camera devices must remain local-only, expose visible privacy state, deny hidden capture, and avoid raw media persistence by default.

Cloud upload defaults are disabled. Any future external cloud path must be explicit, reviewed, and operator-approved rather than implied by adapter behavior. The gate also requires an automation audit trail, trace IDs, human override, and an emergency all-automation pause so SmartHome actions remain inspectable and reversible.

The active contract is `smarthome-privacy-evaluation-gate-core` in `noemaforge/configs/smarthome-privacy-evaluation-gate.json`. The local validator and tests in `helpers/smarthome_privacy_evaluation_gate.mjs` check policy shape, allow/deny sample cases, and bounded runtime. Target-machine SmartHome behavior remains separate evidence work because live device discovery and automation execution require hardware, operator approval, and a clean release gate.
