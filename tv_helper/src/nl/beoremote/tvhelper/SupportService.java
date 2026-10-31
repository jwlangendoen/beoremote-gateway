package nl.beoremote.tvhelper;

import android.app.Service;
import android.content.*;
import android.content.pm.*;
import android.database.*;
import android.net.Uri;
import android.os.*;
import android.util.Log;
import org.json.*;
import java.util.*;

/** Idle native observer. Registration never selects a source or launches an app. */
public final class SupportService extends Service {
    static final String TAG="BeoremoteSupport";
    static final Uri SOURCES=Uri.parse("content://com.bang_olufsen.sourcecontrol.provider.SourceControlProvider/source");
    static final Uri PRODUCTS=Uri.parse("content://com.bang_olufsen.sourcecontrol.provider.SourceControlProvider/product");
    static final Uri SETTINGS=Uri.parse("content://com.bang_olufsen.settings.provider.BeoProvider/beosettings");
    final Handler main=new Handler();final LaunchGate gate=new LaunchGate();
    HandlerThread thread;Handler worker;Object nativeService,powerService;Class<?> nativeApi,powerApi;String productId;long productRow,configuredAt;boolean bound,powerBound,remoteBound,closed,scheduled,inventoryReady;Intent pending;ContentObserver observer;int bindAttempts,powerAttempts;
    final ServiceConnection nativeConnection=new ServiceConnection(){
        public void onServiceConnected(ComponentName n,IBinder b){worker.post(()->{try{
            nativeApi=Class.forName("com.bang_olufsen.sourcecontrol.aidl.ISourceControlService");nativeService=Class.forName(nativeApi.getName()+"$Stub").getMethod("asInterface",IBinder.class).invoke(null,b);
            productId=(String)nativeApi.getMethod("getLocalProductId").invoke(nativeService);
            if(productId==null||!productId.matches("[0-9]{4}\\.[0-9]+\\.[0-9]+@products\\.bang-olufsen\\.com"))throw new Exception("identity");
            try(Cursor c=getContentResolver().query(PRODUCTS,new String[]{"pid"},"product_id=?",new String[]{productId},null)){if(c==null||!c.moveToFirst())throw new Exception("product");productRow=c.getLong(0);}
            JSONObject config=config();ShortcutCatalog.ALL=ShortcutCatalog.parse(config);if(config.has("tv")&&!productId.equals(config.getString("tv")))throw new Exception("wrong TV");
            if(pending!=null){Intent p=pending;pending=null;receive(p);}else reconcile(config,config);capabilities();
        }catch(Exception|LinkageError e){nativeService=null;ShortcutCatalog.ALL=new ShortcutCatalog.Entry[0];gate.cancel();failed("TV source support is unavailable on this firmware.");}});}
        public void onServiceDisconnected(ComponentName n){worker.post(()->{nativeService=null;gate.cancel();});}
    };
    final ServiceConnection powerConnection=new ServiceConnection(){
        public void onServiceConnected(ComponentName n,IBinder b){worker.post(()->{try{powerApi=Class.forName("com.bang_olufsen.powercontrol.aidl.IPowerControlService");powerService=Class.forName(powerApi.getName()+"$Stub").getMethod("asInterface",IBinder.class).invoke(null,b);}catch(Exception|LinkageError e){powerService=null;}});}
        public void onServiceDisconnected(ComponentName n){worker.post(()->powerService=null);}
    };
    final ServiceConnection remoteConnection=new ServiceConnection(){
        public void onServiceConnected(ComponentName n,IBinder b){worker.post(()->{try{Class<?> a=Class.forName("com.bang_olufsen.beobt.aidl.IBeoSettingsChange");Object s=Class.forName(a.getName()+"$Stub").getMethod("asInterface",IBinder.class).invoke(null,b);a.getMethod("onSourceListChanged").invoke(s);}catch(Exception|LinkageError ignored){}finally{main.post(()->{if(remoteBound){unbindService(remoteConnection);remoteBound=false;}});}});}
        public void onServiceDisconnected(ComponentName n){}
    };
    JSONObject config()throws JSONException{return ControlProvider.read(this,"config","{\"entries\":[]}");}
    @Override public void onCreate(){super.onCreate();thread=new HandlerThread("beoremote-support");thread.start();worker=new Handler(thread.getLooper());
        try{JSONObject s=ControlProvider.read(this,"status","{}");if("working".equals(s.optString("state"))){s.put("state","attention");s.put("error","An interrupted change needs to be checked before continuing.");ControlProvider.write(this,"status",s);}}catch(JSONException ignored){}
        observer=new ContentObserver(worker){@Override public void onChange(boolean self){if(scheduled||closed||nativeService==null)return;scheduled=true;worker.postDelayed(()->{scheduled=false;try{JSONObject c=config();reconcile(c,c);capabilities();}catch(Exception|LinkageError e){failed("Source registration needs attention.");}},400);}};
        getContentResolver().registerContentObserver(SOURCES,true,observer);
        bindNative();bindPower();
    }
    void bindNative(){
        if(closed||bound)return;Intent i=new Intent("bang_olufsen.intent.action.sourcecontrol").setComponent(new ComponentName("com.bang_olufsen.powercontroller","com.bang_olufsen.powercontroller.PowerControlService"));
        try{bound=bindService(i,nativeConnection,BIND_AUTO_CREATE);}catch(RuntimeException ignored){}
        if(!bound&&++bindAttempts<10)main.postDelayed(this::bindNative,1000);
        if(bound)main.postDelayed(()->{if(!closed&&bound&&nativeService==null){unbindService(nativeConnection);bound=false;if(++bindAttempts<10)bindNative();else failed("The native TV service could not be reached.");}},8000);
    }
    void bindPower(){
        if(closed||powerBound)return;Intent i=new Intent("android.intent.action.WAKEUP").setComponent(new ComponentName("com.bang_olufsen.powercontroller","com.bang_olufsen.powercontroller.PowerControlService"));
        try{powerBound=bindService(i,powerConnection,BIND_AUTO_CREATE);}catch(RuntimeException ignored){}
        if(!powerBound&&++powerAttempts<10)main.postDelayed(this::bindPower,1000);
    }

