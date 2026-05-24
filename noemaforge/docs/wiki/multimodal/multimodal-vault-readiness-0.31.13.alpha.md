# NoemaForge 0.31.13.alpha-patched1 — multimodal vault readiness

The multimodal discovery/planning layer from 0.31.12 is retained. 0.31.13.alpha-patched1 improves user-facing artifact reporting: if a live media backend is not selected, the GUI should return a planned-only artifact rather than implying that a final audio/image/video file was generated.

Current supported discovery classes include GGUF, safetensors, ckpt, onnx, pt/pth, bin, ggml, tflite, pb and engine artifacts. Live backend adapters remain explicit/manual until the next integration milestone.
