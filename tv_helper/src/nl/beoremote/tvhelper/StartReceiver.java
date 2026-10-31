package nl.beoremote.tvhelper;
import android.content.*;
/** Restricted startup and the app's own maintenance alarm; never selects a source. */
public final class StartReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context,Intent intent){
        if(!"nl.beoremote.tvhelper.START".equals(intent.getAction())&&!SourceMaintenance.CHECK.equals(intent.getAction()))return;
        try{context.startService(new Intent(context,SupportService.class).setAction(SourceMaintenance.CHECK));setResultCode(-1);}catch(RuntimeException error){setResultCode(1);}
    }
}
