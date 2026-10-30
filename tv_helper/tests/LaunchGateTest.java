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
        check(gate.begin("BGW_123456789abc",true,1000));generation=gate.generation;check(!gate.valid(generation,9000));
        System.out.println("TV helper: identities, HDMI handoff, app routing, duplicates, cancellation and expiry passed.");
    }
}
class ShortcutCatalog {
    static Entry[] ALL;
    static final class Entry {final String source,kind,target;Entry(String s,String k,String t){source=s;kind=k;target=t;}}
    static Entry forSource(String s){for(Entry e:ALL)if(e.source.equals(s))return e;return null;}
}
