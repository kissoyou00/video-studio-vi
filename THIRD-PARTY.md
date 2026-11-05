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
| [Ollama](https://ollama.com) (via winget) | MIT | runs the offline script-writing model |
| [Gemma 3 4B](https://ollama.com/library/gemma3) (`gemma3:4b`) | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) | default offline script writer; commercial use allowed under Google's terms and prohibited-use policy |
| [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) (`anthropic`) | MIT | optional Claude engine, user's own API key |
| [rembg](https://github.com/danielgatis/rembg) + `u2net_human_seg` model | MIT / Apache-2.0 | cuts the presenter ("người mẫu") out of their photo |
| [SadTalker](https://github.com/OpenTalker/SadTalker) at commit `cd4c046` (optional, `install_talker.ps1`) | Apache-2.0 | lip-syncs the presenter's photo to the voice; downloaded into `talker/`, patched by `helpers/patch_sadtalker.py`. Its README forbids uses that infringe portrait rights; the app asks for the person's permission. SadTalker ships 3D face model files derived from the Basel Face Model, which has its own terms; check them before commercial use. |
| [facexlib](https://github.com/xinntao/facexlib) detection/alignment weights | MIT | face detection for SadTalker |
| PyTorch, FastAPI, Uvicorn, NumPy, soundfile, Pillow | BSD / MIT / HPND | |

Claude and Gemini are paid or quota-limited online services used only with the user's own API key,
under the provider's terms.
