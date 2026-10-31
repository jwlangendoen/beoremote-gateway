# 0.6.0-dev12

- Connect directly from Sources after the TV and source support have been configured.
- Reorder TV or MUSIC locally, then save the finished list once or cancel the edit.
- Keep unsaved order across tabs; preserve and check drafts after refused or uncertain saves.
- Reduce movement controls in the normal list and improve keyboard focus and status messages.
- Clarify the Beoremote One BT and Android-based Beovision connection, tested Horizon setup and Horizon-only source support.
- Place LIGHT troubleshooting and action help in Light, source help in Sources and connection settings in Configuration.
- Add regression checks for source ownership, callbacks, paused actions and undo recovery after gateway restart or app-data restoration.

# 0.6.0-dev11

- Offer the TV Support update when connected-device launch cancellation is missing.

# 0.6.0-dev10

- Connect and wake Apple TV through its registered remote before opening an app.
- Allow up to twenty seconds for the player, launch capability and selected app
  to become ready. Extra scenes and scripts run only after the launch succeeds.
- Update TV Support to 0.1.3 to cancel a pending app launch when another source
  is chosen or the TV enters standby. Repeated requests replace pending work.
- Preserve custom HA edits and paused automations. Re-save an existing connected
  app source after updating TV Support to upgrade its unchanged launch automation.

# 0.6.0-dev9

- Show the helper's actionable reason when a source-order change is refused,
  including when the source is currently playing.

# 0.6.0-dev8 — development candidate

- List existing local TV sources and gateway shortcuts under MUSIC and TV.
- Move sources up or down on the remote, keeping the two lists separate.
- Restore the previous source order without changing Home Assistant actions.
- Update TV Support to 0.1.2 for collision-checked native positions and recovery
  after interrupted writes; protect the source that is currently playing.

# 0.6.0-dev7

- Show the Horizon menu path for USB debugging and steps to reveal Developer options.
- Remove the extra explanation below the previous-helper replacement option.

# 0.6.0-dev6 — development candidate

- Split setup into Light, Sources and Configuration tabs, with empty states that
  point to Configuration until a TV is chosen.
- Choose MUSIC or TV for each source; update TV Support to 0.1.1 for native list
  placement, changes and recovery. Existing entries default to TV.
- Choose a connected media player and its current app/source directly, including
  Apple TV apps, alongside the correct HDMI input and optional extra HA action.
- Save without playback; validate live device/app choices and keep custom HA edits.

# 0.6.0-dev5 — development only

- Add the TV Support installer and source editor to the existing flow.
- Configure local TV apps or existing HDMI inputs, with optional native HA actions.
- Save without playback, explicitly test on TV, change, remove or restore.
- Keep signed helper source/artifact together; private signing keys stay local.
- Protect management with DUMP, native broadcasts with DEVICE_POWER, and TV
  mutations with selected identity, ownership and revision checks.
- Preserve private native setting originals and recover interrupted plans.
- Retire the verified previous helper only when explicitly replacing it, without migration.
- Keep hardware testing and rollout deferred; nothing is installed by this commit.

# 0.6.0-dev4

- Explain setup in terms of button actions and TV sources; remove player-specific
  assumptions and references to earlier separate setup flows.
- Mark the app inventory as a preview and state that source editing is unavailable.
- Hide button setup until a TV is chosen and explain paused reception accurately.
- Resume reception for the saved TV directly, without choosing it again.
- Keep the source checkbox stable while saving; show progress only during inventory.
- List all installed apps uniformly, without special treatment for particular players.

# 0.6.0-dev3

- Check the ADB authorization state even when the connect command times out.
- Log the fixed inventory stage on timeout, without device addresses or keys.

# 0.6.0-dev2

- Verify native B&O product identity before ADB inventory. Reuse a verified
  receiver address when the TV temporarily disappears from mDNS discovery.
- Refuse old or rediscovered IP addresses that belong to a different product.

# 0.6.0-dev1 — development candidate

- Add optional source setup to the existing TV/button flow, without a second TV chooser.
- Explicit network ADB connection and read-only package inventory for the selected TV.
- Persist the source-management preference and ADB key; use a separate loopback ADB server.
- Keep existing administrator, ingress and page-token checks on the new operations.
- Recognize independent Spotify/Radio packages; do not modify their sources.
- TV helper installation and source editing remain subsequent stages.

# 0.5.1

- Explain the original idea: use Home Assistant a bit like BeoLiving Intelligence.
- Verify the current HA user's administrator rights on the server, using
  Supervisor's authenticated ingress identity. Missing identity or a failed check
  denies access. Every write rechecks permissions; reads cache them for 15 seconds.
- Stop the old receiver if choosing another TV fails. Rebuild an unhealthy
  receiver when the selected TV is rediscovered, even without Watchdog.
- Limit the full time for an incomplete XMPP frame, including trickled input.
- Keep HA event credentials out of environment-configured HTTP proxies.
- Write settings and health files through exclusive private temporary files.
  Return a clear error if app storage is unavailable.
- Update the base image to Debian 13 and remove pip after building. Add dependency
  auditing and high-severity static checks to CI. Document the review and remaining
  OS-package findings in the security notes.

# 0.5.0

- Open directly on your saved buttons, with a compact TV status. Search only
  during setup or after Change TV. Keep service-menu help under No button received?
- Learn buttons in a separate dialog with a 60-second listening window.
  Recognize existing buttons before offering to change them.
- Choose any action in the Home Assistant editor without first creating a light
  action. A new button starts with no action; finish it in Home Assistant.
- Add Run a script alongside scenes and lights-off. Scripts needing inputs use
  the Home Assistant editor.
- Keep paused automations paused when edited. Keep HA-customized rules visible
  when their description or triggers change, without overwriting their contents.
- New and explicitly changed rules allow HA's Run actions while still rejecting
  delayed remote presses when queued execution begins. Existing rules are kept
  as they are until you change them.

# 0.4.2

- Start with no app options to fill in. Technical overrides are optional;
  choose your TV and button actions in Open Web UI.
- Put Start → Open Web UI first in the app introduction. Explain Show in sidebar
  so the app can be opened directly from the Home Assistant menu.
- Shorten the setup guide to three steps. Move remote naming, manual options
  and protocol details to separate pages.
- Existing saved app options are kept. Restore defaults once to clear the old
  technical fields if you no longer use them.

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
