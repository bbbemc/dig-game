"""Procedural combat sounds: metallic sword clashes, whooshes and breaks.

Pure Python (no numpy). Each recipe returns a list of floats in [-1, 1]
(mono) or a ``(left, right)`` pair at the requested sample rate.
``tools/generate_combat_sfx.py`` exports them to ``assets/audio/combat/``;
audio.py synthesizes a recipe in memory only when its file is missing, so
combat is never silent.

Steel is modelled as inharmonic, exponentially decaying modes. Each mode is
a pair of partials a few hertz apart, and their beating gives a ringing
blade its shimmer. Stereo recipes give the two channels different phases
and beats, so the ring is wide while the strike stays centred. A clash is
layered like the real thing:

* the strike: a hard click and a bright noise burst (the transient);
* SHING: very high, fast-dying modes and a falling band of noise (edge
  scraping along edge);
* CLANG: the blade's ring, mid-high modes with a short tail;
* a little low body so the hit has weight.
"""

import math
import random

RATE = 44100
PEAK = 0.89          # -1 dBFS: loud, with headroom so overlaps rarely clip


# -- building blocks ---------------------------------------------------------
def _buffer(rate, seconds):
    return [0.0] * int(rate * seconds)


def _mode(out, rate, freq, amp, decay, start=0.0, phase=0.0, attack=0.0):
    """Mix in a damped sinusoid via the two-term recursion (no per-sample sin)."""
    if freq >= rate * 0.45 or amp <= 0:
        return
    first = int(start * rate)
    w = 2 * math.pi * freq / rate
    r = math.exp(-decay / rate)
    c, r2 = 2 * r * math.cos(w), r * r
    y2, y1 = amp * math.sin(phase - w) / r, amp * math.sin(phase)
    last = min(len(out), first + int(rate * math.log(max(amp, 1e-6) / 1e-5) / decay))
    ramp = int(attack * rate)
    for i in range(first, last):
        n = i - first
        out[i] += y1 if n >= ramp else y1 * n / ramp
        y2, y1 = y1, c * y1 - r2 * y2


def _metal(out, rate, f0, ratios, amps, decays, rng, start=0.0, detune=(1.0, 3.0),
           gain=1.0, spread=0.012, attack=0.0):
    """A struck steel body: every mode is a detuned pair, beating slowly."""
    for ratio, amp, decay in zip(ratios, amps, decays):
        freq = f0 * ratio * (1 + rng.uniform(-spread, spread))
        beat = rng.uniform(*detune)
        for side in (-0.5, 0.5):
            _mode(out, rate, freq + side * beat, gain * amp * 0.5, decay, start,
                  rng.uniform(0, 2 * math.pi), attack)


def _metal_stereo(left, right, rate, f0, modes, rng, start=0.0, detune=(1.0, 3.0),
                  gain=1.0, spread=0.012, attack=0.0):
    """``modes``: (ratio, amp, decay). Same pitches, different beats per side."""
    for ratio, amp, decay in modes:
        freq = f0 * ratio * (1 + rng.uniform(-spread, spread))
        beat = rng.uniform(*detune)
        for out, skew in ((left, rng.uniform(0.75, 1.0)), (right, rng.uniform(1.0, 1.3))):
            for side in (-0.5, 0.5):
                _mode(out, rate, freq + side * beat * skew, gain * amp * 0.5, decay, start,
                      rng.uniform(0, 2 * math.pi), attack)


def _glide(out, rate, f_start, f_end, glide_time, amp, decay, start=0.0, attack=0.002):
    """A sine whose pitch falls (or rises) exponentially: thumps, bends."""
    first = int(start * rate)
    length = min(len(out) - first, int(rate * math.log(max(amp, 1e-6) / 1e-5) / decay))
    phase = 0.0
    ratio = math.log(f_end / f_start)
    for n in range(max(0, length)):
        t = n / rate
        freq = f_start * math.exp(ratio * min(1.0, t / glide_time))
        phase += 2 * math.pi * freq / rate
        envelope = min(1.0, t / attack) * math.exp(-decay * t)
        out[first + n] += amp * envelope * math.sin(phase)


def _burst(out, rate, rng, amp, tau, start=0.0, highpass=0.0, lowpass=0.0, length=None):
    """Exponentially decaying noise, optionally one-pole high/low passed."""
    first = int(start * rate)
    length = int(rate * (length if length else tau * 9))
    hp_a = 1 - math.exp(-2 * math.pi * highpass / rate) if highpass else 0.0
    lp_a = 1 - math.exp(-2 * math.pi * lowpass / rate) if lowpass else 1.0
    hp_state = lp_state = 0.0
    for n in range(min(length, len(out) - first)):
        x = rng.uniform(-1.0, 1.0)
        if hp_a:
            hp_state += hp_a * (x - hp_state)
            x -= hp_state
        lp_state += lp_a * (x - lp_state)
        out[first + n] += amp * lp_state * math.exp(-n / (rate * tau))


