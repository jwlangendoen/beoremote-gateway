# What I've tested

My setup is a Beovision Horizon, a Beoremote One and Home Assistant Green.
Other TV models still need testing.

## On the TV

The gateway appears in the TV's gateway menu and receives LIGHT presses after
being selected. I've received presses and releases for:

- LIGHT 0 and LIGHT 1 digit keys.
- LIGHT function 1, originally called Ochtend (command byte 15).
- LIGHT function 11, originally called Home (command byte 37).

Two scene functions have been checked with the real remote and lights, most
recently on version 0.2.0. Other scene routes were tried using simulated HA events.
The receipt-time check added in 0.2.1 was checked in HA with fresh and old events.
These hardware checks were recorded on 14 October 2026.

## Automated checks

For version 0.2.2 on 30 October 2026, all 37 tests passed on Python 3.12 and 3.13 in GitHub CI.
Both aarch64 and amd64 containers also passed startup, health and shutdown checks.
The tests cover the protocol parser, connection recovery, event delivery, blueprint
conditions and source exports. They use loopback connections and simulated faults.

The source archive was also extracted and tested separately. Button fixtures
contain recorded payload values; test device identities and XML envelopes are
made up. Raw captures and home settings aren't included.

## Setup page (0.3.0)

The new tests cover product discovery and record validation, explicit selection,
remembering only the selected identity, IP changes, pause/restart, keeping manual
settings, ingress access checks and setup form requests. HTTP tests use local
connections and synthetic B&O products. A separate read-only network check found
the known Horizon and resolved the outgoing LAN address; it did not advertise a
gateway or send TV/lighting commands.

The setup page still needs a full run inside real HA ingress and a real Horizon
connection after automatic setup. Existing receiver hardware results above do not
prove that new flow. The updated remote guide includes the IR-profile step; it does
not mean the app can edit remote labels.

## Guided actions (0.4.0)

On 30 October 2026, 75 local automated checks passed on Python 3.12. These include
learning timeout/cancel/release handling, blocking the learning press before event
publication, stable automation IDs, friendly target lists, change/pause/removal,
protecting unrelated or customized rules, ingress requests and HA client failures.
The browser flow was also checked with a simulated TV and scenes.

An isolated official Home Assistant Core 2026.10.4 container, with networking
disabled, accepted the generated automation through its native configuration API.
Create/list/change/pause/enable/delete worked. Saving did not activate the fixture
scene. A fresh synthetic event activated a virtual input boolean; manual execution,
stale events and future events did not. No real HA instance, TV or lights were
contacted by this test. The Supervisor proxy and a physical button still need the
full installation check below.

## Simple app setup (0.4.2)

The default app options are empty and the runtime defaults to auto mode. Existing
manual options remain valid. The startup checks cover empty options as well as
explicit auto and disabled modes; without a selected TV, none opens the receiver
or advertises a gateway. Controller tests cover restarting with a saved TV.

The app schema follows HA's optional-options format: unset fields are hidden
behind its optional-fields switch. Older saved options remain visible until the
user resets them. This behavior was checked against the HA app configuration
documentation and frontend implementation; it was not exercised in the user's
live Supervisor UI.

## Button overview and HA actions (0.5.0)

On 30 October 2026, 83 automated checks passed locally on Python 3.12. The browser
flow was checked with synthetic data at desktop and 390-pixel mobile widths:
compact overview, explicit TV change with the selected radio checked, learning,
recognizing an existing button, changing a paused button to a script and creating
a button with no actions. The latter navigated to its HA editor path; the local
preview does not host that editor.

An isolated official HA Core 2026.10.4 container with networking disabled verified:

- Scene and script execution on a fresh synthetic event; saving executes neither.
- Required script inputs are excluded from the simple picker.
- Manual Run actions works; stale and future remote events are rejected.
- A press waiting behind a long run is checked again when execution starts.
- Pause survives editing, and HA-customized rules stay listed after changing
  their description and adding a catch-all event trigger.
- A new button with no device action loads successfully and can be completed in HA.

The aarch64 app container passed default/auto/disabled startup, ingress access,
health and clean shutdown checks. No household devices were used for these tests.
The installed 0.4.2 app had separately received a physical LIGHT function 11 press
during the UX review, without saving a new mapping. A complete physical 0.5.0
save-and-run check through Supervisor ingress remains to be done.

## Security and failure handling (0.5.1)

On 30 October 2026, 100 tests passed locally on Python 3.12. New checks cover
server-side administrator authorization, immediate write denial after role
revocation, failed access lookups, redirect rejection, event credentials bypassing
HTTP proxies, fixed frame deadlines and normal fragmented streams, failure when
switching TVs, unhealthy worker recovery, temporary-file symlinks and storage errors.

An isolated official HA Core 2026.10.4 with external networking disabled verified
real owner/admin roles, rejection of ordinary and unknown users, and rejection of
a write after an admin was demoted while read access was cached. The ingress
proxy's header contract was checked against Supervisor 2026.10.0 source; the
fixture uses that header with a local proxy boundary, not a full HA OS Supervisor.

See [the security review](SECURITY.md) for dependency scans, OS-package findings,
trust boundaries and remaining limits. No household equipment was attacked or
reconfigured for these tests.

## Optional source extension (0.6.0-dev3, development only)

