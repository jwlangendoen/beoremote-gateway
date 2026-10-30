package nl.beoremote.tvhelper;
import android.content.*;
/** Explicit ADB-only wake after installation; never selects a source. */
public final class StartReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context,Intent intent){
        if(!"nl.beoremote.tvhelper.START".equals(intent.getAction()))return;
        try{context.startService(new Intent(context,SupportService.class));setResultCode(-1);}catch(RuntimeException error){setResultCode(1);}
    }
}
