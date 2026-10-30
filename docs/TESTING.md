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

## Still to try

- A full 0.5.0 setup through HA ingress and the repository installation, including
  learning/saving a physical button and checking the chosen real scene.
- Importing the blueprint and checking it with a real LIGHT press in Dry run.
- Beovision 14, Avant NG and other B&O models.
- Standby, CONTROL, continuous dimming and held buttons on hardware.
- Recovery after a real network outage or a full HA host reboot.
- A physical amd64 HA installation, alternative XMPP ports and TV acceptance of
  the GetContactInfo metadata response.

If you try another setup, please include its model, firmware and which buttons
or actions worked.
