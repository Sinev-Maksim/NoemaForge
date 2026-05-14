# vim:syntax=apparmor
# NoemaForge ToolProxy (template)
#
# This is a TEMPLATE profile. You will almost certainly need to adjust paths.
#
# Suggested approach:
# - Start in complain mode
# - Run canaries
# - Tighten rules
# - Switch to enforce

#include <tunables/global>

profile noemaforge-toolproxy flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>
  #include <abstractions/nameservice>

  # ToolProxy is a Python service; on many hosts it runs as:
  #   /usr/bin/python3 /opt/noemaforge/src/toolproxy.py
  # You may prefer to wrap it with a dedicated launcher binary and attach the profile to that.

  /usr/bin/python3 ixr,
  /opt/noemaforge/** r,

  # Runtime state
  /var/lib/noemaforge/** rw,
  /workspace/** rw,

  # Temporary space inside the service cgroup
  /tmp/** rw,

  # Allow unix sockets (local IPC). Network access is controlled by service hardening + sandbox policy.
  unix (create, listen, accept, send, receive),

  # Deny everything else by default
  deny /** w,
}
