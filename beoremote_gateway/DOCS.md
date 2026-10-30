# Beoremote Gateway 0.4.1

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

## 1. Start the gateway in Home Assistant

1. Install **Beoremote Gateway** from the app store after adding this repository.
2. Open the app's **Info** tab and click **Start**. Leave **Mode** set to **auto**
   for a new installation.
3. Click **Open Web UI** and wake the Horizon. Click **Find my TV** if needed.
4. Select your TV from the discovered products and click **Use this TV**.
   Other B&O speakers may also appear; choose the TV you want to use.
5. Keep the app running and continue with the TV steps below. **Waiting for the
   TV to connect** is expected at this point.

Do these steps before opening the gateway list on the TV. Starting the app alone
is not enough: choosing your TV starts the receiver and makes the gateway visible
on the network. Nothing is selected automatically, even when only one product is
found. Finding the TV in Home Assistant does not select the gateway on the TV.

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

## 2. Select the gateway on the Beovision Horizon

Use your normal Bluetooth-paired Horizon product on the Beoremote One for this
step. The separate infrared profile mentioned later is only for renaming LIGHT
functions, not for connecting the TV to this gateway.

With the app running and your TV selected:

1. Turn on the TV to any source and open the main menu with **MENU**.
2. Select **Settings** and press the **centre button**.
3. Highlight **Service Menu**. Before opening it with the centre button, press
   the **red button**. This reveals the menu containing **Customer Service Menu**.
4. Select **Customer Service Menu** and open it with the centre button.
5. Open **Settings → BeoLink Gateway**. Note the previous gateway selection if
   there is one.
6. From the available gateways, select **Home Assistant Gateway** and confirm
   with the centre button. If you set a different name in the app, select the name
   shown under **Select the gateway on your Horizon** in its setup page instead.
7. Leave the TV menus and return to the app's setup page. Wait for **TV connected**
   before adding a LIGHT action.

In one line: **MENU → Settings → highlight Service Menu → red button → Customer
Service Menu → Settings → BeoLink Gateway → Home Assistant Gateway**.

The service-menu route is described in the
[BeoLiving Horizon connection guide](https://khimo.github.io/bli-guides/manuals/bli-connect-to-TV#beovision-horizon).
That guide connects a BeoLiving device; here you choose this app's name from the
same gateway list. The LIGHT setup continues in Home Assistant below; there is
no BeoLiving login or HOME CONTROL panel to set up for this app. Menu labels can
vary with the TV language or firmware.

If the gateway is missing, check that the app is running, **Use this TV** was
selected and both devices are on the same local network. Close and reopen the
TV's gateway list after the app starts advertising. Discovery alone does not
route button presses: you must explicitly choose the gateway on the TV.

### Name shown on the TV

**Home Assistant Gateway** is the default name in the TV list from 0.4.1.
The app and repository are called **Beoremote Gateway**.

Updates keep existing app options. If your TV still lists **Home Assistant
Licht**, change **Configuration → Name in the TV menu** to **Home Assistant
Gateway**, save and restart the app, then reopen the TV's gateway list. In Dutch,
that field is called **Naam in het tv-menu**. You can also keep your own name;
always select the name shown on the setup page. Renaming the gateway keeps your
saved button actions.

Once your setup is working, enable **Start on boot** and **Watchdog** in the app
so it is available after restarting Home Assistant.

## 3. Give a button an action

In the setup page, click **Add a button**. Open **LIST → LIGHT** on your Beoremote,
choose a function and press it. Selecting LIGHT alone may only enter the menu;
select the actual function you want to use.

Once the app receives the button:

1. Give it a name, such as **Movie**. The app cannot read the display label from
   the remote, so this name is just for your action list.
2. Choose **Activate a scene** and pick one of your existing Home Assistant scenes,
   or **Turn off lights** and choose a light or light group by name.
3. Click **Save action**. Release the remote button, then press it again to try it.

You do not need a blueprint, button code, TV identity or personal access token.
Scenes and light groups need to exist in Home Assistant first. Use **Refresh
actions** after adding them. For a different kind of action, open **More options**
on the saved action to edit it in Home Assistant.

**Change** lets you pick a new scene or lights without learning the button again.
**Pause/Enable** switches the automation off or on; **Remove** deletes it. Saving
an already learned button updates that button instead of creating a duplicate.
Each TV/button has one action in this simple form.

These are ordinary Home Assistant automations, saved in its normal automation
configuration. They survive an app restart or reinstall and appear under
**Settings → Automations & scenes**. If you customize one in Home Assistant, the
app shows it as edited and leaves further changes to Home Assistant. Unrelated
automations are left alone.

If you previously used a blueprint or another automation for the same button,
turn that older automation off before adding the button here. Otherwise both can
run. The app cannot identify arbitrary older automations reliably.

While listening for a button, the app does not publish that TV's remote events.
The captured press and its held repeats are also withheld while you choose the
action. Saving only stores and enables the automation; it does not run the scene.
Only a fresh matching button event runs it afterwards. Listening expires after
30 seconds; a captured button expires after five minutes. Release the button
before trying the saved action.

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
6. Match each button to the action or scene you want in the app.
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
review the changelog and test a real button afterwards. Version 0.4.0 adds the
guided action setup; historical receiver hardware checks and new setup tests are recorded separately in the project testing notes.

To remove: disable its automations, restore the previous TV gateway destination,
then stop and uninstall the app. Importing a blueprint alone changes no TV settings,
remote labels, lighting or existing automations.

## Advanced: events and the optional blueprint

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
