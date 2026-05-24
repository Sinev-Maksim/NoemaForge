# Persona Portraits and Dashboard — 0.31.10

Persona portraits are SVG assets under `noemaforge/ui/personas/portraits`. The
first-run audit now checks that persona catalog entries resolve to portraits and
that the dashboard can be started after first-run.

## Start manually

```bash
noemaforge dashboard start
noemaforge dashboard status
```

Open `http://127.0.0.1:8765/`.

## Autostart policy

Runtime GUI autostart uses the delayed timer. Dashboard autostart remains a
separate user choice and must not start LLMs automatically.
