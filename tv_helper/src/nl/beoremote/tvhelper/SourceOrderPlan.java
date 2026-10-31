package nl.beoremote.tvhelper;

import java.util.*;

/** Permute existing positions within each local remote list; keep logical IDs intact. */
final class SourceOrderPlan {
    static final class Row {
        final long sid,product; final String source; final int type,category; final boolean visible;
        Row(long s,long p,String n,int t,int c,boolean v){sid=s;product=p;source=n;type=t;category=c;visible=v;}
    }
    static final class Move {
        final Row row; final long temporary,target;
        Move(Row r,long temp,long to){row=r;temporary=temp;target=to;}
    }
    static final class Repair {
        final List<Move> moves; final boolean deferred;
        Repair(List<Move> m,boolean d){moves=m;deferred=d;}
    }
    static List<Row> group(List<Row> rows,long product,int category){
        List<Row> result=new ArrayList<>();Set<String> names=new HashSet<>();
        for(Row row:rows)if(row.product==product&&row.category==category&&row.visible){
            if(!names.add(row.source))throw new IllegalStateException("duplicate local source");result.add(row);
        }
        Collections.sort(result,(a,b)->Long.compare(a.sid,b.sid));return result;
    }
    static void exact(List<Row> rows,long product,int category,List<String> names){
        Set<String> current=new HashSet<>();for(Row row:group(rows,product,category))current.add(row.source);
        if(names.size()!=current.size()||new HashSet<>(names).size()!=names.size()||!current.equals(new HashSet<>(names)))throw new IllegalStateException("source list changed");
    }
    static List<Move> plan(List<Row> rows,long product,Map<Integer,List<String>> order,String active){
        return plan(rows,product,order,active,false).moves;
    }
    static Repair repair(List<Row> rows,long product,Map<Integer,List<String>> order,String active){
        return plan(rows,product,order,active,true);
    }
    private static Repair plan(List<Row> rows,long product,Map<Integer,List<String>> order,String active,boolean deferActive){
        if(rows.size()>2048)throw new IllegalStateException("source catalog too large");
        List<Move> moves=new ArrayList<>();Set<Long> used=new HashSet<>();for(Row row:rows)if(!used.add(row.sid))throw new IllegalStateException("duplicate position");
        long temp=-810000;boolean deferred=false;
        for(int category:new int[]{1,3}){
            List<String> desired=order.get(category);if(desired==null)continue;
            List<Row> current=group(rows,product,category),sorted=new ArrayList<>();Map<String,Row> byName=new HashMap<>();
            for(Row row:current)byName.put(row.source,row);
            Set<String> seen=new HashSet<>();
            // Removed sources drop out; newly discovered sources follow the saved order.
            for(String name:desired){if(!seen.add(name))throw new IllegalStateException("duplicate order");Row row=byName.remove(name);if(row!=null)sorted.add(row);}
            for(Row row:current)if(byName.containsKey(row.source))sorted.add(row);
            boolean activeMoves=false;
            for(int i=0;i<sorted.size();i++)if(sorted.get(i).source.equals(active)&&sorted.get(i).sid!=current.get(i).sid)activeMoves=true;
            if(activeMoves){if(!deferActive)throw new IllegalStateException("active source position");deferred=true;continue;}
            for(int i=0;i<sorted.size();i++){
                Row row=sorted.get(i);long target=current.get(i).sid;if(row.sid==target)continue;
                while(used.contains(temp))temp--;used.add(temp);moves.add(new Move(row,temp--,target));
            }
        }
        return new Repair(moves,deferred);
    }
}
