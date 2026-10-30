# 0.2.2 — first release candidate

- English setup guide and an installation button for the app repository.
- A helper to find the TV's BeoCore address and identity on the local network.
- A LIGHT action blueprint: choose a button and your own HA action, with Dry run on initially.
- Source archives, build checks and issue forms for trying other setups.
- Receiver code unchanged from 0.2.1 apart from the version string.

# 0.2.1

- HA events include their original receipt time, so delayed requests can be ignored.
- Added tests for queue delays and receipt-time handling.

# 0.2.0

- Added heartbeat and container health checks for Supervisor Watchdog.
- Discovery refreshes and reconnects after network errors.
- Queued events expire after two seconds; uncertain HTTP requests aren't retried.
- Suppressed repeated presses for the configured LIGHT scene commands.
- Added connection timeouts, status logging and recovery tests.

# 0.1.2

- Added automatic startup after Home Assistant Core.
- New installations still start disabled.

# 0.1.1

- Fixed the mDNS service name and added discovery regression tests.
- First Horizon hardware checks: gateway selection, connection and real LIGHT presses.
- Confirmed remote label renaming and two lighting scenes with the real remote.

# 0.1.0

- Initial BeoCore/XMPP receiver with optional discovery and HA events.
- Protocol and loopback tests, plus an ARM64 build on Home Assistant Green.
