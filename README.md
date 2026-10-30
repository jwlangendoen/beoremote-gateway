# Beoremote Gateway

I wanted to use Home Assistant a bit like BeoLiving Intelligence: control the
rest of the house with the Beoremote One I already have for the TV.
This started with the LIGHT menu. At home I use it to switch between lighting
scenes, but the buttons can run other Home Assistant actions as well.

This runs as a Home Assistant app. Choose your TV, press a LIGHT button and pick
a scene, lights or a script. You can also choose any action in the normal
Home Assistant editor. Everything stays on your local network.

## Get started

You'll need Home Assistant OS, a paired Beoremote One and your TV on the same
local network.

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjwlangendoen%2Fbeoremote-gateway)

Install **Beoremote Gateway**, click **Start**, then **Open Web UI**. Enable
**Show in sidebar** to open it directly from the Home Assistant menu next time.

**[Follow the setup guide →](beoremote_gateway/DOCS.md)**

It covers choosing the TV and adding your first LIGHT button. If button presses
already arrive, you can skip the service-menu steps.

## Compatibility

I've tested it with a **Beovision Horizon, Beoremote One and Home Assistant Green**.
Standby, CONTROL and continuous dimming still need testing. This is an early
version of a hobby project.

**Beovision 14 and Avant NG (2016)** haven't been tested. If you try one, I'd be
interested to hear how it goes: [compatibility report](https://github.com/jwlangendoen/beoremote-gateway/issues/new?template=compatibility.yml).
For newer Mozart products, the [official B&O integration](https://www.home-assistant.io/integrations/bang_olufsen/#beoremote-one)
may already do what you need.

[Remote names](docs/REMOTE.md) · [Advanced settings](docs/REFERENCE.md) ·
[Testing notes](docs/TESTING.md) · [Security](docs/SECURITY.md) ·
[Development](docs/RELEASING.md)

Built with AI assistance and tested on my own Horizon. Independent project,
with no affiliation to Bang & Olufsen.

[MIT license](LICENSE) · [Third-party software](THIRD_PARTY_NOTICES.md)
