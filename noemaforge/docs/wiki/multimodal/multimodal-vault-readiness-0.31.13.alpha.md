# NoemaForge 0.32.1 — multimodal vault readiness

> **Status: historical snapshot (0.31.13.alpha era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

The multimodal discovery/planning layer from 0.31.12 is retained. 0.32.1 improves user-facing artifact reporting: if a live media backend is not selected, the GUI should return a planned-only artifact rather than implying that a final audio/image/video file was generated.

Current supported discovery classes include GGUF, safetensors, ckpt, onnx, pt/pth, bin, ggml, tflite, pb and engine artifacts. Live backend adapters remain explicit/manual until the next integration milestone.
