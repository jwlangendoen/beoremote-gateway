package nl.beoremote.tvhelper;
/** Native route lifecycle without Android or household devices. */
public final class LaunchGateTest {
    static void check(boolean v){if(!v)throw new AssertionError();}
    public static void main(String[] args){
        ShortcutCatalog.ALL=new ShortcutCatalog.Entry[]{new ShortcutCatalog.Entry("BGW_123456789abc","hdmi","HDMI1"),new ShortcutCatalog.Entry("BGW_abcdef123456","app","org.example.player")};
        LaunchGate gate=new LaunchGate();check(!gate.begin("HDMI2",true,0));check(!gate.begin("BGW_123456789abc",false,0));
        check(gate.begin("BGW_123456789abc",true,0));long generation=gate.generation;
        check(gate.next(generation,0,"HDMI1",true,true)==LaunchGate.Next.COMMIT_SHORTCUT);
        check(gate.next(generation,1,"HDMI1",true,true)==LaunchGate.Next.WAIT);
        gate.completed("BGW_123456789abc",true);
        check(gate.next(generation,2,"BGW_123456789abc",true,false)==LaunchGate.Next.RESTORE_TARGET);
        check(gate.next(generation,3,"HDMI1",true,true)==LaunchGate.Next.WAIT);
        gate.completed("HDMI1",true);check(gate.next(generation,4,"HDMI1",true,true)==LaunchGate.Next.SEND_REQUEST);
        gate.delivered(4);check(gate.begin("BGW_123456789abc",true,5));check(!gate.requestWebhook);
        gate.cancel();check(!gate.valid(generation,6));
        check(gate.begin("BGW_abcdef123456",true,10));check(gate.target.equals("BGW_abcdef123456"));generation=gate.generation;
        check(gate.next(generation,600,"HDMI2",true,true)==LaunchGate.Next.START_TARGET);
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
        check(gate.begin("BGW_123456789abc",true,1000));generation=gate.generation;check(!gate.valid(generation,46000));
        // A native wake can take over twenty seconds. Do not compete with the
        // firmware's remembered source, even when HDMI still appears active.
        gate.cancel();check(gate.begin("BGW_123456789abc",true,100000));generation=gate.generation;
        check(gate.next(generation,100500,"HDMI1",false,true)==LaunchGate.Next.WAIT);
        check(gate.next(generation,109000,"SPOTIFY",false,false)==LaunchGate.Next.WAIT);
        check(gate.delay(109000)==150); // No one-millisecond polling during wake.
        check(gate.next(generation,121000,"SPOTIFY",true,false)==LaunchGate.Next.START_TARGET);
        check(gate.deadline==129000); // A separate, bounded handoff budget.
        check(gate.next(generation,121100,"HDMI1",true,false)==LaunchGate.Next.WAIT);
        check(gate.next(generation,121200,"HDMI1",true,true)==LaunchGate.Next.SEND_REQUEST);
        // A new source selection while waking must still cancel the old request.
        gate.cancel();check(gate.begin("BGW_123456789abc",true,200000));generation=gate.generation;
        gate.selected("HDMI3",true);check(!gate.valid(generation,220000));
        check(gate.next(generation,220001,"HDMI3",true,true)==LaunchGate.Next.NONE);
        // No power confirmation: never start HDMI or send a delayed HA action.
        gate.cancel();check(gate.begin("BGW_123456789abc",true,300000));generation=gate.generation;
        check(gate.next(generation,344999,"SPOTIFY",false,false)==LaunchGate.Next.WAIT);
        check(gate.next(generation,345000,"SPOTIFY",false,false)==LaunchGate.Next.NONE);
        // A stalled target handoff remains bounded even after a slow wake.
        gate.cancel();check(gate.begin("BGW_123456789abc",true,400000));generation=gate.generation;
        check(gate.next(generation,430000,"SPOTIFY",true,false)==LaunchGate.Next.START_TARGET);
        check(gate.next(generation,438000,"SPOTIFY",true,false)==LaunchGate.Next.NONE);
        // Exit ownership is independent of the 25-second launch-cancellation window.
        ShortcutCatalog.Entry netflix=new ShortcutCatalog.Entry("BGW_123456789abc","hdmi","HDMI1","player-a");
        ShortcutCatalog.Entry youtube=new ShortcutCatalog.Entry("BGW_abcdef123456","hdmi","HDMI1","player-a");
        ShortcutCatalog.ALL=new ShortcutCatalog.Entry[]{netflix,youtube};
        gate.playbackDispatched(youtube,100);
        check(gate.takePause("TUNEIN",true,100,false)==null); // Stale queued event.
        check(gate.takePause(netflix.source,true,101,false)==null); // App on same input.
        check(gate.takePause("HDMI1",true,102,false)==null); // Native handoff on same input.
        check(gate.takePause("TUNEIN",true,100000,false)==youtube); // Radio, even much later.
        check(gate.takePause("APPLICATION",true,100001,false)==null); // Once only.
        gate.playbackDispatched(netflix,200000);
        check(gate.takePause("SPOTIFY",true,200001,false)==netflix);
        gate.playbackDispatched(netflix,300000);
        check(gate.takePause("",true,300001,true)==netflix); // Standby pauses without waking.
        gate.rememberPlayback("HDMI1",400000); // Restored helper / direct HDMI selection.
        check(gate.takePause("HDMI2",true,400001,false)!=null);
        gate.rememberPlayback("HDMI1",500000);
        check(gate.takePause("HDMI1",false,500001,false)!=null); // Another product.
        ShortcutCatalog.Entry ambiguous=new ShortcutCatalog.Entry("BGW_000000000000","hdmi","HDMI1","other-player");
        ShortcutCatalog.ALL=new ShortcutCatalog.Entry[]{netflix,ambiguous};
        gate.rememberPlayback("HDMI1",600000);
        check(gate.takePause("TUNEIN",true,600001,false)==null); // Do not guess a device.
        ShortcutCatalog.Entry legacy=new ShortcutCatalog.Entry("BGW_000000000000","hdmi","HDMI1");
        gate.playbackDispatched(legacy,700000);
        check(gate.takePause("TUNEIN",true,700001,false)==null); // Old callbacks cannot receive exit events.
        System.out.println("TV helper: identities, HDMI handoff, app routing, duplicates, cancellation and expiry passed.");
    }
}
class ShortcutCatalog {
    static Entry[] ALL;
    static final class Entry {final String source,kind,target,pauseKey;final boolean cancelLaunch=true;Entry(String s,String k,String t){this(s,k,t,"");}Entry(String s,String k,String t,String p){source=s;kind=k;target=t;pauseKey=p;}}
    static Entry forSource(String s){for(Entry e:ALL)if(e.source.equals(s))return e;return null;}
}
