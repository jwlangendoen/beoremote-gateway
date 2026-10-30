# Advanced settings and troubleshooting

For normal setup, use [the short guide](../beoremote_gateway/DOCS.md).
The app's Configuration tab is for overrides; TV selection and LIGHT actions
are set up in **Open Web UI**.

## Updating an older install

Saved options are kept on update. If old technical fields still appear, you can
use **Configuration → ⋮ → Reset to defaults**, confirm and restart the app.
In Dutch, look for **Standaardinstellingen herstellen**. This resets the app
options: the selected TV in the app's private data and your HA automations remain.
Keep your options if you rely on a manual setup or a custom gateway identity or port.

For an old manual setup, change **Mode** to **auto**, save and restart to use
automatic TV selection. Auto mode ignores the old IP and TV identity fields.
Stop an older gateway installation before using the same port and identity.

Older installs may keep the name **Home Assistant Licht**. To rename it, set
**Name in the TV menu** to **Home Assistant Gateway**, save and restart. Select
the name shown in the setup page when choosing the gateway on the TV.

## Network and access

The TV and HA need a trusted IPv4 LAN with mDNS available. Guest Wi-Fi isolation
and VLAN filtering can block discovery. TCP port 5222 must be free on the HA host;
TV acceptance of other ports has not been verified.

The observed BeoCore connection has no TLS or password exchange. Keep it inside
the trusted LAN. IP/JID checks restrict peers but are not cryptographic
authentication.

Auto setup saves the selected TV identity in the app's data folder and follows
its IP address changes. It never selects a different product on its own. Stop
gateway pauses the receiver and remembers the choice, including after a restart.

## Saved button actions

The app creates ordinary Home Assistant automations. They survive an app restart
or reinstall. Saving a learned button again updates its action. Change, Pause,
Enable and Remove manage unchanged actions created by the app. Automations
customized in HA are left for the HA editor to manage.

Listening for a button withholds that TV's remote events. The captured press and
held repeats stay withheld while choosing an action. Saving stores and enables
the automation without running it. A new, fresh press runs it afterwards.
Listening expires after 30 seconds; a captured button expires after five minutes.

## Options

In Configuration, enable **Show unused optional configuration options** to reveal
settings that are not already saved. Normal setup does not need these.

| Option | Meaning |
| --- | --- |
| `mode` | `auto`: setup page and saved TV selection (default); `disabled`: receiver off; `listen`: manual receive only; `advertise`: manual receive and announce. |
| `horizon_address` | Manual TV IPv4 address; ignored in auto mode. |
| `horizon_jid` | Manual TV identity; ignored in auto mode. |
| `advertise_address` | Manual HA LAN IPv4 address; detected automatically in auto mode. |
| `gateway_name` | Name in the TV gateway list; default Home Assistant Gateway. Existing saved names are kept on update. |
| `gateway_jid` | Stable identity, distinct from the TV and other gateways. |
| `xmpp_port` | TCP listener port; default 5222. |
| `publish_ha_events` | Manual modes only. Auto setup enables events after you choose a TV. |
| `log_level` | `info`, `debug`, `warning` or `error`. Debug includes raw telegrams. |

Save and restart after changes. The app uses host networking for discovery and TV
connections. It requests `homeassistant_api` to post events using the built-in
Supervisor token: no personal access token is needed. The setup page also uses
that access to read scenes/lights, save its own automations and enable or disable
them through the same Core API used by the HA automation editor. Protection mode
can stay enabled. No host files or Docker socket are mounted. The setup page is
served through HA ingress; direct LAN requests are rejected. It only accepts the
Supervisor proxy as its TCP peer, and changes require the setup page token. HA
allocates a free port for this page; the app reads it from its own Supervisor info
endpoint without requesting additional Supervisor privileges.

## Troubleshooting

- **No TV in the setup page:** wake it and search again. Check multicast filtering
  and that HA and the TV are on the same LAN. A discovery result alone does not
  establish support for another model.
- **No gateway in the TV list:** start the app, choose the TV with Use this TV,
  then reopen Customer Service Menu → Settings → BeoLink Gateway. Check multicast
  filtering and port conflicts if it is still missing.
  `gateway_discovery_retry` means advertising will retry with increasing delays.
- **Advertised, no stream:** check the TV's selected gateway, IP/JID and TCP port.
  Wake the TV; standby has not been verified.
- **Stream, no events:** select an actual LIGHT function (and check
  `publish_ha_events` if using a manual mode),
  and inspect the `received`/`suppressed` counters in `gateway_status`.
- **No button received:** make sure the TV shows connected and has this gateway
  selected, then retry and press an actual LIGHT function.
- **No scenes/lights:** add them in Home Assistant, then click Refresh actions.
- **Saved but no action:** enable the action, release the button and press it
  again. Check its trace under More options if needed.
- **Runs twice:** turn off the older blueprint/manual automation for that button.
- **Cannot save:** check that HA Core is available and its automation editor works.
  A write may have succeeded before a connection was lost; refresh the list or
  retry the same button. It uses the same automation ID, so retries do not duplicate it.
- **HA unavailable:** old commands expire and uncertain HTTP requests are not
  retried. Try a new press after recovery.

`gateway_status` appears about once a minute. The heartbeat checks process/workers;
a standby TV or unavailable HA alone is not a reason to restart. Use debug logging
temporarily for unknown codes and redact device identities before sharing logs.
CONTROL, dimming and standby are not verified.

## Updates and removal

Back up the app and automations before updating. Updates appear in the app store;
review the changelog and test a real button afterwards. Hardware results and software checks are recorded in [testing notes](TESTING.md).

To remove: disable its automations, restore the previous TV gateway destination,
then stop and uninstall the app. Importing a blueprint alone changes no TV settings,
remote labels, lighting or existing automations.

## Events and the optional blueprint

The guided action setup above is enough for scenes and lights-off. The details
below are for other actions and troubleshooting.

### Inspect raw events

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
Repeat suppression covers simple 13-byte LIGHT press frames, including digit
keys and learned functions. CONTROL and other frame formats remain raw.

### Optional blueprint

Under **Settings → Automations & scenes → Blueprints → Import**, import:

```text
https://github.com/jwlangendoen/beoremote-gateway/blob/main/blueprints/automation/beoremote_light_action.yaml
```

Create one automation per button. Under **Existing automations and more options**
on the setup page, use **Import blueprint** and **Copy TV identity**. Paste the identity into the blueprint, select the LIGHT button
whose payload you observed, and choose your action, such as activating a scene.
Leave **Dry run** enabled initially. Press the real button and inspect the trace:
a fresh matching event stops at the dry-run step before executing your action.
Turn Dry run off once the mapping is correct.

The blueprint matches the TV identity, originator and full payload, rejects old,
future or missing receipt times and checks freshness when a queued run starts.
Manual **Run actions** does not impersonate a remote press. Each automation queues
up to five runs; ordering between separate automations is not guaranteed. Avoid
long delays in scene actions.
