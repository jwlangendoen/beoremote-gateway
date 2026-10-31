# MUSIC and TV sources

Development candidate 0.6.0-dev6 extends the existing gateway. Choose one TV,
configure normal LIGHT actions, and optionally set up sources.
The UI has Light, Sources and Configuration tabs. Without a TV selection,
Light and Sources show a link to Configuration. Native TV selection and optional
ADB/support setup live in Configuration. There are
no required player apps or external-device brands.

## Configuration flow

1. Connect to the chosen TV over authenticated network ADB.
2. Install the bundled, signed Beoremote TV Support APK. It has no Activity.
3. In Sources, choose MUSIC or TV and a launchable local TV app, an HDMI input,
   or an app/source reported by a connected HA media player. Choose the HDMI
   input and the HA device explicitly; their relationship is not inferred.
4. Optionally attach a scene, lights-off, script or normal HA automation editor.
5. Save without playback; explicitly test on TV, change, remove or restore.

A verified previous helper can be retired explicitly. Its eight shortcuts are
removed through its existing management receiver, then it is stopped. This is
replacement, without migration. Its old HA automation is not repurposed. The
new helper does not change standalone players or their registrations.

## Native helper

The source is in `tv_helper/`. `tools/build_helper.py` uses an installed JDK and
Android SDK, with `BEOR_ANDROID_TOOLS` optionally pointing to the tool directory.
Private signing identity is retained in `.local/helper-signing.p12` and its
private configuration. Back those files up for future data-preserving updates.
They are never exported. The bundled base64 APK contains no household endpoint
or credentials. `tools/check_helper.py` verifies the artifact hash and source digest.

The helper supports the observed Horizon firmware aliases WEBMEDIA, DVD, DVD2,
V_AUX, V_AUX2, PC, CAMERA and DTV, with exact ordinal checks. It refuses occupied
slots and registers only generated `BGW_` IDs against the native local product.
Labels and MUSIC/TV-list settings are saved privately before writes and restored when
a shortcut is removed. Native provider operations use bound selection arguments.
Neither the existing HDMI rows nor the source order of other apps is rewritten.

ControlProvider requires `android.permission.DUMP` on every management call.
Native source broadcasts require DEVICE_POWER. The service and background
configuration stay private. Source changes use receipt-time expiry, cancellation,
duplicate suppression and the confirmed native HDMI handoff from the earlier
helper. Launching a local app uses PackageManager's launcher intent. No shell
command, intent URI or arbitrary component comes from the source editor.

## HA and recovery

Source automations have their own stable IDs, limited POST-only/local-only
webhooks, TV/source identity checks and a five-second freshness guard. The helper
posts only after the native route completes and does not retry uncertain HTTP
delivery. Use a shared HA script when a LIGHT button and a source need the same
behavior. Do not create an automation cycle that selects its own source.

The gateway keeps private owner identity, source configuration and the previous
change under `/data/tv-sources/`. Backups include private webhook capabilities
and never enter the browser. The helper retains native setting originals and
an interrupted plan for recovery. Lost ADB replies are reconciled where possible;
otherwise refresh or explicitly restore before continuing. The gateway does not
infer failure from a timeout and delete a capability the TV may already reference.
HA-edited automations are not silently overwritten or deleted.

Every mutation requires the current TV identity, current revision, ingress
administrator access and the page token. A stale browser cannot configure a newly
chosen TV. Source editing remains available while LIGHT reception is paused.

## Validation limit

The source editor, helper build, fixed protocol and state machine are checked
offline. The new helper has not been installed on a household TV. Hardware ADB,
firmware writes, native source selection, standby and physical key behavior still
need the user's integral test. Keep the development PR separate from main until
those results are recorded. No TV or household HA operation is needed to run the
offline tests.

## Connected-device apps

The source editor reads `media_player` entities with SELECT_SOURCE and their
current `source_list`. It does not hardcode Apple TV apps. Saving validates the
entity and exact source again; no media or lighting action is executed on Save.
The helper receives only the native HDMI route and limited callback. After that
route completes, the HA automation selects the chosen app/source before any
additional scene or script. It wakes a sleeping device only if TURN_ON is
advertised, waits at most three seconds and checks request freshness again.
Integration availability, device wake-up and physical remote behavior still
require an integral hardware test.

TV Support 0.1.1 writes both native category (TV 1 / MUSIC 3) and the firmware
remote-list setting. Changes preserve the slot and originals; removal/restoration
uses the correct list. Older saved entries default to TV. The gateway refuses
MUSIC on an older helper and offers an in-place helper update.
