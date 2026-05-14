# vim:syntax=apparmor
# NoemaForge WebGateway (template)

#include <tunables/global>

profile noemaforge-webgateway flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>
  #include <abstractions/nameservice>

  /usr/bin/python3 ixr,
  /opt/noemaforge/** r,

  /var/lib/noemaforge/** rw,
  /workspace/** rw,

  /tmp/** rw,

  # WebGateway needs outbound network (HTTPS) by design.
  network inet stream,
  network inet6 stream,

  unix (create, listen, accept, send, receive),

  deny /** w,
}
