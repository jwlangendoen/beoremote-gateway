package nl.beoremote.tvhelper;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.SystemClock;
import android.util.Log;

/** The manifest restricts source notifications to the native DEVICE_POWER sender. */
public final class SourceReceiver extends BroadcastReceiver {
    static final String RECEIVED_AT = "nl.beoremote.tvhelper.RECEIVED_AT";
    @Override public void onReceive(Context context, Intent intent) {
        try {
            Intent service = new Intent(context, SupportService.class).setAction(intent.getAction());
            if (intent.getExtras() != null) service.putExtras(intent.getExtras());
            service.putExtra(RECEIVED_AT, SystemClock.elapsedRealtime());
            context.startService(service);
        } catch (RuntimeException error) {
            Log.w("BeoremoteSupport", "Bronmelding niet verwerkt: " + error.getClass().getSimpleName());
        }
    }
}
