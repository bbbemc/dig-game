"""Combat sound effects: WAV assets, a synthesized fallback and safe playback.

Sounds load once from ``assets/audio/combat`` (made by
``tools/generate_combat_sfx.py``). A missing or unreadable file is
synthesized in memory from the same recipe (sfx_synth.py), so combat is
never silent; without an audio device, or with any mixer error, ``play``
does nothing and the game runs on.

Playback never blocks: Sound.play only queues the sound for SDL's mixing
thread. An event picks one of its variants (separate takes, plus copies a
few percent higher and lower in pitch), never the same one twice running.
An event cannot restart within SFX_MIN_INTERVAL, and once SFX_MAX_INSTANCES
copies ring the oldest fades out. Sounds starting together share a loudness
budget (SFX_HEADROOM within SFX_ONSET_WINDOW): the first, most important
one plays in full and the rest are turned down so their aligned transients
cannot clip the mix. Only Sound channels are used: ``pygame.mixer.music``
(background music) is never touched.
"""

from array import array
from collections import deque
from pathlib import Path
import random
import time

from config import (SFX_VOLUME, SFX_MIN_INTERVAL, SFX_MAX_INSTANCES,
                    SFX_PITCH_JITTER, SFX_HEADROOM, SFX_ONSET_WINDOW)

SFX_DIR = Path(__file__).resolve().parent / 'assets' / 'audio' / 'combat'
# event: (asset names, gain, pitch variants)
EVENTS = {
    'parry_whoosh': (('parry_whoosh',), 0.55, True),
    'parry_clash': (('parry_clash_01', 'parry_clash_02', 'parry_clash_03'), 0.95, True),
    'parry_perfect': (('parry_perfect',), 1.0, True),
    'parry_failed': (('parry_failed',), 0.7, True),
    'posture_damage': (('posture_damage',), 0.55, True),
    'guard_break': (('guard_break',), 0.85, False),
    'enemy_guard_break': (('enemy_guard_break',), 0.85, False),
    'stun_recover': (('stun_recover',), 0.5, True),
    'deathblow': (('deathblow',), 0.85, False),
}
_bank = None


def sounds():
    """The shared sound bank, created on first use."""
    global _bank
    if _bank is None:
        _bank = SoundBank()
    return _bank