def _sweep(out, rate, rng, seconds, cutoff, envelope, amp, start=0.0, damping=0.7):
    """Band-passed noise (2x oversampled state-variable filter), moving centre.

    ``cutoff(t)`` and ``envelope(t)`` take t in [0, 1] over ``seconds``.
    Oversampling keeps the filter stable up to ~12 kHz.
    """
    first = int(start * rate)
    length = min(len(out) - first, int(rate * seconds))
    low = band = 0.0
    for n in range(max(0, length)):
        t = n / length
        f = 2 * math.sin(math.pi * min(cutoff(t), rate * 0.28) / (2 * rate))
        x = rng.uniform(-1.0, 1.0)
        for _ in range(2):
            low += f * band
            high = x - low - damping * band
            band += f * high
        out[first + n] += amp * envelope(t) * band


def _grains(out, rate, rng, count, window, amp, freq_range, tau=(0.0015, 0.006)):
    """Short bright noise grains scattered in time: metal cracking apart."""
    start, end = window
    for _ in range(count):
        at = rng.uniform(start, end)
        fade = 1 - (at - start) / (end - start)
        centre = rng.uniform(*freq_range)
        grain_tau = rng.uniform(*tau)
        _sweep(out, rate, rng, grain_tau * 5, lambda t, c=centre: c,
               lambda t, k=grain_tau: math.exp(-t * 5), amp * (0.35 + 0.65 * fade), at, 0.35)


def _shape(channels, rate, drive, fade, peak):
    """DC removal, soft saturation, one shared normalisation and a tail fade."""
    a = 1 - math.exp(-2 * math.pi * 30 / rate)     # 30 Hz high-pass
    norm = math.tanh(drive) if drive > 1.0 else 1.0
    shaped = []
    for samples in channels:
        state, out = 0.0, []
        for x in samples:
            state += a * (x - state)
            x -= state
            out.append(math.tanh(x * drive) / norm if drive > 1.0 else x)
        shaped.append(out)
    top = max(1e-9, max(max(abs(x) for x in out) for out in shaped))
    scale = peak / top
    tail = max(1, int(rate * fade))
    for out in shaped:
        length = len(out)
        for n in range(length):
            out[n] *= scale * min(1.0, (length - 1 - n) / tail)
    return shaped


def _finish(samples, rate, drive=1.0, fade=0.02, peak=PEAK):
    return _shape([samples], rate, drive, fade, peak)[0]


def _finish_stereo(centre, left, right, rate, drive=1.0, fade=0.02, peak=PEAK):
    l = [c + x for c, x in zip(centre, left)]
    r = [c + x for c, x in zip(centre, right)]
    return tuple(_shape([l, r], rate, drive, fade, peak))


def _pan(mono, pan):
    """Split a mono buffer by ``pan(t)`` in [-1, 1] (constant power)."""
    left, right, length = [], [], len(mono)
    for n, x in enumerate(mono):
        p = (pan(n / length) + 1) * math.pi / 4
        left.append(x * math.cos(p))
        right.append(x * math.sin(p))
    return left, right


# -- recipes ------------------------------------------------------------------
def parry_whoosh(rate=RATE):
    """Pressing E: a fast blade cutting the air, swinging across the stereo field."""
    rng = random.Random(11)
    out = _buffer(rate, 0.17)
    cutoff = lambda t: 650 + 3900 * math.sin(math.pi * min(1.0, t * 1.15)) ** 2
    envelope = lambda t: (t / 0.35) ** 1.8 if t < 0.35 else ((1 - t) / 0.65) ** 2.4
    _sweep(out, rate, rng, 0.16, cutoff, envelope, 0.9, damping=0.5)
    _sweep(out, rate, rng, 0.16, lambda t: cutoff(t) * 2.1, envelope, 0.3, damping=0.75)
    left, right = _pan(out, lambda t: -0.55 + 1.1 * t)
    return _finish_stereo([0.0] * len(out), left, right, rate, fade=0.03)


CLASH_TAKES = {
    # f0, seed, brightness of the SHING layer: three distinct, slightly pitched takes
    1: (1240.0, 101, 1.0),
    2: (1385.0, 202, 1.12),
    3: (1115.0, 303, 0.9),
}
CLANG = ((1.0, 0.55, 6.5), (1.483, 1.0, 7.5), (2.11, 0.85, 9.0), (2.79, 0.68, 11.0),
         (3.33, 0.5, 13.0), (4.02, 0.4, 16.0))
