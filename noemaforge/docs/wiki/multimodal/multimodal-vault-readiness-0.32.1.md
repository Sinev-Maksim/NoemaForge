# NoemaForge 0.32.1 — multimodal vault readiness

> **Status: historical snapshot (0.32.1 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

The multimodal discovery/planning layer from 0.31.12 is retained. 0.32.1 improves user-facing artifact reporting: if a live media backend is not selected, the GUI should return a planned-only artifact rather than implying that a final audio/image/video file was generated.

Current supported discovery classes include GGUF, safetensors, ckpt, onnx, pt/pth, bin, ggml, tflite, pb and engine artifacts. Live backend adapters remain explicit/manual until the next integration milestone.

## Live Backend Selection Gate

`media-backend-selection-readiness-core` keeps final live-media adapters in `blocked_until_explicit_media_backend_selection` instead of silently promoting plan-only media surfaces into live inference. The gate covers seven backend slots: VLM, STT, TTS, music generation, image generation, video generation and segmentation/mask adapters. Each slot must have an operator selection record, local artifact reference, adapter command surface, input schema, output artifact manifest, error model, plan-only fallback, telemetry/selftest evidence and target live-smoke transcript before it can be treated as a final adapter.

STT and segmentation/mask slots also require explicit privacy evidence because they may touch microphones, cameras or virtual camera output. That evidence must show capture default-off, operator consent, visible privacy state and no autostart. Local validation only checks the readiness contract and documentation trace; it does not start backends, download weights or capture devices.
