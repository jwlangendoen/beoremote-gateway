# Beoremote Gateway

I wanted to control my lights with the Beoremote One I already use for my TV.
The LIGHT menu was there, so it seemed like a nice thing to make work with Home
Assistant.

This little gateway connects my Beovision Horizon to Home Assistant. At home I use
it to switch between lighting scenes. The app lets you teach it a LIGHT button and choose a scene or lights to turn off.

```text
Beoremote One → Beovision Horizon → Gateway → Home Assistant
```

It runs as a Home Assistant app (formerly called an add-on). Everything stays on
your local network. You don't need to install anything on the TV or buy a separate
B&O gateway.

## Does it work with my setup?

I've tested it with a **Beovision Horizon, Beoremote One and Home Assistant Green**.
LIGHT commands work in that setup. Standby, CONTROL and continuous dimming still
need testing. This is an early version of a hobby project.

If you have a **Beovision 14 or Avant NG (2016)**, I'd be interested to hear whether
it works for you too. Those models haven't been tested yet. You can share your
results in a [compatibility report](https://github.com/jwlangendoen/beoremote-gateway/issues/new?template=compatibility.yml).
The [testing notes](docs/TESTING.md) have the details.

For newer Mozart products, the [official B&O integration](https://www.home-assistant.io/integrations/bang_olufsen/#beoremote-one)
already provides remote events and may be all you need.

## Give it a try

You'll need Home Assistant OS with the app store, your remote paired to the TV,
and both devices on the same trusted local IPv4 network.

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjwlangendoen%2Fbeoremote-gateway)

1. Add the repository and install **Beoremote Gateway** from the app store.
2. Click **Start**, then **Open Web UI**. Wake your TV, click **Find my TV**,
   choose it and click **Use this TV**. Keep the app running.
3. On the Horizon, open **MENU → Settings**, highlight **Service Menu** and press
   the **red button before the centre button**. Open **Customer Service Menu →
   Settings → BeoLink Gateway** and select **Home Assistant Gateway** (or the name
   shown in the app). Return to the app and wait for **TV connected**.
4. Click **Add a button**, press a LIGHT function on your remote, give it a name
   and choose a scene or lights to turn off. Save, release the button and press it
   again to try it. No blueprint or device codes needed.

Do the Home Assistant steps first: the app must be running with your TV selected
before you can choose it in the TV's gateway list. Finding the TV in the app does
not select the gateway on the TV. The [step-by-step guide](beoremote_gateway/DOCS.md)
includes the full menu route and what to do if the gateway does not appear.

No IP addresses or long device identities to type. If you are upgrading from
0.2.2, set **Mode** to **auto** once and restart. Existing manual configurations
are preserved. Older installs may still show **Home Assistant Licht**; change
**Name in the TV menu** to **Home Assistant Gateway**, save and restart if you
want the new name. The setup page always shows the name to select.

Want your own names in the LIGHT menu? On the Horizon you first need to show or
add a separate Beovision **infrared** profile on the remote, then use its LIGHT
editor. The [remote naming steps](beoremote_gateway/DOCS.md#give-the-light-functions-your-own-names)
walk through that workaround.

## Want to work on it?

Python 3.12 or 3.13:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python tools/check_release.py
PYTHONPATH=beoremote_gateway .venv/bin/python -m unittest discover -s tests -v
```

The tests run locally without connecting to your TV or Home Assistant.
[Build and release notes](docs/RELEASING.md) are available if you want to make your own version.

Built with AI assistance and tested on my own Horizon. This is an independent
project, with no affiliation to Bang & Olufsen.

[MIT license](LICENSE) · [Third-party software](THIRD_PARTY_NOTICES.md)
