# Mender Module: Model Update

Version scope: NoemaForge 0.32.1/0.32.2 (optional reference integration).

This directory contains the stub for the Mender update module that delivers
NoemaForge model artifacts as OTA packages. Mender is an optional reference
integration; the canonical OTA path is `ota/update_agent.py` with
`ota/rollback_policy.yaml`.

Status: post-MVP reference — not required for the 0.32.2 base release.
See `noemaforge/configs/edge-reference-targets.json` for the optional/reference
classification and `noemaforge/configs/ota-update-layer.json` for the
canonical OTA policy.
