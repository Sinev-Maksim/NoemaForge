# NoemaForge local-first smart-home control backlog

Version: `0.32.1`

## Principle

Value your privacy. Smart plugs, switches, vacuums, cameras, sensors and other home devices should report to and be controlled by the local NoemaForge home server whenever possible, not external cloud services by default.

## Backlog scope

- local MQTT event bus;
- Home Assistant bridge as optional adapter;
- Zigbee, Z-Wave, Matter and Thread adapter stubs;
- smart plug and switch control;
- vacuum start/stop/dock/room-clean control;
- local camera RTSP/ONVIF ingest with explicit opt-in;
- source labels: trusted, simulated, unverified;
- emergency pause for all automations;
- SR/SSR review of automation decisions.

## Safety

No hidden camera or microphone capture. No silent cloud upload. Manual human override always wins.