SHING = ((4.61, 0.5, 21.0), (5.37, 0.45, 25.0), (6.18, 0.4, 29.0), (7.06, 0.34, 34.0),
         (7.93, 0.28, 40.0), (8.84, 0.22, 47.0))


def parry_clash(take=1, rate=RATE):
    """A successful parry: SHING! CLANG! - strike, bright sheen, steel ring."""
    f0, seed, bright = CLASH_TAKES[take]
    rng = random.Random(seed)
    seconds = 0.72
    centre, left, right = (_buffer(rate, seconds) for _ in range(3))
    _metal_stereo(left, right, rate, f0, CLANG, rng, detune=(1.0, 3.2), gain=0.36,
                  attack=0.0025)
    _metal_stereo(left, right, rate, f0, [(r, a * bright, d) for r, a, d in SHING], rng,
                  detune=(3.0, 9.0), gain=0.3, spread=0.03)
    _burst(centre, rate, rng, 1.3, 0.0012, highpass=3200)                  # the click
    _burst(centre, rate, rng, 0.55, 0.006, highpass=1500, lowpass=7000)   # its body
    _sweep(centre, rate, rng, 0.09, lambda t: 9000 - 4800 * t,            # 'shhing'
           lambda t: (1 - t) ** 1.4 * min(1.0, t / 0.08), 0.24, start=0.002, damping=0.45)
    _glide(centre, rate, 200, 115, 0.03, 0.24, 38.0)                       # weight
    return _finish_stereo(centre, left, right, rate, drive=1.3, fade=0.06)


def parry_perfect(rate=RATE):
    """A perfectly timed parry: a bigger, brighter double clang with a long 'ting'."""
    rng = random.Random(404)
    seconds = 1.15
    centre, left, right = (_buffer(rate, seconds) for _ in range(3))
    f0 = 1290.0
    _metal_stereo(left, right, rate, f0, CLANG, rng, detune=(0.8, 2.6), gain=0.34,
                  attack=0.002)
    _metal_stereo(left, right, rate, f0, SHING, rng, detune=(3.0, 8.0), gain=0.34,
                  spread=0.03)
    # The blade catching a hair later: a second, lower clang.
    _metal_stereo(left, right, rate, 905.0, CLANG[:4], rng, start=0.011, detune=(1.0, 2.5),
                  gain=0.22, attack=0.002)
    # The ringing 'ting' that hangs in the air.
    _metal_stereo(left, right, rate, 3140.0, ((1.0, 1.0, 3.4), (1.62, 0.45, 5.0)), rng,
                  detune=(0.6, 1.4), gain=0.16, attack=0.004)
    _burst(centre, rate, rng, 1.45, 0.0013, highpass=3200)
    _burst(centre, rate, rng, 0.8, 0.0012, start=0.011, highpass=2600)
    _burst(centre, rate, rng, 0.6, 0.008, highpass=1400, lowpass=8000)
    _sweep(centre, rate, rng, 0.15, lambda t: 10500 - 6000 * t,
           lambda t: (1 - t) ** 1.2 * min(1.0, t / 0.05), 0.3, start=0.002, damping=0.4)
    _glide(centre, rate, 230, 105, 0.05, 0.42, 26.0)
    return _finish_stereo(centre, left, right, rate, drive=1.35, fade=0.12)


def parry_failed(rate=RATE):
    """A hit lands through the guard: dull, short, low metallic knock."""
    rng = random.Random(5)
    out = _buffer(rate, 0.4)
    _glide(out, rate, 150, 82, 0.06, 1.0, 26.0)
    _burst(out, rate, rng, 0.85, 0.014, lowpass=750)
    _metal(out, rate, 355, (1.0, 1.58, 2.37, 3.1), (1.0, 0.7, 0.45, 0.3),
           (15.0, 19.0, 25.0, 33.0), rng, detune=(2.0, 5.0), gain=0.4)
    return _finish(out, rate, drive=1.5, fade=0.04)


def posture_damage(rate=RATE):
    """The guard straining: a gritty grind and a choked, falling ring."""
    rng = random.Random(57)
    out = _buffer(rate, 0.34)
    _sweep(out, rate, rng, 0.13, lambda t: 2700 - 1000 * t,
           lambda t: (1 - t) ** 2 * min(1.0, t / 0.04), 0.75, damping=0.3)
    _grains(out, rate, rng, 14, (0.0, 0.12), 0.28, (1500, 4200))
    _glide(out, rate, 780, 520, 0.12, 0.3, 13.0)
    _glide(out, rate, 140, 90, 0.05, 0.45, 30.0)
    return _finish(out, rate, drive=1.6, fade=0.04)


