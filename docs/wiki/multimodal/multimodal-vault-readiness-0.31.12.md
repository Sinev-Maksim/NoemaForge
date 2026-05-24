# Multimodal Vault Readiness — 0.31.12

`0.31.12` keeps the `0.31.10/0.31.11` multimodal discovery layer and adds Admin/GUI routes that can create concrete media pipeline runs.

## Commands preserved

```bash
noemaforge multimodal scan --json
noemaforge multimodal status --json
noemaforge multimodal image-metadata IMAGE --json
noemaforge multimodal prepare voice_generate
noemaforge multimodal prepare music_generate
noemaforge multimodal prepare photo_generate
noemaforge multimodal prepare video_generate
noemaforge multimodal mask-plan --json
```

## New Admin routes

```bash
noemaforge admin message --execute --prepare-media --message 'создай музыку'
noemaforge admin message --execute --prepare-media --message 'создай фото'
noemaforge admin message --execute --prepare-media --message 'создай видео'
noemaforge admin message --execute --prepare-media --message 'сделай маску для видеозвонка'
```

These create pipeline runs such as `music_generation`, `photo_generation`, `video_generation` and `camera_mask_bridge`, and can call the existing explicit-only multimodal prepare/plan layer.

## Still explicit-only

Live media generation still requires a selected backend adapter. The release candidate is production-ready as an Admin/pipeline/planning surface, not as a universal live media inference backend.

## GGUF shard handling

`noemaforge multimodal scan --json` is shard-aware in `0.31.12`:

- single `.gguf` files remain candidates;
- `00001-of-N` head shards remain candidates;
- non-head shards are excluded from `entries`;
- excluded shards are reported in `excluded_non_head_shards` with their canonical first-shard hint.

This is required before public release because Vault may contain both complete models and split GGUF chains.
