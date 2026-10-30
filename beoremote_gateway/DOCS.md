# Beoremote Gateway 0.2.2

Receive Beoremote One LIGHT commands through a Beovision Horizon and use them in
Home Assistant. Experimental: only Horizon has been tested. This is a network
receiver, not software installed on the TV.

## Requirements

Use Home Assistant OS with its app store. Reserve IPv4 addresses for the TV and HA
in your router. Both should be on the same trusted LAN, with mDNS available.
Guest Wi-Fi isolation and VLAN filtering can prevent discovery or connections.
TCP port 5222 must be free on the HA host. TV acceptance of alternative ports has
not been verified.

The observed BeoCore connection has no TLS or password exchange. Keep it inside a
trusted LAN; do not expose it to the internet. The IP/JID checks restrict peers but
are not cryptographic authentication.

## 1. Find the TV identity

- `horizon_address`: the TV's IPv4 address.
- `horizon_jid`: the exact `jid` from its `_beocore._tcp.local.` TXT record. This is
  not your Google account, an email address or a value to guess.
- `advertise_address`: Home Assistant's LAN IPv4 address, not a Docker-internal IP.

Inspect the TV in a network service browser. Alternatively, clone this repository
on a computer on the same LAN and run:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r beoremote_gateway/requirements.txt
.venv/bin/python tools/discover.py --timeout 10
```

The helper only browses mDNS. It does not advertise a gateway, change settings,
open a TV session or send control commands. Its output contains private device
identities: do not paste unredacted output into a public issue. If several products
appear, match the IP address against your TV/router. Wake the TV normally if needed.

On macOS you can also use `dns-sd -B _beocore._tcp local.`, followed by
`dns-sd -L 'INSTANCE NAME' _beocore._tcp local.`. Stop each command with Ctrl-C.

## 2. Configure the app

In **Configuration**, enter your values. The example below uses documentation-only
addresses and a synthetic TV identity; replace all three device values. Keep the
default gateway identity for a single gateway.

```yaml
mode: advertise
horizon_address: "192.0.2.10"
horizon_jid: "7980.1234567.12345678@products.bang-olufsen.com"
advertise_address: "192.0.2.20"
gateway_name: "Home Assistant Light"
gateway_jid: "homeassistant.light.gateway@products.bang-olufsen.com"
xmpp_port: 5222
publish_ha_events: true
log_level: info
```

Save, start the app and enable **Start on boot** and **Watchdog**. Look for
`gateway_advertised` in its log. Select your configured gateway name in the TV's
gateway menu; discovery alone does not route remote presses. Note the previous
destination before changing it. The menu name/location can vary by firmware.
`xmpp_stream_open` confirms the TV connected.

## 3. Confirm reception

1. In **Developer tools → Events**, listen for `beoremote_telegram`.
2. On the remote, open **LIST → LIGHT**, navigate to a function and select it.
   Selecting LIGHT alone may just enter light-control mode without a telegram.
3. Check that an event arrives from your TV with the expected `data_hex`.

Events contain `peer_jid`, `originator`, `data_hex`, `data_base64`, `timestamp`
and `received_at`. The TV's `timestamp` is not a Unix receipt time. Use
`received_at` to check freshness.

| Observed choice | Command byte | `data_hex` |
| --- | --- | --- |
| LIGHT 0 | 0 | `001b0000000000000000000000` |
| LIGHT 1 digit key | 1 | `001b0000010000000000000000` |
| LIGHT function 1 (initially Ochtend) | 15 | `001b00000f0000000000000000` |
| LIGHT function 11 (initially Home) | 37 | `001b0000250000000000000000` |
| Release | 126 | `001b00007e0000000000000000` |

Function numbers are not command bytes. Names can be renamed on the remote;
confirm the event rather than guessing. Command bytes 38, 39 and 57 were tested
with simulated events; their physical remote presses remain unverified.
Repeat suppression covers LIGHT bytes 0, 15, 37, 38, 39 and 57. Other commands,
including digit 1, remain raw and may repeat.

## 4. Create an automation

Under **Settings → Automations & scenes → Blueprints → Import**, import:

```text
https://github.com/jwlangendoen/beoremote-gateway/blob/main/blueprints/automation/beoremote_light_action.yaml
```

Create one automation per button. Enter the TV identity, select the LIGHT button
whose payload you observed, and choose your action, such as activating a scene.
Leave **Dry run** enabled initially. Press the real button and inspect the trace:
a fresh matching event stops at the dry-run step before executing your action.
Turn Dry run off once the mapping is correct.

The blueprint matches the TV identity, originator and full payload, rejects old,
future or missing receipt times and checks freshness when a queued run starts.
Manual **Run actions** does not impersonate a remote press. Each automation queues
up to five runs; ordering between separate automations is not guaranteed. Avoid
long delays in scene actions.

## Remote labels

The gateway does not edit remote display text. On the tested remote:

1. Select the separate **Beovision** profile via the product name at the top of LIST.
2. Open **Settings → Advanced → Light menu**.
3. Use **Rename**, **Show** and **Move**.
4. Return to your normal paired TV product.

A renamed LIGHT function was confirmed visible with the Bluetooth-paired Horizon.
**Products** edits product names rather than these function labels.

## Options

| Option | Meaning |
| --- | --- |
| `mode` | `disabled`: no listener/advertising; `listen`: receive only; `advertise`: receive and announce `_beocore._tcp`. |
| `horizon_address` | Allowed TV IPv4 address; required in active modes. |
| `horizon_jid` | Exact TV identity; required in active modes. |
| `advertise_address` | HA host LAN IPv4 address; required in advertise mode. |
| `gateway_name` | Name in the TV gateway menu. Existing Dutch default retained for updates. |
| `gateway_jid` | Stable identity, distinct from the TV and other gateways. |
| `xmpp_port` | TCP listener port; default 5222. |
| `publish_ha_events` | Publish HA events; default off. |
| `log_level` | `info`, `debug`, `warning` or `error`. Debug includes raw telegrams. |

Save and restart after changes. The app uses host networking for discovery and TV
connections. It requests `homeassistant_api` to post events using the built-in
Supervisor token: no personal access token is needed. That permission allows
broader Core API access, although this code only posts events. Protection mode
can stay enabled. No host files or Docker socket are mounted.

## Troubleshooting

- **No discovery:** check LAN addresses, multicast filtering and port conflicts.
  `gateway_discovery_retry` means advertising will retry with increasing delays.
- **Advertised, no stream:** check the TV's selected gateway, IP/JID and TCP port.
  Wake the TV; standby has not been verified.
- **Stream, no events:** check `publish_ha_events`, select an actual LIGHT function,
  and inspect the `received`/`suppressed` counters in `gateway_status`.
- **Events, no action:** inspect the automation trace, Dry run, payload and identity.
- **HA unavailable:** old commands expire and uncertain HTTP requests are not
  retried. Try a new press after recovery.

`gateway_status` appears about once a minute. The heartbeat checks process/workers;
a standby TV or unavailable HA alone is not a reason to restart. Use debug logging
temporarily for unknown codes and redact device identities before sharing logs.
CONTROL, dimming and standby are not verified.

## Updates and removal

Back up the app and automations before updating. Updates appear in the app store;
review the changelog and test a real button afterwards. Candidate 0.2.2 keeps the
receiver implementation from 0.2.1; hardware evidence is recorded separately.

To remove: disable its automations, restore the previous TV gateway destination,
then stop and uninstall the app. Importing a blueprint alone changes no TV settings,
remote labels, lighting or existing automations.
