# Beoremote Gateway 0.4.2

Use the LIGHT buttons on your Beoremote One for Home Assistant scenes.
You need Home Assistant OS, a paired Beoremote and a Beovision Horizon on the
same local network. Only Horizon has been tested.

## 1. Open the app

1. Install **Beoremote Gateway** from the app store and click **Start**.
2. Click **Open Web UI**. This is where you set everything up; you can leave
   the **Configuration** tab alone.
3. Turn on your TV, choose it in the app and click **Use this TV**.

Enable **Show in sidebar** on the app's Info tab to open Beoremote Gateway
directly from the Home Assistant menu next time.

## 2. Connect the Horizon

Keep the app running. On the TV, use your Beoremote:

1. Open **MENU → Settings**.
2. Highlight **Service Menu** and press the **red button before the centre button**.
3. Open **Customer Service Menu → Settings → BeoLink Gateway**.
4. Select **Home Assistant Gateway** and confirm with the centre button.
   If the app shows a different gateway name, select that one.

Return to the app and wait for **TV connected**.

## 3. Add a LIGHT button

1. In the app, click **Add a button**.
2. On the remote, open **LIST → LIGHT** and press the function you want to use.
3. Give it a name and choose a Home Assistant scene, or choose **Turn off lights**.
4. Click **Save action**. Release the button, then press it again to try it.

Create your scenes in Home Assistant first. Turn off any older automation for the
same button, so one press does not run both. Use **Change** or **Pause** beside a
saved button to adjust it later.

## If you get stuck

- **TV missing?** Wake it and click **Find my TV**.
- **Gateway missing on the TV?** Check that you clicked **Use this TV**, then
  close and reopen the TV's gateway list.
- **No button received?** Check for **TV connected** and press an actual LIGHT
  function, rather than just opening the LIGHT menu.

[Rename the LIGHT functions on your remote](https://github.com/jwlangendoen/beoremote-gateway/blob/main/docs/REMOTE.md)
· [Advanced settings and troubleshooting](https://github.com/jwlangendoen/beoremote-gateway/blob/main/docs/REFERENCE.md)

TV menu steps: [BeoLiving's Horizon guide](https://khimo.github.io/bli-guides/manuals/bli-connect-to-TV#beovision-horizon).
