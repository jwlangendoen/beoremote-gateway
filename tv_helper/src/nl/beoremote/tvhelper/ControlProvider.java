package nl.beoremote.tvhelper;
import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.os.*;
import android.util.Base64;
import org.json.*;

/** Every call requires shell/system DUMP permission, including reads. */
public final class ControlProvider extends ContentProvider {
    static final Object LOCK=new Object();
    static final String PREFS="support";
    @Override public boolean onCreate(){return true;}
    static JSONObject read(Context c,String key,String fallback)throws JSONException{return new JSONObject(c.getSharedPreferences(PREFS,0).getString(key,fallback));}
    static void write(Context c,String key,JSONObject value){
        String encoded=value.toString();android.content.SharedPreferences prefs=c.getSharedPreferences(PREFS,0);
        // A healthy periodic check must not rewrite unchanged status/originals to flash.
        if(encoded.equals(prefs.getString(key,null)))return;
        if(!prefs.edit().putString(key,encoded).commit())throw new IllegalStateException("storage");
    }
    @Override public Bundle call(String method,String argument,Bundle extras){
        getContext().enforceCallingPermission("android.permission.DUMP","ADB management only");
        JSONObject result=new JSONObject();
        synchronized(LOCK){boolean reserved=false;try{
            if("status".equals(method)){
                result=read(getContext(),"status","{\"state\":\"starting\"}");
                result.put("launch_diagnostics",new JSONObject(SupportService.launchDiagnostics));
                JSONObject cfg=read(getContext(),"config","{\"entries\":[]}");JSONArray rows=new JSONArray();JSONArray entries=cfg.getJSONArray("entries");
                for(int i=0;i<entries.length();i++){JSONObject copy=new JSONObject(entries.getJSONObject(i).toString());copy.remove("callback");rows.put(copy);}
                result.put("entries",rows);result.put("revision",cfg.optString("revision",""));result.put("owner",cfg.optString("owner",""));
                getContext().startService(new Intent(getContext(),SupportService.class));
            }else if("backup".equals(method)){
                result.put("config",read(getContext(),"config","{\"entries\":[]}"));result.put("originals",read(getContext(),"originals","{}"));
            }else if("apply".equals(method)||"test".equals(method)||"refresh".equals(method)){
                if(argument==null||argument.length()>48000)throw new JSONException("size");
                JSONObject request=new JSONObject(new String(Base64.decode(argument,Base64.DEFAULT),"UTF-8"));
                JSONObject state=read(getContext(),"status","{}");if("working".equals(state.optString("state")))throw new JSONException("busy");
                String op=request.getString("operation");if(!op.matches("[a-f0-9]{32}"))throw new JSONException("operation");
                if("apply".equals(method)){
                    JSONObject current=read(getContext(),"config","{\"entries\":[]}");
                    if(!current.optString("revision","").equals(request.getString("expected")))throw new JSONException("revision");
                    JSONObject next=request.getJSONObject("config");
                    if(!next.getString("owner").matches("[a-f0-9]{32}")||(!current.optString("owner","").isEmpty()&&!current.getString("owner").equals(next.getString("owner"))))throw new JSONException("owner");
                    if(!next.getString("revision").matches("[a-f0-9]{32}"))throw new JSONException("revision");ShortcutCatalog.parse(next);
                }else if("test".equals(method)&&!request.getString("id").matches("BGW_[a-f0-9]{12}"))throw new JSONException("entry");
                state.put("state","working");state.put("operation",op);state.remove("error");write(getContext(),"status",state);reserved=true;
                getContext().startService(new Intent(getContext(),SupportService.class).setAction(method).putExtra("request",request.toString()));result.put("operation",op);
            }else throw new JSONException("method");
        }catch(Exception error){try{if(reserved){JSONObject state=read(getContext(),"status","{}");state.put("state","attention").put("error","The operation could not be started. Refresh TV Support.");write(getContext(),"status",state);}result=new JSONObject().put("error","TV support rejected this operation: "+error.getClass().getSimpleName());}catch(JSONException ignored){}}}
        Bundle response=new Bundle();response.putString("result",Base64.encodeToString(result.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8),Base64.NO_WRAP));return response;
    }
    @Override public Cursor query(Uri u,String[]p,String s,String[]a,String o){throw new UnsupportedOperationException();}
    @Override public String getType(Uri u){return null;}
    @Override public Uri insert(Uri u,ContentValues v){throw new UnsupportedOperationException();}
    @Override public int update(Uri u,ContentValues v,String s,String[]a){throw new UnsupportedOperationException();}
    @Override public int delete(Uri u,String s,String[]a){throw new UnsupportedOperationException();}
}
