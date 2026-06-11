# Trixie recovery operating rule — 0.29.14

> **Status: historical snapshot (02914 era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Source: `noemaforge_debug_context.txt`.

## Known-good legacy live-validation host baseline

- Debian GNU/Linux 13 / Trixie.
- Kernel `6.12.85+deb13-amd64`.
- NVIDIA RTX 3080 Ti.
- NVIDIA driver `550.163.01`.
- Secure Boot enabled.
- GUI/GDM/GNOME healthy after unloading heavy LLM.

## Mandatory invariant

Do not enable heavy NoemaForge LLM autostart on boot until delayed/limited start is implemented and verified.

Reason: Qwen2.5 14B can consume enough RAM/VRAM/disk I/O to cause GDM timeout or general system pressure on 16 GiB RAM systems.

## Daily operation

```bash
gui-status
chatgpt-light
sudo systemctl start noemaforge-llama@main.service
sudo noemaforge-llm-stop
```

## Recovery operation

```bash
sudo gui-rescue
```

## Release blocker

`noemaforge-llm-backends-manager.timer`, `noemaforge-modelscan.timer`, and `noemaforge-llama@main.service` should remain disabled by default in this hardware profile.
