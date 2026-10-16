"""Sekiro-style posture: the player's combat state and enemy posture meters.

Posture is counted in whole points. Every enemy attack that gets through the
player's guard adds one; a full meter breaks the guard. A perfect parry adds
nothing to the player and one point to the attacker instead.

The player's combat state is derived from timers, so every transition is
deterministic and nothing can stay stuck:

    NORMAL -> PARRY_ACTIVE -> PARRY_RECOVERY -> NORMAL    press E (the parry
                                    cooldown is spent in NORMAL, unable to parry)
    NORMAL -> GUARD_BROKEN -> STUNNED -> NORMAL           posture full
    any    -> DEAD                                        death overrides all

A guard break interrupts any parry. Posture does not recover while stunned
and is back at zero when the stun ends. Everything here advances with the
game's dt, so pause and hitstop freeze it.
"""

from config import (PLAYER_MAX_POSTURE, PLAYER_STUN_DURATION, GUARD_BREAK_TIME,
                    POSTURE_RECOVERY_DELAY, POSTURE_RECOVERY_INTERVAL,
                    NORMAL_ENEMY_MAX_POSTURE, BOSS_MAX_POSTURE,
                    ENEMY_POSTURE_RECOVERY_DELAY, ENEMY_POSTURE_RECOVERY_INTERVAL)
from parry import ACTIVE, RECOVERY, Parry

NORMAL, PARRY_ACTIVE, PARRY_RECOVERY = 'normal', 'parry_active', 'parry_recovery'
GUARD_BROKEN, STUNNED, DEAD = 'guard_broken', 'stunned', 'dead'
_EPSILON = 1e-9


class Posture:
    """Points from 0 to ``maximum`` that return one by one after a quiet spell.

    ``calm`` counts the seconds since the last point was added. Once it passes
    ``delay``, recovery starts and a point comes back every ``interval``; with
    the defaults a meter at 2 drops to 1 six seconds after the hit, then to 0
    at eight. Any new point restarts the delay.
    """

    def __init__(self, maximum, delay, interval):
        self.maximum, self.delay, self.interval = maximum, delay, interval
        self.value = 0
        self.calm = 0.0
        self.since_rise = 99.0     # seconds since the last point (UI pop)

    @property
    def full(self):
        return self.value >= self.maximum

    def add(self, points=1):
        """Add points; True when this fills the meter."""
        self.value = min(self.maximum, self.value + points)
        self.calm = 0.0
        self.since_rise = 0.0
        return self.full

    def reset(self):
        self.value = 0
        self.calm = 0.0

    def recovery_progress(self):
        """0..1 through the interval that will return the next point."""
        if not self.value or self.calm <= self.delay:
            return 0.0
        return min(1.0, (self.calm - self.delay) / self.interval)

    def update(self, dt):
        self.since_rise += dt
        if not self.value:
            self.calm = 0.0
            return
        self.calm += dt
        while self.value and self.calm + _EPSILON >= self.delay + self.interval:
            self.value -= 1
            self.calm -= self.interval
        if not self.value:
            self.calm = 0.0


class PlayerCombat:
    """The player's parry, posture and guard-break stun in one state machine."""

    def __init__(self):
        self.parry = Parry()
        self.posture = Posture(PLAYER_MAX_POSTURE, POSTURE_RECOVERY_DELAY,
                               POSTURE_RECOVERY_INTERVAL)
        self.stun = 0.0            # seconds of guard break left (both phases)
        self.dead = False

    @property
    def state(self):
        if self.dead:
            return DEAD
        if self.stun > 0:
            recoil_left = self.stun - (PLAYER_STUN_DURATION - GUARD_BREAK_TIME)
            return GUARD_BROKEN if recoil_left > 0 else STUNNED
        if self.parry.state == ACTIVE:
            return PARRY_ACTIVE
        if self.parry.state == RECOVERY:
            return PARRY_RECOVERY
        return NORMAL

    def can_act(self):
        """Move, jump, parry, dig or throw: not while broken, never when dead."""
        return not self.dead and self.stun <= 0

    def start_parry(self):
        return self.can_act() and self.parry.start()

    def take_hit(self):
        """An enemy attack got through. Returns 'posture', 'guard_break' or None.

        Already broken (or dead): the hit still hurts but adds no posture, so
        one break is never counted twice.
        """
        if not self.can_act():
            return None
        if self.posture.add(1):
            self.stun = PLAYER_STUN_DURATION
            self.parry.interrupt()
            return 'guard_break'
        return 'posture'

    def die(self):
        self.dead = True
        self.stun = 0.0
        self.parry.interrupt()

    def update(self, dt):
        """Advance by dt; returns the parry's events, or ['recovered'] as a stun ends."""
        if self.dead or dt <= 0:
            return []
        if self.stun > 0:
            self.stun -= dt
            if self.stun <= _EPSILON:
                self.stun = 0.0
                self.posture.reset()
                return ['recovered']
            return []
        self.posture.update(dt)
        return self.parry.update(dt)


def give_posture(enemy, boss=False):
    """Enemies that take part in parry combat carry a posture meter."""
    if boss:
        enemy.posture = Posture(BOSS_MAX_POSTURE, ENEMY_POSTURE_RECOVERY_DELAY,
                                ENEMY_POSTURE_RECOVERY_INTERVAL)
    else:
        enemy.posture = Posture(NORMAL_ENEMY_MAX_POSTURE, ENEMY_POSTURE_RECOVERY_DELAY,
                                ENEMY_POSTURE_RECOVERY_INTERVAL)
    enemy.stun_timer = getattr(enemy, 'stun_timer', 0.0)
    enemy.broken = False
    return enemy


def tick_enemy(enemy, dt):
    """Stun and posture timers of one enemy; True as its guard break ends."""
    if getattr(enemy, 'stun_timer', 0) > 0:
        enemy.stun_timer = max(0.0, enemy.stun_timer - dt)
        if enemy.stun_timer == 0 and getattr(enemy, 'broken', False):
            enemy.broken = False
            enemy.posture.reset()
            return True
        return False               # posture holds while the enemy is stunned
    posture = getattr(enemy, 'posture', None)
    if posture is not None:
        posture.update(dt)
    return False
