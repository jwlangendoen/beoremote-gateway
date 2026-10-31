package android.content; import android.os.IBinder; public interface ServiceConnection {void onServiceConnected(ComponentName n,IBinder b);void onServiceDisconnected(ComponentName n);}
