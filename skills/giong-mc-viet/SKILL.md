---
name: giong-mc-viet
description: Records Vietnamese voiceover, by default OFFLINE with VieNeu-TTS v3 (preset voice "Hải Đăng", temperature 0.3, top_k 10 — the user picked this after comparing many models), or online with Microsoft edge-tts (vi-VN-NamMinhNeural, rate +6%, pitch +3Hz) for the energetic ad-MC voice used in earlier videos. Produces one MP3 per line plus a joined voice track, an SRT subtitle file and lines.json. Use this whenever the user wants Vietnamese narration, lồng tiếng, giọng đọc, giọng MC, giọng AI, lời thoại, voice-over or thuyết minh for a video, ad, promo, TikTok/Reels clip, slideshow or game trailer, or asks to reuse "giọng đọc như video trước" / "giọng MC quảng cáo", even if they don't name a tool.
---

# Giọng đọc tiếng Việt (VieNeu offline / edge-tts)

Two engines, same script format and same output files:

| Engine | When | Voice |
|--------|------|-------|
| **VieNeu-TTS v3 (offline, default)** | everyday use, no internet needed, also when edge-tts keeps failing | preset **Hải Đăng** (male, northern, natural), `temperature 0.3`, `top_k 10` |
| edge-tts (online) | the user asks for "giọng như video trước" / the game-promo MC voice | `vi-VN-NamMinhNeural`, `rate +6%`, `pitch +3Hz` |

**Why these settings:** the user compared viXTTS, F5-TTS (two Vietnamese checkpoints), OmniVoice and VieNeu presets. They rejected the others as robotic, with unclear tones and words that weren't "tròn chữ". VieNeu Hải Đăng at temperature 0.3 was the first one they called "đã ổn". Lower temperature gives crisper articulation; don't raise it back to the library default (0.8) unless the user wants more expressive variety.

## 1. Write the script

The voice is only as lively as the words. Write lines the way a TV/TikTok ad MC talks:

- **Short lines**, about 5–15 words each, one idea per line. Each line becomes one subtitle and one MP3, which makes syncing with video scenes easy.
- **Spoken vs subtitle text.** TTS reads digits oddly, so spell numbers out in the spoken text ("hai mươi loài") and keep digits in the subtitle ("20 loài"). Write `spoken | subtitle` on one line; if both are the same, just write the sentence.
- **Southern MC flavour** through word choice: "nè", "nha", "hông", "luôn á", "thiệt", "liền", "vô", "hết sẩy", "bạn ơi!". Use them lightly; one or two per line is plenty.
- Exclamation marks and question marks make the voice rise and sound excited; commas add small pauses; "..." makes a dramatic pause.
- End with a clear call to action (link, "tải ngay", "rủ bạn bè").

Show the script to the user before recording if they haven't approved the wording yet. Re-recording is cheap, but their time isn't.

## 2a. Record offline with VieNeu (default)

Run `scripts/record_voice_offline.py` with the **VieNeu environment's Python** (not the system Python):

```bash
~/Developer/tts-vi/.venv-vieneu/Scripts/python <skill-dir>/scripts/record_voice_offline.py script.txt --out voice
```

Options:
- `--voice "Adam"`: another preset. Southern: Adam, Thái Sơn, Minh Triết, Đức Trí (male); Mỹ Duyên, Thùy Dung, Thục Đoan, Kim Thanh (female). Northern: Hải Đăng, Trúc Ly, Mai Anh, Thiện Minh, … Central: Quang Sơn, Ngọc Trân. List them all with `Vieneu().list_preset_voices()`.
- `--ref clip.wav`: clone a voice from a clean 3–8 s clip instead of a preset. Only clone a voice the user owns or has permission to use.
- `--speed 1.06`: faster or slower without changing pitch (ffmpeg atempo). Stay within about 0.9–1.15.
- `--temperature 0.3 --top-k 10`: the approved defaults.
- `--gap 0.4`, `--only 3 5`: same as edge-tts below.

Speed: about 1 s per line on the RTX 3050 GPU (CPU works too, slower). The first run loads the model (~45 s).

Output is the same as edge-tts (table below), plus `lineNN.wav` and `voice_full.wav`: lossless 48 kHz copies for editing. Durations come from the samples, so they are exact.

Things to tell the user when relevant:
- **Licence:** VieNeu-TTS v3 is Apache-2.0, so it is fine for commercial work (ads, client videos).
- **Watermark:** the library embeds an inaudible AI watermark by default. Leave it on, especially for cloned voices.
- Southern presets merge hỏi/ngã ("quãng" sounds like "quảng"). That is the accent, not a bug.

**Setting up on a new machine** (Windows, NVIDIA GPU; ~3 GB download):

```bash
python -m venv ~/Developer/tts-vi/.venv-vieneu
~/Developer/tts-vi/.venv-vieneu/Scripts/python -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
~/Developer/tts-vi/.venv-vieneu/Scripts/python -m pip install "transformers==4.57.6" vieneu
```

Without an NVIDIA GPU, skip the torch line: `pip install vieneu` alone runs on CPU via ONNX. ffmpeg must be on PATH (`winget install Gyan.FFmpeg`). The model (~260 MB) downloads on first use.

## 2b. Record online with edge-tts

Requires Python and edge-tts (`python -m pip install --user edge-tts`; it needs internet). Then run:

```bash
python <skill-dir>/scripts/record_voice.py script.txt --out voice
```

Options: `--voice vi-VN-HoaiMyNeural` (female), `--rate +10%`, `--pitch +0Hz`, `--gap 0.4` (seconds of silence between lines in the joined track), `--only 3 5` (re-record just those lines after editing them; the others are kept).

Microsoft has no truly southern Vietnamese voice: NamMinh has a standard northern accent, and the southern feel comes from the wording. If the user wants a real southern accent, use a southern VieNeu preset instead.

Durations are worked out from the MP3 size (edge-tts writes constant 48 kbps), so they are accurate to a few hundredths of a second. Each clip has roughly 0.1–0.3 s of silence at the start and end; if exact lip-sync matters, trim it in the editor.

The free service drops many requests at random ("No audio was received"), often several in a row. The script retries with short waits, nudging rate/pitch by one inaudible step each time, and only as a last resort reads at plain settings. A line that needed a nudge is printed with "(read at …)"; if it was read at `+0% +0Hz`, re-record it with `--only <number>`. If the service keeps failing, switch to VieNeu (2a).

## Output (both engines)

| File | Use |
|------|-----|
| `line01.mp3`, `line02.mp3`, … | one clip per line, for placing scene by scene |
| `voice_full.mp3` | all lines joined with the gap, ready to drop into CapCut / Premiere |
| `subtitles.srt` | subtitles timed to `voice_full.mp3` (uses the subtitle text) |
| `lines.json` | spoken text, subtitle text, file name, start/end and duration of each line |

## 3. Use it in a video

- Sum the durations in `lines.json` to check the length against the target (for example 45 s). To lengthen, add a longer `--gap` or a longer ending; to shorten, cut words. Don't speed the voice up past ~+15%, or it starts to sound rushed.
- When building the video yourself (canvas/WebCodecs, ffmpeg, etc.), put music at roughly a quarter of the voice level and duck it while each line plays. The voice must stay clearly on top.
- Optional check: transcribe `voice_full.mp3` with local Whisper and compare it with the script to catch misread words before handing the files over.
- Tell the user which engine, voice and settings were used, and where the files are.
