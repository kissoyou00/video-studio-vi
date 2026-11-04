"""Record a Vietnamese voiceover OFFLINE with VieNeu-TTS v3: same outputs as record_voice.py
(one MP3 per line, voice_full.mp3, subtitles.srt, lines.json) plus a lossless lineNN.wav per line.

Run with the VieNeu environment's Python, not the system one:
    ~/Developer/tts-vi/.venv-vieneu/Scripts/python record_voice_offline.py script.txt [--out voice]
        [--voice "Hải Đăng"] [--ref my_voice.wav] [--speed 1.06] [--gap 0.4] [--only 3 5]
        [--temperature 0.3] [--top-k 10]
Script: UTF-8 text, one voice line per line; "spoken text | subtitle text" when they differ; blank lines and # comments are skipped.
Needs ffmpeg on PATH (MP3 encoding and --speed).
"""
import argparse, json, os, shutil, subprocess, sys

import numpy as np
import soundfile as sf

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')   # Vietnamese text on Windows consoles
except Exception:
    pass
try:
    from vieneu import Vieneu
except ImportError:
    sys.exit('vieneu is not installed in this Python. Run this script with ~/Developer/tts-vi/.venv-vieneu/Scripts/python')

SR = 48000   # VieNeu v3 Turbo output rate


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


def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *args], check=True)


def stamp(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('script'); ap.add_argument('--out', default='voice')
    ap.add_argument('--voice', default='Hải Đăng', help='VieNeu preset name (ignored when --ref is given)')
    ap.add_argument('--ref', default=None, help='3-8 s clean clip to clone instead of a preset')
    ap.add_argument('--speed', type=float, default=1.0, help='tempo without pitch change, e.g. 1.06 = 6%% faster')
    ap.add_argument('--temperature', type=float, default=0.3); ap.add_argument('--top-k', type=int, default=10)
    ap.add_argument('--gap', type=float, default=0.4); ap.add_argument('--only', type=int, nargs='*', default=[])
    a = ap.parse_args()
    if not shutil.which('ffmpeg'):
        sys.exit('ffmpeg is not on PATH (winget install Gyan.FFmpeg, then open a new terminal)')
    lines = parse(a.script)
    if not lines:
        sys.exit('the script has no lines')
    os.makedirs(a.out, exist_ok=True)

    tts = Vieneu()
    who = dict(ref_audio=a.ref) if a.ref else dict(voice=a.voice)
    for i, (say, _) in enumerate(lines, 1):
        wav_path = os.path.join(a.out, f'line{i:02d}.wav')
        if a.only and i not in a.only and os.path.exists(wav_path):
            continue
        audio = tts.infer(say, **who, temperature=a.temperature, top_k=a.top_k)
        sf.write(wav_path, np.asarray(audio, dtype=np.float32), SR)
        if abs(a.speed - 1.0) > 1e-3:   # atempo keeps the pitch, unlike resampling
            tmp = wav_path + '.tmp.wav'
            ffmpeg('-i', wav_path, '-af', f'atempo={a.speed}', '-ar', str(SR), tmp)
            os.replace(tmp, wav_path)
        ffmpeg('-i', wav_path, '-c:a', 'libmp3lame', '-b:a', '192k', os.path.join(a.out, f'line{i:02d}.mp3'))
        print(f'ok line{i:02d}.mp3  {sf.info(wav_path).duration:.2f}s  {say}')

    gap = np.zeros(int(round(a.gap * SR)), dtype=np.float32)
    parts, meta, srt, t = [], [], [], 0.0
    for i, (say, sub) in enumerate(lines, 1):
        name = f'line{i:02d}'
        audio, sr = sf.read(os.path.join(a.out, name + '.wav'), dtype='float32')
        d = len(audio) / sr
        parts.append(audio)
        meta.append({'file': name + '.mp3', 'say': say, 'sub': sub, 'start': round(t, 3), 'end': round(t + d, 3), 'duration': round(d, 3)})
        srt.append(f'{i}\n{stamp(t)} --> {stamp(t + d)}\n{sub}\n')
        t += d
        if len(gap) and i < len(lines):
            parts.append(gap); t += len(gap) / SR
    full_wav = os.path.join(a.out, 'voice_full.wav')
    sf.write(full_wav, np.concatenate(parts), SR)
    ffmpeg('-i', full_wav, '-c:a', 'libmp3lame', '-b:a', '192k', os.path.join(a.out, 'voice_full.mp3'))
    with open(os.path.join(a.out, 'subtitles.srt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(srt))
    with open(os.path.join(a.out, 'lines.json'), 'w', encoding='utf-8') as f:
        json.dump({'engine': 'vieneu-v3-turbo', 'voice': a.ref or a.voice, 'temperature': a.temperature, 'top_k': a.top_k,
                   'speed': a.speed, 'gap': a.gap, 'total': round(t, 2), 'lines': meta}, f, ensure_ascii=False, indent=1)
    print(f'done: {len(lines)} lines, {t:.1f}s total -> {os.path.abspath(a.out)}')


main()
