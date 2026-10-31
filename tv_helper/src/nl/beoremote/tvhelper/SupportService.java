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
public class SupportService extends Service {
    static final String TAG="BeoremoteSupport";
    // Process-local, bounded and free of callbacks, product IDs and app labels.
    // A status read can inspect a failure long after the logcat buffer rolled over.
    static volatile String launchDiagnostics="{\"events\":[]}";
    final ArrayDeque<JSONObject> launchEvents=new ArrayDeque<>();
    volatile boolean publicationPending=true;
    static final Uri SOURCES=Uri.parse("content://com.bang_olufsen.sourcecontrol.provider.SourceControlProvider/source");
    static final Uri PRODUCTS=Uri.parse("content://com.bang_olufsen.sourcecontrol.provider.SourceControlProvider/product");
    static final Uri SETTINGS=Uri.parse("content://com.bang_olufsen.settings.provider.BeoProvider/beosettings");
    final Handler main=new Handler();final LaunchGate gate=new LaunchGate();
    HandlerThread thread;Handler worker;Object nativeService,powerService;Class<?> nativeApi,powerApi;String productId;long productRow,configuredAt;boolean bound,powerBound,remoteBound,closed,scheduled,inventoryReady,orderDeferred;Intent pending;ContentObserver observer;int bindAttempts,powerAttempts,remoteGeneration;
    final ServiceConnection nativeConnection=new ServiceConnection(){
        public void onServiceConnected(ComponentName n,IBinder b){worker.post(()->{try{
            nativeApi=Class.forName("com.bang_olufsen.sourcecontrol.aidl.ISourceControlService");nativeService=Class.forName(nativeApi.getName()+"$Stub").getMethod("asInterface",IBinder.class).invoke(null,b);
            productId=(String)nativeApi.getMethod("getLocalProductId").invoke(nativeService);
            if(productId==null||!productId.matches("[0-9]{4}\\.[0-9]+\\.[0-9]+@products\\.bang-olufsen\\.com"))throw new Exception("identity");
            try(Cursor c=getContentResolver().query(PRODUCTS,new String[]{"pid"},"product_id=?",new String[]{productId},null)){if(c==null||!c.moveToFirst())throw new Exception("product");productRow=c.getLong(0);}
            JSONObject config=config();ShortcutCatalog.ALL=ShortcutCatalog.parse(config);if(config.has("tv")&&!productId.equals(config.getString("tv")))throw new Exception("wrong TV");
            if(pending!=null){Intent p=pending;pending=null;receive(p);}else reconcile(config,config);gate.rememberPlayback(activeSource(),SystemClock.elapsedRealtime());capabilities();if(publicationPending)publish();
        }catch(Exception|LinkageError e){nativeService=null;ShortcutCatalog.ALL=new ShortcutCatalog.Entry[0];gate.cancel();failed("TV source support is unavailable on this firmware.");}});}
        public void onServiceDisconnected(ComponentName n){worker.post(()->{nativeService=null;gate.cancel();});}
    };
    final ServiceConnection powerConnection=new ServiceConnection(){
        public void onServiceConnected(ComponentName n,IBinder b){worker.post(()->{try{powerApi=Class.forName("com.bang_olufsen.powercontrol.aidl.IPowerControlService");powerService=Class.forName(powerApi.getName()+"$Stub").getMethod("asInterface",IBinder.class).invoke(null,b);}catch(Exception|LinkageError e){powerService=null;}});}
        public void onServiceDisconnected(ComponentName n){worker.post(()->powerService=null);}
    };
    final ServiceConnection remoteConnection=new ServiceConnection(){
        public void onServiceConnected(ComponentName n,IBinder b){worker.post(()->{try{Class<?> a=Class.forName("com.bang_olufsen.beobt.aidl.IBeoSettingsChange");Object s=Class.forName(a.getName()+"$Stub").getMethod("asInterface",IBinder.class).invoke(null,b);a.getMethod("onSourceListChanged").invoke(s);publicationPending=false;}catch(Exception|LinkageError ignored){}finally{main.post(()->{if(remoteBound){unbindService(remoteConnection);remoteBound=false;}});}});}
        public void onServiceDisconnected(ComponentName n){}
    };
    JSONObject config()throws JSONException{return ControlProvider.read(this,"config","{\"entries\":[]}");}
    @Override public void onCreate(){super.onCreate();thread=new HandlerThread("beoremote-support");thread.start();worker=new Handler(thread.getLooper());
        SourceMaintenance.schedule(this);
        try{JSONObject s=ControlProvider.read(this,"status","{}");if("working".equals(s.optString("state"))){s.put("state","attention");s.put("error","An interrupted change needs to be checked before continuing.");ControlProvider.write(this,"status",s);}}catch(JSONException ignored){}
        observer=new ContentObserver(worker){@Override public void onChange(boolean self){if(scheduled||closed||nativeService==null)return;scheduled=true;worker.postDelayed(()->{scheduled=false;maintainSources();},400);}};
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
    boolean launchInProgress(){return gate.phase!=LaunchGate.Phase.IDLE&&gate.phase!=LaunchGate.Phase.SENT;}
    void maintainSources(){
        if(closed)return;
        // A slow native boot must not exhaust the only binding retry window.
        if(nativeService==null||powerService==null)main.post(()->{if(!bound){bindAttempts=0;bindNative();}if(!powerBound){powerAttempts=0;bindPower();}});
        if(nativeService==null||launchInProgress())return;
        synchronized(ControlProvider.LOCK){try{
            JSONObject c=config();reconcile(c,c);
            JSONObject state=ControlProvider.read(this,"status","{}");
            if("Source registration needs attention.".equals(state.optString("error",""))){state.put("state","ready");state.remove("error");ControlProvider.write(this,"status",state);}
            capabilities();if(publicationPending)publish();
        }catch(Exception|LinkageError e){failed("Source registration needs attention.");}}
    }
    void receive(Intent intent){
        String action=intent.getAction();if(action==null||Intent.ACTION_BOOT_COMPLETED.equals(action)||Intent.ACTION_MY_PACKAGE_REPLACED.equals(action))return;
        if(SourceMaintenance.CHECK.equals(action)){maintainSources();return;}
        if("apply".equals(action)||"test".equals(action)||"refresh".equals(action)){
            if(nativeService==null){pending=intent;return;}
            synchronized(ControlProvider.LOCK){try{
                JSONObject request=new JSONObject(intent.getStringExtra("request"));
                if("apply".equals(action)){
                    JSONObject old=config(),next=request.getJSONObject("config");if(!productId.equals(next.getString("tv")))throw new Exception("identity");
                    SourceOrder ordering=new SourceOrder(this,SOURCES,productRow);ordering.recover(old);
                    if(request.has("order_check"))ordering.check(request.getJSONObject("order_check"),next,activeSource());
                    cancelLaunch("",false,SystemClock.elapsedRealtime(),true);gate.cancel();configuredAt=SystemClock.elapsedRealtime();
                    JSONObject attempt=ControlProvider.read(this,"attempt","{\"entries\":[]}");
                    JSONObject previous=union(old,attempt);ControlProvider.write(this,"attempt",next);
                    try{reconcile(next,previous);ControlProvider.write(this,"config",next);ordering.recover(next);ShortcutCatalog.ALL=ShortcutCatalog.parse(next);gate.rememberPlayback(activeSource(),SystemClock.elapsedRealtime());ControlProvider.write(this,"attempt",new JSONObject().put("entries",new JSONArray()));}
                    catch(Exception error){
                        // A cleanup failure after commit must not undo committed native order.
                        if(!next.getString("revision").equals(config().optString("revision",""))){try{reconcile(old,union(next,attempt));ControlProvider.write(this,"attempt",new JSONObject().put("entries",new JSONArray()));}catch(Exception rollback){failed("Source change failed. Restore the previous setup before continuing.");}}
                        else ShortcutCatalog.ALL=ShortcutCatalog.parse(next);
                        throw error;
                    }
                }else if("refresh".equals(action)){
                    // Firmware can replace its table without notifying ContentObservers.
                    // Refresh repairs saved registrations and republishes even an unchanged list.
                    if(launchInProgress())throw new Exception("source start in progress");
                    JSONObject current=config();reconcile(current,current);publish();inventoryReady=false;
                }else{
                    if(ShortcutCatalog.forSource(request.getString("id"))==null)throw new Exception("source");
                    startSource(request.getString("id"));
                }
                JSONObject state=ControlProvider.read(this,"status","{}");state.put("state","ready");state.put("operation",request.getString("operation"));state.remove("error");ControlProvider.write(this,"status",state);capabilities();
            }catch(Exception|LinkageError e){failed("source start in progress".equals(e.getMessage())?"A source is starting. Wait a moment, then refresh sources.":"active source position".equals(e.getMessage())?"Switch to another source, then refresh sources before moving the source that is playing.":"The TV change was not confirmed. Check the TV and refresh before trying again.");}}
            return;
        }
        if("beo.intent.action.POWER_STATE_CHANGE".equals(action)){int s=intent.getIntExtra("STATE",-1);if(s==4||s==5||s==6){cancelLaunch("",false,intent.getLongExtra(SourceReceiver.RECEIVED_AT,SystemClock.elapsedRealtime()),true);gate.cancel();}if(s==4||s==5||s==6)pausePlayback("",true,intent.getLongExtra(SourceReceiver.RECEIVED_AT,SystemClock.elapsedRealtime()),true);launchTrace("power_event", "", s);return;}
        try{Object source=intent.getParcelableExtra("source_name_product_id");if(source==null||productId==null)return;String name=(String)source.getClass().getMethod("getName").invoke(source),owner=(String)source.getClass().getMethod("getProductId").invoke(source);boolean local=productId.equals(owner);
            if("beo.intent.action.source_changed".equals(action)){gate.completed(name,local);launchTrace("source_changed",local?name:"other_product",powerState());return;}
            if("beo.intent.action.source_change_begin".equals(action)){
                if(intent.getLongExtra(SourceReceiver.RECEIVED_AT,0)<configuredAt)return;
                cancelLaunch(name,local,intent.getLongExtra(SourceReceiver.RECEIVED_AT,SystemClock.elapsedRealtime()),false);
                pausePlayback(name,local,intent.getLongExtra(SourceReceiver.RECEIVED_AT,SystemClock.elapsedRealtime()),false);
                if(local)gate.rememberPlayback(name,intent.getLongExtra(SourceReceiver.RECEIVED_AT,SystemClock.elapsedRealtime()));
                if(gate.begin(name,local,intent.getLongExtra(SourceReceiver.RECEIVED_AT,SystemClock.elapsedRealtime()))){launchTrace("source_requested",name,powerState());long generation=gate.generation;worker.post(()->advance(generation));}else{gate.selected(name,local);launchTrace("source_selected",local?name:"other_product",powerState());}
            }
        }catch(Exception|LinkageError e){gate.cancel();}
    }
    void cancelLaunch(String name,boolean local,long received,boolean standby){
        ShortcutCatalog.Entry previous=gate.takeCancellation(name,local,received,standby);
        if(previous!=null)try{WebhookClient.send(previous.callback,previous.source,productId,true);}catch(Exception error){Log.w(TAG,"Source cancellation was not confirmed; not retried.");}
    }
    void pausePlayback(String name,boolean local,long received,boolean standby){
        ShortcutCatalog.Entry previous=gate.takePause(name,local,received,standby);
        if(previous!=null)try{WebhookClient.pause(previous.callback,previous.source,productId);launchTrace("pause_delivered",previous.target,powerState());}
        catch(Exception error){launchTrace("pause_failed",previous.target,powerState());Log.w(TAG,"Source pause was not confirmed; not retried.");}
    }
    void advance(long generation){
        if(closed)return;
        boolean expired=generation==gate.generation&&gate.phase!=LaunchGate.Phase.IDLE&&gate.phase!=LaunchGate.Phase.SENT&&SystemClock.elapsedRealtime()>=gate.deadline;
        if(!gate.valid(generation,SystemClock.elapsedRealtime())){if(expired)launchTrace("expired","",powerState());return;}
        try{
            String current=activeSource();boolean on=televisionOn();LaunchGate.Next next=gate.next(generation,SystemClock.elapsedRealtime(),current,on,on&&gate.target.equals(current)&&targetPlaying());
            if(next==LaunchGate.Next.NONE)return;
            if(next!=LaunchGate.Next.WAIT)launchTrace(next.name().toLowerCase(Locale.ROOT),current,powerState());
            if(next==LaunchGate.Next.COMMIT_SHORTCUT||next==LaunchGate.Next.RESTORE_TARGET)completeSource(next==LaunchGate.Next.COMMIT_SHORTCUT?gate.shortcut.source:gate.target);
            else if(next==LaunchGate.Next.START_TARGET)startSource(gate.target);
            else if(next==LaunchGate.Next.SEND_REQUEST||next==LaunchGate.Next.COMPLETE_DUPLICATE){
                if(next==LaunchGate.Next.SEND_REQUEST){ShortcutCatalog.Entry e=gate.shortcut;
                    if("app".equals(e.kind)){Intent launch=launchIntent(e.target);if(launch==null)throw new Exception("app removed");launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);startActivity(launch);}
                    long sentAt=SystemClock.elapsedRealtime();gate.dispatched(sentAt);WebhookClient.send(e.callback,e.source,productId);gate.playbackDispatched(e,sentAt);
                }gate.delivered(SystemClock.elapsedRealtime());launchTrace("delivered",current,powerState());return;
            }
            worker.postDelayed(()->advance(generation),gate.delay(SystemClock.elapsedRealtime()));
        }catch(Exception|LinkageError e){gate.cancel();launchTrace("failed","",powerState());Log.w(TAG,"Source action failed; not retried.");}
    }
    void launchTrace(String event,String source,int power){
        try{
            String safe=source.startsWith("BGW_")?"gateway_shortcut":source.matches("[A-Z][A-Z0-9_]{0,39}")?source:source.isEmpty()?"":"other";
            JSONObject row=new JSONObject().put("at_ms",System.currentTimeMillis()).put("elapsed_ms",SystemClock.elapsedRealtime()).put("event",event).put("phase",gate.phase.name()).put("generation",gate.generation).put("power_state",power).put("source",safe);
            if(launchEvents.size()==64)launchEvents.removeFirst();launchEvents.addLast(row);
            JSONArray rows=new JSONArray();for(JSONObject item:launchEvents)rows.put(item);
            launchDiagnostics=new JSONObject().put("events",rows).toString();
        }catch(JSONException ignored){}
    }
    Intent launchIntent(String pkg){Intent i=getPackageManager().getLeanbackLaunchIntentForPackage(pkg);return i!=null?i:getPackageManager().getLaunchIntentForPackage(pkg);}
    int powerState(){try{return powerService!=null?(Integer)powerApi.getMethod("getCurrentPowerState").invoke(powerService):-1;}catch(Exception e){return -1;}}
    boolean televisionOn(){return powerState()==3;}
    @SuppressWarnings({"rawtypes","unchecked"}) int ordinal(String name)throws Exception{return Enum.valueOf((Class<? extends Enum>)Class.forName("com.bang_olufsen.sourcecontrol.ISourceControl$SourceTypes"),name).ordinal();}
    boolean targetPlaying(){try{String name="app".equals(gate.shortcut.kind)?ShortcutCatalog.TYPES[gate.shortcut.slot]:gate.target;return ((Integer)nativeApi.getMethod("getCurrentSource").invoke(nativeService))==ordinal(name);}catch(Exception e){return false;}}
    void startSource(String name)throws Exception{Class<?> t=Class.forName("com.bang_olufsen.networklink.model.UniqueSourceId");nativeApi.getMethod("startSource",t,int.class).invoke(nativeService,t.getConstructor(String.class,String.class).newInstance(name,productId),0);}
    void completeSource(String name)throws Exception{Class<?> t=Class.forName("com.bang_olufsen.networklink.model.UniqueSourceId");nativeApi.getMethod("sourceChange",t).invoke(nativeService,t.getConstructor(String.class,String.class).newInstance(name,productId));}
    String activeSource(){try(Cursor c=getContentResolver().query(SOURCES,new String[]{"source_name"},"source_pid=? AND is_active=1",new String[]{""+productRow},null)){if(c==null)throw new IllegalStateException("source state unavailable");return c.moveToFirst()?c.getString(0):"";}}
    JSONObject setting(String key)throws JSONException{JSONObject j=new JSONObject().put("exists",false);try(Cursor c=getContentResolver().query(SETTINGS,new String[]{"current_value_text"},"key=?",new String[]{key},null)){if(c==null)throw new JSONException("setting unavailable");if(c.moveToFirst())j.put("exists",true).put("value",c.isNull(0)?JSONObject.NULL:c.getString(0));}return j;}
    void putSetting(String key,String value)throws JSONException{JSONObject before=setting(key);if(before.getBoolean("exists")&&Objects.equals(value,before.isNull("value")?null:before.getString("value")))return;ContentValues v=new ContentValues();v.put("key",key);if(value==null)v.putNull("current_value_text");else v.put("current_value_text",value);getContentResolver().update(SETTINGS,v,"key=?",new String[]{key});JSONObject got=setting(key);if(!got.getBoolean("exists")||!Objects.equals(value,got.isNull("value")?null:got.getString("value")))throw new JSONException("setting");}
    void publish(){publicationPending=true;main.post(()->{if(closed||remoteBound)return;try{
        int generation=++remoteGeneration;
        remoteBound=bindService(new Intent("com.bang_olufsen.beobtremote.BeoBtRemoteService").setComponent(new ComponentName("com.bang_olufsen.beobtremote","com.bang_olufsen.beobtremote.BeoBtRemoteService")),remoteConnection,BIND_AUTO_CREATE);
        if(remoteBound)main.postDelayed(()->{if(remoteBound&&remoteGeneration==generation){unbindService(remoteConnection);remoteBound=false;}},8000);
    }catch(RuntimeException ignored){}});}
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
        for(ShortcutCatalog.Entry e:entries){String where="source_pid=? AND source_name=?";String[] args={""+productRow,e.source};boolean exists;String label=null;int category=-1,inUse=0,sensed=0;
            try(Cursor c=getContentResolver().query(SOURCES,new String[]{"source_type","source_friendly_name","category","is_use","signal_sensed"},where,args,null)){exists=c!=null&&c.moveToFirst();if(exists){if(c.getInt(0)!=e.firmwareOrdinal)throw new Exception("source type");label=c.getString(1);category=c.getInt(2);inUse=c.getInt(3);sensed=c.getInt(4);}}
            String listKey="sourcelist_"+ShortcutCatalog.SUFFIXES[e.slot]+"_beoremote_list";
            String labelKey="sourcelist_"+ShortcutCatalog.SUFFIXES[e.slot]+"_friendly_name";
            if(exists&&e.label.equals(label)&&category==e.category&&inUse==1&&sensed==1&&e.sourceList.equals(setting(listKey).optString("value",""))&&e.label.equals(setting(labelKey).optString("value","")))continue;
            putSetting("sourcelist_"+ShortcutCatalog.SUFFIXES[e.slot]+"_friendly_name",e.label);putSetting(listKey,e.sourceList);
            ContentValues v=new ContentValues();v.put("source_friendly_name",e.label);v.put("category",e.category);v.put("is_use",1);v.put("signal_sensed",1);
            if(exists){if(getContentResolver().update(SOURCES,v,where,args)!=1)throw new Exception("rename");}
            else{v.put("source_pid",productRow);v.put("source_name",e.source);v.put("source_type",e.firmwareOrdinal);v.put("is_active",0);v.put("is_use",1);v.put("profile","");v.put("source_ir_key",0);v.put("signal_sensed",1);v.put("cp_scheme",8);if(getContentResolver().insert(SOURCES,v)==null)throw new Exception("insert");}changed=true;
        }
        orderDeferred=false;
        try{changed|=ordering.apply(next,activeSource());}
        catch(IllegalStateException error){
            // Background repair must keep routing available while a source is playing.
            // Explicit edits still require the active source to keep its position.
            if(!"active source position".equals(error.getMessage())||!next.optString("revision","").equals(config().optString("revision","")))throw error;
            orderDeferred=true;
        }
        if(next.optString("revision","").equals(config().optString("revision","")))ordering.recover(next);
        ControlProvider.write(this,"originals",originals);if(changed||recovered)publish();
    }
    void capabilities()throws Exception{synchronized(ControlProvider.LOCK){
        JSONObject state=ControlProvider.read(this,"status","{}");if(!"working".equals(state.optString("state"))&&!"attention".equals(state.optString("state")))state.put("state","ready");state.put("tv",productId);state.put("version","0.1.6");state.put("source_lists",new JSONArray().put("tv").put("music"));state.put("source_wake_wait",true).put("source_pause",true).put("source_repair",true).put("source_order_deferred",orderDeferred);state.put("source_order",true).put("catalog",new SourceOrder(this,SOURCES,productRow).catalog());
        JSONArray slots=new JSONArray(),inputs=new JSONArray(),apps=new JSONArray();
        boolean legacyTrusted=false;try{PackageInfo info=getPackageManager().getPackageInfo("nl.johan.horizonappletv",PackageManager.GET_SIGNATURES);byte[] hash=java.security.MessageDigest.getInstance("SHA-256").digest(info.signatures[0].toByteArray());StringBuilder hex=new StringBuilder();for(byte b:hash)hex.append(String.format(java.util.Locale.ROOT,"%02x",b&255));legacyTrusted=info.versionCode>=108&&"6ce62474011f288bed0a822e0c8587a83c05d3dec19226a19e6002e619979921".equals(hex.toString());}catch(Exception ignored){}
        int legacySources=0;Set<String> legacyNames=new HashSet<>(Arrays.asList("ATV_NETFLIX","ATV_YOUTUBE","ATV_PLUS","ATV_PRIME","ATV_SVT","ATV_HBO","ATV_F1_TV","ATV_NLZIET"));
        try(Cursor c=getContentResolver().query(SOURCES,new String[]{"source_name"},"source_pid=?",new String[]{""+productRow},null)){if(c!=null)while(c.moveToNext())if(legacyNames.contains(c.getString(0)))legacySources++;}
        state.put("legacy_trusted",legacyTrusted).put("legacy_sources",legacySources).put("source_cancel",true);
        for(int i=0;i<8;i++){if(ordinal(ShortcutCatalog.TYPES[i])!=ShortcutCatalog.ORDINALS[i])throw new Exception("firmware");boolean free;try(Cursor c=getContentResolver().query(SOURCES,new String[]{"source_name"},"source_pid=? AND source_type=?",new String[]{""+productRow,""+ShortcutCatalog.ORDINALS[i]},null)){free=c!=null&&!c.moveToFirst();}slots.put(new JSONObject().put("slot",i).put("free",free));}
        try(Cursor c=getContentResolver().query(SOURCES,new String[]{"source_name","source_friendly_name"},"source_pid=?",new String[]{""+productRow},null)){if(c!=null)while(c.moveToNext())if(c.getString(0).matches("HDMI[1-4]"))inputs.put(new JSONObject().put("id",c.getString(0)).put("name",c.getString(1)));}
        if(inventoryReady&&state.has("apps"))apps=state.getJSONArray("apps");
        else{PackageManager pm=getPackageManager();int count=0;for(ApplicationInfo a:pm.getInstalledApplications(0)){if(count>=256)break;if(launchIntent(a.packageName)==null)continue;String label=a.loadLabel(pm).toString();apps.put(new JSONObject().put("package",a.packageName).put("name",label.substring(0,Math.min(label.length(),128))).put("system",(a.flags&ApplicationInfo.FLAG_SYSTEM)!=0));count++;}inventoryReady=true;}
        state.put("slots",slots).put("inputs",inputs).put("apps",apps);ControlProvider.write(this,"status",state);
    }}
    void failed(String message){synchronized(ControlProvider.LOCK){try{JSONObject s=ControlProvider.read(this,"status","{}");s.put("state","attention").put("error",message);ControlProvider.write(this,"status",s);}catch(Exception ignored){}}Log.w(TAG,message);}
    @Override public void onDestroy(){closed=true;main.removeCallbacksAndMessages(null);getContentResolver().unregisterContentObserver(observer);if(bound)unbindService(nativeConnection);if(powerBound)unbindService(powerConnection);if(remoteBound)unbindService(remoteConnection);worker.removeCallbacksAndMessages(null);thread.quitSafely();super.onDestroy();}
}
