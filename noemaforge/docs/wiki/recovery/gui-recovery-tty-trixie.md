# GUI recovery from TTY on Debian Trixie

GUI recovery on Debian Trixie is treated as an operator safety path, not as an automatic repair loop. The recovery commands must preserve the display manager when possible, avoid repeated disruptive restarts, and keep `/run/nologin` cleanup visible in evidence so a failed first-start run does not leave the host locked out.

The alpha package keeps `gui-rescue` and `gui-status` wrappers for compatibility with older dispatcher states. Help flags must print help only; they must not trigger recovery actions. When recovery is needed, the safer path starts with state inspection, then a minimal non-blocking display-manager restoration, and only then broader rescue steps if the target evidence shows they are necessary.

Target-machine validation remains required for final confidence because GDM, Secure Boot, NVIDIA modules and systemd behavior vary by host. Local release gates therefore validate command shape, documentation and dry-run contracts while keeping live GUI recovery as a target-open evidence item.
