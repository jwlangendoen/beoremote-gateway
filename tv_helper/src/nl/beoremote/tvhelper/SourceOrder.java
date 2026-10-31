package nl.beoremote.tvhelper;

import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import org.json.*;
import java.util.*;

/** Native adapter: only the selected product's position column may be changed. */
final class SourceOrder implements SourceOrderTransaction.Store {
    final Context context;final Uri uri;final long product;final SourceOrderTransaction transaction;
    SourceOrder(Context c,Uri u,long p){context=c;uri=u;product=p;transaction=new SourceOrderTransaction(this,p);}
    public List<SourceOrderPlan.Row> rows(){
        List<SourceOrderPlan.Row> rows=new ArrayList<>();
        try(Cursor c=context.getContentResolver().query(uri,new String[]{"sid","source_pid","source_name","source_type","category","is_use"},null,null,"sid ASC")){
            if(c==null)throw new IllegalStateException("source order unavailable");
            while(c.moveToNext()){if(rows.size()>=2048)throw new IllegalStateException("catalog too large");rows.add(new SourceOrderPlan.Row(c.getLong(0),c.getLong(1),c.getString(2),c.getInt(3),c.getInt(4),c.getInt(5)==1));}
        }return rows;
    }
    public SourceOrderTransaction.Journal journal(){
        try{
            JSONObject j=ControlProvider.read(context,"order_attempt","{}");if(!j.has("revision"))return null;
            String revision=j.getString("revision");if(!revision.matches("[a-f0-9]{32}"))throw new JSONException("revision");
            JSONArray array=j.getJSONArray("moves");if(array.length()>256)throw new JSONException("limit");List<SourceOrderPlan.Move> moves=new ArrayList<>();
            for(int i=0;i<array.length();i++){JSONObject m=array.getJSONObject(i);String name=m.getString("source");if(name.isEmpty()||name.length()>128)throw new JSONException("source");moves.add(new SourceOrderPlan.Move(new SourceOrderPlan.Row(m.getLong("from"),product,name,m.getInt("type"),m.getInt("category"),true),0,m.getLong("to")));}
            return new SourceOrderTransaction.Journal(revision,moves);
        }catch(JSONException e){throw new IllegalStateException("order recovery unavailable",e);}
    }
    public void save(SourceOrderTransaction.Journal journal){
        try{JSONObject data=new JSONObject();if(journal!=null){JSONArray moves=new JSONArray();for(SourceOrderPlan.Move m:journal.moves)moves.put(new JSONObject().put("source",m.row.source).put("type",m.row.type).put("category",m.row.category).put("from",m.row.sid).put("to",m.target));data.put("revision",journal.revision).put("moves",moves);}ControlProvider.write(context,"order_attempt",data);}
        catch(JSONException e){throw new IllegalStateException("order journal",e);}
    }
    public void move(SourceOrderPlan.Row row,long from,long to){
        if(row.product!=product)throw new IllegalStateException("wrong product");
        ContentValues values=new ContentValues();values.put("sid",to);
        if(context.getContentResolver().update(uri,values,"source_pid=? AND source_name=? AND source_type=? AND sid=? AND category=? AND is_use=?",new String[]{""+product,row.source,""+row.type,""+from,""+row.category,"1"})!=1)throw new IllegalStateException("source changed during ordering");
    }
    static List<String> names(JSONArray array)throws JSONException{
        if(array.length()>256)throw new JSONException("order limit");List<String> names=new ArrayList<>();
        for(int i=0;i<array.length();i++){String name=array.getString(i);if(name.isEmpty()||name.length()>128)throw new JSONException("source");names.add(name);}return names;
    }
    Map<Integer,List<String>> desired(JSONObject config)throws JSONException{
        Map<Integer,List<String>> result=new HashMap<>();JSONObject order=config.optJSONObject("order");
        if(order!=null){Iterator<String> keys=order.keys();while(keys.hasNext()){String key=keys.next();if(!key.equals("tv")&&!key.equals("music"))throw new JSONException("list");result.put(key.equals("music")?3:1,names(order.getJSONArray(key)));}}return result;
    }
    void check(JSONObject expected,JSONObject next,String active)throws JSONException{
        String group=expected.getString("source_list");if(!group.equals("tv")&&!group.equals("music"))throw new JSONException("list");
        List<String> ids=names(expected.getJSONArray("ids"));List<SourceOrderPlan.Row> rows=rows();
        SourceOrderPlan.exact(rows,product,group.equals("music")?3:1,ids);
        if(!ids.equals(desired(next).get(group.equals("music")?3:1)))throw new JSONException("order mismatch");
        SourceOrderPlan.plan(rows,product,desired(next),active);
    }
    boolean recover(JSONObject committed){return transaction.recover(committed.optString("revision",""));}
    boolean apply(JSONObject next,String active)throws JSONException{
        List<SourceOrderPlan.Move> moves=SourceOrderPlan.plan(rows(),product,desired(next),active);transaction.begin(next.optString("revision",""),moves);return !moves.isEmpty();
    }
    SourceOrderPlan.Repair repair(JSONObject next,String active)throws JSONException{
        SourceOrderPlan.Repair plan=SourceOrderPlan.repair(rows(),product,desired(next),active);
        transaction.begin(next.optString("revision",""),plan.moves);return plan;
    }
    JSONArray catalog()throws JSONException{
        JSONArray array=new JSONArray();
        try(Cursor c=context.getContentResolver().query(uri,new String[]{"source_name","source_friendly_name","category","is_use"},"source_pid=?",new String[]{""+product},"sid ASC")){
            if(c==null)throw new JSONException("source catalog unavailable");
            while(c.moveToNext())if(c.getInt(3)==1&&(c.getInt(2)==1||c.getInt(2)==3)){
                if(array.length()>=256)throw new JSONException("catalog too large");
                String name=c.getString(0),label=c.isNull(1)||c.getString(1).isEmpty()?name:c.getString(1);
                array.put(new JSONObject().put("id",name).put("name",label).put("source_list",c.getInt(2)==3?"music":"tv"));
            }
        }return array;
    }
}
