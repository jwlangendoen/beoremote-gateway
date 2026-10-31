package nl.beoremote.tvhelper;
/** Native route lifecycle without Android or household devices. */
public final class LaunchGateTest {
    static void check(boolean v){if(!v)throw new AssertionError();}
    public static void main(String[] args){
        ShortcutCatalog.ALL=new ShortcutCatalog.Entry[]{new ShortcutCatalog.Entry("BGW_123456789abc","hdmi","HDMI1"),new ShortcutCatalog.Entry("BGW_abcdef123456","app","org.example.player")};
        LaunchGate gate=new LaunchGate();check(!gate.begin("HDMI2",true,0));check(!gate.begin("BGW_123456789abc",false,0));
        check(gate.begin("BGW_123456789abc",true,0));long generation=gate.generation;
        check(gate.next(generation,0,"HDMI1",true)==LaunchGate.Next.COMMIT_SHORTCUT);
        check(gate.next(generation,1,"HDMI1",true)==LaunchGate.Next.WAIT);
        gate.completed("BGW_123456789abc",true);
        check(gate.next(generation,2,"BGW_123456789abc",false)==LaunchGate.Next.RESTORE_TARGET);
        check(gate.next(generation,3,"HDMI1",true)==LaunchGate.Next.WAIT);
        gate.completed("HDMI1",true);check(gate.next(generation,4,"HDMI1",true)==LaunchGate.Next.SEND_REQUEST);
        gate.delivered(4);check(gate.begin("BGW_123456789abc",true,5));check(!gate.requestWebhook);
        gate.cancel();check(!gate.valid(generation,6));
        check(gate.begin("BGW_abcdef123456",true,10));check(gate.target.equals("BGW_abcdef123456"));generation=gate.generation;
        check(gate.next(generation,600,"HDMI2",true)==LaunchGate.Next.START_TARGET);
        gate.selected("HDMI3",true);check(!gate.valid(generation,601));
        gate.cancel();gate.begin("BGW_123456789abc",true,10000);gate.dispatched(10001);gate.delivered(10001);
        check(gate.takeCancellation("HDMI1",true,10000,false)==null); // Queued handoff event.
        check(gate.takeCancellation("BGW_123456789abc",true,10500,false)==null); // Held key.
        check(gate.takeCancellation("BGW_abcdef123456",true,10501,false)!=null); // Another shortcut, same HDMI possible.
        check(gate.takeCancellation("HDMI2",true,10502,false)==null); // Once only.
        gate.cancel();gate.begin("BGW_123456789abc",true,20000);gate.dispatched(20001);gate.delivered(20001);
        check(gate.takeCancellation("",true,20100,true)!=null); // Standby.
        gate.cancel();gate.begin("BGW_123456789abc",true,30000);gate.dispatched(30001);gate.delivered(30001);
        check(gate.takeCancellation("HDMI1",false,30100,false)!=null); // Another product.
        gate.cancel();gate.begin("BGW_123456789abc",true,40000);gate.dispatched(40001);gate.delivered(40001);
        check(gate.takeCancellation("HDMI1",true,66000,false)==null); // No late cancellation.
        gate.cancel();gate.begin("BGW_123456789abc",true,70000);gate.dispatched(70001);gate.delivered(70001);
        check(gate.takeCancellation("HDMI1",true,71500,false)!=null); // Explicitly choosing underlying input cancels.
        gate.cancel();gate.begin("BGW_123456789abc",true,80000);gate.dispatched(80001);gate.delivered(81501);
        check(gate.takeCancellation("HDMI2",true,80500,false)!=null); // Choice received while HTTP was in flight.
        check(gate.begin("BGW_123456789abc",true,1000));generation=gate.generation;check(!gate.valid(generation,9000));
        System.out.println("TV helper: identities, HDMI handoff, app routing, duplicates, cancellation and expiry passed.");
    }
}
class ShortcutCatalog {
    static Entry[] ALL;
    static final class Entry {final String source,kind,target;final boolean cancelLaunch=true;Entry(String s,String k,String t){source=s;kind=k;target=t;}}
    static Entry forSource(String s){for(Entry e:ALL)if(e.source.equals(s))return e;return null;}
}
