"""Local, free transcription backend: faster-whisper, Scribe-shaped output.

Used by transcribe.py when `.env` (or the environment) sets
TRANSCRIBE_BACKEND=local. Returns the same JSON shape Scribe does — a `words`
list of `word` / `spacing` entries with start/end and speaker_id — so
pack_transcripts.py, render.py and timeline_view.py work unchanged.

Differences from Scribe, worth knowing at edit time:
  - Whisper tends to drop fillers ("um", "ừm", "à"). An initial prompt full of
    fillers nudges it toward verbatim, but expect some to be missing; check
    suspicious gaps with timeline_view before trusting them as silence.
  - Word timestamps drift more than Scribe's. Pad cuts toward the looser end
    of the 30–200ms window.
  - No diarization and no audio events: every word is speaker_0.

Settings (env or .env): WHISPER_MODEL (default large-v3), WHISPER_DEVICE
(default cuda, falls back to cpu), WHISPER_COMPUTE (default int8_float16 on
cuda, int8 on cpu).

Standalone test:
    python helpers/transcribe_local.py <16khz_mono.wav> [--language vi]
"""

from __future__ import annotations

import os
import sys
import threading
import wave
from pathlib import Path

import numpy as np


def _add_cuda_dll_dirs() -> None:
    """Windows: make the pip-installed cuBLAS/cuDNN DLLs loadable by ctranslate2."""
    if os.name != "nt":
        return
    try:
        import nvidia  # namespace package from nvidia-cublas-cu12 / nvidia-cudnn-cu12
    except ImportError:
        return
    for root in nvidia.__path__:
        for bin_dir in Path(root).glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


_add_cuda_dll_dirs()

from faster_whisper import WhisperModel  # noqa: E402


# Nudges Whisper to keep disfluencies instead of cleaning them up. The prompt must be
# in the audio's language and properly punctuated: a mixed-language one makes Whisper
# drop capitals and punctuation, which render.py's caption chunking relies on.
FILLER_PROMPTS = {
    "vi": "Ừm, à, ờ, thì, kiểu như là, ừ, ơ... Ừm, tôi nghĩ là, à, cái này.",
    "en": "Umm, uh, like, you know, I mean... Uh, so, um, yeah.",
}

_model: WhisperModel | None = None
_model_lock = threading.Lock()
# One GPU, one model: batch mode's worker threads take turns instead of each
# loading a copy (4 copies of large-v3 do not fit in 4 GB).
_run_lock = threading.Lock()


def _setting(name: str, default: str) -> str:
    from transcribe import read_dotenv  # same directory
    return os.environ.get(name) or read_dotenv().get(name) or default


def get_model() -> WhisperModel:
    global _model
    with _model_lock:
        if _model is None:
            name = _setting("WHISPER_MODEL", "large-v3")
            device = _setting("WHISPER_DEVICE", "cuda")
            compute = _setting("WHISPER_COMPUTE", "int8_float16" if device == "cuda" else "int8")
            try:
                _model = WhisperModel(name, device=device, compute_type=compute)
            except Exception as e:
                if device != "cuda":
                    raise
                print(f"  cuda unavailable ({e}); falling back to cpu", flush=True)
                _model = WhisperModel(name, device="cpu", compute_type="int8")
        return _model


def _load_wav(audio_path: Path) -> np.ndarray:
    """16-bit wav → float32 samples. Read here rather than by faster-whisper, whose
    PyAV decoder breaks across av versions; transcribe.py already made it 16 kHz mono."""
    with wave.open(str(audio_path), "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{audio_path.name}: expected 16 kHz mono 16-bit wav")
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def call_whisper(audio_path: Path, language: str | None = None) -> dict:
    """Transcribe a 16 kHz mono wav and return a Scribe-shaped dict."""
    model = get_model()
    audio = _load_wav(audio_path)
    with _run_lock:
        if not language:
            language, _prob, _all = model.detect_language(audio)
        segments, info = model.transcribe(
            audio,
            language=language,
            word_timestamps=True,
            initial_prompt=FILLER_PROMPTS.get(language),
            condition_on_previous_text=False,  # limits repetition loops on long takes
            # VAD can drop excited or quiet speech and shift the first word's timing;
            # WHISPER_VAD=0 keeps everything (at the risk of a stray word over music).
            vad_filter=_setting("WHISPER_VAD", "1") != "0",
            beam_size=5,
        )
        raw_words = [w for seg in segments for w in (seg.words or [])]

    words: list[dict] = []
    prev_end: float | None = None
    for w in raw_words:
        text = w.word.strip()
        if not text:
            continue
        start, end = round(w.start, 3), round(w.end, 3)
        if prev_end is not None and start > prev_end:
            words.append({"text": " ", "start": prev_end, "end": start, "type": "spacing",
                          "speaker_id": "speaker_0"})
        words.append({"text": text, "start": start, "end": end, "type": "word",
                      "speaker_id": "speaker_0", "logprob": round(w.probability, 4)})
        prev_end = end

    return {
        "language_code": info.language,
        "language_probability": round(info.language_probability, 4),
        "text": " ".join(w["text"] for w in words if w["type"] == "word"),
        "words": words,
        "backend": "faster-whisper",
    }


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Test the local Whisper backend on one file")
    ap.add_argument("path", type=Path)
    ap.add_argument("--language", default=None)
    args = ap.parse_args()
    result = call_whisper(args.path, args.language)
    print(json.dumps({k: v for k, v in result.items() if k != "words"}, ensure_ascii=False, indent=2))
    for w in [w for w in result["words"] if w["type"] == "word"][:30]:
        print(f"  {w['start']:7.2f}-{w['end']:7.2f}  {w['text']}")
    sys.exit(0)
