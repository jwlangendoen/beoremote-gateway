package nl.beoremote.tvhelper;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.SystemClock;

/** Process-independent, non-waking registration check. Never opens a source. */
final class SourceMaintenance {
    static final String CHECK = "nl.beoremote.tvhelper.CHECK_SOURCES";
    static final long INTERVAL = 60000L;

    static void schedule(Context context) {
        AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
        PendingIntent check = PendingIntent.getBroadcast(context, 1,
                new Intent(context, StartReceiver.class).setAction(CHECK), flags);
        // Inexact and non-waking: Android may batch this, especially in standby.
        // Repeating alarms survive ordinary process death, unlike Handler callbacks.
        alarms.setInexactRepeating(AlarmManager.ELAPSED_REALTIME,
                SystemClock.elapsedRealtime() + INTERVAL, INTERVAL, check);
    }
}
