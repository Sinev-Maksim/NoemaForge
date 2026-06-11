# Multimodal Vault Readiness — 0.31.10

> **Status: historical snapshot (0.31.10 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

NoemaForge now scans Vault assets beyond GGUF and classifies likely model families:
vision, STT, TTS, music generation, image generation, video generation,
segmentation/matting and virtual-camera mask support.

## Commands

```bash
noemaforge multimodal scan --json
noemaforge multimodal status --json
noemaforge multimodal image-metadata /path/to/image.jpg --json
noemaforge multimodal prepare voice_generate
noemaforge multimodal prepare music_generate
noemaforge multimodal prepare photo_generate
noemaforge multimodal prepare video_generate
noemaforge multimodal mask-plan --json
noemaforge persona gui-status --json
```

## Safety

No media backend auto-starts from GUI first-run. Camera and microphone pipelines
remain manual-only until the operator starts them explicitly.