def guard_break(rate=RATE):
    """Posture broken: a heavy, low steel crash that cracks apart."""
    rng = random.Random(77)
    seconds = 1.3
    centre, left, right = (_buffer(rate, seconds) for _ in range(3))
    _glide(centre, rate, 80, 40, 0.3, 1.0, 4.6, attack=0.003)
    _burst(centre, rate, rng, 0.95, 0.045, highpass=400)
    _burst(centre, rate, rng, 0.55, 0.16, lowpass=1300)
    modes = tuple(zip((1.0, 1.41, 1.93, 2.51, 3.18, 3.97, 4.88, 6.02, 7.4),
                      (0.9, 1.0, 0.85, 0.8, 0.65, 0.55, 0.45, 0.35, 0.25),
                      (3.0, 3.8, 4.8, 6.0, 7.4, 9.0, 11.0, 14.0, 18.0)))
    _metal_stereo(left, right, rate, 430, modes, rng, detune=(2.0, 5.5), gain=0.36,
                  spread=0.02)
    _burst(centre, rate, rng, 0.6, 0.004, start=0.045, highpass=1800)     # second impact
    _grains(left, rate, rng, 20, (0.02, 0.42), 0.32, (1800, 6500))
    _grains(right, rate, rng, 20, (0.02, 0.42), 0.32, (1800, 6500))
    return _finish_stereo(centre, left, right, rate, drive=2.0, fade=0.12)


def enemy_guard_break(rate=RATE):
    """The enemy's guard shatters: a bright clash, then steel bending away."""
    rng = random.Random(91)
    out = _buffer(rate, 1.0)
    _metal(out, rate, 1450, (1.0, 1.52, 2.27, 2.9, 3.7), (0.7, 1.0, 0.8, 0.55, 0.4),
           (8.0, 10.0, 13.0, 17.0, 22.0), rng, detune=(1.5, 4.0), gain=0.38)
    _burst(out, rate, rng, 1.1, 0.0018, highpass=2600)
    # 60 ms later: the break - a crunch, a thump and two falling, bending rings.
    _burst(out, rate, rng, 0.75, 0.022, start=0.06, highpass=500, lowpass=4000)
    _glide(out, rate, 115, 58, 0.15, 0.8, 11.0, start=0.06)
    _glide(out, rate, 980, 610, 0.45, 0.22, 4.5, start=0.06)
    _glide(out, rate, 1530, 940, 0.45, 0.14, 5.5, start=0.065)
    _grains(out, rate, rng, 22, (0.06, 0.36), 0.3, (2000, 7000))
    return _finish(out, rate, drive=1.6, fade=0.1)


def stun_recover(rate=RATE):
    """Back on guard: a quick rising draw and a light, high ring."""
    rng = random.Random(13)
    out = _buffer(rate, 0.45)
    _sweep(out, rate, rng, 0.13, lambda t: 1200 + 4600 * t,
           lambda t: math.sin(math.pi * t) ** 1.2, 0.6, damping=0.6)
    _metal(out, rate, 2100, (1.0, 1.48, 2.2), (0.8, 1.0, 0.5), (9.0, 12.0, 16.0),
           rng, start=0.1, detune=(1.0, 2.5), gain=0.34)
    _burst(out, rate, rng, 0.35, 0.0012, start=0.1, highpass=3000)
    return _finish(out, rate, fade=0.05)


def deathblow(rate=RATE):
    """Finishing a guard-broken enemy: a fast slash into a meaty steel thunk."""
    rng = random.Random(29)
    out = _buffer(rate, 0.8)
    _sweep(out, rate, rng, 0.09, lambda t: 700 + 3600 * t ** 1.4,
           lambda t: t ** 1.5, 0.75, damping=0.8)
    _glide(out, rate, 125, 52, 0.12, 1.0, 8.5, start=0.085)
    _burst(out, rate, rng, 0.8, 0.03, start=0.085, lowpass=2200)
    _burst(out, rate, rng, 0.7, 0.002, start=0.085, highpass=2400)
    _metal(out, rate, 640, (1.0, 1.55, 2.3, 3.05), (1.0, 0.8, 0.55, 0.4),
           (7.0, 9.0, 12.0, 16.0), rng, start=0.085, detune=(2.0, 5.0), gain=0.3)
    return _finish(out, rate, drive=1.7, fade=0.08)


RECIPES = {
    'parry_whoosh': parry_whoosh,
    'parry_clash_01': lambda rate=RATE: parry_clash(1, rate),
    'parry_clash_02': lambda rate=RATE: parry_clash(2, rate),
    'parry_clash_03': lambda rate=RATE: parry_clash(3, rate),
    'parry_perfect': parry_perfect,
    'parry_failed': parry_failed,
    'posture_damage': posture_damage,
    'guard_break': guard_break,
    'enemy_guard_break': enemy_guard_break,
    'stun_recover': stun_recover,
    'deathblow': deathblow,
}
