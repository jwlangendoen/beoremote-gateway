package nl.beoremote.tvhelper;

import android.app.*;
import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.os.*;
import java.util.*;
import org.json.*;

/** Execute the real SupportService reconciliation against a silent in-memory provider. */
public final class SourceRecoveryTest {
    static final String TV="7980.1234567.12345678@products.bang-olufsen.com";
    static final String A="BGW_000000000001", B="BGW_000000000002", C="BGW_000000000003";
    static int checks;
    static void check(boolean ok,String message){checks++;if(!ok)throw new AssertionError(message);}
    static Map<String,Object> row(Object...pairs){Map<String,Object> r=new HashMap<>();for(int i=0;i<pairs.length;i+=2)r.put((String)pairs[i],pairs[i+1]);return r;}

    static final class MemoryProvider extends ContentResolver {
        final List<Map<String,Object>> rows=new ArrayList<>();final Map<String,String> settings=new HashMap<>();long sid=20;int writes,settingsWrites;
        MemoryProvider(){
            rows.add(row("sid",10L,"source_pid",1L,"source_name","HDMI2","source_type",5,"category",1,"is_use",1,"is_active",1,"signal_sensed",1,"source_friendly_name","HDMI"));
            rows.add(row("sid",11L,"source_pid",1L,"source_name","LINE_IN","source_type",8,"category",3,"is_use",1,"is_active",0,"signal_sensed",1,"source_friendly_name","Line in"));
            rows.add(row("sid",200L,"source_pid",2L,"source_name","FOREIGN","source_type",12,"category",1,"is_use",1,"is_active",0,"signal_sensed",1,"source_friendly_name","Other TV"));
            for(String suffix:ShortcutCatalog.SUFFIXES){settings.put("sourcelist_"+suffix+"_friendly_name",suffix);settings.put("sourcelist_"+suffix+"_beoremote_list","none");}
        }
        Map<String,Object> source(String name){for(Map<String,Object> r:rows)if(name.equals(r.get("source_name")))return r;return null;}
        void removeOwned(){rows.removeIf(r->((String)r.get("source_name")).startsWith("BGW_"));}
        boolean matches(Map<String,Object> r,String where,String[] args){
            if(where==null)return true;int next=0;
            for(String raw:where.split(" AND ")){String part=raw.trim();boolean not=part.contains("<>");String[] bits=part.split(not?"<>":"=");String expected=bits[1].equals("?")?args[next++]:bits[1];boolean same=Objects.equals(String.valueOf(r.get(bits[0])),expected);if(not?same:!same)return false;}
            return true;
        }
        @Override public Cursor query(Uri uri,String[] projection,String where,String[] args,String sort){
            List<Map<String,Object>> selected=new ArrayList<>();
            if(uri.toString().endsWith("/product")){selected.add(row("pid",1L));}
            else if(uri.toString().endsWith("/beosettings")){
                String key=args[0];if(settings.containsKey(key))selected.add(row("key",key,"current_value_text",settings.get(key)));
            }else{
                for(Map<String,Object> r:rows)if(matches(r,where,args))selected.add(new HashMap<>(r));
                if(sort!=null)selected.sort((x,y)->Long.compare(((Number)x.get("sid")).longValue(),((Number)y.get("sid")).longValue()));
            }
            return new Cursor(){int at=-1;public boolean moveToFirst(){at=0;return at<selected.size();}public boolean moveToNext(){return ++at<selected.size();}Object value(int i){return selected.get(at).get(projection[i]);}public String getString(int i){Object v=value(i);return v==null?null:v.toString();}public int getInt(int i){return ((Number)value(i)).intValue();}public long getLong(int i){return ((Number)value(i)).longValue();}public boolean isNull(int i){return value(i)==null;}public void close(){}};
        }
        @Override public Uri insert(Uri uri,ContentValues values){Map<String,Object> r=new HashMap<>(values);r.put("sid",sid++);rows.add(r);writes++;return uri;}
        @Override public int update(Uri uri,ContentValues values,String where,String[] args){
            if(uri.toString().endsWith("/beosettings")){settings.put(args[0],(String)values.get("current_value_text"));settingsWrites++;return 1;}
            int n=0;for(Map<String,Object> r:rows)if(matches(r,where,args)){r.putAll(values);n++;}writes+=n;return n;
        }
        @Override public int delete(Uri uri,String where,String[] args){if(uri.toString().endsWith("/beosettings")){return settings.remove(args[0])==null?0:1;}int n=rows.size();rows.removeIf(r->matches(r,where,args));writes+=n-rows.size();return n-rows.size();}
    }
    static final class Helper extends SupportService {
        int publications,sourceOpens,failedPublications;
        Helper(MemoryProvider provider,SharedPreferences storage,AlarmManager alarms){resolver=provider;prefs=storage;alarm=alarms;nativeService=new Object();productId=TV;productRow=1;worker=new Handler();}
        @Override void bindNative(){}@Override void bindPower(){}
        @Override int ordinal(String name){for(int i=0;i<ShortcutCatalog.TYPES.length;i++)if(ShortcutCatalog.TYPES[i].equals(name))return ShortcutCatalog.ORDINALS[i];throw new AssertionError(name);}
        @Override void publish(){publications++;if(failedPublications>0){failedPublications--;publicationPending=true;}else publicationPending=false;}
        @Override void startSource(String s){sourceOpens++;throw new AssertionError("Maintenance opened a source");}
        @Override void completeSource(String s){sourceOpens++;throw new AssertionError("Maintenance changed playback");}
        @Override public void startActivity(Intent i){throw new AssertionError("Maintenance opened an app");}
    }
    static JSONObject config(){
        JSONArray entries=new JSONArray();int i=0;
        for(String id:new String[]{A,B,C}){boolean music=++i==3;entries.put(new JSONObject().put("id",id).put("name",music?"Audio":"App "+i).put("kind",music?"app":"hdmi").put("target",music?"org.example.audio":"HDMI2").put("slot",i-1).put("source_list",music?"music":"tv"));}
        return new JSONObject().put("owner","aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa").put("revision","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb").put("tv",TV).put("entries",entries).put("order",new JSONObject().put("tv",new JSONArray().put(A).put(B).put("HDMI2")).put("music",new JSONArray().put(C).put("LINE_IN")));
    }
    public static void main(String[] args)throws Exception{
        MemoryProvider provider=new MemoryProvider();SharedPreferences storage=new SharedPreferences();AlarmManager alarms=new AlarmManager();
        Helper helper=new Helper(provider,storage,alarms);ControlProvider.write(helper,"config",config());String saved=storage.getString("config","");helper.onCreate();
        check(alarms.type==AlarmManager.ELAPSED_REALTIME,"check must never wake a sleeping TV");
        check(alarms.interval==60000 && alarms.at>SystemClock.now,"maintenance is delayed, inexact and repeating");
        PendingIntent survivingAlarm=alarms.scheduled;SourceMaintenance.schedule(helper);
        check(survivingAlarm==alarms.scheduled,"repeated scheduling must not multiply alarms");
        helper.receive(new Intent(SourceMaintenance.CHECK));
        for(String id:new String[]{A,B,C})check(provider.source(id)!=null,"missing saved shortcut restored: "+id);
        check(helper.publications==1,"restored catalog published to remote");
        check(provider.source("HDMI2").get("sid").equals(10L),"active HDMI position retained during playback");
        check(SourceOrderPlan.group(new SourceOrder(helper,SupportService.SOURCES,1).rows(),1,3).get(0).source.equals(C),"inactive MUSIC order repairs even when the active TV input would move");
        check(provider.source("FOREIGN").get("sid").equals(200L),"other product untouched");
        check(ControlProvider.read(helper,"status","{}").getBoolean("source_order_deferred"),"deferred order is reported instead of interrupting playback");
        check(storage.getString("config","").equals(saved),"repair retains revision, names, targets and saved order");
        int writes=provider.writes,settingWrites=provider.settingsWrites,commits=storage.commits;
        helper.receive(new Intent(SourceMaintenance.CHECK));
        check(provider.writes==writes && provider.settingsWrites==settingWrites,"healthy check performs no native writes");
        check(storage.commits==commits,"healthy check does not rewrite preferences to flash");
        helper.failedPublications=1;helper.publish();int retry=helper.publications;
        helper.maintainSources();check(helper.publications==retry+1 && !helper.publicationPending,"failed remote publication retries even when the native table is already healthy");
        check(provider.writes==writes,"publication retry does not rewrite native sources");
        provider.removeOwned(); // No observer notification, as with the firmware's bulk refresh.
        new StartReceiver().onReceive(helper,survivingAlarm.intent);
        check(helper.starts.size()==1 && helper.starts.get(0).target==SupportService.class,"alarm restarts only the existing support service");
        helper.receive(helper.starts.get(0));
        for(String id:new String[]{A,B,C})check(provider.source(id)!=null,"silent table replacement repaired without observer");
        Helper restarted=new Helper(provider,storage,alarms);provider.removeOwned();restarted.onCreate();restarted.receive(new Intent(SourceMaintenance.CHECK));
        check(provider.source(A)!=null && storage.getString("config","").equals(saved),"fresh process recovers from persisted configuration");
        check(alarms.scheduled==survivingAlarm,"ordinary process death retains one alarm identity");
        provider.source(A).put("is_use",0);provider.source(A).put("signal_sensed",0);restarted.maintainSources();
        check(provider.source(A).get("is_use").equals(1) && provider.source(A).get("signal_sensed").equals(1),"owned visibility flags repaired");
        provider.rows.remove(provider.source(B));provider.rows.add(row("sid",300L,"source_pid",1L,"source_name","OCCUPIED","source_type",60,"category",1,"is_use",1,"is_active",0));writes=provider.writes;
        restarted.maintainSources();
        check(provider.source(B)==null && provider.source("OCCUPIED")!=null && provider.writes==writes,"alias conflict is refused before any native writes");
        check(ControlProvider.read(restarted,"status","{}").getString("state").equals("attention"),"conflict remains visible");
        provider.rows.remove(provider.source("OCCUPIED"));restarted.maintainSources();
        check(provider.source(B)!=null && ControlProvider.read(restarted,"status","{}").getString("state").equals("ready"),"later check recovers transient registration failure");
        provider.rows.remove(provider.source(A));restarted.gate.phase=LaunchGate.Phase.WAITING;writes=provider.writes;restarted.maintainSources();
        check(provider.source(A)==null && provider.writes==writes,"background repair waits for an in-flight source start");
        restarted.gate.phase=LaunchGate.Phase.IDLE;
        Intent refresh=new Intent("refresh").putExtra("request",new JSONObject().put("operation","cccccccccccccccccccccccccccccccc").toString());
        restarted.receive(refresh);check(provider.source(A)!=null,"manual Refresh repairs, not just reads, missing sources");
        int published=restarted.publications;restarted.receive(refresh);check(restarted.publications==published+1,"manual Refresh republishes an unchanged catalog");
        provider.source("HDMI2").put("is_active",0);provider.source(C).put("is_active",1);restarted.maintainSources();
        List<SourceOrderPlan.Row> tv=SourceOrderPlan.group(new SourceOrder(restarted,SupportService.SOURCES,1).rows(),1,1);
        check(tv.get(0).source.equals(A) && tv.get(1).source.equals(B) && tv.get(2).source.equals("HDMI2"),"saved TV order restored once another list is active");
        check(!ControlProvider.read(restarted,"status","{}").getBoolean("source_order_deferred"),"deferred message clears after safe ordering repair");
        check(restarted.sourceOpens==0 && helper.sourceOpens==0 && WebhookClient.sends==0,"no source open, webhook, pause, wake or Home Assistant action during maintenance");
        Build.VERSION.SDK_INT=28;SourceMaintenance.schedule(restarted);check((alarms.scheduled.flags&PendingIntent.FLAG_IMMUTABLE)!=0,"newer Android alarm is immutable");
        System.out.println("PASS: "+checks+" real helper/provider recovery checks");
    }
}