class SoundBank:
    def __init__(self, directory=SFX_DIR):
        self.directory = Path(directory)
        self.variants = {}         # event -> [Sound, ...]
        self.sources = {}          # asset name -> 'file' | 'synth' | None
        self.volume = SFX_VOLUME
        self.requests = deque(maxlen=64)   # every event the game asked for
        self.played = deque(maxlen=64)     # (event, variant index) actually started
        self.last_time = {}
        self.last_variant = {}
        self.channels = {}         # event -> channels it started, oldest first
        self.peaks = {}            # Sound -> its loudest sample (0..1)
        self.onsets = []           # (time, level) of sounds that just started
        self.random = random.Random()
        self.enabled = False
        self.format = None
        try:
            import pygame
            self.pygame = pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.format = pygame.mixer.get_init()
            self.enabled = bool(self.format)
            if self.enabled and pygame.mixer.get_num_channels() < 16:
                pygame.mixer.set_num_channels(16)
        except Exception:
            self.enabled = False

    # -- loading -----------------------------------------------------------
    def preload(self):
        """Load every event now (at launch) so the first parry never stalls."""
        for event in EVENTS:
            self._event(event)

    def _event(self, event):
        if event not in self.variants:
            names, gain, pitched = EVENTS[event]
            loaded = [sound for sound in map(self._load, names) if sound is not None]
            if pitched and SFX_PITCH_JITTER:
                for sound in list(loaded):
                    for factor in (1 - SFX_PITCH_JITTER, 1 + SFX_PITCH_JITTER):
                        shifted = self._repitch(sound, factor)
                        if shifted is not None:
                            loaded.append(shifted)
            for sound in loaded:
                sound.set_volume(gain)
                self.peaks[sound] = self._peak(sound)
            self.variants[event] = loaded
        return self.variants[event]

    def _load(self, name):
        if not self.enabled:
            return None
        path = self.directory / f'{name}.wav'
        try:
            sound = self.pygame.mixer.Sound(str(path))
            self.sources[name] = 'file'
            return sound
        except Exception:
            pass
        try:
            sound = self._synthesize(name)
            self.sources[name] = 'synth' if sound is not None else None
            return sound
        except Exception:
            self.sources[name] = None
            return None

    def _synthesize(self, name):
        """The file is missing: build the same recipe at the mixer's format."""
        from sfx_synth import RECIPES
        rate, size, channels = self.format
        if abs(size) != 16:
            return None
        samples = RECIPES[name](rate)
        sides = list(samples) if isinstance(samples, tuple) else [samples]
        if channels == 1 and len(sides) == 2:
            sides = [[(a + b) / 2 for a, b in zip(*sides)]]
        while len(sides) < channels:
            sides.append(sides[-1])
        pcm = array('h', (max(-32767, min(32767, round(v * 32767)))
                          for frame in zip(*sides[:channels]) for v in frame))
        return self.pygame.mixer.Sound(buffer=pcm.tobytes())

    def _peak(self, sound):
        try:
            if abs(self.format[1]) != 16:
                return 1.0
            raw = array('h')
            raw.frombytes(sound.get_raw())
            return max(max(raw), -min(raw)) / 32768
        except Exception:
            return 1.0

    def _repitch(self, sound, factor):
        """A copy played ``factor`` times faster (higher) by linear resampling."""
        rate, size, channels = self.format
        if abs(size) != 16:
            return None
        try:
            raw = array('h')
            raw.frombytes(sound.get_raw())
            frames = len(raw) // channels
            length = int((frames - 1) / factor)
            columns = [raw[c::channels] for c in range(channels)]
            mono = all(column == columns[0] for column in columns[1:])
            positions = [n * factor for n in range(length)]
            out = array('h', bytes(2 * length * channels))
            done = None
            for c, src in enumerate(columns):
                if done is None or not mono:
                    done = array('h', [int(src[int(p)] + (src[int(p) + 1] - src[int(p)])
                                           * (p - int(p))) for p in positions])
                out[c::channels] = done
            return self.pygame.mixer.Sound(buffer=out.tobytes())
        except Exception:
            return None

    # -- playback ----------------------------------------------------------
    def set_volume(self, volume):
        """SFX volume, separate from any music: 0 mutes, 1 is full."""
        self.volume = max(0.0, min(1.0, float(volume)))

    def reset_limits(self):
        self.last_time.clear()
        self.last_variant.clear()
        self.onsets.clear()

    def play(self, event):
        """Start ``event`` if allowed; returns the variant index or None."""
        self.requests.append(event)
        if not self.enabled or event not in EVENTS:
            return None
        variants = self._event(event)
        if not variants:
            return None
        now = time.monotonic()
        if now - self.last_time.get(event, -1e9) < SFX_MIN_INTERVAL:
            return None            # the same frame's duplicate: one is enough
        try:
            # At most SFX_MAX_INSTANCES copies ring at once: the oldest tail
            # fades out to make room, so the newest hit is always heard.
            ringing = [channel for channel in self.channels.get(event, ())
                       if channel.get_busy() and channel.get_sound() in variants]
            while len(ringing) >= SFX_MAX_INSTANCES:
                ringing.pop(0).fadeout(40)
            choices = [n for n in range(len(variants))
                       if n != self.last_variant.get(event) or len(variants) == 1]
            index = self.random.choice(choices)
            sound = variants[index]
            # The loudness budget: sounds starting together cannot clip.
            self.onsets = [(t, level) for t, level in self.onsets
                           if now - t < SFX_ONSET_WINDOW]
            full = self.peaks.get(sound, 1.0) * sound.get_volume() * self.volume
            room = SFX_HEADROOM - sum(level for _, level in self.onsets)
            scale = 1.0 if full <= 0 else min(1.0, room / full)
            if scale < 0.2:
                return None        # no room left: skip rather than whisper
            channel = sound.play()
            if channel is not None:
                channel.set_volume(self.volume * scale)
                ringing.append(channel)
            self.channels[event] = ringing
            self.onsets.append((now, full * scale))
        except Exception:
            return None
        self.last_time[event] = now
        self.last_variant[event] = index
        self.played.append((event, index, self.volume * scale))
        return index
