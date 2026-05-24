# NoemaForge 0.32.1 — Persona Portraits and Fallback Avatars

## Root cause fixed
The GUI now serves `/ui/...` static assets from the NoemaForge root and supports HEAD/GET checks. Relative `../../ui/...` paths are replaced with absolute `/ui/...` paths.

## Fallback
If a portrait is missing, NoemaForge generates a deterministic per-person SVG avatar. GPU/image-model avatar generation remains explicit/manual and persistent per persona.
