package nl.beoremote.tvhelper;

/** Pure request lifecycle; time is monotonic and supplied by the caller. */
final class LaunchGate {
    String target = "";
    static final long REPEAT_GRACE_MS = 1200;
    static final long HANDOFF_DELAY_MS = 500;
    static final long WAKE_TIMEOUT_MS = 45000;
    static final long HANDOFF_TIMEOUT_MS = 8000;
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
    ShortcutCatalog.Entry deliveredShortcut;
    long deliveredAt;

    ShortcutCatalog.Entry playbackShortcut;
    long playbackAt;

    // Setup/restart may observe an input without replaying its launch webhook.
    // Adopt only an unambiguous configured player on that input.
    void rememberPlayback(String name, long now) {
        ShortcutCatalog.Entry selected = ShortcutCatalog.forSource(name);
        String input = selected != null ? selected.target : name;
        ShortcutCatalog.Entry found = null;
        for (ShortcutCatalog.Entry entry : ShortcutCatalog.ALL) {
            if (!"hdmi".equals(entry.kind) || !entry.target.equals(input) || entry.pauseKey.isEmpty()) continue;
            if (found != null && !found.pauseKey.equals(entry.pauseKey)) { playbackShortcut = null; return; }
            found = entry;
        }
        playbackShortcut = found;
        playbackAt = now;
    }
    void playbackDispatched(ShortcutCatalog.Entry entry, long now) {
        playbackShortcut = !entry.pauseKey.isEmpty() && "hdmi".equals(entry.kind) ? entry : null;
        playbackAt = now;
    }
    ShortcutCatalog.Entry takePause(String name, boolean local, long received, boolean standby) {
        if (playbackShortcut == null || received <= playbackAt) return null;
        ShortcutCatalog.Entry next = local ? ShortcutCatalog.forSource(name) : null;
        String input = next != null && "hdmi".equals(next.kind) ? next.target : name;
        if (!standby && local && playbackShortcut.target.equals(input)) return null;
        ShortcutCatalog.Entry previous = playbackShortcut;
        playbackShortcut = null;
        return previous;
    }

    // Keep the HA wake request cancellable after the native HDMI handoff ended.
    ShortcutCatalog.Entry takeCancellation(String name, boolean local, long received, boolean standby) {
        if (deliveredShortcut == null || received <= deliveredAt) return null;
        if (!standby && local && deliveredShortcut.source.equals(name)
                && received <= deliveredAt + REPEAT_GRACE_MS) return null;
        ShortcutCatalog.Entry previous = deliveredShortcut;
        deliveredShortcut = null;
        return received < deliveredAt + 25000 ? previous : null;
    }

    boolean begin(String name, boolean local, long now) {
        ShortcutCatalog.Entry next = ShortcutCatalog.forSource(name);
        if (!local || next == null) return false;
        if (pending() && next == shortcut) return false;
        // The single worker can receive a queued native event after an HTTP POST
        // finishes. Its arrival time, rather than processing time, identifies a duplicate.
        requestWebhook = !(phase == Phase.SENT && next == shortcut && now <= completedAt + REPEAT_GRACE_MS);
        generation++;
        deadline = now + WAKE_TIMEOUT_MS;
        handoffAt = now + HANDOFF_DELAY_MS;
        phase = Phase.WAITING;
        direct = false;
        shortcutConfirmed = false;
        targetConfirmed = false;
        shortcut = next;
        target = "app".equals(next.kind) ? next.source : next.target;
        return true;
    }

    Next next(long id, long now, String current, boolean televisionOn, boolean targetPlaying) {
        if (!valid(id, now)) return Next.NONE;
        if (phase == Phase.WAITING) {
            // During a native wake the firmware restores its remembered source.
            // Starting HDMI before POWER_ON competes with that restoration.
            // Keep wake time separate from the subsequent source handoff budget.
            if (!televisionOn) return Next.WAIT;
            deadline = now + HANDOFF_TIMEOUT_MS;
            // A remembered HDMI source while asleep is not an active television.
            // Re-read the source at dispatch time; never use a previous request's state.
            if (target.equals(current) && targetPlaying) {
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
                && (phase == Phase.REDIRECTING || targetConfirmed) && target.equals(current) && televisionOn && targetPlaying)
            return requestWebhook ? Next.SEND_REQUEST : Next.COMPLETE_DUPLICATE;
        return Next.WAIT;
    }

    long delay(long now) {
        return phase == Phase.WAITING ? (now < handoffAt ? handoffAt - now : 150)
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
    void dispatched(long now) {
        if (requestWebhook && shortcut.cancelLaunch) { deliveredShortcut = shortcut; deliveredAt = now; }
    }
    void delivered(long now) { phase = Phase.SENT; completedAt = now; }
    void cancel() { generation++; phase = Phase.IDLE; shortcut = null; }
}
