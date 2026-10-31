package android.content; import java.util.*; public class Intent {
 public static final String ACTION_BOOT_COMPLETED="boot",ACTION_MY_PACKAGE_REPLACED="replaced";public static final int FLAG_ACTIVITY_NEW_TASK=1;
 public String action;public Class<?> target;final Map<String,Object> extras=new HashMap<>();
 public Intent(String a){action=a;}public Intent(Context c,Class<?> t){target=t;}
 public String getAction(){return action;}public Intent setAction(String a){action=a;return this;}public Intent setComponent(ComponentName c){return this;}public Intent addFlags(int f){return this;}
 public Intent putExtra(String k,String v){extras.put(k,v);return this;}public String getStringExtra(String k){return (String)extras.get(k);}
 public Object getParcelableExtra(String k){return extras.get(k);}public int getIntExtra(String k,int d){return (Integer)extras.getOrDefault(k,d);}public long getLongExtra(String k,long d){return (Long)extras.getOrDefault(k,d);}
}