On 30 October 2026, all 121 tests passed locally on Python 3.12. These cover the
existing gateway plus source opt-in, exact TV identity checks, missing discovery
records, stale addresses, ADB authorization/timeout states, fixed inventory
commands, private persistence and administrator/page-token checks. The TCP frame
deadline test accepts either EOF or a reset within the same deadline on macOS.

The aarch64 image passed default/auto/disabled startup, ingress restriction,
heartbeat and clean shutdown checks with external networking disabled. The real
Debian ADB client started its own daemon, reused a private key and shut down
without touching other ADB servers.

A local development installation on the Green was tested through real Supervisor
ingress, retaining the existing interface and five HA button actions. The TV
choice and source option survived updates. Discovery found the selected Horizon,
and its native product identity matched the selected JID. Its ADB TCP port was
reachable, but the TV did not complete the ADB connection; an existing Mac ADB
session also reported this TV offline. The package inventory has not succeeded
on hardware yet. A physical LIGHT press has not been verified for this candidate.

The original 0.5.0 repository installation was backed up and restored to running
after the test. The candidate's receiver is paused, source management disabled,
and its boot setting is manual. No HA button actions, TV sources, player APKs or
TV settings were changed. Nothing was published from this development work.

## Setup flow review (0.6.0-dev4, development only)

On 30 October 2026, 123 tests passed locally on Python 3.12. Added checks verify
that resuming keeps the saved TV identity, does not choose another product, and
requires the page token and current administrator access.

A separate browser pass used a clean local fixture with simulated TV discovery,
LIGHT presses, HA scripts and ADB results. It covered TV selection, adding a
script action, optional app inventory, pending TV authorization, connection
failure, system-app filtering, pausing and direct resumption. At 390 pixels the
content reflowed without clipped controls; keyboard Tab and Enter reached and
opened help with a visible focus indicator. This was not a full screen-reader
or accessibility-conformance test. Hardware authorization, APK installation and
source editing were not exercised by the fixture.

The review removed player-specific assumptions, references to earlier separate
flows, an inaccurate paused-state instruction and the source checkbox's visual
reset while saving. Source editing is explicitly unavailable in this preview.

After a partial HA backup, the local candidate was uninstalled. The original
repository app was updated through its existing repository to 0.5.1; automatic
updates remained enabled. One Beoremote installation remained, with all five
existing button actions present. The temporary management terminal was stopped.
The 0.6.0 development changes are separate from that installed repository version.

## Source editor and TV Support (0.6.0-dev6, development only)

On 30 October 2026, 155 local Python tests passed. They cover fixed management
operations, the bundled installer, slot allocation, current TV/revision/owner
checks, private backups, save without playback, explicit tests, HA customizations,
ambiguous replies, missing webhook integration and paused-action preservation.
The helper built against Android API 28 with minimum API 21 and Java 8; its signed
artifact, source digest and restricted manifest were checked. Pure Java tests
cover identity, HDMI handoff, app routing, duplicate suppression, cancellation
and request expiry.

A fresh isolated Home Assistant Core 2026.10.4 with networking disabled accepted
the source webhook automation and activated only a virtual test script on a fresh
matching request. Wrong TV/source identities and stale/future timestamps did not
activate it. Saving executed nothing; editing, removing and restoring preserved
paused state. The minimal fixture explicitly loaded the webhook integration;
the gateway now checks its availability before linking an HA action.

The local browser fixture covered connection, explicit previous-helper replacement,
installation, a local-app source, an HDMI source with a script, saving and requesting
a test. All device and HA operations there were simulated. The last native browser
confirmation could not be completed after the Mac locked; removal and restoration
were independently checked through the editor and real isolated Core APIs.

At the user's request, no further household TV or HA operations were performed.
The new APK has not been installed on the TV, and no rollout or merge to the
auto-update branch was performed. Hardware ADB, actual registration, native
playback/standby and physical remote behavior remain for the integral test.

## Still to try

- A full 0.5.0 setup through HA ingress and the repository installation, including
  learning/saving a physical button and checking the chosen real scene.
- Importing the blueprint and checking it with a real LIGHT press in Dry run.
- Beovision 14, Avant NG and other B&O models.
- Standby, CONTROL, continuous dimming and held buttons on hardware.
- Recovery after a real network outage or a full HA host reboot.
- A physical amd64 HA installation, alternative XMPP ports and TV acceptance of
  the GetContactInfo metadata response.
- Complete ADB authorization/inventory and physical LIGHT checks for 0.6.0.

If you try another setup, please include its model, firmware and which buttons
or actions worked.

## MUSIC/TV, connected apps and tabs (0.6.0-dev6)

- 162 Python regressions pass, including list change/restore, live media-player
  capability and app validation, no playback on Save, automation ordering and
  pause preservation. TV Support 0.1.1 is rebuilt and its signed source digest
  passes; existing lifecycle tests pass.
- Browser fixtures verify Light/Sources/Configuration, both unconfigured empty
  states and Configuration links, source setup, MUSIC and TV saves and direct
  connected-device app selection. No household device is used by those fixtures.
- Network-disabled Home Assistant Core 2026.10.4 accepts the app selection and
  wake/wait schema, reports a virtual player's apps, runs select_source followed
  by a virtual script only for a valid fresh callback, rejects wrong/stale/future
  callbacks and preserves paused state across edits/removal/restoration.
- Native MUSIC placement, actual Apple TV launch and remote keys remain hardware
  checks until an explicit physical result is recorded.
