# Third-party code and models

## helpers/ — from browser-use/video-use (MIT)

`helpers/transcribe.py`, `render.py` and `grade.py` come from
[browser-use/video-use](https://github.com/browser-use/video-use) at commit `43cfc56`, under the MIT
licence in `helpers/LICENSE-video-use`. Changes made here:

- `transcribe.py`: `TRANSCRIBE_BACKEND=local` switch to free offline transcription; `.env` read as UTF-8.
- `transcribe_local.py` (new): faster-whisper backend that writes ElevenLabs-Scribe-shaped JSON;
  `WHISPER_VAD=0` to keep quiet or excited speech.
- `render.py`, `grade.py`: Windows paths escaped correctly inside ffmpeg filter graphs.

## Models and libraries downloaded at install or first use (not stored in this repo)

| Item | Licence | Note |
|------|---------|------|
| [VieNeu-TTS v3 Turbo](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo) (`vieneu`) | Apache-2.0 | Vietnamese voice; commercial use allowed; adds an inaudible AI watermark by default |
| [MOSS-Audio-Tokenizer-Nano](https://huggingface.co/OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano) | see model card | used by VieNeu |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + Whisper large-v3 | MIT | offline transcription |
| [FFmpeg](https://ffmpeg.org) (Gyan.FFmpeg build via winget) | GPL | cutting, effects, encoding |
| PyTorch, FastAPI, Uvicorn, NumPy, soundfile | BSD / MIT | |
