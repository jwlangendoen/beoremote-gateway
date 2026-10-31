package nl.beoremote.tvhelper;

import org.json.*;

/** Fixed firmware aliases; user data cannot supply ordinals or provider paths. */
final class ShortcutCatalog {
    static final String[] TYPES={"WEBMEDIA","DVD","DVD2","V_AUX","V_AUX2","PC","CAMERA","DTV"};
    static final int[] ORDINALS={12,60,61,62,63,65,64,58};
    static final String[] SUFFIXES={"webmedia","dvd","dvd_2","aux","aux_2","pc","camera","dtv"};
    static volatile Entry[] ALL=new Entry[0];
    static final class Entry {
        final String source,label,kind,target,callback,sourceList,pauseKey; final int slot,firmwareOrdinal,category; final boolean cancelLaunch;
        Entry(JSONObject j) throws JSONException {
            source=j.getString("id");label=j.getString("name");kind=j.getString("kind");target=j.getString("target");slot=j.getInt("slot");callback=j.optString("callback","");
            sourceList=j.optString("source_list","tv");
            cancelLaunch=j.optBoolean("cancel_launch",false);
            pauseKey=j.optString("pause_key", "");
            if(!pauseKey.isEmpty() && (!pauseKey.matches("[a-f0-9]{32}") || !"hdmi".equals(kind) || !cancelLaunch || callback.isEmpty()))throw new JSONException("pause route");
            if(!"tv".equals(sourceList)&&!"music".equals(sourceList))throw new JSONException("source list");
            category="music".equals(sourceList)?3:1;
            if(!source.matches("BGW_[a-f0-9]{12}") || label.trim().length()<1 || label.length()>32 || label.matches("(?s).*[\\p{Cntrl}].*") || slot<0 || slot>=TYPES.length)throw new JSONException("entry");
            if(!"app".equals(kind) && !"hdmi".equals(kind))throw new JSONException("route");
            if("app".equals(kind) && !target.matches("[A-Za-z0-9_]+(?:\\.[A-Za-z0-9_]+)+"))throw new JSONException("package");
            if("hdmi".equals(kind) && !target.matches("HDMI[1-4]"))throw new JSONException("input");
            firmwareOrdinal=ORDINALS[slot];
            if(!callback.isEmpty())WebhookClient.validate(callback);
        }
    }
    static Entry[] parse(JSONObject config) throws JSONException {
        JSONArray array=config.getJSONArray("entries");if(array.length()>8)throw new JSONException("limit");
        Entry[] entries=new Entry[array.length()];java.util.HashSet<String> ids=new java.util.HashSet<>();java.util.HashSet<Integer> slots=new java.util.HashSet<>();
        for(int i=0;i<entries.length;i++){entries[i]=new Entry(array.getJSONObject(i));if(!ids.add(entries[i].source)||!slots.add(entries[i].slot))throw new JSONException("duplicate");}
        return entries;
    }
    static Entry forSource(String name){for(Entry e:ALL)if(e.source.equals(name))return e;return null;}
}
