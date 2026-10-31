package android.content; import java.util.*; public class SharedPreferences {
 public final Map<String,String> data=new HashMap<>();public int commits;
 public String getString(String k,String d){return data.getOrDefault(k,d);}public Editor edit(){return new Editor();}
 public class Editor {String key,value;public Editor putString(String k,String v){key=k;value=v;return this;}public boolean commit(){commits++;data.put(key,value);return true;}}
}
