# NoemaForge MultiOS Runtime Host Roadmap — 0.32.1

Tracking ID: `NFG-PROP-0.32.1-multiOS-runtime-pack`
Status: candidate alpha backlog pack; documentation only in `0.32.1`
Runtime impact: none. This does not add Windows/macOS launchers, runtime connectors, Docker dependencies, Ollama, MLX, vLLM, SSH, or remote HTTP runtime requirements to the active install.

## Goal

Prepare NoemaForge for a future architecture where Linux remains the reference runtime while Windows and macOS can act as first-class host/control nodes.

Current principle:

```text
NoemaForge = orchestration platform
Host OS = linux | windows | macos
Runtime = local_process | WSL2 | Docker | remote Linux | Ollama | MLX | llama.cpp | vLLM | remote HTTP gateway
```

## Design decisions

- Keep Linux as the reference production runtime for systemd, NVIDIA/CUDA, long-running services, headless deployment and predictable permissions.
- Treat Windows and macOS as first-class control/authoring/UI hosts.
- Do not force local heavy inference on weak Windows/macOS hosts.
- Prefer a runtime gateway when the host is resource constrained.
- Preserve existing Linux launcher/systemd behaviour until the abstraction layer is proven.

## Proposed architecture layer

```text
noemaforge/runtime/
  os_probe.py
  hardware_probe.py
  registry.py
  selector.py
  base.py
  connectors/
    local_process.py
    remote_http.py
    remote_ssh.py
    ollama.py
    mlx.py
    llamacpp.py
    vllm.py
  launchers/
    darwin.py
    windows.py
    linux.py
```

## Future CLI surface

```text
noemaforge runtime detect
noemaforge runtime list
noemaforge runtime select --profile auto
noemaforge runtime health
noemaforge launch
noemaforge launch --host-ui
noemaforge launch --runtime remote_linux
```

## Acceptance criteria for a future implementation

1. Linux backward compatibility remains intact.
2. Windows host detection works without enabling local heavy inference by default.
3. macOS host detection works and can report Apple Silicon vs Intel.
4. Control-only mode can connect to a remote runtime gateway.
5. Remote runtime mode exposes health and readiness checks.
6. Runtime health report includes host OS, hardware summary, runtime type, selected connector, readiness, and security notes.

## Non-goals for `0.32.1`

- No universal Windows shell replacement.
- No macOS Finder replacement.
- No automatic installation of Ollama/MLX/vLLM.
- No automatic remote SSH execution.
- No heavy local inference on unsupported hosts.

## Source material

See `docs/source_reports/noemaforge-patch-31-13-multiOS.md`.
