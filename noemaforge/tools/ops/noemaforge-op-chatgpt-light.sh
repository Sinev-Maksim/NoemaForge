#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: tools/ops/noemaforge-op-chatgpt-light.sh
# Zone: operator/gui-helper
# Purpose: Install/launch a low-memory Firefox profile for ChatGPT.
# Callers: noemaforge chatgpt-light, sudo noemaforge chatgpt-light install, wrapper chatgpt-light.
# Safety: Launch requires an active graphical user session; install is safe from root.
# === End NoemaForge File Header ===
set -euo pipefail

ACTION="${1:-launch}"
shift || true

pick_user() {
  if [ -n "${NOEMAFORGE_TARGET_USER:-}" ]; then echo "$NOEMAFORGE_TARGET_USER"; return; fi
  if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then echo "$SUDO_USER"; return; fi
  if id cat >/dev/null 2>&1; then echo cat; return; fi
  id -un
}

install_for_user() {
  local user="$1"
  local home uid gid
  home="$(getent passwd "$user" | cut -d: -f6)"
  uid="$(id -u "$user")"
  gid="$(id -g "$user")"
  test -n "$home" || { echo "ERROR: cannot resolve home for user $user" >&2; exit 1; }

  install -d -o "$uid" -g "$gid" "$home/.mozilla/firefox/chatgpt-light" "$home/.local/bin"
  cat > "$home/.mozilla/firefox/chatgpt-light/user.js" <<'EOC'
user_pref("browser.preferences.defaultPerformanceSettings.enabled", false);
user_pref("dom.ipc.processCount", 2);
user_pref("dom.ipc.processCount.webIsolated", 2);
user_pref("browser.sessionstore.restore_on_demand", true);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.startup.page", 0);
EOC
  chown "$uid:$gid" "$home/.mozilla/firefox/chatgpt-light/user.js"

  cat > "$home/.local/bin/chatgpt-light" <<'EOC'
#!/usr/bin/env bash
set -euo pipefail
exec /usr/local/bin/noemaforge chatgpt-light launch "$@"
EOC
  chmod 0755 "$home/.local/bin/chatgpt-light"
  chown "$uid:$gid" "$home/.local/bin/chatgpt-light"

  echo "[chatgpt-light] installed profile and user wrapper for $user"
}

launch_for_user() {
  local user="$1"
  local home uid firefox
  home="$(getent passwd "$user" | cut -d: -f6)"
  uid="$(id -u "$user")"
  firefox="$(command -v firefox-esr || command -v firefox || true)"
  test -n "$firefox" || { echo "ERROR: firefox-esr/firefox not found" >&2; exit 1; }
  test -d "$home/.mozilla/firefox/chatgpt-light" || install_for_user "$user"

  local cmd=(systemd-run --user --scope -p MemoryHigh=3500M -p MemoryMax=4G -p MemorySwapMax=1G "$firefox" --no-remote --profile "$home/.mozilla/firefox/chatgpt-light" https://chatgpt.com)

  if [ "$(id -u)" -eq 0 ]; then
    echo "[chatgpt-light] launching as $user via user systemd..."
    exec runuser -u "$user" -- env \
      XDG_RUNTIME_DIR="/run/user/$uid" \
      DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
      "${cmd[@]}"
  else
    exec "${cmd[@]}"
  fi
}

target_user="$(pick_user)"

case "$ACTION" in
  install|prepare)
    install_for_user "$target_user"
    ;;
  launch|start|open)
    launch_for_user "$target_user"
    ;;
  status)
    home="$(getent passwd "$target_user" | cut -d: -f6)"
    echo "target_user=$target_user"
    ls -lah "$home/.mozilla/firefox/chatgpt-light" 2>/dev/null || true
    ls -lah "$home/.local/bin/chatgpt-light" 2>/dev/null || true
    pgrep -a -f '[f]irefox.*chatgpt-light' || true
    ;;
  *)
    echo "Usage: noemaforge chatgpt-light [install|launch|status]" >&2
    exit 2
    ;;
esac
