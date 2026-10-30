# Beoremote Gateway 0.5.0

Use your Beoremote One's LIGHT buttons for Home Assistant actions. You need
Home Assistant OS and a paired Beoremote with a Beovision Horizon on the same
network. Only Horizon has been tested.

## 1. Choose your TV

Install **Beoremote Gateway**, click **Start**, then **Open Web UI**.
Turn on your TV, choose it and click **Use this TV**.

Enable **Show in sidebar** on the app's Info tab for direct access next time.
The Configuration tab only contains optional technical settings.

## 2. Add a button

1. Click **Add a button**.
2. On your remote, open **LIST → LIGHT** and press a function.
3. Give it a name and choose an action:
   - **Choose in Home Assistant** opens the ordinary automation editor. Add
     any actions you want and click **Save** there. Until then the button does nothing.
   - **Activate a scene**, **Turn off lights** or **Run a script** lets you
     choose an existing scene, light group or script directly.
4. Release the button, then press it again to try it.

Learning and saving do not run the action. If the button is already set up,
you'll see its existing name and action instead of creating another one.

Use **Change** or **Pause** beside a button, or **Open in Home Assistant** for
more options. Scripts with required inputs need the Home Assistant editor.
Disable any older automation for the same button so one press doesn't run both.

## No button received?

Try with the TV on and press an actual LIGHT function. If it arrives, no TV menu
changes are needed. A Horizon that used the gateway before may reconnect itself.

Otherwise, keep the app running and use your Beoremote on the TV:

1. Open **MENU → Settings**.
2. Highlight **Service Menu** and press the **red button before the centre button**.
3. Open **Customer Service Menu → Settings → BeoLink Gateway**.
4. Select **Home Assistant Gateway** and confirm with the centre button.
   If your gateway has another name, select that one.

If it's missing, check your TV choice in the app, then reopen the TV's gateway list.
These steps are also under **No button received?** in the app.

[Rename LIGHT functions on the remote](https://github.com/jwlangendoen/beoremote-gateway/blob/main/docs/REMOTE.md)
· [Advanced settings and troubleshooting](https://github.com/jwlangendoen/beoremote-gateway/blob/main/docs/REFERENCE.md)

TV menu steps: [BeoLiving's Horizon guide](https://khimo.github.io/bli-guides/manuals/bli-connect-to-TV#beovision-horizon).
