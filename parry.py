"""Parry timing: READY -> ACTIVE -> RECOVERY -> COOLDOWN -> READY.

Pure game-time state, advanced with the frame's dt, so the window lasts the
same at any frame rate (time left over at a transition carries into the next
phase). The Game asks ``is_active()`` while it resolves an enemy hit and
calls ``succeed()`` when that hit is deflected; it owns all consequences
(stun, knockback, effects, sound).

A success ends the window at once: one press deflects the hits that land in
that same frame and nothing after it, and the cooldown still runs in full.
Posture, guard breaks and the player's stun live in combat.py, which owns a
Parry and may ``interrupt`` it.
"""

from config import PARRY_ACTIVE_TIME, PARRY_RECOVERY_TIME, PARRY_COOLDOWN

READY, ACTIVE, RECOVERY, COOLDOWN = 'ready', 'active', 'recovery', 'cooldown'
DURATIONS = {ACTIVE: PARRY_ACTIVE_TIME, RECOVERY: PARRY_RECOVERY_TIME,
             COOLDOWN: PARRY_COOLDOWN}
NEXT = {ACTIVE: RECOVERY, RECOVERY: COOLDOWN, COOLDOWN: READY}


class Parry:
    def __init__(self):
        self.state = READY
        self.timer = 0.0          # seconds left in the current phase
        self.elapsed = 0.0        # seconds since the last press (for animation)
        self.succeeded = False    # the current attempt deflected something
        self.deflecting = False   # a hit was deflected during this frame

    def can_parry(self):
        return self.state == READY

    def start(self):
        """Press E: open the window. Returns False while recovering/cooling."""
        if not self.can_parry():
            return False
        self.state, self.timer = ACTIVE, DURATIONS[ACTIVE]
        self.elapsed = 0.0
        self.succeeded = self.deflecting = False
        return True

    def is_active(self):
        """Whether an attack resolved now would be deflected."""
        return self.state == ACTIVE or self.deflecting

    def succeed(self):
        """The window caught a hit: close it and begin recovery."""
        if self.state == ACTIVE:
            self.state, self.timer = RECOVERY, DURATIONS[RECOVERY]
            self.succeeded = True
        self.deflecting = True

    def interrupt(self):
        """A guard break cuts the parry short: back to READY, nothing pending."""
        self.state, self.timer = READY, 0.0
        self.succeeded = self.deflecting = False

    def update(self, dt):
        """Advance by dt seconds; return the events: 'whiff', 'ready'."""
        events = []
        self.deflecting = False
        if self.state == READY or dt <= 0:
            return events
        self.elapsed += dt
        while self.state != READY and dt > 0:
            if dt < self.timer:
                self.timer -= dt
                break
            dt -= self.timer
            if self.state == ACTIVE and not self.succeeded:
                events.append('whiff')
            self.state = NEXT[self.state]
            self.timer = DURATIONS.get(self.state, 0.0)
            if self.state == READY:
                events.append('ready')
        return events

    def cooldown_fraction(self):
        """Share of the wait still left after a press, from 1 down to 0."""
        if self.state == READY:
            return 0.0
        total = sum(DURATIONS.values())
        left = self.timer + sum(DURATIONS[s] for s in (RECOVERY, COOLDOWN)
                                if _order(s) > _order(self.state))
        return max(0.0, min(1.0, left / total))


def _order(state):
    return (ACTIVE, RECOVERY, COOLDOWN).index(state)
