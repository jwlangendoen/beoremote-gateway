package nl.beoremote.tvhelper;
import java.util.*;

/** Exercise position writes and every interruption boundary without Android devices. */
public final class SourceOrderTest {
    static void check(boolean value){if(!value)throw new AssertionError();}
    static SourceOrderPlan.Row row(long sid,long product,String name,int type,int category){return new SourceOrderPlan.Row(sid,product,name,type,category,true);}
    static final class Store implements SourceOrderTransaction.Store {
        List<SourceOrderPlan.Row> rows=new ArrayList<>(Arrays.asList(row(1,7,"HDMI1",10,1),row(2,7,"BGW_123456789abc",12,1),row(3,7,"RADIO",43,3),row(4,7,"MUSIC",44,3),row(-810000,99,"OTHER_TV",10,1)));
        SourceOrderTransaction.Journal journal;int writes,failAt=-1;boolean failCleanup;
        public List<SourceOrderPlan.Row> rows(){return new ArrayList<>(rows);}
        public SourceOrderTransaction.Journal journal(){return journal;}
        public void save(SourceOrderTransaction.Journal j){if(j==null&&failCleanup)throw new IllegalStateException("cleanup interrupted");journal=j;}
        public void move(SourceOrderPlan.Row expected,long from,long to){
            if(writes++==failAt)throw new IllegalStateException("interrupted");
            for(SourceOrderPlan.Row r:rows)if(r.sid==to)throw new AssertionError("collision");
            for(int i=0;i<rows.size();i++){SourceOrderPlan.Row r=rows.get(i);if(r.product==expected.product&&r.source.equals(expected.source)&&r.type==expected.type&&r.sid==from){rows.set(i,row(to,r.product,r.source,r.type,r.category));return;}}
            throw new IllegalStateException("identity changed");
        }
        long sid(String name){for(SourceOrderPlan.Row r:rows)if(r.source.equals(name))return r.sid;throw new AssertionError();}
    }
    static Map<Integer,List<String>> order(){Map<Integer,List<String>> order=new HashMap<>();order.put(1,Arrays.asList("BGW_123456789abc","HDMI1"));order.put(3,Arrays.asList("MUSIC","RADIO"));return order;}
    public static void main(String[] args){
        String oldRevision="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",nextRevision="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
        Store store=new Store();List<SourceOrderPlan.Move> plan=SourceOrderPlan.plan(store.rows(),7,order(),"");
        check(plan.size()==4);check(plan.get(0).temporary!=-810000);
        new SourceOrderTransaction(store,7).begin(nextRevision,plan);
        check(store.sid("BGW_123456789abc")==1&&store.sid("HDMI1")==2&&store.sid("MUSIC")==3&&store.sid("RADIO")==4);
        new SourceOrderTransaction(store,7).recover(nextRevision);check(store.journal==null);
        check(store.sid("OTHER_TV")==-810000);
        check(SourceOrderPlan.plan(store.rows(),7,order(),"").isEmpty());
        Store cleanup=new Store();new SourceOrderTransaction(cleanup,7).begin(nextRevision,SourceOrderPlan.plan(cleanup.rows(),7,order(),""));cleanup.failCleanup=true;
        try{new SourceOrderTransaction(cleanup,7).recover(nextRevision);throw new AssertionError();}catch(IllegalStateException expected){}
        check(cleanup.sid("HDMI1")==2&&cleanup.journal!=null);cleanup.failCleanup=false;
        new SourceOrderTransaction(cleanup,7).recover(nextRevision);check(cleanup.sid("HDMI1")==2&&cleanup.journal==null);
        // Failure before or after every one of the eight position writes must recover.
        for(int interruption=0;interruption<=8;interruption++){
            Store fault=new Store();fault.failAt=interruption;
            try{new SourceOrderTransaction(fault,7).begin(nextRevision,SourceOrderPlan.plan(fault.rows(),7,order(),""));}catch(IllegalStateException expected){}
            fault.failAt=-1;new SourceOrderTransaction(fault,7).recover(oldRevision);
            check(fault.sid("HDMI1")==1&&fault.sid("BGW_123456789abc")==2&&fault.sid("RADIO")==3&&fault.sid("MUSIC")==4&&fault.sid("OTHER_TV")==-810000);
            check(fault.journal==null);
        }
        Store active=new Store();try{SourceOrderPlan.plan(active.rows(),7,order(),"HDMI1");throw new AssertionError();}catch(IllegalStateException expected){}
        try{SourceOrderPlan.exact(active.rows(),7,1,Arrays.asList("HDMI1","HDMI1"));throw new AssertionError();}catch(IllegalStateException expected){}
        try{SourceOrderPlan.exact(active.rows(),7,1,Arrays.asList("HDMI1","OTHER_TV"));throw new AssertionError();}catch(IllegalStateException expected){}
        SourceOrderPlan.exact(active.rows(),7,1,Arrays.asList("BGW_123456789abc","HDMI1"));
        // Recovery must refuse an occupied original position rather than overwrite it.
        Store collision=new Store();new SourceOrderTransaction(collision,7).begin(nextRevision,SourceOrderPlan.plan(collision.rows(),7,order(),""));
        collision.rows.removeIf(r->r.source.equals("HDMI1"));collision.rows.add(row(99,7,"HDMI1",10,1));collision.rows.add(row(2,99,"FOREIGN",10,1));
        try{new SourceOrderTransaction(collision,7).recover(oldRevision);throw new AssertionError();}catch(IllegalStateException expected){}
        check(collision.sid("FOREIGN")==2&&collision.journal!=null);
        Store changed=new Store();new SourceOrderTransaction(changed,7).begin(nextRevision,SourceOrderPlan.plan(changed.rows(),7,order(),""));
        changed.rows.removeIf(r->r.source.equals("HDMI1"));changed.rows.add(row(2,7,"HDMI1",10,3));
        int writes=changed.writes;
        try{new SourceOrderTransaction(changed,7).recover(oldRevision);throw new AssertionError();}catch(IllegalStateException expected){}
        check(changed.writes==writes&&changed.journal!=null);
        // A newly discovered source follows the retained relative order.
        Store added=new Store();added.rows.add(row(5,7,"NEW",15,1));Map<Integer,List<String>> remembered=order();remembered.get(1).set(0,"REMOVED");
        List<SourceOrderPlan.Move> updated=SourceOrderPlan.plan(added.rows(),7,remembered,"");check(!updated.isEmpty());
        System.out.println("Source ordering: MUSIC/TV separation, existing positions, active source, collisions and every interruption boundary passed.");
    }
}
