package android.content; import java.util.*;import android.app.AlarmManager;import android.content.pm.PackageManager; public class Context {
 public static final String ALARM_SERVICE="alarm";public static final int BIND_AUTO_CREATE=1;
 public SharedPreferences prefs=new SharedPreferences();public AlarmManager alarm=new AlarmManager();public ContentResolver resolver;public final List<Intent> starts=new ArrayList<>();public int activities;
 public Object getSystemService(String name){return alarm;}public SharedPreferences getSharedPreferences(String n,int m){return prefs;}public ContentResolver getContentResolver(){return resolver;}public PackageManager getPackageManager(){return new PackageManager();}
 public void startService(Intent i){starts.add(i);}public void startActivity(Intent i){activities++;}public boolean bindService(Intent i,ServiceConnection c,int f){return true;}public void unbindService(ServiceConnection c){}public void enforceCallingPermission(String p,String m){}
}
