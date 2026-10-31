# Beoremote Gateway 0.6.0-dev15

Control Home Assistant with your Beoremote One BT through an Android-based
Beovision TV. The remote pairs with the TV over Bluetooth; the TV forwards
its LIGHT commands to the gateway over your local network.

You need Home Assistant OS and a compatible TV on the same local network.
Only Beovision Horizon has been tested. Other Android-based Beovision models
are unverified; source management and the TV Support app support Horizon only.

## 1. Choose your TV

Install **Beoremote Gateway**, click **Start**, then **Open Web UI**.
Turn on your TV, choose it and click **Use this TV**.

Enable **Show in sidebar** on the app's Info tab for direct access next time.
In the gateway's **Configuration** tab, choose your TV and optionally set up
source support. Use **Light** to configure LIGHT buttons and **Sources** to
manage the remote's source lists.

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

## Sources (experimental)

Use **Configuration** to choose your TV and enable **Set up sources**, then **Connect to TV**.
Once source support is configured, use **Connect** directly in **Sources**
to load the chosen TV without returning to Configuration.
Use **Light** for LIGHT buttons and **Sources** for shortcuts. Until a TV is chosen,
both tabs point to Configuration.
On Horizon, open **Home → Settings → General settings → Android settings →
Developer options** and enable **USB debugging**. If Developer options is hidden,
open **About → Build** in Android settings and select Build seven times with the
centre button. Some firmware also needs a separate network ADB option; the
gateway requires port 5555. Allow the connection on the TV if asked.

Menu references: [Horizon user manual](https://bangolufsenassistentgohe.blob.core.windows.net/manuals/TELEVISIONS/BEOVISION_HORIZON/EN_1703_BeoVision_Horizon_EU_v1_3.pdf)
and [Android TV developer setup](https://developer.android.com/training/tv/get-started/create#run-on-device).
Ordinary button actions do not need ADB or a TV installation.

Choose **Install TV Support**. This small background app has no TV screen.
Source setup currently supports Beovision Horizon with Android 5.1; the helper
also checks the native firmware aliases before changing the source list.

If a supported previous helper is found, **Replace the previous source helper**
removes its old shortcuts and stops it. No shortcuts or old HA actions are
migrated. Choose a normal input first if the old shortcut is still active.
Other TV apps are kept.

In **Sources**, choose **Add a source**, give it a name and choose **MUSIC** or **TV**
for its remote list. Choose a local TV app, an existing HDMI input, or an app on a
connected device. For the latter, select the HDMI input, the device in Home Assistant
(such as Apple TV) and one of its reported apps or sources. The device must already
be integrated in Home Assistant. TV Support 0.1.1 or later is needed for MUSIC. Optionally select a scene, lights-off, a script, or **Choose in Home Assistant**
for any action or condition in its normal automation editor.

Connected-device apps need TV Support 0.1.3 for cancellation during wake-up.
Update it in Configuration, then re-save an existing app shortcut to update its
unchanged launch automation. Custom Home Assistant edits and paused actions are kept.
TV Support 0.1.5 can also pause a configured connected player when you leave its
HDMI input for another source, including Radio or Spotify, or put the TV in standby.
Update TV Support and re-save each unchanged connected-device source to enable it.
A paused, off, unreachable or unsupported player is left alone. Switching between
apps on the same HDMI input does not pause the player. A delayed exit is ignored
if a newer gateway source selection has already started. Pause is best effort,
without wake-up or retries, and depends on the local HA connection. Customized
source automations are preserved and do not automatically gain exit handling.

On selection, the gateway connects and wakes Apple TV through its registered
remote and waits up to twenty seconds for the chosen app to become available.
Other players are woken only when supported. If the device or app stays unavailable,
the extra scene or script does not run. Choosing another source or putting the TV
in standby asks Home Assistant to cancel the pending launch. Cancellation uses
the same local connection and cannot be confirmed if that connection is lost.

**Sources** lists existing local TV sources as well as shortcuts added here,
grouped under **TV** and **MUSIC**. Choose **Reorder** beside TV or MUSIC, then use **Move up** or **Move down**
to arrange a local preview. **Save TV order** or **Save MUSIC order** applies
the finished list once; **Cancel** discards the local edit. You can reorder
one list at a time. Tab changes keep the edit; save or cancel before changing
TV setup or editing sources. This needs TV Support 0.1.2 or later; Configuration
offers the update. Moving does not select a source or run an HA action. If the
playing source would move, select a source outside the list being edited first:
use a MUSIC source while ordering TV, or a TV source while ordering MUSIC.
Switching between apps on the same HDMI device does not change the active TV
input. Choose **Check TV order**, then save again; your draft is kept.
**Restore previous setup**
also restores the order from before the last saved change. If a save is not
confirmed, **Check TV order** reads the actual TV state before another attempt.
A preserved draft is applied only to the same TV and unchanged list; an order
that already matches the TV is accepted without sending it again.

**Save source** adds or updates the shortcut without opening it. **Test on TV**
selects it and can run its linked HA action. Check the actual picture and remote
controls. **Remove** deletes a shortcut created here. Switch away from an active
shortcut before removing it. **Restore previous setup** recovers the list and
unchanged source automation from before the last edit; later HA edits are kept.

Only free firmware source slots are used. Existing HDMI and player sources are
not taken over. Hiding setup closes the ADB connection; configured shortcuts
keep working on the TV. Local-app routes need no HA action for daily use.
HA actions use limited local webhooks; the TV receives no general HA token.
Use a stable local address for the HA host. Saving sources refreshes the callback
address for the edited source.

The final candidate still needs an integrated installation and physical remote
test, including recovery after device and network restarts. Earlier hardware
checks do not establish that complete flow. Keep it on the development branch
until the remaining checks in the testing notes are recorded.

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
