# Desktop app shell — decision record

Status: **accepted direction (2026-06-10)**, implementation scheduled with the
Admin GUI fixpack. Owner: Admin GUI track.

## Problem

The Admin GUI currently lives in a browser tab. The product goal is for
NoemaForge to look and feel like an application — its own window, own icon,
no address bar or tab strip — without dragging in a heavyweight UI runtime.
The constraint hierarchy: keep the stdlib-only Python core, keep zero new
mandatory dependencies, keep Linux first-class (Debian Trixie reference
host), keep macOS/Windows viable for the 0.33.1 system-independence milestone.

## Options considered

| Option | Weight | Verdict |
|---|---|---|
| Electron / Tauri app | new build toolchain (Node/Rust), large artifacts | Rejected for MVP — disproportionate to a localhost dashboard |
| pywebview / native webview binding | new Python dependency + per-OS webview packages | Fallback candidate, not default |
| **Browser app-mode window + PWA manifest** | zero new dependencies | **Accepted** |

## Decision

Two complementary, dependency-free layers:

1. **App-mode launcher.** A `noemaforge dashboard app` command (and the
   equivalent `noema start` flow) starts the dashboard server if needed, then
   opens the installed Chromium-family browser in application mode:
   `chromium|google-chrome|microsoft-edge --app=http://127.0.0.1:8765/
   --window-size=1280,860`. App mode gives a standalone window with no tabs
   or address bar. Resolution order: chromium → chrome → edge → GNOME Web
   (epiphany application mode) → plain default browser as the last fallback
   (`xdg-open` / `os.startfile` / `open`). The launcher only spawns a local
   browser process — no new privileges, no network exposure.
2. **PWA manifest.** The dashboard serves `manifest.webmanifest`
   (name, icons from the existing persona/brand SVG set,
   `display: standalone`, `start_url: /`) plus the matching
   `<link rel="manifest">` and theme-color meta. Users of any
   PWA-capable browser can then "Install" NoemaForge as a desktop app with an
   icon, including on macOS and Windows, with no code shipped by us.

A native webview wrapper (pywebview) stays documented as an optional future
enhancement if app-mode windows prove insufficient (e.g. tray integration,
kiosk deployments); it must remain an optional extra, never a core
dependency.

## Acceptance criteria

- `noemaforge dashboard app` opens a standalone window on the reference host
  (Debian Trixie/GNOME) when a Chromium-family browser is installed, and
  falls back to the default browser otherwise — never fails hard.
- The dashboard passes PWA installability checks (valid manifest, icons,
  served from the localhost origin).
- No new mandatory Python or system dependency is introduced; `--dry-run`
  prints the exact browser command without launching.
- The window title and icon say NoemaForge, not the browser.

## Consequences

- The GUI remains a single localhost web app — one codebase for browser tab,
  app window and installed PWA.
- App identity (icon, name, standalone window) lands with the fixpack; deeper
  OS integration (tray, notifications) is deferred until a real need is
  registered in the defect/feature register.
