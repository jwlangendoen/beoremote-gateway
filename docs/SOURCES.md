# Optional source management

The goal is to use a Beoremote for more Home Assistant actions, through LIGHT
buttons and, eventually, shortcuts in the TV's source list. TV setup starts with
one choice of TV. Button actions are available immediately; the optional TV
sources feature offers additional setup when needed.

Development candidate 0.6.0-dev4 keeps the existing gateway and adds a **TV sources**
preview. **Show installed TV apps** reveals connection instructions and **Find TV
apps**. The preview inventories apps only; helper installation, source editing
and routing source selections to Home Assistant are not implemented yet.

## Implemented

- Persist the source-management choice privately, initially disabled.
- Connect with a private persistent ADB key, using a separate loopback ADB server.
- Resolve the selected B&O identity to its current IP; never fall back to another product.
- Verify `/BeoDevice` product identity before ADB; reuse a verified receiver IP
  if a fresh mDNS browse temporarily misses the TV.
- Inventory model, Android version and package IDs, with system packages hidden initially.
- Treat installed apps uniformly, without assuming particular players are installed.
- Keep source inventory available when LIGHT reception is paused.
- Require current administrator access and the page token for both new operations.

The inventory has fixed read-only commands. It cannot accept shell commands,
install an APK, launch an app or change a TV source. Finding a package does not
prove that it is launchable or behaves correctly as a B&O source.

Source settings are in `/data/source-management.json`, with ADB keys under
`/data/adb/`. The default ADB key directory also points there in the container.
Reading the screen or enabling the extension does not start ADB. Turning it off
closes the app's own ADB server, without stopping other integrations' servers.

## Next stages

1. Validate the candidate through real Supervisor ingress and TV ADB inventory.
2. Add model/firmware checks, scoped backups, and installation of a configurable TV helper.
3. Migrate the current Apple TV helper with its signing identity, source IDs and rollback data.
4. Add an editor for local apps, existing HDMI inputs and external devices via HA scripts.
5. Offer test/save/remove using verified available firmware source slots.

The source list has finite firmware slots; do not offer unlimited entries or
assume TV/MUSIC placement works for every package. Media keys, standby and
audio-only behavior require route-specific checks.

Both LIGHT buttons and source selections should use the same native HA scripts.
Future source events need identity, freshness, completion and loop prevention;
do not duplicate actions already handled by a LIGHT mapping or legacy blueprint.

Existing standalone players keep their own installation, configuration and
source registration. The gateway does not assume any particular player is present
and the inventory does not manage or duplicate existing sources.
