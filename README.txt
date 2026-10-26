ATI Straton X Bluetooth integration — experimental version 0.1.1

Uses Home Assistant's Bluetooth integration and existing connectable ESPHome
proxies. No separate proxy key, Wi-Fi address, cloud account or firmware flash.

Install custom_components/ati_straton_x in Home Assistant's config directory,
restart Home Assistant, then open Settings > Devices & services. Configure each
discovered StratonX light, or Add integration > ATI Straton X to select a visible
light. Default ATI passcode is 0. Identity is verified through GATT when adding.

Features
- One device per unique fixture serial number; duplicate setup rejected.
- Actual tank ID read every poll and attached to all entities. Group membership
  is metadata in this release, not a writable Home Assistant light group.
- Two fixture temperature sensors and controller temperature, in Celsius.
- Firmware, last successful poll, schedule-point count and complete schedule
  nodes as attributes, plus schedule last-read timestamp.
- Refresh schedule button.
- Explicit targeted UTC clock-sync button, restricted to tested firmware 1.4.0.2.
  A successful button call confirms transport only; it is not clock readback.

Polling
Default 60 seconds per fixture; configurable 30–300 seconds in integration options.
All fixtures and setup flows share one connection lock, so sessions never overlap.
Actual cadence includes connection time and queueing. Sessions disconnect after
each poll. Schedule reads occur at startup and every 15 minutes, or on manual
refresh. Failed polls mark entities unavailable and back off up to 15 minutes.
Discovery uses Home Assistant's shared scanner rather than starting another scan.

Tank isolation
Assign the frag-tank light to a separate tank in ATI first. The integration reads
that ID automatically. This release has no schedule-write or channel-control
commands, so it cannot broadcast a schedule to either group. Group isolation for
future writes still requires testing against two separate tank groups.

Limitations
Current channel output is NOT yet decoded or exposed. Schedule channel values
are stored targets (0–1023), not optical output or verified live PWM levels.
No brightness/on-off entities or schedule editor until write behavior is verified.
Protocol evidence comes from firmware 1.3.0.6 and live reads on 1.4.0.2.
A concurrent schedule edit with an unchanged node count may produce a mixed
snapshot; avoid editing in ATI during refresh. Refresh again after app edits.
Manual diagnostic integration remains separate and should not be run while this
integration is polling. It is retained for protocol investigation and rollback.

Rollback: disable the ATI Straton X entries in Devices & services. This stops
polling without deleting devices or changing any lamp's saved program.
