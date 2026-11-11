"""The Stage 5.5 boss intro cutscene and the boss fight's music.

pygame cannot decode video, so the clip is read by ``imageio-ffmpeg``: it
runs its own bundled ffmpeg as a separate process and streams raw frames
through a pipe. (OpenCV was avoided on purpose: its wheels bundle a second
copy of SDL2, which clashes with pygame's in one process.) Frames are taken
in order; when the game falls behind, the late ones are dropped, so playback
keeps real time at any frame rate. The clip's own sound plays on a mixer
channel beside it. Without imageio-ffmpeg, the clip or an audio device the
game simply skips the cutscene (or plays it silently): it never blocks the
boss room.

The fight's music streams through ``pygame.mixer.music``, which the combat
sounds never touch (see audio.py), and fades in when the cutscene ends.

Assets: ``assets/cutscenes/boss_intro.mp4`` (960 x 640, 30 fps, no sound),
``assets/cutscenes/boss_intro.mp3`` (its sound) and
``assets/audio/music/boss_theme.mp3`` (the fight's music).
"""

from pathlib import Path

import pygame

from config import CUTSCENE_FADE

ASSETS = Path(__file__).resolve().parent / 'assets'
BOSS_INTRO_VIDEO = ASSETS / 'cutscenes' / 'boss_intro.mp4'
BOSS_INTRO_AUDIO = ASSETS / 'cutscenes' / 'boss_intro.mp3'
BOSS_MUSIC = ASSETS / 'audio' / 'music' / 'boss_theme.mp3'
SKIP_HINT = 'SPACE / ENTER : SKIP'


class Cutscene:
    """A video clip played full screen, letterboxed to keep its shape."""

    def __init__(self, video, audio=None, volume=1.0):
        import imageio_ffmpeg            # optional dependency: see load_boss_intro
        self.frames = imageio_ffmpeg.read_frames(str(video))
        meta = next(self.frames)         # the reader yields its metadata first
        self.size = tuple(meta['size'])
        self.fps = meta.get('fps') or 30.0
        self.duration = meta.get('duration') or 0.0
        self.time = 0.0
        self.index = -1                  # last frame read from the clip
        self.image = None                # that frame as a pygame surface
        self.done = False
        self.sound = self.channel = None
        if audio is not None and Path(audio).exists():
            try:
                if pygame.mixer.get_init():
                    self.sound = pygame.mixer.Sound(str(audio))
                    self.sound.set_volume(volume)
            except pygame.error:
                self.sound = None
        self._next_frame(0)

    def start(self):
        """Begin playback (its sound starts with the first frame)."""
        if self.sound is not None:
            try:
                self.channel = self.sound.play()
            except pygame.error:
                self.channel = None

    def _next_frame(self, target):
        """Read on to frame ``target`` (dropping late ones); False at the end."""
        frame = None
        while self.index < target:
            try:
                frame = next(self.frames)
            except (StopIteration, RuntimeError):
                return False
            self.index += 1
        if frame is not None:
            self.image = pygame.image.frombuffer(frame, self.size, 'RGB')
        return True

    def update(self, dt):
        if self.done:
            return
        self.time += dt
        if self.duration and self.time >= self.duration:
            self.finish()                # never read past the last frame
            return
        target = int(self.time * self.fps)
        if target > self.index and not self._next_frame(target):
            self.finish()

    def skip(self):
        if self.channel is not None:
            self.channel.fadeout(250)
        self.finish()

    def finish(self):
        if not self.done:
            self.done = True
            self.frames.close()          # ends the ffmpeg process

    def draw(self, surface, hint_font=None):
        surface.fill((0, 0, 0))
        if self.image is not None:
            width, height = surface.get_size()
            scale = min(width / self.image.get_width(), height / self.image.get_height())
            size = (round(self.image.get_width() * scale), round(self.image.get_height() * scale))
            image = (self.image if size == self.image.get_size()
                     else pygame.transform.smoothscale(self.image, size))
            surface.blit(image, image.get_rect(center=(width // 2, height // 2)))
        # In from black at the start, out to black at the end.
        fade_in, fade_out = CUTSCENE_FADE
        dark = max(1 - self.time / fade_in,
                   (self.time - (self.duration - fade_out)) / fade_out if self.duration else 0.0)
        if dark > 0:
            shade = pygame.Surface(surface.get_size())
            shade.set_alpha(round(255 * min(1.0, dark)))
            surface.blit(shade, (0, 0))
        if hint_font is not None and self.time > 0.6:
            hint = hint_font.render(SKIP_HINT, False, (169, 147, 120))
            surface.blit(hint, hint.get_rect(bottomright=(surface.get_width() - 16,
                                                          surface.get_height() - 12)))


def load_boss_intro(volume=1.0):
    """The boss intro cutscene, or None when it cannot play here."""
    if not BOSS_INTRO_VIDEO.exists():
        return None
    try:
        return Cutscene(BOSS_INTRO_VIDEO, BOSS_INTRO_AUDIO, volume)
    except (ImportError, OSError, RuntimeError, StopIteration) as error:
        print(f'Boss intro skipped: {error}')
        return None


def play_music(path, volume, fade_ms=0):
    """Loop a music track; quietly does nothing without the file or a mixer."""
    if not Path(path).exists():
        return False
    try:
        if not pygame.mixer.get_init():
            return False
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.set_volume(volume)
        pygame.mixer.music.play(loops=-1, fade_ms=fade_ms)
        return True
    except pygame.error:
        return False


def set_music_volume(volume):
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.set_volume(volume)
    except pygame.error:
        pass


def stop_music(fade_ms=800):
    try:
        if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            pygame.mixer.music.fadeout(fade_ms)
    except pygame.error:
        pass
