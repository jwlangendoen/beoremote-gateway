# Beoremote Gateway 0.3.0

Receive Beoremote One LIGHT commands through a Beovision Horizon and use them in
Home Assistant. Experimental: only Horizon has been tested. This is a network
receiver, not software installed on the TV.

## Requirements

Use Home Assistant OS with its app store. The TV and HA should be on the same
trusted IPv4 LAN, with mDNS available. DHCP reservations are useful for manual
setups; auto mode follows the chosen TV when its address changes.
Guest Wi-Fi isolation and VLAN filtering can prevent discovery or connections.
TCP port 5222 must be free on the HA host. TV acceptance of alternative ports has
not been verified.

The observed BeoCore connection has no TLS or password exchange. Keep it inside a
trusted LAN; do not expose it to the internet. The IP/JID checks restrict peers but
are not cryptographic authentication.

## 1. Find your TV automatically

Start the app and click **Open Web UI**. The setup page looks for B&O products on
your local network. Wake the Horizon if it does not appear, choose your TV and
click **Use this TV**. Other B&O speakers may also appear: choose the TV you want
to use. Nothing is selected automatically, even when only one product is found.

The app finds both the TV identity and the outgoing Home Assistant LAN address.
You do not need a terminal, network service browser or personal access token.
Your selected TV identity is saved privately in the app's data folder. The app
looks for that same identity after a restart and periodically while running, so
an IP address change can be picked up. It never switches to another product on its own.

If your TV is asleep or temporarily absent, the setup page waits for it. **Find my
TV** searches again. **Stop gateway** pauses the receiver and keeps the choice;
select the TV again to resume. This paused state also survives an app restart.

### Upgrading from 0.2.2

Existing app options are preserved during an update. In **Configuration**, change
**Mode** to **auto**, save and restart, then open the setup page. The old address
fields can stay as they are; auto mode ignores them. Manual `listen` and `advertise`
configurations keep working until you choose to change modes. `disabled` keeps
the receiver off while leaving the setup page available.

If an older local gateway is still installed, stop it before using the same port
and gateway identity in the new installation.

## 2. Connect the Horizon

After choosing the TV, the app announces itself and enables HA event publishing.
In the TV's gateway menu, select the name shown on the setup page (the existing
default is **Home Assistant Licht**). Note the previous destination before changing
it. The menu name/location can vary by firmware.

The setup page shows **TV connected** when the Horizon opens its connection.
Discovery finds the device; selecting the gateway on the TV routes the button
presses. Enable **Start on boot** and **Watchdog** once your setup is working.

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

Create one automation per button. Use **Import blueprint** and **Copy TV identity** on
the setup page. Paste the identity into the blueprint, select the LIGHT button
whose payload you observed, and choose your action, such as activating a scene.
Leave **Dry run** enabled initially. Press the real button and inspect the trace:
a fresh matching event stops at the dry-run step before executing your action.
Turn Dry run off once the mapping is correct.

The blueprint matches the TV identity, originator and full payload, rejects old,
future or missing receipt times and checks freshness when a queued run starts.
Manual **Run actions** does not impersonate a remote press. Each automation queues
up to five runs; ordering between separate automations is not guaranteed. Avoid
long delays in scene actions.

## Give the LIGHT functions your own names

The names on the remote are edited on the **Beoremote One** itself. They are not
Home Assistant scene names. On the Horizon, the editor is accessed through a
separate **Beovision infrared (IR) product profile**, which can be a bit hidden.

1. Press **LIST**, open **Settings → Advanced → Products** and make the extra
   **Beovision** IR product visible. On remotes with a **Show** menu, enable it
   there; other firmware may offer an add-product flow. This is a separate profile
   alongside your Bluetooth-paired Horizon. Keep the Horizon pairing.
2. Press LIST and go to the current product name at the top of the display.
   Select the separate **Beovision** IR profile you just added or made visible.
3. Open **Settings → Advanced → Light menu** in that profile.
4. Use **Show** to expose the functions you want, **Rename** to give them names
   such as Movie or All off, and **Move** to choose their order.
5. Switch back to your usual Bluetooth-paired Horizon product through LIST.
   The renamed LIGHT functions are also available when controlling the Horizon.
6. Match each button to the action or scene you want in the HA blueprint.
   Renaming a function does not create a scene or change its command byte.

The product **Rename** setting under Products changes the product's name, not the
LIGHT function labels. You need the separate **Light menu** for those. Renaming
a function and returning to the Bluetooth Horizon profile was checked on the real remote.

The menu wording can vary with remote firmware. B&O explains
[showing an IR product](https://support.bang-olufsen.com/hc/en-us/articles/360045510351-How-do-I-set-up-Beoremote-One-for-use-with-Beosound-Moment)
and [switching products](https://support.bang-olufsen.com/hc/en-us/articles/360041313292-How-do-I-switch-between-products-using-my-Beoremote-One).
The [HA B&O documentation](https://www.home-assistant.io/integrations/bang_olufsen/#configuring-light-and-control-functions)
also describes the LIGHT editor. Adding the Beovision profile is the extra step
needed when that profile is not already in the remote's product list.

## Options

| Option | Meaning |
| --- | --- |
| `mode` | `auto`: setup page and saved TV selection (default); `disabled`: receiver off; `listen`: manual receive only; `advertise`: manual receive and announce. |
| `horizon_address` | Manual TV IPv4 address; ignored in auto mode. |
| `horizon_jid` | Manual TV identity; ignored in auto mode. |
| `advertise_address` | Manual HA LAN IPv4 address; detected automatically in auto mode. |
| `gateway_name` | Name in the TV gateway menu. Existing Dutch default retained for updates. |
| `gateway_jid` | Stable identity, distinct from the TV and other gateways. |
| `xmpp_port` | TCP listener port; default 5222. |
| `publish_ha_events` | Manual modes only. Auto setup enables events after you choose a TV. |
| `log_level` | `info`, `debug`, `warning` or `error`. Debug includes raw telegrams. |

Save and restart after changes. The app uses host networking for discovery and TV
connections. It requests `homeassistant_api` to post events using the built-in
Supervisor token: no personal access token is needed. That permission allows
broader Core API access, although this code only posts events. Protection mode
can stay enabled. No host files or Docker socket are mounted. The setup page is
served through HA ingress; direct LAN requests are rejected. It only accepts the
Supervisor proxy as its TCP peer, and changes require the setup page token. HA
allocates a free port for this page; the app reads it from its own Supervisor info
endpoint without requesting additional Supervisor privileges.

## Troubleshooting

- **No TV in the setup page:** wake it and search again. Check multicast filtering
  and that HA and the TV are on the same LAN. A discovery result alone does not
  establish support for another model.
- **No gateway discovery on the TV:** check multicast filtering and port conflicts.
  `gateway_discovery_retry` means advertising will retry with increasing delays.
- **Advertised, no stream:** check the TV's selected gateway, IP/JID and TCP port.
  Wake the TV; standby has not been verified.
- **Stream, no events:** select an actual LIGHT function (and check
  `publish_ha_events` if using a manual mode),
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
review the changelog and test a real button afterwards. Version 0.3.0 adds the
setup page; historical receiver hardware checks and new setup tests are recorded separately in the project testing notes.

To remove: disable its automations, restore the previous TV gateway destination,
then stop and uninstall the app. Importing a blueprint alone changes no TV settings,
remote labels, lighting or existing automations.