    @Override public int onStartCommand(Intent intent,int flags,int id){if(intent!=null)worker.post(()->receive(intent));return START_STICKY;}
    @Override public IBinder onBind(Intent i){return null;}
    void receive(Intent intent){
        String action=intent.getAction();if(action==null||Intent.ACTION_BOOT_COMPLETED.equals(action)||Intent.ACTION_MY_PACKAGE_REPLACED.equals(action))return;
        if("apply".equals(action)||"test".equals(action)||"refresh".equals(action)){
            if(nativeService==null){pending=intent;return;}
            synchronized(ControlProvider.LOCK){try{
                JSONObject request=new JSONObject(intent.getStringExtra("request"));
                if("apply".equals(action)){
                    JSONObject old=config(),next=request.getJSONObject("config");if(!productId.equals(next.getString("tv")))throw new Exception("identity");
                    SourceOrder ordering=new SourceOrder(this,SOURCES,productRow);ordering.recover(old);
                    if(request.has("order_check"))ordering.check(request.getJSONObject("order_check"),next,activeSource());
                    gate.cancel();configuredAt=SystemClock.elapsedRealtime();
                    JSONObject attempt=ControlProvider.read(this,"attempt","{\"entries\":[]}");
                    JSONObject previous=union(old,attempt);ControlProvider.write(this,"attempt",next);
                    try{reconcile(next,previous);ControlProvider.write(this,"config",next);ordering.recover(next);ShortcutCatalog.ALL=ShortcutCatalog.parse(next);ControlProvider.write(this,"attempt",new JSONObject().put("entries",new JSONArray()));}
                    catch(Exception error){
                        // A cleanup failure after commit must not undo committed native order.
                        if(!next.getString("revision").equals(config().optString("revision",""))){try{reconcile(old,union(next,attempt));ControlProvider.write(this,"attempt",new JSONObject().put("entries",new JSONArray()));}catch(Exception rollback){failed("Source change failed. Restore the previous setup before continuing.");}}
                        else ShortcutCatalog.ALL=ShortcutCatalog.parse(next);
                        throw error;
                    }
                }else if("refresh".equals(action)){
                    inventoryReady=false;
                }else{
                    if(ShortcutCatalog.forSource(request.getString("id"))==null)throw new Exception("source");
                    startSource(request.getString("id"));
                }
                JSONObject state=ControlProvider.read(this,"status","{}");state.put("state","ready");state.put("operation",request.getString("operation"));state.remove("error");ControlProvider.write(this,"status",state);capabilities();
            }catch(Exception|LinkageError e){failed("active source position".equals(e.getMessage())?"Switch to another source, then refresh sources before moving the source that is playing.":"The TV change was not confirmed. Check the TV and refresh before trying again.");}}
            return;
        }
        if("beo.intent.action.POWER_STATE_CHANGE".equals(action)){int s=intent.getIntExtra("STATE",-1);if(s==4||s==5||s==6)gate.cancel();return;}
        try{Object source=intent.getParcelableExtra("source_name_product_id");if(source==null||productId==null)return;String name=(String)source.getClass().getMethod("getName").invoke(source),owner=(String)source.getClass().getMethod("getProductId").invoke(source);boolean local=productId.equals(owner);
            if("beo.intent.action.source_changed".equals(action)){gate.completed(name,local);return;}
            if("beo.intent.action.source_change_begin".equals(action)){
                if(intent.getLongExtra(SourceReceiver.RECEIVED_AT,0)<configuredAt)return;
                if(gate.begin(name,local,intent.getLongExtra(SourceReceiver.RECEIVED_AT,SystemClock.elapsedRealtime()))){long generation=gate.generation;worker.post(()->advance(generation));}else gate.selected(name,local);
            }
        }catch(Exception|LinkageError e){gate.cancel();}
    }
    void advance(long generation){
        if(closed||!gate.valid(generation,SystemClock.elapsedRealtime()))return;
        try{
            String current=activeSource();LaunchGate.Next next=gate.next(generation,SystemClock.elapsedRealtime(),current,gate.target.equals(current)&&televisionOn()&&targetPlaying());
            if(next==LaunchGate.Next.NONE)return;
            if(next==LaunchGate.Next.COMMIT_SHORTCUT||next==LaunchGate.Next.RESTORE_TARGET)completeSource(next==LaunchGate.Next.COMMIT_SHORTCUT?gate.shortcut.source:gate.target);
            else if(next==LaunchGate.Next.START_TARGET)startSource(gate.target);
            else if(next==LaunchGate.Next.SEND_REQUEST||next==LaunchGate.Next.COMPLETE_DUPLICATE){
                if(next==LaunchGate.Next.SEND_REQUEST){ShortcutCatalog.Entry e=gate.shortcut;
                    if("app".equals(e.kind)){Intent launch=launchIntent(e.target);if(launch==null)throw new Exception("app removed");launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);startActivity(launch);}
                    WebhookClient.send(e.callback,e.source,productId);
                }gate.delivered(SystemClock.elapsedRealtime());return;
            }
            worker.postDelayed(()->advance(generation),gate.delay(SystemClock.elapsedRealtime()));
        }catch(Exception|LinkageError e){gate.cancel();Log.w(TAG,"Source action failed; not retried.");}
    }
    Intent launchIntent(String pkg){Intent i=getPackageManager().getLeanbackLaunchIntentForPackage(pkg);return i!=null?i:getPackageManager().getLaunchIntentForPackage(pkg);}
    boolean televisionOn(){try{return powerService!=null&&((Integer)powerApi.getMethod("getCurrentPowerState").invoke(powerService))==3;}catch(Exception e){return false;}}
    @SuppressWarnings({"rawtypes","unchecked"}) int ordinal(String name)throws Exception{return Enum.valueOf((Class<? extends Enum>)Class.forName("com.bang_olufsen.sourcecontrol.ISourceControl$SourceTypes"),name).ordinal();}
    boolean targetPlaying(){try{String name="app".equals(gate.shortcut.kind)?ShortcutCatalog.TYPES[gate.shortcut.slot]:gate.target;return ((Integer)nativeApi.getMethod("getCurrentSource").invoke(nativeService))==ordinal(name);}catch(Exception e){return false;}}
    void startSource(String name)throws Exception{Class<?> t=Class.forName("com.bang_olufsen.networklink.model.UniqueSourceId");nativeApi.getMethod("startSource",t,int.class).invoke(nativeService,t.getConstructor(String.class,String.class).newInstance(name,productId),0);}
    void completeSource(String name)throws Exception{Class<?> t=Class.forName("com.bang_olufsen.networklink.model.UniqueSourceId");nativeApi.getMethod("sourceChange",t).invoke(nativeService,t.getConstructor(String.class,String.class).newInstance(name,productId));}
    String activeSource(){try(Cursor c=getContentResolver().query(SOURCES,new String[]{"source_name"},"source_pid=? AND is_active=1",new String[]{""+productRow},null)){if(c==null)throw new IllegalStateException("source state unavailable");return c.moveToFirst()?c.getString(0):"";}}
    JSONObject setting(String key)throws JSONException{JSONObject j=new JSONObject().put("exists",false);try(Cursor c=getContentResolver().query(SETTINGS,new String[]{"current_value_text"},"key=?",new String[]{key},null)){if(c==null)throw new JSONException("setting unavailable");if(c.moveToFirst())j.put("exists",true).put("value",c.isNull(0)?JSONObject.NULL:c.getString(0));}return j;}
    void putSetting(String key,String value)throws JSONException{ContentValues v=new ContentValues();v.put("key",key);if(value==null)v.putNull("current_value_text");else v.put("current_value_text",value);getContentResolver().update(SETTINGS,v,"key=?",new String[]{key});JSONObject got=setting(key);if(!got.getBoolean("exists")||!Objects.equals(value,got.isNull("value")?null:got.getString("value")))throw new JSONException("setting");}
    void publish(){main.post(()->{if(closed||remoteBound)return;try{remoteBound=bindService(new Intent("com.bang_olufsen.beobtremote.BeoBtRemoteService").setComponent(new ComponentName("com.bang_olufsen.beobtremote","com.bang_olufsen.beobtremote.BeoBtRemoteService")),remoteConnection,BIND_AUTO_CREATE);}catch(RuntimeException ignored){}});}
    JSONObject union(JSONObject first,JSONObject second)throws JSONException{
        JSONObject result=new JSONObject(first.toString());JSONArray rows=new JSONArray();Set<String> seen=new HashSet<>();
        for(JSONObject list:new JSONObject[]{first,second}){JSONArray a=list.getJSONArray("entries");for(int i=0;i<a.length();i++){JSONObject row=a.getJSONObject(i);if(seen.add(row.getString("id")))rows.put(row);}}
        return result.put("entries",rows);
    }
    void reconcile(JSONObject next,JSONObject previous)throws Exception{
        SourceOrder ordering=new SourceOrder(this,SOURCES,productRow);boolean recovered=ordering.recover(config());
        ShortcutCatalog.Entry[] entries=ShortcutCatalog.parse(next);JSONArray previousRows=previous.getJSONArray("entries");ShortcutCatalog.Entry[] old=new ShortcutCatalog.Entry[previousRows.length()];for(int i=0;i<old.length;i++)old[i]=new ShortcutCatalog.Entry(previousRows.getJSONObject(i));Set<String> nextIds=new HashSet<>();for(ShortcutCatalog.Entry e:entries)nextIds.add(e.source);
        JSONObject originals=ControlProvider.read(this,"originals","{}");
        // Validate the complete plan and save originals before the first native write.
        for(ShortcutCatalog.Entry e:entries){
            if(ordinal(ShortcutCatalog.TYPES[e.slot])!=e.firmwareOrdinal)throw new Exception("firmware");
            if("app".equals(e.kind)&&launchIntent(e.target)==null)throw new Exception("launchable app");
            if("hdmi".equals(e.kind)){try(Cursor c=getContentResolver().query(SOURCES,new String[]{"source_name"},"source_pid=? AND source_name=?",new String[]{""+productRow,e.target},null)){if(c==null||!c.moveToFirst())throw new Exception("input");}}
            try(Cursor c=getContentResolver().query(SOURCES,new String[]{"source_name"},"source_pid=? AND source_type=? AND source_name<>?",new String[]{""+productRow,""+e.firmwareOrdinal,e.source},null)){if(c==null||c.moveToFirst())throw new Exception("slot occupied or unavailable");}
            if(!originals.has(""+e.slot)){JSONObject saved=new JSONObject();for(String suffix:new String[]{"friendly_name","beoremote_list"}){String key="sourcelist_"+ShortcutCatalog.SUFFIXES[e.slot]+"_"+suffix;saved.put(key,setting(key));}originals.put(""+e.slot,saved);}
        }
        for(ShortcutCatalog.Entry e:old)if(!nextIds.contains(e.source)&&e.source.equals(activeSource()))throw new Exception("active source");
        ControlProvider.write(this,"originals",originals);
        boolean changed=false;
        for(ShortcutCatalog.Entry e:old)if(!nextIds.contains(e.source)){
            int deleted=getContentResolver().delete(SOURCES,"source_pid=? AND source_name=? AND source_type=?",new String[]{""+productRow,e.source,""+e.firmwareOrdinal});changed|=deleted>0;
            if(originals.has(""+e.slot)){JSONObject saved=originals.getJSONObject(""+e.slot);Iterator<String> keys=saved.keys();while(keys.hasNext()){String key=keys.next();JSONObject original=saved.getJSONObject(key);JSONObject current=setting(key);String expected=key.endsWith("friendly_name")?e.label:e.sourceList;
                if(current.getBoolean("exists")&&!expected.equals(current.optString("value","")))throw new Exception("setting changed outside helper");
                if(original.getBoolean("exists"))putSetting(key,original.isNull("value")?null:original.getString("value"));else getContentResolver().delete(SETTINGS,"key=?",new String[]{key});}
                originals.remove(""+e.slot);
            }
        }
        for(ShortcutCatalog.Entry e:entries){String where="source_pid=? AND source_name=?";String[] args={""+productRow,e.source};boolean exists;String label=null;int category=-1;
            try(Cursor c=getContentResolver().query(SOURCES,new String[]{"source_type","source_friendly_name","category"},where,args,null)){exists=c!=null&&c.moveToFirst();if(exists){if(c.getInt(0)!=e.firmwareOrdinal)throw new Exception("source type");label=c.getString(1);category=c.getInt(2);}}
            String listKey="sourcelist_"+ShortcutCatalog.SUFFIXES[e.slot]+"_beoremote_list";
            if(exists&&e.label.equals(label)&&category==e.category&&e.sourceList.equals(setting(listKey).optString("value","")))continue;
            putSetting("sourcelist_"+ShortcutCatalog.SUFFIXES[e.slot]+"_friendly_name",e.label);putSetting(listKey,e.sourceList);
            ContentValues v=new ContentValues();v.put("source_friendly_name",e.label);v.put("category",e.category);
            if(exists){if(getContentResolver().update(SOURCES,v,where,args)!=1)throw new Exception("rename");}
            else{v.put("source_pid",productRow);v.put("source_name",e.source);v.put("source_type",e.firmwareOrdinal);v.put("is_active",0);v.put("is_use",1);v.put("profile","");v.put("source_ir_key",0);v.put("signal_sensed",1);v.put("cp_scheme",8);if(getContentResolver().insert(SOURCES,v)==null)throw new Exception("insert");}changed=true;
        }
        changed|=ordering.apply(next,activeSource());
        if(next.optString("revision","").equals(config().optString("revision","")))ordering.recover(next);
        ControlProvider.write(this,"originals",originals);if(changed||recovered)publish();
    }
    void capabilities()throws Exception{synchronized(ControlProvider.LOCK){
        JSONObject state=ControlProvider.read(this,"status","{}");if(!"working".equals(state.optString("state"))&&!"attention".equals(state.optString("state")))state.put("state","ready");state.put("tv",productId);state.put("version","0.1.2");state.put("source_lists",new JSONArray().put("tv").put("music"));state.put("source_order",true).put("catalog",new SourceOrder(this,SOURCES,productRow).catalog());
        JSONArray slots=new JSONArray(),inputs=new JSONArray(),apps=new JSONArray();
        boolean legacyTrusted=false;try{PackageInfo info=getPackageManager().getPackageInfo("nl.johan.horizonappletv",PackageManager.GET_SIGNATURES);byte[] hash=java.security.MessageDigest.getInstance("SHA-256").digest(info.signatures[0].toByteArray());StringBuilder hex=new StringBuilder();for(byte b:hash)hex.append(String.format(java.util.Locale.ROOT,"%02x",b&255));legacyTrusted=info.versionCode>=108&&"6ce62474011f288bed0a822e0c8587a83c05d3dec19226a19e6002e619979921".equals(hex.toString());}catch(Exception ignored){}
        int legacySources=0;Set<String> legacyNames=new HashSet<>(Arrays.asList("ATV_NETFLIX","ATV_YOUTUBE","ATV_PLUS","ATV_PRIME","ATV_SVT","ATV_HBO","ATV_F1_TV","ATV_NLZIET"));
        try(Cursor c=getContentResolver().query(SOURCES,new String[]{"source_name"},"source_pid=?",new String[]{""+productRow},null)){if(c!=null)while(c.moveToNext())if(legacyNames.contains(c.getString(0)))legacySources++;}
        state.put("legacy_trusted",legacyTrusted).put("legacy_sources",legacySources);
        for(int i=0;i<8;i++){if(ordinal(ShortcutCatalog.TYPES[i])!=ShortcutCatalog.ORDINALS[i])throw new Exception("firmware");boolean free;try(Cursor c=getContentResolver().query(SOURCES,new String[]{"source_name"},"source_pid=? AND source_type=?",new String[]{""+productRow,""+ShortcutCatalog.ORDINALS[i]},null)){free=c!=null&&!c.moveToFirst();}slots.put(new JSONObject().put("slot",i).put("free",free));}
        try(Cursor c=getContentResolver().query(SOURCES,new String[]{"source_name","source_friendly_name"},"source_pid=?",new String[]{""+productRow},null)){if(c!=null)while(c.moveToNext())if(c.getString(0).matches("HDMI[1-4]"))inputs.put(new JSONObject().put("id",c.getString(0)).put("name",c.getString(1)));}
        if(inventoryReady&&state.has("apps"))apps=state.getJSONArray("apps");
        else{PackageManager pm=getPackageManager();int count=0;for(ApplicationInfo a:pm.getInstalledApplications(0)){if(count>=256)break;if(launchIntent(a.packageName)==null)continue;String label=a.loadLabel(pm).toString();apps.put(new JSONObject().put("package",a.packageName).put("name",label.substring(0,Math.min(label.length(),128))).put("system",(a.flags&ApplicationInfo.FLAG_SYSTEM)!=0));count++;}inventoryReady=true;}
        state.put("slots",slots).put("inputs",inputs).put("apps",apps);ControlProvider.write(this,"status",state);
    }}
    void failed(String message){synchronized(ControlProvider.LOCK){try{JSONObject s=ControlProvider.read(this,"status","{}");s.put("state","attention").put("error",message);ControlProvider.write(this,"status",s);}catch(Exception ignored){}}Log.w(TAG,message);}
    @Override public void onDestroy(){closed=true;main.removeCallbacksAndMessages(null);getContentResolver().unregisterContentObserver(observer);if(bound)unbindService(nativeConnection);if(powerBound)unbindService(powerConnection);if(remoteBound)unbindService(remoteConnection);worker.removeCallbacksAndMessages(null);thread.quitSafely();super.onDestroy();}
}
