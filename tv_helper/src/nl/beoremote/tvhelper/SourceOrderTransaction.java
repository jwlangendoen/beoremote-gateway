package nl.beoremote.tvhelper;

import java.util.*;

/** Recoverable position-only writes. A committed config revision decides recovery. */
final class SourceOrderTransaction {
    static final class Journal {
        final String revision; final List<SourceOrderPlan.Move> moves;
        Journal(String r,List<SourceOrderPlan.Move> m){revision=r;moves=m;}
    }
    interface Store {
        List<SourceOrderPlan.Row> rows();
        Journal journal();
        void save(Journal journal);
        void move(SourceOrderPlan.Row row,long from,long to);
    }
    final Store store; final long product;
    SourceOrderTransaction(Store s,long p){store=s;product=p;}
    void begin(String revision,List<SourceOrderPlan.Move> moves){
        if(moves.isEmpty())return;
        if(!revision.matches("[a-f0-9]{32}")||store.journal()!=null)throw new IllegalStateException("order recovery required");
        Journal journal=new Journal(revision,moves);store.save(journal);positions(journal,true);
    }
    boolean recover(String committed){
        Journal journal=store.journal();if(journal==null)return false;
        positions(journal,journal.revision.equals(committed));store.save(null);return true;
    }
    void positions(Journal journal,boolean forward){
        if(journal.moves.size()>256)throw new IllegalStateException("order too large");
        List<SourceOrderPlan.Row> rows=store.rows(),selected=new ArrayList<>();
        Set<String> names=new HashSet<>();Set<Long> targets=new HashSet<>(),used=new HashSet<>();
        for(SourceOrderPlan.Row row:rows)if(!used.add(row.sid))throw new IllegalStateException("duplicate position");
        boolean same=true;
        for(SourceOrderPlan.Move move:journal.moves){
            if(move.row.product!=product||!names.add(move.row.source)||!targets.add(forward?move.target:move.row.sid))throw new IllegalStateException("invalid order journal");
            SourceOrderPlan.Row found=null;
            for(SourceOrderPlan.Row row:rows)if(row.product==product&&row.source.equals(move.row.source)){if(found!=null||row.type!=move.row.type||row.category!=move.row.category||!row.visible)throw new IllegalStateException("source identity changed");found=row;}
            if(found==null)throw new IllegalStateException("source removed during ordering");
            selected.add(found);same&=found.sid==(forward?move.target:move.row.sid);
        }
        for(SourceOrderPlan.Row row:rows)if(targets.contains(row.sid)&&!selected.contains(row))throw new IllegalStateException("order position occupied");
        if(same)return;
        long temporary=-810000;List<Long> staged=new ArrayList<>();
        for(SourceOrderPlan.Row row:selected){while(used.contains(temporary))temporary--;used.add(temporary);store.move(row,row.sid,temporary);staged.add(temporary--);}
        for(int i=0;i<selected.size();i++)store.move(selected.get(i),staged.get(i),forward?journal.moves.get(i).target:journal.moves.get(i).row.sid);
    }
}
