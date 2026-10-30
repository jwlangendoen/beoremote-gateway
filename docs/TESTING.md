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

## Still to try

- A full 0.3.0 setup through HA ingress and the repository installation.
- Importing the blueprint and checking it with a real LIGHT press in Dry run.
- Beovision 14, Avant NG and other B&O models.
- Standby, CONTROL, continuous dimming and held buttons on hardware.
- Recovery after a real network outage or a full HA host reboot.
- A physical amd64 HA installation, alternative XMPP ports and TV acceptance of
  the GetContactInfo metadata response.

If you try another setup, please include its model, firmware and which buttons
or actions worked.
