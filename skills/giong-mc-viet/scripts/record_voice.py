"""Record a Vietnamese MC voiceover with edge-tts: one MP3 per script line, a joined track, an SRT and lines.json.

Usage:  python record_voice.py script.txt [--out voice] [--voice vi-VN-NamMinhNeural] [--rate +6%] [--pitch +3Hz]
                               [--gap 0.4] [--only 3 5]
Script: UTF-8 text, one voice line per line; "spoken text | subtitle text" when they differ; blank lines and # comments are skipped.
"""
import argparse, asyncio, json, os, sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')   # Vietnamese text on Windows consoles
except Exception:
    pass
try:
    import edge_tts
except ImportError:
    sys.exit('edge-tts is not installed: python -m pip install --user edge-tts')

KBPS = 48000          # edge-tts writes 24 kHz mono MP3 at a constant 48 kbps
FRAME_SEC = 576 / 24000   # one MPEG-2 layer III frame: 576 samples, 144 bytes at 48 kbps


def silence(sec, like):
    """Silent MP3 frames in the same format as the recorded clips (header copied from one of them, empty audio data)."""
    with open(like, 'rb') as f:
        head = f.read(4)
    if len(head) < 4 or head[0] != 0xFF:
        head = b'\xff\xf3\x64\xc0'   # MPEG-2 layer III, 48 kbps, 24 kHz, mono
    return (head + b'\x00' * 140) * max(0, round(sec / FRAME_SEC))


def parse(path):
    lines = []
    with open(path, encoding='utf-8-sig') as f:
        for raw in f:
            s = raw.strip()
            if not s or s.startswith('#'):
                continue
            say, _, sub = s.partition('|')
            lines.append((say.strip(), (sub or say).strip()))
    return lines


def nudge(value, unit, d):
    n = int(value.rstrip(unit)) + d
    return f'{n:+d}{unit}'


async def record(text, path, voice, rate, pitch):
    """The free service drops many requests at random ("No audio was received"). Retry with waits, nudging rate/pitch by
    an inaudible 1 step each time; as a last resort read at plain settings. Returns the settings that worked."""
    tries = [(rate, pitch)]
    for d in (1, -1, 2, -2):
        tries += [(nudge(rate, '%', d), pitch), (rate, nudge(pitch, 'Hz', -d))]
    tries += [('+0%', '+0Hz')] * 3
    for k, (r, p) in enumerate(tries):
        try:
            await edge_tts.Communicate(text, voice, rate=r, pitch=p).save(path)
            if os.path.getsize(path) > 6000:   # under ~1 s means the service cut the line short
                return r, p
        except edge_tts.exceptions.NoAudioReceived:
            pass
        await asyncio.sleep(1.5 + k * 0.7)
    raise RuntimeError(f'no audio after {len(tries)} tries (wait a minute, then run again with --only): {text}')


def seconds(path):
    return os.path.getsize(path) * 8 / KBPS


def stamp(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('script'); ap.add_argument('--out', default='voice')
    ap.add_argument('--voice', default='vi-VN-NamMinhNeural'); ap.add_argument('--rate', default='+6%'); ap.add_argument('--pitch', default='+3Hz')
    ap.add_argument('--gap', type=float, default=0.4); ap.add_argument('--only', type=int, nargs='*', default=[])
    a = ap.parse_args()
    lines = parse(a.script)
    if not lines:
        sys.exit('the script has no lines')
    os.makedirs(a.out, exist_ok=True)

    for i, (say, _) in enumerate(lines, 1):
        path = os.path.join(a.out, f'line{i:02d}.mp3')
        if a.only and i not in a.only and os.path.exists(path):
            continue
        r, p = await record(say, path, a.voice, a.rate, a.pitch)
        note = '' if (r, p) == (a.rate, a.pitch) else f'  (read at {r} {p})'
        print(f'ok line{i:02d}.mp3  {seconds(path):.2f}s  {say}{note}')

    gap = silence(a.gap, os.path.join(a.out, 'line01.mp3'))
    meta, t, srt = [], 0.0, []
    with open(os.path.join(a.out, 'voice_full.mp3'), 'wb') as full:
        for i, (say, sub) in enumerate(lines, 1):
            name = f'line{i:02d}.mp3'; d = seconds(os.path.join(a.out, name))
            with open(os.path.join(a.out, name), 'rb') as f:
                full.write(f.read())
            meta.append({'file': name, 'say': say, 'sub': sub, 'start': round(t, 3), 'end': round(t + d, 3), 'duration': round(d, 3)})
            srt.append(f'{i}\n{stamp(t)} --> {stamp(t + d)}\n{sub}\n')
            t += d
            if gap and i < len(lines):
                full.write(gap); t += len(gap) * 8 / KBPS
    with open(os.path.join(a.out, 'subtitles.srt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(srt))
    with open(os.path.join(a.out, 'lines.json'), 'w', encoding='utf-8') as f:
        json.dump({'voice': a.voice, 'rate': a.rate, 'pitch': a.pitch, 'gap': a.gap, 'total': round(t, 2), 'lines': meta}, f, ensure_ascii=False, indent=1)
    print(f'done: {len(lines)} lines, {t:.1f}s total -> {os.path.abspath(a.out)}')


asyncio.run(main())
