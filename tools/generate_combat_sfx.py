"""Export the procedural combat sounds (sfx_synth.py) as 16-bit WAV files.

    python tools/generate_combat_sfx.py            # writes assets/audio/combat/
    python tools/generate_combat_sfx.py --out DIR  # somewhere else

Deterministic: the same recipes always produce the same files. The game
loads these; if one is missing it synthesizes that recipe in memory instead.
"""
import argparse
from array import array
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sfx_synth import RATE, RECIPES

DEFAULT_OUT = Path(__file__).resolve().parents[1] / 'assets' / 'audio' / 'combat'


def write_wav(path, samples, rate=RATE):
    """``samples``: a list (mono) or a (left, right) pair (stereo)."""
    channels = list(samples) if isinstance(samples, tuple) else [samples]
    pcm = array('h', (max(-32767, min(32767, round(v * 32767)))
                      for frame in zip(*channels) for v in frame))
    if sys.byteorder == 'big':
        pcm.byteswap()
    with wave.open(str(path), 'wb') as file:
        file.setnchannels(len(channels))
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(pcm.tobytes())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, recipe in RECIPES.items():
        start = time.perf_counter()
        samples = recipe(RATE)
        path = args.out / f'{name}.wav'
        write_wav(path, samples)
        channels = samples if isinstance(samples, tuple) else (samples,)
        peak = max(max(abs(v) for v in channel) for channel in channels)
        print(f'{path.name:24} {len(channels[0]) / RATE:5.2f} s  '
              f'{"stereo" if len(channels) == 2 else "mono  "}  peak {peak:.2f}  '
              f'{(time.perf_counter() - start) * 1000:6.0f} ms')


if __name__ == '__main__':
    main()
