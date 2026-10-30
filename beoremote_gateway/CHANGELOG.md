# 0.4.1

- Spell out setup in order: start the app, choose the TV, open the Horizon's
  Customer Service Menu and select the gateway, then add LIGHT actions.
- Add the red-button entry step and the Settings → BeoLink Gateway menu route
  to the setup page and guides, with a link to the BeoLiving instructions.
- Use Home Assistant Gateway as the default name in the TV list. Existing saved
  names and custom names stay as they are; the guide explains how to rename them.

# 0.4.0

- Add LIGHT buttons directly in the app: press a button, name it and choose a
  Home Assistant scene or lights to turn off. No blueprint or device codes needed.
- Change, pause, enable and remove these ordinary HA automations from the app.
- Withhold the learning press and held repeats; saving does not run the action.
- Preserve automations customized in HA and leave unrelated automations alone.
- Suppress held repeats for all simple LIGHT press frames, including digit keys.
- Keep the blueprint as an optional advanced route and simplify the main guide.

# 0.3.0

- Set up the gateway inside Home Assistant with **Open Web UI**: find B&O products
  on the LAN and explicitly choose your TV.
- TV identity and gateway LAN address are detected automatically. The chosen
  identity is remembered and rediscovered after restarts and IP changes.
- Added connection status, Stop gateway and a copy button for the blueprint identity.
- Kept manual configurations and disabled mode for existing installs. Switch Mode
  to auto once to use the setup page after updating from 0.2.2.
- Added English/Dutch option labels and an ingress-only setup interface.
- Expanded the remote naming guide: show/add the separate Beovision IR profile,
  edit the LIGHT functions there, then return to the Bluetooth Horizon profile.

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
