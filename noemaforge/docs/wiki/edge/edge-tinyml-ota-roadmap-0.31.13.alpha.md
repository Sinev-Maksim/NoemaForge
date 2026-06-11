# NFG-PROP-0.32.1-edge-ml-pack — Edge / TinyML / OTA backlog

> **Status: historical snapshot (0.31.13.alpha era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Status: candidate backlog pack / future-version idea.  
Release anchor: NoemaForge `0.32.1` documentation patch.  
Runtime impact: **none**. This package is intentionally recorded as roadmap/Wiki/TODO material only and must not become a hard dependency for public `0.32.1` startup.

## Goal

Add a future NoemaForge architecture layer for edge/MCU inference, safe OTA rollout, metrics ingestion, and model validation before deployment.

The MVP recommendation is:

```text
docker-compose + MQTT + gateway inference + signed model manifest + rule guard + health/metrics
```

KubeEdge, eKuiper, Mender, and RAUC are tracked as reference implementations or post-MVP integration targets, not as required dependencies for `0.32.1`.

## External reference anchors

- TensorFlow Lite for Microcontrollers: MCU-oriented inference with examples such as Hello World, Micro Speech, Magic Wand, and Person Detection. The core runtime is designed for devices with only a few kilobytes of memory.
  - https://www.tensorflow.org/lite/microcontrollers
  - https://www.tensorflow.org/lite/microcontrollers/get_started
- KubeEdge: future orchestration target for Kubernetes-style edge application/device management and MQTT-capable edge communication.
  - https://kubeedge.io/docs/
- LF Edge eKuiper: preferred future local stream/rules engine candidate for resource-constrained edge devices, with SQL/graph rules and MQTT/REST source/sink patterns.
  - https://ekuiper.org/docs/en/v2.0/
- Mender: OTA reference for staged/phased deployments, delta updates, Update Modules, container/app updates, and nearby microcontroller update workflows.
  - https://docs.mender.io/
- RAUC: signed bundle update reference for embedded Linux and A/B-style robust update workflows.
  - https://rauc.io/

## 1. Sense_Layer.Edge

Add adapters for collecting signals from devices, OS sources, and controllers.

Candidate files:

```text
sense/edge/input_contract.yaml
sense/edge/mqtt_adapter.py
sense/edge/serial_adapter.py
sense/edge/metrics_schema.py
```

Acceptance criteria:

- NoemaForge accepts sensor/system metrics via MQTT and serial.
- Metrics are normalized into one schema.
- Data source trust is explicit: `trusted`, `simulated`, or `unverified`.

## 2. TinyML_Node

Add an MCU / floor-controller inference validation mode.

Candidate files:

```text
runtime/tinyml/tflm_manifest.yaml
runtime/tinyml/golden_vectors/
runtime/tinyml/model_size_gate.py
runtime/tinyml/static_arena_report.md
```

Acceptance criteria:

- A model is rejected without golden test vectors.
- Latency, RAM arena, model size, and model hash are checked.
- MCU inference never makes direct control decisions without fallback rules.

## 3. Gateway_Inference_Service

Add a containerized inference service for an edge gateway.

Candidate files:

```text
gateway/inference_service/app.py
gateway/inference_service/model_loader.py
gateway/inference_service/health.py
gateway/inference_service/Dockerfile
```

Acceptance criteria:

- One REST/MQTT inference endpoint exists.
- A model is loaded only through a manifest.
- `/health`, `/ready`, and `/metrics` exist.

## 4. Edge_Rules_Engine

Add a local rule layer before and after ML.

Candidate files:

```text
gateway/rules/ekuiper/
gateway/rules/rule_contract.sql
gateway/rules/fallback_rules.yaml
```

Acceptance criteria:

- ML score is never applied without a rule guard.
- Thresholds, anomaly routing, and drift flags are supported.
- `whitebox_only` mode exists.

## 5. Model_Manifest_And_Signing

Define one manifest contract for NoemaForge-hosted models.

Candidate manifest:

```yaml
model_id: example_edge_model
runtime: onnx | tflm | llama.cpp | python
sha256: ""
signature: ""
input_contract: ""
latency_budget_ms: 50
memory_budget_mb: 128
fallback: whitebox
rollout: canary
```

Acceptance criteria:

- A model without `sha256` and signature is rejected for deployment.
- The manifest records resource budgets.
- QA role can block release independently from Developer.

## 6. OTA_Update_Layer

Add safe model/container/gateway update packaging.

Candidate files:

```text
ota/manifest.schema.yaml
ota/update_agent.py
ota/rollback_policy.yaml
ota/mender_module_model_update/
ota/rauc_bundle_notes.md
```

Acceptance criteria:

- Staged rollout is available.
- Rollback to the previous model/container/gateway bundle is available.
- OTA does not activate a model without a health gate.

## 7. CI_Model_Gates

Add release gates before a model can be attached to NoemaForge.

Candidate files:

```text
ci/validate_model.py
ci/latency_benchmark.py
ci/memory_budget_check.py
ci/golden_replay.py
ci/sign_artifact.py
```

Acceptance criteria:

- Accuracy regression, latency, memory, schema compatibility, and signature are checked.
- Edge models require replay tests.
- Evidence is stored as `release_evidence.json`.

## TODO insert

```text
## NFG-PROP-0.32.1-edge-ml-pack
- [ ] Add Sense_Layer.Edge for MQTT/serial/metrics ingestion.
- [ ] Add TinyML_Node package for MCU inference validation.
- [ ] Add Gateway_Inference_Service with model manifest loading.
- [ ] Add Edge_Rules_Engine with whitebox fallback.
- [ ] Add signed Model Manifest contract.
- [ ] Add OTA_Update_Layer with rollback and health gates.
- [ ] Add CI_Model_Gates: latency, memory, golden replay, signature.
- [ ] Keep KubeEdge as post-MVP orchestration target.
- [ ] Keep eKuiper as preferred local stream/rule engine.
- [ ] Keep Mender/RAUC as OTA reference implementations.
```

## Release guidance

For public `0.32.1`, keep this as an experimental backlog package only:

- Do not require MQTT, serial adapters, Docker, KubeEdge, eKuiper, Mender, or RAUC for first-start.
- Do not block Admin GUI, Dev Team, model-selection, or localized HOW2START on this pack.
- Treat the first implementation slice as local gateway MVP: manifest + MQTT adapter + `/health` + metrics + whitebox fallback.
