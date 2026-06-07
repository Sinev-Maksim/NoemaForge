# Local-Only Admin

NoemaForge's Admin GUI/API is a **localhost-only operator surface by default** — a deliberate trust
choice, not an oversight. It is one of the project's strongest trust signals.

## What this means

- The Admin server (`admin_gui_server.py`) binds **`127.0.0.1`** (default port `8765`). It is not
  exposed off-loopback by default; reaching it requires being on the machine (or an explicit,
  operator-chosen tunnel).
- There is **no hidden auto-start** of LLM / media / camera / GPU surfaces. Heavy and privileged
  work is operator-initiated and plan-gated.
- Privileged actions are **plan-only jobs**: the GUI emits the exact `sudo noemaforge …` command
  (always with `--keep-display`) for the operator to review and run; the GUI process does not
  perform the privileged step itself.

## Why localhost-only

- Minimizes attack surface: the control plane is not a network service that must be hardened against
  the internet.
- Keeps the operator in the loop: actions are visible and approved locally before they run.
- Aligns with the privacy-first, local-first design: the machine stays in the operator's control.

## If you must expose it

Exposing the Admin API beyond loopback is an explicit operator decision and should be paired with
authentication and a trusted transport (e.g. an SSH tunnel or a reverse proxy with auth). The
default posture assumes **loopback only**, and the threat model (`threat-model.md`) is written for
that default.

## Related

- `threat-model.md` — trust zones and defenses.
- `../architecture/control-plane.md` — plan-then-apply control-plane design.
- `capability-tokens.md` — how tool access is gated even from the local control plane.
