# Tool gap matrix and feature import backlog

Status: merged in `0.29.14`.
Source: `summary_dialogue_noemaforge_tools.md`.

## Purpose

This page tracks which external AI-tool concepts are already represented in NoemaForge and which should be imported into the prelaunch backlog.

## Compared tool families

| Tool / family | NoemaForge status | Import target | Priority |
|---|---|---|---|
| Claude Chat | Partially represented | Long-context UX, artifact discipline, structured project memory | Medium |
| Claude Code | Partially represented | Code-agent workspace, patch review, repo-aware execution loop | High |
| Grok / xAI-like realtime assistant | Conceptually represented | Realtime/social/news connector policy; safety gating | Low/Medium |
| Gemini | Partially represented | Multimodal workspace, Android/Google ecosystem connector assumptions | Medium |
| DeepSeek | Model-family support only | Local model registry, quantization/eval profiles | Medium |
| Perplexity | Partially missing | Answer-with-sources workflow, search citation UX, source confidence layer | High |
| Whisper Flow | Mostly missing | Voice-first capture, dictation pipeline, local transcription queue | High |
| OpenClaw / browser agents | Partially missing | Web automation, UI action safety, replayable browser tasks | Medium/High |
| NotebookLM | Partially missing | Source-grounded notebook, document collections, audio overview mode | High |

## Backlog import

### P0 / release-blocking for public prelaunch

- Source-grounded answer mode with citation/provenance metadata.
- Safe local tool invocation policy with capability tokens.
- Repo-aware code-agent workflow with dry-run and patch preview.
- Prelaunch README explaining which tools are experimental, safe, and OS-specific.

### P1 / near-term

- Notebook-like collections for docs/PDF/code bundles.
- Voice capture/transcription queue.
- Search-result confidence and contradiction handling.
- Model/provider comparison matrix for Claude/Gemini/Grok/DeepSeek/local models.

### P2 / later

- Browser automation sandbox.
- Audio overview generation.
- Realtime social/news connectors.

## Architectural rule

Features should be imported as capabilities behind the NoemaForge tool/security substrate, not copied as UI clones.
