# vim:syntax=apparmor
# NoemaForge LocalGateway (template)

#include <tunables/global>

profile noemaforge-localgateway flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>
  #include <abstractions/nameservice>

  /usr/bin/python3 ixr,
  /opt/noemaforge/** r,

  /var/lib/noemaforge/** rw,
  /workspace/** rw,

  /tmp/** rw,

  # LocalGateway needs local network visibility. Keep this scoped.
  network,

  unix (create, listen, accept, send, receive),

  deny /** w,
}
