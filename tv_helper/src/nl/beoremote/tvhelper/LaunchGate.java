package nl.beoremote.tvhelper;

/** Pure request lifecycle; time is monotonic and supplied by the caller. */
final class LaunchGate {
    String target = "";
    static final long REPEAT_GRACE_MS = 1200;
    static final long HANDOFF_DELAY_MS = 500;
    enum Phase { IDLE, WAITING, COMMITTING_SHORTCUT, RESTORING_TARGET, REDIRECTING, SENT }
    enum Next { NONE, WAIT, COMMIT_SHORTCUT, RESTORE_TARGET, START_TARGET, SEND_REQUEST, COMPLETE_DUPLICATE }
    Phase phase = Phase.IDLE;
    long generation;
    long deadline;
    long handoffAt;
    long completedAt;
    boolean requestWebhook;
    boolean direct;
    boolean shortcutConfirmed;
    boolean targetConfirmed;
    ShortcutCatalog.Entry shortcut;

    boolean begin(String name, boolean local, long now) {
        ShortcutCatalog.Entry next = ShortcutCatalog.forSource(name);
        if (!local || next == null) return false;
        if (pending() && next == shortcut) return false;
        // The single worker can receive a queued native event after an HTTP POST
        // finishes. Its arrival time, rather than processing time, identifies a duplicate.
        requestWebhook = !(phase == Phase.SENT && next == shortcut && now <= completedAt + REPEAT_GRACE_MS);
        generation++;
        deadline = now + 8000;
        handoffAt = now + HANDOFF_DELAY_MS;
        phase = Phase.WAITING;
        direct = false;
        shortcutConfirmed = false;
        targetConfirmed = false;
        shortcut = next;
        target = "app".equals(next.kind) ? next.source : next.target;
        return true;
    }

    Next next(long id, long now, String current, boolean televisionOn) {
        if (!valid(id, now)) return Next.NONE;
        if (phase == Phase.WAITING) {
            // A remembered HDMI source while asleep is not an active television.
            // Re-read the source at dispatch time; never use a previous request's state.
            if (target.equals(current) && televisionOn) {
                direct = true;
                phase = Phase.COMMITTING_SHORTCUT;
                return Next.COMMIT_SHORTCUT;
            }
            if (now < handoffAt) return Next.WAIT;
            redirected();
            return Next.START_TARGET;
        }
        if (phase == Phase.COMMITTING_SHORTCUT && shortcutConfirmed && shortcut.source.equals(current)) {
            phase = Phase.RESTORING_TARGET;
            return Next.RESTORE_TARGET;
        }
        if ((phase == Phase.RESTORING_TARGET || phase == Phase.REDIRECTING)
                && (phase == Phase.REDIRECTING || targetConfirmed) && target.equals(current) && televisionOn)
            return requestWebhook ? Next.SEND_REQUEST : Next.COMPLETE_DUPLICATE;
        return Next.WAIT;
    }

    long delay(long now) {
        return phase == Phase.WAITING ? Math.max(1, handoffAt - now)
                : direct ? 50 : 150;
    }

    void selected(String name, boolean local) {
        if (!pending()) return;
        if (local && shortcut != null && shortcut.source.equals(name)) return;
        if (local && target.equals(name)
                && (phase == Phase.REDIRECTING || phase == Phase.RESTORING_TARGET)) return;
        cancel();
    }

    void completed(String name, boolean local) {
        if (!local || !pending()) return;
        if (phase == Phase.COMMITTING_SHORTCUT && shortcut.source.equals(name)) shortcutConfirmed = true;
        if ((phase == Phase.RESTORING_TARGET || phase == Phase.REDIRECTING) && target.equals(name))
            targetConfirmed = true;
    }

    private boolean pending() { return phase != Phase.IDLE && phase != Phase.SENT; }

    boolean valid(long id, long now) {
        if (id != generation || phase == Phase.IDLE || phase == Phase.SENT) return false;
        if (now >= deadline) { cancel(); return false; }
        return true;
    }

    void redirected() { phase = Phase.REDIRECTING; }
    void delivered(long now) { phase = Phase.SENT; completedAt = now; }
    void cancel() { generation++; phase = Phase.IDLE; shortcut = null; }
}
