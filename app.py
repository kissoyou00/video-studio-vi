"""Video Studio — local web app: dựng video (local Whisper + video-use render.py) and Vietnamese voiceover (VieNeu-TTS).

Started by launch.py (Desktop shortcut, no console) or start.bat (console, for debugging); install.ps1
sets up both Python environments. Data lives in ~/VideoStudio/{projects,voices,refs}; nothing is
written inside this folder.

Transcription and rendering run as subprocesses of the Whisper environment (.venv-whisper), calling
helpers/transcribe.py and helpers/render.py. Voice generation runs in-process (.venv) so the VieNeu
model stays loaded. A 4 GB card fits one model at a time, so GPU jobs are serialised and the voice
model is unloaded before Whisper runs.
"""

from __future__ import annotations

import gc
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
HOME = Path.home()
WORK = Path(os.environ.get("STUDIO_HOME", HOME / "VideoStudio"))
PROJECTS, VOICES, REFS = WORK / "projects", WORK / "voices", WORK / "refs"
HELPERS = HERE / "helpers"   # vendored from browser-use/video-use (MIT), patched for Windows + local Whisper


def _whisper_python() -> Path:
    """Python that runs transcribe.py / render.py (needs faster-whisper). install.ps1 makes
    .venv-whisper; the older hand setup used the system Python 3.12."""
    for cand in (os.environ.get("STUDIO_WHISPER_PYTHON"), HERE / ".venv-whisper" / "Scripts" / "python.exe",
                 HOME / "AppData/Local/Programs/Python/Python312/python.exe"):
        if cand and Path(cand).exists():
            return Path(cand)
    return Path(sys.executable)


SYS_PY = _whisper_python()
for _d in (PROJECTS, VOICES, REFS):
    _d.mkdir(parents=True, exist_ok=True)

_links = HOME / "AppData/Local/Microsoft/WinGet/Links"   # winget's ffmpeg
if _links.exists() and str(_links) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = str(_links) + os.pathsep + os.environ.get("PATH", "")
# The app runs under pythonw (no console); without this every ffmpeg/Python child would flash a
# black window. Grandchildren (render.py's ffmpeg calls) inherit the hidden console.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# Children must not inherit this venv's identity: the Windows venv launcher sets __PYVENV_LAUNCHER__,
# and a plain python.exe that inherits it loads *this* venv's site-packages (ModuleNotFoundError: idna).
_VENV_VARS = {"__PYVENV_LAUNCHER__", "VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH"}
ENV = {**{k: v for k, v in os.environ.items() if k.upper() not in _VENV_VARS},
       "PYTHONUTF8": "1", "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
       "TRANSCRIBE_BACKEND": "local",   # helpers/transcribe.py → free offline faster-whisper, no API key
       "WHISPER_VAD": "0"}  # VAD drops excited/quiet speech; for editing, missing words are worse than extra ones

sys.path.insert(0, str(HELPERS))
import scriptgen  # noqa: E402
from grade import PRESETS as GRADE_PRESETS  # noqa: E402
from render import SUB_FORCE_STYLE, build_master_srt  # noqa: E402

SR = 48000
ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
GRADES = {"none": "", "subtle": GRADE_PRESETS["subtle"], "punch": GRADE_PRESETS["neutral_punch"],
          "warm": GRADE_PRESETS["warm_cinematic"]}
FILLERS = {"ừm", "ừ", "ờ", "ơ", "à", "uh", "um", "umm", "uhm", "hmm", "ờm", "ừmm", "ơ ơ"}
PRESET_VOICES = [  # (name, gender, region, style) — from Vieneu().list_preset_voices(), v3.8.3
    ("Hải Đăng", "Nam", "Bắc", "Tự nhiên"), ("Adam bựa", "Nam", "Bắc", "Tự nhiên"), ("Thiện Minh", "Nam", "Bắc", "Kể chuyện"),
    ("Thiền Tâm Đức", "Nam", "Bắc", "Kể chuyện"), ("Minh Đức", "Nam", "Bắc", "Tin tức"), ("Phạm Tuyên", "Nam", "Bắc", "Tự nhiên"),
    ("Xuân Vĩnh", "Nam", "Bắc", "Tự nhiên"), ("Thanh Bình", "Nam", "Bắc", "Kể chuyện"), ("Quốc Tuấn", "Nam", "Bắc", "Tự nhiên"),
    ("Trúc Ly", "Nữ", "Bắc", "Tự nhiên"), ("Mai Anh", "Nữ", "Bắc", "Tin tức"), ("Ngọc Huyền", "Nữ", "Bắc", "Tự nhiên"),
    ("Ngọc Linh", "Nữ", "Bắc", "Kể chuyện"), ("Đoan Trang", "Nữ", "Bắc", "Tự nhiên"), ("Quỳnh Anh", "Nữ", "Bắc", "Đọc truyện"),
    ("Adam", "Nam", "Nam", "Tự nhiên"), ("Thái Sơn", "Nam", "Nam", "Kể chuyện"), ("Minh Triết", "Nam", "Nam", "Tin tức"),
    ("Đức Trí", "Nam", "Nam", "Đọc truyện"), ("Thùy Dung", "Nữ", "Nam", "Tin tức"), ("Thục Đoan", "Nữ", "Nam", "Kể chuyện"),
    ("Mỹ Duyên", "Nữ", "Nam", "Đọc truyện"), ("Kim Thanh", "Nữ", "Nam", "Đọc truyện"),
    ("Quang Sơn", "Nam", "Trung", "Tự nhiên"), ("Ngọc Trân", "Nữ", "Trung", "Tự nhiên"),
]
DEFAULT_SETTINGS = {
    "aspect": "9:16", "grade": "subtle", "subtitles": "speech", "language": "vi",
    "max_pause": 0.8, "remove_fillers": False, "pad_ms": 120,
    "orig_volume": 1.0, "voice_id": "", "voice_offset": 0.0, "voice_volume": 1.0,
    "music": "", "music_volume": 0.25, "duck": True,
    # editing effects (tick boxes in the UI); text effects carry their own text
    "fx_fade": False, "fx_transition": "none", "fx_jump_zoom": False, "fx_ken_burns": False,
    "fx_freeze_end": False, "fx_hook_on": False, "fx_hook": "", "fx_lower_on": False, "fx_lower": "",
    "fx_end_on": False, "fx_end": "Cảm ơn mọi người đã xem!", "fx_watermark_on": False, "fx_watermark": "",
    "fx_progress": False, "fx_letterbox": False, "fx_vignette": False, "fx_sharpen": False,
    "fx_denoise": False, "fx_whoosh": False,
}
FREEZE_S = 2.0
FONT_BLACK = "C:/Windows/Fonts/seguibl.ttf"
FONT_BOLD = "C:/Windows/Fonts/segoeuib.ttf"
ACCENT = "0xD94F2B"

app = FastAPI(title="Video Studio")
PLOCK = threading.RLock()   # project.json read-modify-write
GPU = threading.Lock()      # one GPU user at a time (4 GB card)
JOBS: dict[str, dict] = {}


# -------- helpers ------------------------------------------------------------

def slug(name: str, fallback: str = "file") -> str:
    s = unicodedata.normalize("NFKD", name.replace("đ", "d").replace("Đ", "D")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:40].strip("-") or fallback


def safe_id(x: str) -> str:
    """Validate an id taken from a URL or settings. Never re-slug ids: an id made by an older
    slug() may end in '-', and re-slugging it would point at a folder that doesn't exist."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,80}", x or ""):
        raise HTTPException(400, "Mã không hợp lệ")
    return x


def voice_dir(vid: str) -> Path | None:
    if not vid:
        return None
    d = VOICES / safe_id(vid)
    return d if (d / "lines.json").exists() else None


def unique(path: Path) -> Path:
    if not path.exists():
        return path
    for k in range(2, 1000):
        cand = path.with_name(f"{path.stem}-{k}{path.suffix}")
        if not cand.exists():
            return cand
    raise RuntimeError("too many files with the same name")


def rel(path: Path) -> str:
    return path.resolve().relative_to(WORK.resolve()).as_posix()


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height:stream_side_data=rotation", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    d = json.loads(out.stdout or "{}")
    streams = d.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    rot = next((sd["rotation"] for sd in (v.get("side_data_list") or []) if sd.get("rotation") is not None), 0)
    if int(round(float(rot))) % 180:
        w, h = h, w
    return {"duration": round(float((d.get("format") or {}).get("duration") or 0), 3), "width": w, "height": h,
            "has_video": bool(v), "has_audio": any(s.get("codec_type") == "audio" for s in streams)}


def ffmpeg(*args: str) -> None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    if r.returncode:
        raise RuntimeError("ffmpeg: " + r.stderr.strip()[-600:])


def srt_stamp(t: float) -> str:
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# -------- jobs ---------------------------------------------------------------

def start_job(kind: str, fn, *args) -> str:
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"id": jid, "kind": kind, "status": "running", "log": [], "result": None, "error": None,
                 "started": time.time(), "finished": None}

    def run() -> None:
        job = JOBS[jid]
        try:
            job["result"] = fn(job, *args)
            job["status"] = "done"
        except Exception as e:  # surfaced to the UI
            job["status"] = "error"
            job["error"] = str(e)
            job["log"].append(traceback.format_exc()[-1500:])
        job["finished"] = time.time()

    threading.Thread(target=run, daemon=True).start()
    return jid


def log(job: dict, msg: str) -> None:
    job["log"].append(msg)
    del job["log"][:-300]


def run_cmd(job: dict, cmd: list, cwd: Path | None = None) -> None:
    log(job, "$ " + " ".join(Path(str(c)).name if i < 2 else str(c) for i, c in enumerate(cmd[:6])) + (" …" if len(cmd) > 6 else ""))
    p = subprocess.Popen([str(c) for c in cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", env=ENV, creationflags=NO_WINDOW)
    for line in p.stdout:
        line = line.rstrip()
        if line and "Warning" not in line and "warn(" not in line:
            log(job, line)
    if p.wait():
        raise RuntimeError(f"Lệnh lỗi (mã {p.returncode}). Dòng cuối: " + " | ".join(job["log"][-3:]))


# -------- voice model (in-process, lazily loaded) -----------------------------

class TTS:
    model = None

    @classmethod
    def get(cls, job: dict):
        if cls.model is None:
            log(job, "Đang nạp model giọng VieNeu (lần đầu mất khoảng 45 giây)…")
            from vieneu import Vieneu
            cls.model = Vieneu()
            log(job, "Đã nạp model giọng.")
        return cls.model

    @classmethod
    def unload(cls, job: dict | None = None) -> None:
        if cls.model is not None:
            cls.model = None
            gc.collect()
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
            if job:
                log(job, "Đã giải phóng bộ nhớ card đồ hoạ cho Whisper.")


# -------- projects -----------------------------------------------------------

def pdir_of(pid: str) -> Path:
    d = PROJECTS / safe_id(pid)
    if not (d / "project.json").exists():
        raise HTTPException(404, "Không tìm thấy dự án")
    return d


def load(pid: str) -> dict:
    p = json.loads((pdir_of(pid) / "project.json").read_text(encoding="utf-8"))
    p["settings"] = {**DEFAULT_SETTINGS, **p.get("settings", {})}
    return p


def save(pid: str, p: dict) -> None:
    path = pdir_of(pid) / "project.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def transcript_path(pdir: Path, sid: str) -> Path:
    return pdir / "edit" / "transcripts" / f"{sid}.json"


# Whisper's stock hallucinations over music or silence (it was trained on YouTube outros).
HALLUCINATION = re.compile(r"đăng ký kênh|ủng hộ kênh|subscribe|cảm ơn các bạn đã (xem|theo dõi)|hẹn gặp lại các bạn|"
                           r"ghiền mì gõ|la la school|thank(s| you) for watching", re.I)


def words_of(pdir: Path, sid: str) -> list[dict]:
    """Transcript words, minus whole sentences that are known Whisper hallucinations. Deterministic,
    so the word indices stored in `removed` stay valid."""
    tp = transcript_path(pdir, sid)
    if not tp.exists():
        return []
    data = json.loads(tp.read_text(encoding="utf-8"))
    words = [{"t": w["text"], "s": w["start"], "e": w["end"]}
             for w in data.get("words", []) if w.get("type") == "word" and w.get("start") is not None]
    out, sentence = [], []
    for w in words:
        sentence.append(w)
        if w["t"].rstrip().endswith((".", "!", "?")) or w is words[-1]:
            if not HALLUCINATION.search(" ".join(x["t"] for x in sentence)):
                out += sentence
            sentence = []
    return out


def norm_word(t: str) -> str:
    return re.sub(r"[^\w\s]", "", t.lower()).strip()


def plan(p: dict, pdir: Path) -> tuple[list[dict], float]:
    """Kept ranges from the transcript edits. Cut edges snap to word boundaries, padded but never
    reaching into a neighbouring (removed) word; pauses longer than max_pause become cuts."""
    s = p["settings"]
    pad = max(0.0, float(s["pad_ms"])) / 1000
    max_pause = float(s["max_pause"] or 0)
    ranges: list[dict] = []
    for src in p["sources"]:
        if not src.get("include", True):
            continue
        dur = float(src["duration"])
        words = words_of(pdir, src["id"])
        if src.get("mode") == "full" or not words:
            a = max(0.0, float(src.get("trim_start") or 0))
            b = dur - max(0.0, float(src.get("trim_end") or 0)) - 0.05
            if b - a > 0.2:
                ranges.append({"source": src["id"], "start": round(a, 3), "end": round(b, 3), "beat": "nguyên clip"})
            continue
        removed = set(src.get("removed") or [])
        groups: list[list[int]] = []
        for i, w in enumerate(words):
            if i in removed or (s["remove_fillers"] and norm_word(w["t"]) in FILLERS):
                continue
            g = groups[-1] if groups else None
            if g and g[-1] == i - 1 and not (max_pause and w["s"] - words[i - 1]["e"] > max_pause):
                g.append(i)
            else:
                groups.append([i])
        segs: list[list[float]] = []
        for g in groups:
            first, last = g[0], g[-1]
            lo = words[first - 1]["e"] if first > 0 else 0.0
            hi = words[last + 1]["s"] if last + 1 < len(words) else dur - 0.05
            a = max(lo, words[first]["s"] - pad, 0.0)
            b = min(hi, words[last]["e"] + pad, dur - 0.05)
            if segs and a <= segs[-1][1] + 0.05:
                segs[-1][1] = max(segs[-1][1], b)
            elif b - a > 0.1:
                segs.append([a, b])
        for a, b in segs:
            ranges.append({"source": src["id"], "start": round(a, 3), "end": round(b, 3), "beat": "lời nói"})
    return ranges, round(sum(r["end"] - r["start"] for r in ranges), 2)


def out_dims(p: dict) -> tuple[int, int]:
    if p["settings"]["aspect"] in ASPECTS:
        return ASPECTS[p["settings"]["aspect"]]
    src = next((x for x in p["sources"] if x.get("include", True) and x.get("width")), None)
    if not src:
        return 1080, 1920
    k = 1920 / max(src["width"], src["height"])
    return int(src["width"] * k) // 2 * 2, int(src["height"] * k) // 2 * 2


# -------- jobs: transcribe / render / voice ----------------------------------

def job_transcribe(job: dict, pid: str, language: str) -> dict:
    pdir = pdir_of(pid)
    with GPU:
        TTS.unload(job)
        for src in load(pid)["sources"]:
            if transcript_path(pdir, src["id"]).exists():
                continue
            if not src.get("has_audio"):
                log(job, f"{src['name']}: không có âm thanh, giữ nguyên cả clip.")
                continue
            log(job, f"Đang chuyển giọng nói thành chữ: {src['name']}")
            cmd = [SYS_PY, HELPERS / "transcribe.py", pdir / src["file"], "--edit-dir", pdir / "edit"]
            if language and language != "auto":
                cmd += ["--language", language]
            try:
                run_cmd(job, cmd)
            except RuntimeError as e:
                log(job, f"{src['name']}: không chuyển được ({e}). Giữ nguyên cả clip.")
    with PLOCK:
        p = load(pid)
        for src in p["sources"]:
            n = len(words_of(pdir, src["id"]))
            src["words"] = n
            if "mode" not in src or src.get("mode_auto", True):
                src["mode"] = "speech" if n >= 5 else "full"   # music / B-roll clips stay whole
        save(pid, p)
    return {"ok": True}


def make_whoosh_track(path: Path, cuts: list[float], total: float) -> None:
    """Synthesised whoosh (swept low-passed noise) peaking on each clip change; no stock files."""
    rng = np.random.default_rng(5)
    track = np.zeros(int((total + 1) * SR), dtype=np.float32)
    n, peak = int(0.5 * SR), 0.34
    t = np.arange(n) / SR
    for c in cuts:
        noise = rng.standard_normal(n).astype(np.float32)
        cutoff = 300 + 3500 * np.exp(-((t - peak) / 0.1) ** 2)
        a = np.exp(-2 * np.pi * cutoff / SR)
        out, acc = np.empty(n, dtype=np.float32), 0.0
        for i in range(n):
            acc = a[i] * acc + (1 - a[i]) * noise[i]
            out[i] = acc
        out *= np.where(t < peak, (t / peak) ** 2, np.exp(-(t - peak) / 0.06))
        out *= 0.3 / (np.abs(out).max() + 1e-9)
        i0 = int(max(0.0, c - peak) * SR)
        seg = track[i0:i0 + n]
        seg += out[:len(seg)]
    sf.write(str(path), track[: int(total * SR)], SR)


def mix_audio(job: dict, video: Path, out: Path, s: dict, total: float, scene_cuts: list[float], edit: Path) -> None:
    """total = final length (freeze frame included). Original audio is padded to cover the freeze."""
    inputs: list[str] = ["-i", str(video)]
    a0 = [f"aresample={SR}", "aformat=channel_layouts=stereo"]
    if s.get("fx_denoise"):
        a0.append("afftdn=nf=-25")   # FFT noise reduction on the camera audio only
    a0 += [f"volume={float(s['orig_volume']):.3f}", "apad"]
    parts = [f"[0:a]{','.join(a0)}[a0]"]
    speech = ["[a0]"]
    k = 1
    vdir = voice_dir(s.get("voice_id", ""))
    if s.get("voice_id") and not vdir:
        log(job, "CẢNH BÁO: không tìm thấy bản giọng đọc đã chọn, video sẽ không có giọng đọc AI.")
    if vdir:
        ms = int(max(0.0, float(s["voice_offset"])) * 1000)
        log(job, f"Thêm giọng đọc AI từ giây {ms / 1000:.1f}")
        inputs += ["-i", str(vdir / "voice_full.wav")]
        parts.append(f"[{k}:a]aresample={SR},aformat=channel_layouts=stereo,adelay={ms}:all=1,"
                     f"volume={float(s['voice_volume']):.3f}[a{k}]")
        speech.append(f"[a{k}]")
        k += 1
    if len(speech) > 1:
        parts.append(f"{''.join(speech)}amix=inputs={len(speech)}:duration=first:normalize=0[sp]")
    else:
        parts.append("[a0]anull[sp]")
    music = WORK / s["music"] if s.get("music") else None
    if music and music.exists():
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        parts.append(f"[{k}:a]aresample={SR},aformat=channel_layouts=stereo,volume={float(s['music_volume']):.3f}[mu]")
        if s.get("duck", True):   # music dips under speech and the AI voice
            parts += ["[sp]asplit=2[sp1][sc]",
                      "[mu][sc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[mud]",
                      "[sp1][mud]amix=inputs=2:duration=first:normalize=0[mx]"]
        else:
            parts.append("[sp][mu]amix=inputs=2:duration=first:normalize=0[mx]")
    else:
        parts.append("[sp]anull[mx]")
    k += 1 if music and music.exists() else 0
    last = "[mx]"
    if s.get("fx_whoosh") and scene_cuts:
        wpath = edit / "_whoosh.wav"
        make_whoosh_track(wpath, scene_cuts, total)
        inputs += ["-i", str(wpath)]
        parts.append(f"[{k}:a]aresample={SR},aformat=channel_layouts=stereo[wh]")
        parts.append("[mx][wh]amix=inputs=2:duration=first:normalize=0[mxw]")
        last = "[mxw]"
        log(job, f"Thêm tiếng whoosh ở {len(scene_cuts)} chỗ chuyển clip")
    post = [f"loudnorm=I=-14:TP=-1.5:LRA=11", f"aresample={SR}"]
    if s.get("fx_fade"):
        post += ["afade=t=in:st=0:d=0.4", f"afade=t=out:st={max(0.0, total - 0.7):.2f}:d=0.7"]
    post.append("alimiter=limit=0.84:level=false")
    parts.append(f"{last}{','.join(post)}[out]")
    log(job, "Đang trộn âm thanh (tiếng gốc, giọng đọc, nhạc nền) và chuẩn hoá âm lượng…")
    ffmpeg(*inputs, "-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[out]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(out))


def timeline(ranges: list[dict]) -> list[dict]:
    """Ranges placed on the output timeline, with the kind of cut that starts each one."""
    segs, t = [], 0.0
    for i, r in enumerate(ranges):
        d = r["end"] - r["start"]
        cut = "" if i == 0 else ("scene" if r["source"] != ranges[i - 1]["source"] else "jump")
        segs.append({"a": round(t, 3), "b": round(t + d, 3), "source": r["source"], "kind": r["beat"], "cut": cut})
        t += d
    return segs


def clean_text(text: str) -> str:
    """drawtext can't draw emoji: drop symbols outside the basic planes, keep Vietnamese."""
    return "".join(ch for ch in text if ord(ch) < 0x2190 or unicodedata.category(ch)[0] in "LNPZ").strip()


def fx_lines(edit: Path, name: str, text: str, fontsize: int, width: int) -> list[str]:
    """Wrap text into balanced lines, one file per line for drawtext (no escaping issues).
    One drawtext per line: Segoe UI Black's built-in line gap is far too tall for stacked titles."""
    import math
    import textwrap
    text = clean_text(text)
    per_line = max(8, int(width * 0.86 / (fontsize * 0.56)))
    n = max(1, math.ceil(len(text) / per_line))
    lines = textwrap.wrap(text, max(8, math.ceil(len(text) / n) + 2)) or [" "]   # even lengths, no 1-word tail
    paths = []
    for i, line in enumerate(lines):
        f = edit / f"_fx_{name}_{i}.txt"
        f.write_text(line, encoding="utf-8")
        paths.append(f.as_posix().replace(":", r"\:"))
    return paths


def drawtext_lines(paths: list[str], font: str, fs: int, y0: int, opts: str, x: str = "(w-text_w)/2") -> list[str]:
    step = int(fs * 1.2)
    return [f"drawtext=fontfile='{font}':textfile='{p}':fontsize={fs}:x={x}:y={y0 + i * step}:{opts}"
            for i, p in enumerate(paths)]


def fade_alpha(a: float, b: float, fi: float = 0.25, fo: float = 0.3) -> str:
    return f"if(lt(t,{a + fi:.2f}),(t-{a:.2f})/{fi},if(lt(t,{b - fo:.2f}),1,({b:.2f}-t)/{fo}))"


def apply_video_fx(job: dict, src: Path, dst: Path, s: dict, w: int, h: int, segs: list[dict], total: float,
                   preview: bool, subs: Path | None, edit: Path) -> float:
    """Effects pass on the cut video. Returns the final length. Order: zoom → transitions → look →
    freeze → fades → bars → text → progress bar → subtitles LAST (video-use Hard Rule 1)."""
    chain: list[str] = []
    m = min(w, h)
    font_black = FONT_BLACK.replace(":", r"\:")
    font_bold = FONT_BOLD.replace(":", r"\:")
    scene_cuts = [g["a"] for g in segs if g["cut"] == "scene"]

    zoom_terms = []
    if s.get("fx_jump_zoom"):   # alternate 100% / 108% across jump cuts inside one clip hides the jump
        level = 0
        for g in segs:
            level = 0 if g["cut"] != "jump" else 1 - level
            if level:
                zoom_terms.append(f"0.08*gte(t,{g['a']})*lt(t,{g['b']})")
    if s.get("fx_ken_burns"):   # slow push-in on clips kept whole
        for g in segs:
            if g["kind"] == "nguyên clip" and g["b"] - g["a"] > 2:
                zoom_terms.append(f"0.06*gte(t,{g['a']})*lt(t,{g['b']})*(t-{g['a']})/{g['b'] - g['a']:.3f}")
    if zoom_terms:
        z = "1+" + "+".join(zoom_terms)
        chain += [f"scale=w='trunc({w}*({z})/2)*2':h=-2:eval=frame", f"crop={w}:{h}:x=(iw-ow)/2:y=(ih-oh)*0.4"]

    tr = s.get("fx_transition", "none")
    if tr in ("dip", "flash") and scene_cuts:
        k, width = (-0.9, 0.18) if tr == "dip" else (0.7, 0.12)
        expr = "+".join(f"{k}*max(0,1-abs(t-{c})/{width})" for c in scene_cuts)
        chain.append(f"eq=brightness='{expr}':eval=frame")
    if s.get("fx_sharpen"):
        chain.append("unsharp=5:5:0.7")
    if s.get("fx_vignette"):
        chain.append("vignette=angle=PI/5")

    final = total
    if s.get("fx_freeze_end"):
        chain.append(f"tpad=stop_mode=clone:stop_duration={FREEZE_S}")
        final = total + FREEZE_S
    if s.get("fx_fade"):
        chain += ["fade=t=in:st=0:d=0.5", f"fade=t=out:st={max(0.0, final - 0.7):.2f}:d=0.7"]
    bar_h = 0
    if s.get("fx_letterbox"):
        bar_h = int(h * 0.07) // 2 * 2
        chain += [f"drawbox=x=0:y=0:w=iw:h={bar_h}:color=black:t=fill",
                  f"drawbox=x=0:y={h - bar_h}:w=iw:h={bar_h}:color=black:t=fill"]

    if s.get("fx_hook_on") and s.get("fx_hook", "").strip():
        fs = int(m * 0.085)
        chain += drawtext_lines(fx_lines(edit, "hook", s["fx_hook"], fs, w), font_black, fs, int(h * 0.13) + bar_h,
                                f"fontcolor=0xFFD93D:borderw={max(2, fs // 12)}:bordercolor=black:"
                                f"enable='between(t,0.2,3.3)':alpha='{fade_alpha(0.2, 3.3)}'")
    if s.get("fx_lower_on") and s.get("fx_lower", "").strip() and total > 3:
        fs = int(m * 0.045)
        pad = int(fs * 0.5)
        b = min(5.5, total)
        # sits above the subtitle zone (~65-70% height) so captions are never covered
        x = f"w-text_w-{int(w * 0.06) + pad}" if s.get("fx_lower_align") == "right" else str(int(w * 0.06) + pad)
        chain += drawtext_lines(fx_lines(edit, "lower", s["fx_lower"], fs, int(w * 0.8)), font_bold, fs, int(h * 0.54),
                                f"fontcolor=white:box=1:boxcolor={ACCENT}@0.92:boxborderw={pad}:"
                                f"enable='between(t,1,{b})':alpha='{fade_alpha(1, b)}'", x=x)
    if s.get("fx_end_on") and s.get("fx_end", "").strip():
        fs = int(m * 0.075)
        a = max(0.0, final - 2.6)
        chain += drawtext_lines(fx_lines(edit, "end", s["fx_end"], fs, w), font_black, fs, int(h * 0.38),
                                f"fontcolor=white:borderw={max(2, fs // 12)}:bordercolor=black:"
                                f"enable='gte(t,{a:.2f})':alpha='min(1,(t-{a:.2f})/0.3)'")
    if s.get("fx_watermark_on") and s.get("fx_watermark", "").strip():
        fs = int(m * 0.032)
        chain += drawtext_lines(fx_lines(edit, "wm", s["fx_watermark"], fs, w)[:1], font_bold, fs, int(h * 0.035) + bar_h,
                                "fontcolor=white@0.6:borderw=2:bordercolor=black@0.4", x=f"w-text_w-{int(w * 0.04)}")

    inputs = ["-i", str(src)]
    graph = [f"[0:v]{','.join(chain) or 'null'}[va]"]
    if s.get("fx_progress"):
        ph = max(4, int(h * 0.005)) // 2 * 2
        inputs += ["-f", "lavfi", "-i", f"color=c={ACCENT}:s={w}x{ph}:r=30"]
        graph.append(f"[va][1:v]overlay=x='-W+W*t/{final:.3f}':y={bar_h}:shortest=1[vb]")
    else:
        graph.append("[va]null[vb]")
    if subs is not None:
        sp = subs.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
        graph.append(f"[vb]subtitles='{sp}':force_style='{SUB_FORCE_STYLE}'[vout]")
    else:
        graph.append("[vb]null[vout]")

    used = [k for k in ("fx_fade", "fx_jump_zoom", "fx_ken_burns", "fx_freeze_end", "fx_hook_on", "fx_lower_on",
                        "fx_end_on", "fx_watermark_on", "fx_progress", "fx_letterbox", "fx_vignette", "fx_sharpen") if s.get(k)]
    if tr in ("dip", "flash"):
        used.append(f"fx_transition={tr}" + ("" if scene_cuts else " (chỉ có 1 clip, không có chỗ chuyển)"))
    log(job, "Hiệu ứng: " + (", ".join(used) if used else "không") + ("; phụ đề in sau cùng" if subs else ""))
    enc = ["-preset", "ultrafast", "-crf", "26"] if preview else ["-preset", "fast", "-crf", "18"]
    ffmpeg(*inputs, "-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "0:a", "-c:v", "libx264", *enc,
           "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "copy", str(dst))
    return final


def caption_chunks(text: str, start: float, end: float, max_words: int = 4, max_chars: int = 20) -> list:
    """Split one voice line into short uppercase cues, timed by character share, so they match
    render.py's bold 2-3 word caption style instead of wrapping a whole sentence over the picture."""
    chunks: list[list[str]] = [[]]
    for w in text.split():
        cur = chunks[-1]
        if cur and (len(cur) >= max_words or len(" ".join(cur + [w])) > max_chars):
            chunks.append([])
        chunks[-1].append(w)
        if w[-1] in ".,!?;:":
            chunks.append([])
    chunks = [c for c in chunks if c]
    weights = [len(" ".join(c)) + 2 for c in chunks]
    t, out = start, []
    for c, wgt in zip(chunks, weights):
        d = (end - start) * wgt / sum(weights)
        out.append((t, t + d, " ".join(c).rstrip(",;:").upper()))
        t += d
    return out


def job_render(job: dict, pid: str, quality: str) -> dict:
    preview = quality == "preview"
    pdir = pdir_of(pid)
    p = load(pid)
    s = p["settings"]
    ranges, total = plan(p, pdir)
    if not ranges:
        raise RuntimeError("Không có đoạn nào để dựng. Hãy chọn ít nhất một clip, hoặc bớt xoá chữ.")
    missing = [x["name"] for x in p["sources"] if x.get("include", True) and not x.get("has_audio")]
    if missing:
        raise RuntimeError("Clip không có âm thanh chưa được hỗ trợ: " + ", ".join(missing))
    w, h = out_dims(p)
    if preview:
        w, h = w // 4 * 2, h // 4 * 2
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    if GRADES.get(s["grade"]):
        vf += "," + GRADES[s["grade"]]
    edit = pdir / "edit"
    edit.mkdir(exist_ok=True)
    edl = {"version": 1, "sources": {x["id"]: (pdir / x["file"]).as_posix() for x in p["sources"]},
           "ranges": ranges, "grade": vf, "total_duration_s": total}
    # Subtitles are burned by apply_video_fx, after every effect, never by render.py.
    subs: Path | None = None
    if s["subtitles"] == "speech":
        subs = edit / "master.srt"
        build_master_srt(edl, edit, subs)
    elif s["subtitles"] == "voice":
        vdir = voice_dir(s.get("voice_id", ""))
        if not vdir:
            log(job, "CẢNH BÁO: phụ đề theo giọng đọc nhưng chưa chọn bản giọng đọc, video sẽ không có phụ đề.")
        else:
            off = float(s["voice_offset"])
            lines = json.loads((vdir / "lines.json").read_text(encoding="utf-8"))["lines"]
            cues = [c for l in lines for c in caption_chunks(l["sub"], l["start"] + off, l["end"] + off) if c[0] < total]
            srt = [f"{i}\n{srt_stamp(a)} --> {srt_stamp(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1)]
            subs = edit / "voice_subs.srt"
            subs.write_text("\n".join(srt), encoding="utf-8")
    (edit / "edl.json").write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
    log(job, f"Dựng {len(ranges)} đoạn, tổng {total:.1f} giây, khung {w}x{h}" + (" (bản xem thử)" if preview else ""))
    cut = edit / "_cut.mp4"
    run_cmd(job, [SYS_PY, HELPERS / "render.py", edit / "edl.json", "-o", cut, "--fps", "30", "--no-loudnorm",
                  "--no-subtitles", *(["--draft"] if preview else [])])
    segs = timeline(ranges)
    fxv = edit / "_fx.mp4"
    final = apply_video_fx(job, cut, fxv, s, w, h, segs, total, preview, subs, edit)
    out_dir = pdir / "renders"
    out_dir.mkdir(exist_ok=True)
    out = unique(out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{'xem-thu' if preview else 'thanh-pham'}.mp4")
    mix_audio(job, fxv, out, s, final, [g["a"] for g in segs if g["cut"] == "scene"], edit)
    for f in (cut, fxv, edit / "_whoosh.wav"):
        f.unlink(missing_ok=True)
    entry = {"file": rel(out), "quality": quality, "duration": probe(out)["duration"], "size_mb": round(out.stat().st_size / 1e6, 1),
             "created": time.strftime("%Y-%m-%d %H:%M"), "width": w, "height": h}
    with PLOCK:
        p = load(pid)
        p.setdefault("renders", []).insert(0, entry)
        save(pid, p)
    log(job, f"Xong: {out.name}")
    return entry


def parse_script(text: str) -> list[tuple[str, str]]:
    lines = []
    for raw in text.splitlines():
        t = raw.strip()
        if not t or t.startswith("#"):
            continue
        say, _, sub = t.partition("|")
        lines.append((say.strip(), (sub or say).strip()))
    return lines


def declick(audio: np.ndarray, fade_in_s: float = 0.015, fade_out_s: float = 0.015) -> np.ndarray:
    """Short fades at both ends: a line that starts or stops mid-waveform pops when joined to silence."""
    x = audio.copy()
    a, b = min(len(x), int(fade_in_s * SR)), min(len(x), int(fade_out_s * SR))
    if a:
        x[:a] *= np.linspace(0, 1, a, dtype=np.float32)
    if b:
        x[-b:] *= np.linspace(1, 0, b, dtype=np.float32)
    return x


def onset_peak(path: Path) -> float:
    x, sr = sf.read(str(path), dtype="float32")
    return float(np.abs(x[: int(0.005 * sr)]).max()) if len(x) else 0.0


def pick_best_takes(job: dict, takes: dict[int, list[Path]], lines: list[tuple[str, str]]) -> dict[int, dict]:
    """Whisper-score every take; per line keep the fewest wrong words, then the cleanest start.
    Runs in the Whisper environment as one subprocess (one model load for the whole job)."""
    order = [(i, k, p) for i, ps in takes.items() for k, p in enumerate(ps)]
    req_f, out_f = takes[1][0].parent / "_score_in.json", takes[1][0].parent / "_score_out.json"
    req_f.write_text(json.dumps([{"path": str(p), "text": lines[i - 1][0]} for i, _, p in order], ensure_ascii=False),
                     encoding="utf-8")
    log(job, f"Đang kiểm tra {len(order)} bản đọc bằng Whisper để chọn bản đúng nhất…")
    try:
        run_cmd(job, [SYS_PY, HELPERS / "score_takes.py", req_f, out_f])
        scores = json.loads(out_f.read_text(encoding="utf-8"))
    except Exception as e:   # no Whisper env or it failed: keep the first take, don't lose the job
        log(job, f"Không kiểm tra được bằng Whisper ({e}); dùng bản đọc đầu tiên.")
        return {}
    best: dict[int, dict] = {}
    for (i, k, p), sc in zip(order, scores):
        key = (sc["errors"], onset_peak(p))
        if i not in best or key < best[i]["_key"]:
            best[i] = {"_key": key, "take": k, "errors": sc["errors"], "words": sc["words"], "diff": sc["diff"],
                       "takes": len(takes[i])}
    for i, b in sorted(best.items()):
        b.pop("_key")
        log(job, f"Câu {i}: chọn bản {b['take'] + 1}/{b['takes']}" +
            (" (Whisper nghe đúng hết)" if not b["errors"] else f" (Whisper nghe khác {b['errors']} chữ: {b['diff']})"))
    return best


def job_voice(job: dict, req: dict) -> dict:
    lines = parse_script(req.get("text", ""))
    if not lines:
        raise RuntimeError("Chưa có lời thoại")
    title = (req.get("title") or lines[0][1])[:60]
    vid = time.strftime("%Y%m%d-%H%M%S") + "-" + slug(title, "giong-doc")
    d = VOICES / vid
    d.mkdir(parents=True)
    mydir = myvoice_dir(req["myvoice"]) if req.get("myvoice") else None
    label = f"Giọng của tôi: {myvoice_meta(mydir)['name']}" if mydir else (req.get("voice") or "Hải Đăng")
    temp, top_k = float(req.get("temperature", 0.3)), int(req.get("top_k", 10))
    speed, gap = float(req.get("speed", 1.0)), float(req.get("gap", 0.4))
    takes_n = max(1, min(5, int(req.get("takes", 3))))
    tdir = d / "_takes"
    tdir.mkdir()
    takes: dict[int, list[Path]] = {}
    with GPU:
        model = TTS.get(job)
        who = {"voice": voice_profile(job, mydir, model) if mydir else label}
        for i, (say, _) in enumerate(lines, 1):
            log(job, f"Câu {i}/{len(lines)}" + (f" ({takes_n} lần đọc)" if takes_n > 1 else "") + f": {say[:70]}")
            for k in range(takes_n):
                # VieNeu starts sounding on its very first frame and often clips the first consonant
                # ("Sách"→"rách", plus a pop); a leading "..." gives it a beat to start cleanly.
                audio = np.asarray(model.infer("... " + say, **who, temperature=temp, top_k=top_k), dtype=np.float32)
                p = tdir / f"line{i:02d}_{k}.wav"
                sf.write(str(p), audio, SR)
                takes.setdefault(i, []).append(p)
        checks = pick_best_takes(job, takes, lines) if takes_n > 1 else {}
    for i in range(1, len(lines) + 1):
        best = checks.get(i, {}).get("take", 0)
        audio, _ = sf.read(str(takes[i][best]), dtype="float32")
        sf.write(str(d / f"line{i:02d}.wav"), declick(audio), SR)
        if abs(speed - 1.0) > 1e-3:   # rubberband: clean time-stretch, pitch and timbre kept (atempo warbles)
            tmp = d / f"line{i:02d}.tmp.wav"
            ffmpeg("-i", d / f"line{i:02d}.wav", "-af",
                   f"rubberband=tempo={speed}:pitchq=quality:formant=preserved:transients=smooth", "-ar", str(SR), tmp)
            os.replace(tmp, d / f"line{i:02d}.wav")
        ffmpeg("-i", d / f"line{i:02d}.wav", "-c:a", "libmp3lame", "-b:a", "192k", d / f"line{i:02d}.mp3")
    shutil.rmtree(tdir, ignore_errors=True)
    gap_s = np.zeros(int(round(gap * SR)), dtype=np.float32)
    parts, meta, srt, t = [], [], [], 0.0
    for i, (say, sub) in enumerate(lines, 1):
        audio, _ = sf.read(str(d / f"line{i:02d}.wav"), dtype="float32")
        dur = len(audio) / SR
        parts.append(audio)
        meta.append({"file": f"line{i:02d}.mp3", "say": say, "sub": sub, "start": round(t, 3), "end": round(t + dur, 3),
                     "duration": round(dur, 3), **({"check": checks[i]} if i in checks else {})})
        srt.append(f"{i}\n{srt_stamp(t)} --> {srt_stamp(t + dur)}\n{sub}\n")
        t += dur
        if len(gap_s) and i < len(lines):
            parts.append(gap_s)
            t += len(gap_s) / SR
    sf.write(str(d / "voice_full.wav"), np.concatenate(parts), SR)
    ffmpeg("-i", d / "voice_full.wav", "-c:a", "libmp3lame", "-b:a", "192k", d / "voice_full.mp3")
    (d / "subtitles.srt").write_text("\n".join(srt), encoding="utf-8")
    info = {"id": vid, "title": title, "voice": label, "takes": takes_n,
            "temperature": temp, "top_k": top_k, "speed": speed, "gap": gap, "total": round(t, 2),
            "created": time.strftime("%Y-%m-%d %H:%M"), "text": req.get("text", ""), "lines": meta}
    (d / "lines.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    log(job, f"Xong: {len(lines)} câu, {t:.1f} giây")
    return voice_entry(d)


def voice_entry(d: Path) -> dict:
    info = json.loads((d / "lines.json").read_text(encoding="utf-8"))
    base = rel(d)
    info["files"] = {"mp3": f"{base}/voice_full.mp3", "wav": f"{base}/voice_full.wav", "srt": f"{base}/subtitles.srt"}
    for line in info["lines"]:
        line["url"] = f"{base}/{line['file']}"
    return info


# -------- API: general -------------------------------------------------------

@app.get("/api/info")
def info() -> dict:
    return {"voices": [{"name": n, "gender": g, "region": r, "style": st} for n, g, r, st in PRESET_VOICES],
            "aspects": list(ASPECTS) + ["original"], "grades": list(GRADES), "defaults": DEFAULT_SETTINGS,
            "talker": talker_ready(),
            "work": str(WORK)}


@app.get("/api/running")
def running_jobs() -> dict:
    return {"running": [j["kind"] for j in JOBS.values() if j["status"] == "running"]}


@app.post("/api/shutdown")
def shutdown() -> dict:
    """The app has no console window to close, so the UI's quit button ends the process here."""
    threading.Timer(0.5, lambda: os._exit(0)).start()   # let this response reach the browser first
    return {"ok": True}


@app.get("/api/jobs/{jid}")
def job_status(jid: str) -> dict:
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "Không tìm thấy tác vụ")
    return {**job, "log": job["log"][-40:], "elapsed": round((job["finished"] or time.time()) - job["started"], 1)}


# -------- API: projects ------------------------------------------------------

@app.get("/api/projects")
def list_projects() -> list:
    out = []
    for f in sorted(PROJECTS.glob("*/project.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        p = json.loads(f.read_text(encoding="utf-8"))
        out.append({"id": f.parent.name, "name": p["name"], "created": p.get("created"), "sources": len(p["sources"])})
    return out


@app.post("/api/projects")
def create_project(body: dict = Body(...)) -> dict:
    name = (body.get("name") or "").strip() or "Dự án mới"
    d = unique(PROJECTS / slug(name, "du-an"))
    (d / "sources").mkdir(parents=True)
    p = {"name": name, "created": time.strftime("%Y-%m-%d %H:%M"), "sources": [], "settings": dict(DEFAULT_SETTINGS),
         "renders": []}
    (d / "project.json").write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"id": d.name}


@app.get("/api/projects/{pid}")
def get_project(pid: str) -> dict:
    p = load(pid)
    pdir = pdir_of(pid)
    for src in p["sources"]:
        src["url"] = rel(pdir / src["file"])
        src["transcribed"] = transcript_path(pdir, src["id"]).exists()
    for r in p.get("renders", []):
        r["exists"] = (WORK / r["file"]).exists()
    p["id"] = pdir.name
    p["plan_total"] = round(plan(p, pdir)[1] + (FREEZE_S if p["settings"].get("fx_freeze_end") else 0), 2)
    return p


@app.put("/api/projects/{pid}")
def update_project(pid: str, body: dict = Body(...)) -> dict:
    with PLOCK:
        p = load(pid)
        if "settings" in body:
            p["settings"].update({k: v for k, v in body["settings"].items() if k in DEFAULT_SETTINGS})
        if "sources" in body:
            by_id = {s["id"]: s for s in p["sources"]}
            ordered = []
            for upd in body["sources"]:
                src = by_id.pop(upd.get("id"), None)
                if not src:
                    continue
                for k in ("include", "mode", "trim_start", "trim_end", "removed"):
                    if k in upd:
                        src[k] = upd[k]
                if "mode" in upd:
                    src["mode_auto"] = False
                ordered.append(src)
            p["sources"] = ordered + list(by_id.values())
        if "name" in body and body["name"].strip():
            p["name"] = body["name"].strip()
        save(pid, p)
    return get_project(pid)


@app.post("/api/projects/{pid}/upload")
def upload_sources(pid: str, files: list[UploadFile] = File(...)) -> dict:
    pdir = pdir_of(pid)
    added = []
    for f in files:
        ext = Path(f.filename or "video.mp4").suffix.lower() or ".mp4"
        dest = unique(pdir / "sources" / f"{slug(Path(f.filename or 'video').stem, 'video')}{ext}")
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out, 1 << 20)
        info = probe(dest)
        if not info["has_video"]:
            dest.unlink()
            raise HTTPException(400, f"{f.filename}: không đọc được video")
        added.append({"id": dest.stem, "name": f.filename, "file": f"sources/{dest.name}", **info,
                      "include": True, "mode": "speech" if info["has_audio"] else "full", "mode_auto": True,
                      "trim_start": 0, "trim_end": 0, "removed": []})
    with PLOCK:
        p = load(pid)
        p["sources"] += added
        save(pid, p)
    return get_project(pid)


@app.delete("/api/projects/{pid}/sources/{sid}")
def delete_source(pid: str, sid: str) -> dict:
    pdir = pdir_of(pid)
    with PLOCK:
        p = load(pid)
        src = next((s for s in p["sources"] if s["id"] == sid), None)
        if not src:
            raise HTTPException(404, "Không tìm thấy clip")
        p["sources"].remove(src)
        save(pid, p)
    (pdir / src["file"]).unlink(missing_ok=True)
    transcript_path(pdir, sid).unlink(missing_ok=True)
    return get_project(pid)


@app.delete("/api/projects/{pid}/renders")
def delete_render(pid: str, file: str) -> dict:
    with PLOCK:
        p = load(pid)
        p["renders"] = [r for r in p.get("renders", []) if r["file"] != file]
        save(pid, p)
    target = (WORK / file).resolve()
    if target.is_relative_to(pdir_of(pid).resolve()):
        target.unlink(missing_ok=True)
    return get_project(pid)


@app.post("/api/projects/{pid}/music")
def upload_music(pid: str, file: UploadFile = File(...)) -> dict:
    pdir = pdir_of(pid)
    (pdir / "music").mkdir(exist_ok=True)
    dest = unique(pdir / "music" / f"{slug(Path(file.filename or 'nhac').stem, 'nhac')}{Path(file.filename or '.mp3').suffix.lower()}")
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out, 1 << 20)
    return update_project(pid, {"settings": {"music": rel(dest)}})


@app.get("/api/projects/{pid}/words/{sid}")
def get_words(pid: str, sid: str) -> list:
    return words_of(pdir_of(pid), sid)


@app.post("/api/projects/{pid}/plan")
def get_plan(pid: str) -> dict:
    p = load(pid)
    ranges, total = plan(p, pdir_of(pid))
    return {"ranges": ranges, "total": round(total + (FREEZE_S if p["settings"].get("fx_freeze_end") else 0), 2)}


@app.post("/api/projects/{pid}/transcribe")
def transcribe(pid: str, body: dict = Body(default={})) -> dict:
    pdir_of(pid)
    return {"job": start_job("transcribe", job_transcribe, pid, body.get("language") or load(pid)["settings"]["language"])}


@app.post("/api/projects/{pid}/render")
def render(pid: str, body: dict = Body(default={})) -> dict:
    pdir_of(pid)
    return {"job": start_job("render", job_render, pid, body.get("quality", "preview"))}


# -------- API: voices --------------------------------------------------------

@app.get("/api/voices")
def list_voices() -> list:
    return [voice_entry(d) for d in sorted(VOICES.iterdir(), reverse=True) if (d / "lines.json").exists()]


@app.post("/api/voices/generate")
def generate_voice(body: dict = Body(...)) -> dict:
    return {"job": start_job("voice", job_voice, body)}


@app.delete("/api/voices/{vid}")
def delete_voice(vid: str) -> dict:
    d = VOICES / safe_id(vid)
    if d.exists():
        shutil.rmtree(d)
    return {"ok": True}


# -------- API: saved cloned voices ("Giọng của tôi") -------------------------
# refs/<id>/ref.wav      cleaned reference clip (what the voice was cloned from)
#          voice.npz     VieNeu speaker embedding + reference codes, encoded once
#          meta.json     {name, created, duration, source}
#          sample.mp3    a fixed sentence read in the cloned voice, to judge the clone

SAMPLE_TEXT = "Xin chào, đây là giọng đọc được tạo từ đoạn ghi âm của bạn. Nghe có giống không nhỉ?"
MIN_REF_S, MAX_REF_S = 15.0, 60.0   # recommended 45-60 s: more pieces → steadier voice embedding


def myvoice_dir(vid: str) -> Path:
    d = REFS / safe_id(vid)
    if not (d / "meta.json").exists():
        raise HTTPException(404, "Không tìm thấy giọng đã lưu")
    return d


def myvoice_meta(d: Path) -> dict:
    return json.loads((d / "meta.json").read_text(encoding="utf-8"))


def myvoice_entry(d: Path) -> dict:
    base = rel(d)
    return {**myvoice_meta(d), "id": d.name, "ref_url": f"{base}/ref.wav",
            "sample_url": f"{base}/sample.mp3" if (d / "sample.mp3").exists() else "",
            "ready": (d / "voice.npz").exists()}


def name_taken(name: str, except_id: str = "") -> bool:
    return any(myvoice_meta(d)["name"].casefold() == name.casefold()
               for d in REFS.iterdir() if (d / "meta.json").exists() and d.name != except_id)


def migrate_legacy_refs() -> None:
    """Earlier versions kept bare refs/*.wav clips; turn each into a named saved voice."""
    for f in REFS.glob("*.wav"):
        d = unique(REFS / slug(f.stem, "giong"))
        d.mkdir(parents=True)
        shutil.move(str(f), d / "ref.wav")
        (d / "meta.json").write_text(json.dumps(
            {"name": f.stem, "created": time.strftime("%Y-%m-%d %H:%M", time.localtime(d.stat().st_mtime)),
             "duration": probe(d / "ref.wav")["duration"], "source": "upload"}, ensure_ascii=False, indent=1),
            encoding="utf-8")


migrate_legacy_refs()


SEG_S = 7.0   # VieNeu v3 Turbo is built for 3-8 s references; longer recordings are split into pieces


def split_reference(wav: Path, out_dir: Path) -> list[Path]:
    """Cut a long recording into ~SEG_S pieces at the quietest 20 ms near each boundary (between words)."""
    audio, sr = sf.read(str(wav), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    hop = int(0.02 * sr)
    n = len(audio) // hop
    rms = np.sqrt((audio[: n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)
    total = len(audio) / sr
    cuts, t = [0], SEG_S
    while total - t > 3.0:
        lo, hi = int((t - 1.0) / 0.02), min(n, int((t + 1.0) / 0.02))
        i = lo + int(np.argmin(rms[lo:hi]))
        cuts.append(i * hop)
        t = i * hop / sr + SEG_S
    cuts.append(len(audio))
    out_dir.mkdir(exist_ok=True)
    paths = []
    for k, (a, b) in enumerate(zip(cuts, cuts[1:])):
        if (b - a) / sr >= 3.0:
            p = out_dir / f"seg{k:02d}.wav"
            sf.write(str(p), audio[a:b], sr)
            paths.append(p)
    return paths


def enroll(job: dict, model, d: Path) -> None:
    """Long recordings: enrol every ~7 s piece, average the speaker embeddings (minus outliers such as
    noise or another voice), and keep the reference codes of the most typical piece. The codes stay
    short because the model was trained on short references; the embedding gains from all the data."""
    ref = d / "ref.wav"
    segs = split_reference(ref, d / "_segs") if probe(ref)["duration"] >= 2 * SEG_S else [ref]
    embs, codes = [], []
    try:
        for i, p in enumerate(segs, 1):
            if len(segs) > 1:
                log(job, f"Phân tích đoạn {i}/{len(segs)}…")
            e, c = model.encode_reference(str(p), denoise=True)
            embs.append(np.asarray(e, dtype=np.float32).ravel())
            codes.append(None if c is None else np.asarray(c, dtype=np.int64))
    finally:
        shutil.rmtree(d / "_segs", ignore_errors=True)
    E = np.stack(embs)
    norms = np.linalg.norm(E, axis=1)

    def centroid(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        m = E[mask].mean(axis=0)
        m *= norms[mask].mean() / (np.linalg.norm(m) + 1e-9)   # averaging shrinks the norm; restore it
        return m, E @ m / (norms * np.linalg.norm(m) + 1e-9)

    keep = np.ones(len(E), dtype=bool)
    mean, cos = centroid(keep)
    if len(E) >= 3:
        keep = cos >= cos.max() - 0.25           # drop pieces that don't sound like the rest
        mean, cos = centroid(keep)
    best = int(np.argmax(np.where(keep, cos, -1)))
    np.savez(d / "voice.npz", speaker_emb=mean.astype(np.float32),
             codes=codes[best] if codes[best] is not None else np.zeros(0, dtype=np.int64))
    meta = myvoice_meta(d)
    meta.update({"segments": len(E), "segments_used": int(keep.sum()), "consistency": round(float(cos[keep].mean()), 3)})
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    if len(E) > 1:
        log(job, f"Đã gộp {int(keep.sum())}/{len(E)} đoạn (độ đồng đều giọng {cos[keep].mean():.2f}).")


def voice_profile(job: dict, d: Path, model) -> dict:
    """The saved voice as VieNeu's `voice=` dict; enrols (and caches) it on first use."""
    npz = d / "voice.npz"
    if not npz.exists():
        log(job, f"Đang phân tích giọng \"{myvoice_meta(d)['name']}\"…")
        enroll(job, model, d)
    z = np.load(npz)
    return {"speaker_emb": z["speaker_emb"], "codes": z["codes"] if z["codes"].size else None}


def job_myvoice_create(job: dict, d: Path) -> dict:
    with GPU:
        model = TTS.get(job)
        profile = voice_profile(job, d, model)
        log(job, "Đang đọc thử một câu bằng giọng vừa clone…")
        audio = np.asarray(model.infer("... " + SAMPLE_TEXT, voice=profile, temperature=0.3, top_k=10), dtype=np.float32)
    sf.write(str(d / "sample.wav"), declick(audio), SR)
    ffmpeg("-i", d / "sample.wav", "-c:a", "libmp3lame", "-b:a", "160k", d / "sample.mp3")
    (d / "sample.wav").unlink(missing_ok=True)
    log(job, f"Đã lưu giọng \"{myvoice_meta(d)['name']}\".")
    return myvoice_entry(d)


@app.get("/api/myvoices")
def list_myvoices() -> list:
    dirs = [d for d in REFS.iterdir() if (d / "meta.json").exists()]
    return [myvoice_entry(d) for d in sorted(dirs, key=lambda x: myvoice_meta(x).get("created", ""), reverse=True)]


@app.post("/api/myvoices")
def create_myvoice(file: UploadFile = File(...), name: str = Form(...), source: str = Form("upload")) -> dict:
    name = name.strip()
    if not name or len(name) > 60:
        raise HTTPException(400, "Hãy đặt tên cho giọng (tối đa 60 ký tự).")
    if name_taken(name):
        raise HTTPException(400, f"Đã có giọng tên \"{name}\". Hãy chọn tên khác.")
    d = unique(REFS / slug(name, "giong"))
    d.mkdir(parents=True)
    raw = d / f"_upload{Path(file.filename or '.webm').suffix.lower() or '.webm'}"
    try:
        with raw.open("wb") as out:
            shutil.copyfileobj(file.file, out, 1 << 20)
        # mono 24 kHz, leading silence trimmed, at most MAX_REF_S; enroll() splits it into ~7 s pieces
        ffmpeg("-i", raw, "-af", "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1",
               "-t", str(MAX_REF_S), "-ac", "1", "-ar", "24000", d / "ref.wav")
        dur = probe(d / "ref.wav")["duration"]
        if dur < MIN_REF_S:
            raise HTTPException(400, f"Đoạn ghi âm chỉ có {dur:.1f} giây giọng nói. Cần ít nhất {MIN_REF_S:.0f} giây "
                                     "(tốt nhất 45–60 giây), nói rõ ràng, ít tiếng ồn.")
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    finally:
        raw.unlink(missing_ok=True)
    (d / "meta.json").write_text(json.dumps(
        {"name": name, "created": time.strftime("%Y-%m-%d %H:%M"), "duration": dur,
         "source": "mic" if source == "mic" else "upload"}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"id": d.name, "job": start_job("clone", job_myvoice_create, d)}


@app.patch("/api/myvoices/{vid}")
def rename_myvoice(vid: str, body: dict = Body(...)) -> dict:
    d = myvoice_dir(vid)
    name = (body.get("name") or "").strip()
    if not name or len(name) > 60:
        raise HTTPException(400, "Tên giọng không hợp lệ (1-60 ký tự).")
    if name_taken(name, except_id=d.name):
        raise HTTPException(400, f"Đã có giọng tên \"{name}\".")
    meta = myvoice_meta(d)
    meta["name"] = name
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return myvoice_entry(d)


@app.delete("/api/myvoices/{vid}")
def delete_myvoice(vid: str) -> dict:
    shutil.rmtree(myvoice_dir(vid))
    return {"ok": True}


# -------- script writer (📝 Kịch bản tab) -----------------------------------

SCRIPTS = WORK / "scripts"
SCRIPTS.mkdir(parents=True, exist_ok=True)
# API keys live outside WORK: everything under WORK is served at /files.
AI_SETTINGS = Path(os.environ.get("STUDIO_SECRETS") or Path(os.environ.get("APPDATA") or HOME) / "VideoStudio" / "ai-settings.json")
AI_DEFAULTS = {"engine": "ollama", "ollama_model": scriptgen.DEFAULT_OLLAMA_MODEL,
               "claude_key": "", "claude_model": scriptgen.CLAUDE_MODELS[0][0], "gemini_key": "", "gemini_model": ""}
DURATIONS = (15, 30, 45, 60, 90, 120)


def ai_settings() -> dict:
    try:
        return {**AI_DEFAULTS, **json.loads(AI_SETTINGS.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(AI_DEFAULTS)


def ai_public(s: dict) -> dict:
    """Settings for the page: keys are never sent back, only whether one is saved and its last 4 characters."""
    out = {k: v for k, v in s.items() if not k.endswith("_key")}
    for k in ("claude_key", "gemini_key"):
        out[k.replace("_key", "_key_hint")] = ("…" + s[k][-4:]) if s[k] else ""
    out["ollama_installed"] = bool(scriptgen.ollama_exe())
    out["ollama_running"] = scriptgen.ollama_up()
    out["ollama_models"] = scriptgen.ollama_models() if out["ollama_running"] else []
    out["claude_models"] = [{"id": i, "label": l} for i, l in scriptgen.CLAUDE_MODELS]
    out["styles"] = list(scriptgen.STYLES)
    out["durations"] = list(DURATIONS)
    return out


def script_path(sid: str) -> Path:
    p = SCRIPTS / f"{safe_id(sid)}.json"
    if not p.exists():
        raise HTTPException(404, "Không tìm thấy kịch bản")
    return p


def script_entry(d: dict) -> dict:
    return {**d, "voice_text": scriptgen.voice_text(d["lines"]),
            "words": sum(len(l["say"].split()) for l in d["lines"]),
            "est_seconds": round(sum(len(l["say"].split()) for l in d["lines"]) / scriptgen.WORDS_PER_SECOND)}


def job_script(job: dict, req: dict) -> dict:
    s = ai_settings()
    engine = req.get("engine") or s["engine"]
    prompt, n = scriptgen.user_prompt(req["brief"], req["duration"], req.get("style", "vui"), req.get("audience", ""))
    t0 = time.time()
    raw, model = ai_generate(job, engine, s, scriptgen.SYSTEM, prompt)
    out = tidy_or_fail(raw)
    doc = save_script(req, engine, model, time.time() - t0, out)
    log(job, f"Xong: {len(out['lines'])} câu, {len(out['shots'])} cảnh.")
    return script_entry(doc)


def ai_generate(job: dict, engine: str, s: dict, system: str, prompt: str, images: list[str] | None = None,
                schema: dict | None = None) -> tuple[dict, str]:
    say = lambda m: log(job, m)  # noqa: E731
    try:
        if engine == "ollama":
            with GPU:   # the local model needs the whole 4 GB card
                TTS.unload(job)
                return scriptgen.generate(engine, s, system, prompt, say, images, schema)
        return scriptgen.generate(engine, s, system, prompt, say, images, schema)
    except scriptgen.ScriptError as e:
        raise RuntimeError(str(e)) from None


def tidy_or_fail(raw: dict, n_images: int = 0) -> dict:
    try:
        return scriptgen.tidy(raw, n_images)
    except scriptgen.ScriptError as e:
        raise RuntimeError(str(e)) from None


def save_script(req: dict, engine: str, model: str, seconds: float, out: dict, **extra) -> dict:
    sid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    doc = {"id": sid, "created": time.time(), "brief": req["brief"], "duration": req["duration"],
           "style": req.get("style", "vui"), "audience": req.get("audience", ""),
           "engine": engine, "model": model or "", "seconds": round(seconds, 1), **out, **extra}
    (SCRIPTS / f"{sid}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


@app.get("/api/ai-settings")
def get_ai_settings() -> dict:
    return ai_public(ai_settings())


@app.put("/api/ai-settings")
def put_ai_settings(body: dict = Body(...)) -> dict:
    s = ai_settings()
    for k in ("engine", "ollama_model", "claude_model", "gemini_model"):
        if k in body and isinstance(body[k], str):
            s[k] = body[k].strip()
    for k in ("claude_key", "gemini_key"):   # "" clears a key; a missing field keeps it
        if k in body and isinstance(body[k], str):
            s[k] = body[k].strip()
    if s["engine"] not in ("ollama", "claude", "gemini"):
        raise HTTPException(400, "AI không hợp lệ")
    if s["claude_model"] not in dict(scriptgen.CLAUDE_MODELS):
        s["claude_model"] = scriptgen.CLAUDE_MODELS[0][0]
    AI_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    AI_SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    return ai_public(s)


@app.get("/api/ai-settings/gemini-models")
def get_gemini_models() -> dict:
    key = ai_settings()["gemini_key"]
    if not key:
        raise HTTPException(400, "Chưa có khoá API Gemini")
    try:
        return {"models": scriptgen.gemini_models(key)}
    except Exception as e:
        raise HTTPException(400, f"Không lấy được danh sách model Gemini (khoá sai hoặc mất mạng): {e}")


@app.post("/api/scripts/generate")
def generate_script(body: dict = Body(...)) -> dict:
    brief = str(body.get("brief") or "").strip()
    if len(brief) < 10:
        raise HTTPException(400, "Hãy viết nội dung video rõ hơn (ít nhất một câu).")
    try:
        duration = int(body.get("duration") or 30)
    except ValueError:
        duration = 30
    req = {"brief": brief[:4000], "duration": min(max(duration, 10), 180), "style": str(body.get("style") or "vui"),
           "audience": str(body.get("audience") or "")[:300], "engine": str(body.get("engine") or "")}
    return {"job": start_job("script", job_script, req)}


@app.get("/api/scripts")
def list_scripts() -> list:
    out = []
    for p in sorted(SCRIPTS.glob("*.json"), reverse=True):
        try:
            out.append(script_entry(json.loads(p.read_text(encoding="utf-8"))))
        except (OSError, ValueError, KeyError):
            continue
    return out


@app.put("/api/scripts/{sid}")
def update_script(sid: str, body: dict = Body(...)) -> dict:
    """Save the user's edits. `voice_text` (the editable 'say | sub' lines) replaces the lines;
    a line without '|' is re-spelled from its text, so typing '50k' still reads correctly."""
    p = script_path(sid)
    d = json.loads(p.read_text(encoding="utf-8"))
    for k in ("title", "hook", "lower_third", "end_card"):
        if isinstance(body.get(k), str):
            d[k] = body[k].strip()[:80]
    if isinstance(body.get("voice_text"), str):
        lines = []
        for say, sub in parse_script(body["voice_text"]):
            lines.append({"say": scriptgen.to_speech(sub) if say == sub else say, "sub": sub})
        if not lines:
            raise HTTPException(400, "Kịch bản cần ít nhất một câu")
        d["lines"] = lines
    if isinstance(body.get("shots"), list):
        d["shots"] = [{"line": int(s.get("line") or i + 1), "desc": str(s.get("desc") or ""), "prompt_en": str(s.get("prompt_en") or "")}
                      for i, s in enumerate(body["shots"]) if isinstance(s, dict)]
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return script_entry(d)


@app.delete("/api/scripts/{sid}")
def delete_script(sid: str) -> dict:
    script_path(sid).unlink()
    return {"ok": True}


# -------- automatic videos (⚡ Video tự động tab) ------------------------------
# Photos + a brief → the AI describes the photos once → 2-4 scripts, each from a different angle →
# VieNeu voice per script → a slideshow (blurred-fill zoom or pan per line) → the editing effects pass
# (hook, lower third, end card, progress bar, transitions, captions) → audio mix with optional music.

AUTO = WORK / "auto"
AUTO.mkdir(parents=True, exist_ok=True)
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".jfif"}
MOTIONS = ["in", "pan_fwd", "out", "pan_back"]
GRADIENTS = [("0x1f3c88", "0xd94f2b"), ("0x0f766e", "0x1e293b"), ("0x7c2d12", "0x1f2937"), ("0x4c1d95", "0x0e7490")]
VOICE_LEAD, VOICE_TAIL = 0.4, 1.6   # silence before the first line and after the last (end card)


def prep_image(src: Path, dst: Path, max_side: int) -> None:
    """Upright (EXIF), RGB, at most max_side px, as JPEG."""
    from PIL import Image, ImageOps
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_side, max_side))
        im.save(dst, "JPEG", quality=90)


def b64(path: Path) -> str:
    import base64
    return base64.b64encode(path.read_bytes()).decode()


def slide(img: Path | None, dst: Path, d: float, w: int, h: int, motion: str, k: int, preview: bool,
          model_side: str = "") -> None:
    """One still → d seconds of video. 'in'/'out': whole photo over a blurred copy of itself, slow zoom.
    'pan_*': photo fills the frame and the camera travels along its long side. With a presenter on
    `model_side`, the photo is always shown whole, smaller, on the other side and higher up."""
    if img is not None and model_side and motion.startswith("pan"):
        motion = "in" if motion == "pan_fwd" else "out"
    frames = max(2, round(d * 30))
    enc = ["-c:v", "libx264", "-preset", "ultrafast" if preview else "veryfast", "-crf", "26" if preview else "20",
           "-pix_fmt", "yuv420p", "-r", "30", "-an", "-frames:v", str(frames)]
    if img is None:
        c0, c1 = GRADIENTS[k % len(GRADIENTS)]
        ffmpeg("-f", "lavfi", "-i", f"gradients=s={w}x{h}:c0={c0}:c1={c1}:x0=0:y0=0:x1={w}:y1={h}:speed=0.015:rate=30:duration={d + 0.1:.3f}",
               *enc, dst)
        return
    src = ["-loop", "1", "-framerate", "30", "-t", f"{d + 0.1:.3f}", "-i", str(img)]
    if motion in ("in", "out"):
        z = f"1+0.10*on/{frames}" if motion == "in" else f"1.10-0.10*on/{frames}"
        if model_side:   # product on the side opposite the presenter, upper part of the frame
            fw, fh = (0.62, 0.56) if h > w else (0.5, 0.8)
            pos = f"{'(W-w)*0.08' if model_side == 'right' else '(W-w)*0.92'}:(H-h)*{0.25 if h > w else 0.4}"
        else:
            fw, fh, pos = 0.94, 0.74, "(W-w)/2:(H-h)/2*0.92"
        fc = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=28,eq=brightness=-0.14[bg];"
              f"[0:v]scale={int(w * fw)}:{int(h * fh)}:force_original_aspect_ratio=decrease[fg];"
              f"[bg][fg]overlay={pos},scale={2 * w}:{2 * h},"   # 2x before zoompan: less stair-step jitter
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps=30,setsar=1[v]")
    else:
        from PIL import Image
        with Image.open(img) as im:
            wide = im.width / im.height > w / h
        p = f"(t/{d:.3f})" if motion == "pan_fwd" else f"(1-t/{d:.3f})"
        x, y = (f"(iw-{w})*{p}", f"(ih-{h})/2") if wide else (f"(iw-{w})/2", f"(ih-{h})*{p}")
        fc = (f"[0:v]scale={int(w * 1.08)}:{int(h * 1.08)}:force_original_aspect_ratio=increase,"
              f"crop=w={w}:h={h}:x='{x}':y='{y}',setsar=1[v]")
    ffmpeg(*src, "-filter_complex", fc, "-map", "[v]", *enc, dst)


def build_slideshow(job: dict, work: Path, imgs: list[Path], lines: list[dict], shots: list[dict], total: float,
                    w: int, h: int, k: int, preview: bool, model_side: str = "",
                    clips: dict[int, Path] | None = None) -> tuple[Path, list[dict]]:
    """Cut on every voice line; returns the silent-audio video and the timeline for apply_video_fx.
    A line with an AI clip (clips[line]) uses the clip; the others use a photo slide."""
    pick = {s["line"]: s.get("image", 0) for s in shots}
    starts = [0.0] + [VOICE_LEAD + l["start"] for l in lines[1:]]
    bounds = list(zip(starts, starts[1:] + [total]))
    segs, files, prev = [], [], None
    for i, (a, b) in enumerate(bounds, 1):
        f = work / f"_slide{i:02d}.mp4"
        clip = (clips or {}).get(i)
        if clip:
            log(job, f"  Cảnh {i}/{len(bounds)}: {b - a:.1f} giây, clip AI")
            clip_segment(clip, f, b - a, w, h, preview)
            src = clip
        else:
            img = None
            if imgs:
                no = pick.get(i, 0)
                img = imgs[no - 1] if 1 <= no <= len(imgs) else imgs[(i - 1) % len(imgs)]
            log(job, f"  Cảnh {i}/{len(bounds)}: {b - a:.1f} giây" + (f", ảnh {imgs.index(img) + 1}" if img else ""))
            slide(img, f, b - a, w, h, MOTIONS[(i + k) % len(MOTIONS)], k, preview, model_side)
            src = img
        files.append(f)
        segs.append({"a": round(a, 3), "b": round(b, 3), "source": str(src), "kind": "ảnh",
                     "cut": "" if i == 1 else ("scene" if src != prev else "jump")})
        prev = src
    lst = work / "_slides.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in files), encoding="utf-8")
    base = work / "_base.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", lst, "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo",
           "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-t", f"{total:.3f}", base)
    for f in files + [lst]:
        f.unlink(missing_ok=True)
    return base, segs


# ---- presenter ("người mẫu"): cut out with rembg; optionally lip-synced with SadTalker (install_talker.ps1)

TALKER = HERE / "talker"
TALK_CODE, TALK_PY = TALKER / "sadtalker", TALKER / ".venv" / "Scripts" / "python.exe"
_REMBG: dict = {}


def talker_ready() -> bool:
    return TALK_PY.exists() and (TALK_CODE / "checkpoints" / "SadTalker_V0.0.2_256.safetensors").exists() \
        and (TALK_CODE / "gfpgan" / "weights" / "detection_Resnet50_Final.pth").exists()


def cut_model(src: Path, dst: Path) -> None:
    """Person photo → RGBA cut-out cropped to the person (rembg u2net_human_seg, CPU, ~2 s)."""
    from PIL import Image, ImageOps
    from rembg import new_session, remove
    if "s" not in _REMBG:
        _REMBG["s"] = new_session("u2net_human_seg")
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((1600, 1600))
        cut = remove(im, session=_REMBG["s"])
    alpha = cut.getchannel("A").point(lambda v: 255 if v > 128 else 0)   # bbox of the solid part, not haze
    box = alpha.getbbox()
    if not box or (box[2] - box[0]) * (box[3] - box[1]) < 0.02 * cut.width * cut.height:
        raise RuntimeError("Không tìm thấy người trong ảnh người mẫu. Hãy dùng ảnh chụp rõ một người.")
    cut.crop(box).save(dst)


def talking_model(job: dict, cut: Path, voice_wav: Path, total: float, work: Path) -> tuple[Path, Path] | None:
    """SadTalker 'full' + still: only the face moves, the body stays, so the cut-out's own alpha
    is the matte for every frame. Returns (talking video on gray, matte) or None on failure."""
    from PIL import Image
    src, mask = work / "_talk_src.png", work / "_talk_mask.png"
    with Image.open(cut) as im:
        im = im.convert("RGBA")
        im.thumbnail((900, 900))   # the face is pasted back per frame; bigger only costs time
        im = im.crop((0, 0, im.width // 2 * 2, im.height // 2 * 2))
        bg = Image.new("RGBA", im.size, (128, 128, 128, 255))
        bg.alpha_composite(im)
        bg.convert("RGB").save(src)
        im.getchannel("A").save(mask)
    audio = work / "_talk.wav"
    ffmpeg("-i", voice_wav, "-af", f"adelay={int(VOICE_LEAD * 1000)}:all=1,apad=whole_dur={total:.3f}",
           "-ar", "16000", "-ac", "1", audio)
    out_dir = work / "_talk"
    out_dir.mkdir(exist_ok=True)
    log(job, f"  Người mẫu nhép miệng theo giọng đọc (SadTalker, khoảng {max(1, round(total * 12 / 60))} phút)…")
    try:
        with GPU:
            TTS.unload(job)
            run_cmd(job, [TALK_PY, "inference.py", "--driven_audio", audio, "--source_image", src, "--result_dir", out_dir,
                          "--still", "--preprocess", "full", "--size", "256", "--checkpoint_dir", "checkpoints"], cwd=TALK_CODE)
    except Exception as e:
        log(job, f"  Không làm được người mẫu nhép miệng ({e}); dùng ảnh tĩnh.")
        return None
    vids = sorted(out_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
    return (vids[-1], mask) if vids else None


def overlay_presenter(job: dict, base: Path, dst: Path, w: int, h: int, side: str, cut: Path,
                      talk: tuple[Path, Path] | None, preview: bool) -> None:
    """Presenter stands at the bottom on `side`, slides in during the first half second."""
    from PIL import Image
    with Image.open(cut) as im:
        cw, ch = im.size
    mh = h * (0.6 if h > w else 0.88)
    mw = mh * cw / ch
    if mw > w * 0.62:   # wide photo (arms out, half body): limit the width instead
        mw, mh = w * 0.62, w * 0.62 * ch / cw
    mw, mh = int(mw) // 2 * 2, int(mh) // 2 * 2
    x = w - mw - int(w * 0.02) if side == "right" else int(w * 0.02)
    start = w if side == "right" else -mw
    xe = f"if(lt(t,0.45),{start}+({x}-({start}))*sin(t/0.45*PI/2),{x})"
    y = h - mh + int(mh * 0.02)
    if talk:
        inputs = ["-i", str(base), "-i", str(talk[0]), "-loop", "1", "-i", str(talk[1])]
        pre = (f"[1:v]scale={mw}:{mh},format=rgba[tv];[2:v]scale={mw}:{mh},format=gray[mk];[tv][mk]alphamerge[m];")
    else:
        inputs = ["-i", str(base), "-loop", "1", "-i", str(cut)]
        pre = f"[1:v]scale={mw}:{mh},format=rgba[m];"
    log(job, "  Ghép người mẫu" + (" (đang nói)" if talk else "") + f" bên {'phải' if side == 'right' else 'trái'}")
    ffmpeg(*inputs, "-filter_complex", pre + f"[0:v][m]overlay=x='{xe}':y={y}:eof_action=repeat:shortest=0[v]",
           "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "ultrafast" if preview else "fast",
           "-crf", "26" if preview else "18", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "copy",
           "-t", f"{probe(base)['duration']:.3f}", dst)


def run_entry(rdir: Path) -> dict:
    return json.loads((rdir / "run.json").read_text(encoding="utf-8"))


def save_run(rdir: Path, run: dict) -> None:
    (rdir / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")


def update_run(rdir: Path, fn) -> dict:
    """Read-modify-write run.json under the project lock: the page assigns clips while the job still
    writes voices for other variants, and neither may overwrite the other."""
    with PLOCK:
        run = run_entry(rdir)
        fn(run)
        save_run(rdir, run)
        return run


# ---- "Clip từ Muse": per-scene requests the user pastes into Muse (muse.ai, Meta's agent; no public API).
# Measured 2026-11-05: "Tạo một video dọc 9:16 dài 5 giây: …" → 720x1280, 5.0 s, ~30 s to make, Download in "…".
MUSE_URL = "https://muse.ai/"
CAMERA = ["máy quay tiến chậm vào chủ thể", "máy quay lia ngang chậm từ trái sang phải", "máy quay lùi ra từ từ",
          "máy quay lướt nhẹ từ dưới lên", "máy quay cố định, chủ thể chuyển động nhẹ nhàng"]
ASPECT_WORDS = {"9:16": "dọc 9:16", "16:9": "ngang 16:9", "1:1": "vuông 1:1", "4:5": "dọc 4:5"}
DOWNLOADS = Path(os.environ.get("STUDIO_DOWNLOADS") or HOME / "Downloads")
CLIP_EXT = {".mp4", ".mov", ".webm", ".m4v"}


def muse_prompt(shot: dict, sub: str, aspect: str, i: int) -> str:
    scene = shot.get("desc") or f"hình ảnh minh hoạ cho câu \"{sub}\""
    return (f"Tạo một video {ASPECT_WORDS.get(aspect, 'dọc 9:16')} dài 5 giây: {scene.rstrip('.')}, {CAMERA[(i - 1) % len(CAMERA)]}. "
            "Phong cách quảng cáo, chân thực, ánh sáng đẹp, không có chữ, không có logo.")


def clip_segment(clip: Path, dst: Path, d: float, w: int, h: int, preview: bool) -> None:
    """AI clip → exactly d seconds at w x h: cover-crop; a clip shorter than the line is slowed down up
    to 1.5x, then its last frame is held."""
    frames = max(2, round(d * 30))
    cd = probe(clip)["duration"] or d
    factor = min(max(d / cd, 1.0), 1.5)
    vf = (f"setpts={factor:.4f}*PTS,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
          f"fps=30,tpad=stop_mode=clone:stop_duration={d + 0.5:.2f}")
    ffmpeg("-i", clip, "-vf", vf, "-an", "-frames:v", str(frames), "-c:v", "libx264",
           "-preset", "ultrafast" if preview else "veryfast", "-crf", "26" if preview else "20", "-pix_fmt", "yuv420p", "-r", "30", dst)


def write_scene_texts(job: dict, engine: str, s: dict, brief: str, images_txt: str, subs: list[str]) -> dict[str, str]:
    """One visible 5-second scene per voice line, for Muse. The small local model, asked inside the
    script call, covered only 2 of 7 lines, so this is its own call."""
    log(job, f"Viết yêu cầu tạo clip cho {len(subs)} cảnh…")
    written: dict[str, str] = {}
    try:
        raw, _ = ai_generate(job, engine, s, scriptgen.SCENES_SYSTEM, scriptgen.scenes_prompt(brief, images_txt, subs),
                             None, scriptgen.SCENES_SCHEMA)
        for x in raw.get("scenes") or []:
            try:
                i = int(x.get("line"))
            except (TypeError, ValueError):
                continue
            text = scriptgen.clean_scene(x.get("scene"))
            if 1 <= i <= len(subs) and text:
                written.setdefault(str(i), text)
    except Exception as e:
        log(job, f"  Không viết được yêu cầu cảnh ({e}).")
    missing = len(subs) - len(written)
    if missing:
        log(job, f"  {missing} cảnh chưa có mô tả, hãy điền trước khi duyệt.")
    return written


def write_variant(job: dict, run: dict, k: int, engine: str, s: dict) -> dict:
    """Step 1 for variant k: the script (and, for Muse, one scene request per line)."""
    req = run["request"]
    n_img = len(run["images"])
    images_txt = run.get("images_txt", "")
    log(job, f"Viết kịch bản {k + 1}/{req['variants']}…")
    brief = req["brief"] + (f"\nTên thương hiệu / người bán: {req['brand']}" if req.get("brand") else "")
    if run.get("model"):
        brief += ("\nVideo có một người mẫu đứng giới thiệu sản phẩm: lời đọc là lời người mẫu nói trực tiếp với "
                  "người xem, tự nhiên, xưng \"mình\" và gọi người xem là \"bạn\". "
                  + (f"Người mẫu tên là {req['model_name']}." if req.get("model_name")
                     else "Không biết tên người mẫu: không để người mẫu tự giới thiệu tên."))
    prompt, _ = scriptgen.user_prompt(brief, req["duration"], req["style"], req.get("audience", ""),
                                      scriptgen.ANGLES[k % len(scriptgen.ANGLES)], images_txt, n_img)
    t1 = time.time()
    raw, model = ai_generate(job, engine, s, scriptgen.SYSTEM, prompt, None, scriptgen.SCHEMA_IMG if n_img else scriptgen.SCHEMA)
    out = tidy_or_fail(raw, n_img)
    doc = save_script(req, engine, model, time.time() - t1, out, auto_run=run["id"])
    v = {"status": "chờ duyệt", "include": True, "script_id": doc["id"], "title": out["title"], "hook": out["hook"]}
    if req.get("clips") == "muse":
        v["scene_text"] = write_scene_texts(job, engine, s, req["brief"], images_txt, [l["sub"] for l in out["lines"]])
    return v


def variant_from_script(job: dict, run: dict, engine: str, s: dict) -> dict:
    """Step 1 from a script the user already wrote in the 📝 Kịch bản tab. It is copied, so edits made
    here don't change the original. Muse scenes come from its shot list; the AI fills only the gaps."""
    req = run["request"]
    src = json.loads(script_path(run["from_script"]).read_text(encoding="utf-8"))
    log(job, f"Dùng kịch bản có sẵn: {src['title']} ({len(src['lines'])} câu)")
    n_img = len(run["images"])
    shots = {x["line"]: x for x in src.get("shots", [])}
    out = {k2: src.get(k2, "") for k2 in ("title", "hook", "lower_third", "end_card")}
    out["lines"] = src["lines"]
    out["shots"] = [{"line": i, "desc": shots.get(i, {}).get("desc", ""), "prompt_en": shots.get(i, {}).get("prompt_en", ""),
                     **({"image": shots.get(i, {}).get("image") or ((i - 1) % n_img) + 1} if n_img else {})}
                    for i in range(1, len(src["lines"]) + 1)]
    doc = save_script(req, src.get("engine", ""), src.get("model", ""), 0, out, auto_run=run["id"], copied_from=src["id"])
    v = {"status": "chờ duyệt", "include": True, "script_id": doc["id"], "title": out["title"], "hook": out["hook"]}
    if req.get("clips") == "muse":
        texts = {str(i): scriptgen.clean_scene(sh["desc"]) or sh["prompt_en"] for i, sh in
                 ((x["line"], x) for x in out["shots"]) if scriptgen.clean_scene(sh["desc"]) or sh["prompt_en"]}
        gaps = [i for i in range(1, len(out["lines"]) + 1) if str(i) not in texts]
        if gaps:
            more = write_scene_texts(job, engine, s, req["brief"], run.get("images_txt", ""), [l["sub"] for l in out["lines"]])
            texts.update({str(i): more[str(i)] for i in gaps if str(i) in more})
        v["scene_text"] = texts
    return v


def produce_variant(job: dict, rdir: Path, k: int) -> None:
    """Step 2 for an approved variant: voice; then Muse scene list (wait for clips) or the slideshow render."""
    run = run_entry(rdir)
    req, v = run["request"], run["variants"][k]
    doc = json.loads(script_path(v["script_id"]).read_text(encoding="utf-8"))
    log(job, f"Giọng đọc cho video {k + 1}…")
    voice = job_voice(job, {"text": scriptgen.voice_text(doc["lines"]), "title": f"Video tự động {k + 1} - {doc['title']}",
                            "voice": req.get("voice") or "Hải Đăng", "myvoice": req.get("myvoice") or "",
                            "takes": req.get("takes", 3), "speed": req.get("speed", 1.0), "gap": 0.35})
    upd = {"voice_id": voice["id"], "total": round(VOICE_LEAD + voice["total"] + VOICE_TAIL, 2), "title": doc["title"],
           "hook": doc["hook"], "status": "đã có giọng"}
    if req.get("clips") == "muse":
        shots = {x["line"]: x for x in doc["shots"]}
        texts = v.get("scene_text") or {}
        starts = [0.0] + [VOICE_LEAD + l["start"] for l in voice["lines"][1:]]
        ends = starts[1:] + [upd["total"]]
        upd["scenes"] = [{"line": i, "sub": l["sub"], "seconds": round(ends[i - 1] - starts[i - 1], 1),
                          "image": shots.get(i, {}).get("image", 0),
                          "prompt": muse_prompt({"desc": texts.get(str(i), "")}, l["sub"], req["aspect"], i)}
                         for i, l in enumerate(voice["lines"], 1)]
        upd["clips"] = {}
        upd["status"] = "chờ clip"
    update_run(rdir, lambda r: r["variants"][k].update(upd))
    if req.get("clips") != "muse":
        render_variant(job, rdir, k)


def render_variant(job: dict, rdir: Path, k: int) -> dict:
    run = run_entry(rdir)
    req, v = run["request"], run["variants"][k]
    imgs = [WORK / p for p in run["images"]]
    cut = rdir / "model-cut.png" if run.get("model") else None
    doc = json.loads(script_path(v["script_id"]).read_text(encoding="utf-8"))
    voice = voice_entry(VOICES / safe_id(v["voice_id"]))
    total = VOICE_LEAD + voice["total"] + VOICE_TAIL
    w, h = ASPECTS.get(req["aspect"], ASPECTS["9:16"])
    preview = req.get("quality") == "preview"
    if preview:
        w, h = w // 4 * 2, h // 4 * 2
    clips = {int(i): WORK / p for i, p in (v.get("clips") or {}).items() if (WORK / p).exists()}
    log(job, f"Dựng video {k + 1} ({total:.1f} giây" + (f", {len(clips)}/{len(voice['lines'])} cảnh dùng clip AI" if req.get("clips") == "muse" else "") + ")…")
    work = rdir / f"v{k + 1}"
    work.mkdir(exist_ok=True)
    side = ("right", "left")[k % 2] if cut else ""
    base, segs = build_slideshow(job, work, imgs, voice["lines"], doc["shots"], total, w, h, k, preview, side, clips)
    if cut:
        talk = None
        if req.get("model_talk") and talker_ready():
            talk = talking_model(job, cut, VOICES / voice["id"] / "voice_full.wav", total, work)
        pres = work / "_pres.mp4"
        overlay_presenter(job, base, pres, w, h, side, cut, talk, preview)
        base = pres
    st = {**DEFAULT_SETTINGS, "orig_volume": 0.0, "voice_id": voice["id"], "voice_offset": VOICE_LEAD, "voice_volume": 1.0,
          "music": run.get("music", ""), "music_volume": 0.22, "duck": True,
          "fx_fade": True, "fx_progress": True, "fx_whoosh": bool(imgs or clips),
          "fx_transition": ["none", "flash", "dip", "none"][k % 4] if (imgs or clips) else "none",
          "fx_hook_on": bool(doc["hook"]), "fx_hook": doc["hook"],
          # the AI's lower third is often a guess (it misreads logos); only the name the user typed is shown
          "fx_lower_on": bool(req.get("brand")), "fx_lower": req.get("brand", ""),
          "fx_lower_align": "right" if side == "left" else "left",   # never over the presenter
          "fx_end_on": bool(doc["end_card"]), "fx_end": doc["end_card"]}
    cues = [c for l in voice["lines"] for c in caption_chunks(l["sub"], l["start"] + VOICE_LEAD, l["end"] + VOICE_LEAD)]
    subs = work / "subs.srt"
    subs.write_text("\n".join(f"{i}\n{srt_stamp(a)} --> {srt_stamp(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1)),
                    encoding="utf-8")
    fxv = work / "_fx.mp4"
    final = apply_video_fx(job, base, fxv, st, w, h, segs, total, preview, subs, work)
    old = WORK / v["file"] if v.get("file") else None
    out = unique(rdir / f"video-{k + 1}-{slug(doc['title'], 'video')}.mp4")
    mix_audio(job, fxv, out, st, final, [g["a"] for g in segs if g["cut"] == "scene"], work)
    shutil.rmtree(work, ignore_errors=True)
    if old and old.exists() and old != out:
        old.unlink()   # re-render after adding clips replaces the earlier cut
    info = {"status": "xong", "file": rel(out), "duration": probe(out)["duration"], "size_mb": round(out.stat().st_size / 1e6, 1),
            "clips_used": len(clips)}
    update_run(rdir, lambda r: r["variants"][k].update(info))
    log(job, f"Xong video {k + 1}: {out.name}")
    return info


def job_autovideo(job: dict, rdir: Path) -> dict:
    """Step 1 (scripts). Stops at 'chờ duyệt kịch bản': the user edits, then approves (job_auto_produce)."""
    run = run_entry(rdir)
    req = run["request"]
    s = ai_settings()
    engine = req.get("engine") or s["engine"]
    t0 = time.time()
    imgs = [WORK / p for p in run["images"]]

    if run.get("model"):
        log(job, "Tách nền ảnh người mẫu…")
        cut_model(WORK / run["model"], rdir / "model-cut.png")
        if req.get("model_talk") and not talker_ready():
            log(job, "Chưa cài phần nhép miệng (chạy install_talker.ps1); người mẫu sẽ là ảnh tĩnh.")

    if imgs:
        log(job, f"AI xem {len(imgs)} ảnh…")
        ai_dir = rdir / "_ai"
        ai_dir.mkdir(exist_ok=True)
        small = []
        for i, p in enumerate(imgs, 1):
            q = ai_dir / f"img{i}.jpg"
            prep_image(p, q, 896)
            small.append(b64(q))
        desc, _ = ai_generate(job, engine, s, scriptgen.DESCRIBE_SYSTEM, scriptgen.describe_prompt(len(imgs), req["brief"]),
                              small, scriptgen.DESCRIBE_SCHEMA)
        shutil.rmtree(ai_dir, ignore_errors=True)
        notes, txt = scriptgen.images_text(desc), scriptgen.images_text(desc, with_text=False)
        run = update_run(rdir, lambda r: r.update(image_notes=notes, images_txt=txt))
        log(job, "AI thấy:\n" + notes)

    n = 1 if run.get("from_script") else int(req["variants"])
    run = update_run(rdir, lambda r: r.update(variants=[{"status": "chờ"} for _ in range(n)]))
    for k in range(n):
        try:
            v = variant_from_script(job, run, engine, s) if run.get("from_script") else write_variant(job, run, k, engine, s)
            update_run(rdir, lambda r: r["variants"][k].update(v))
        except Exception as e:
            err = str(e)
            update_run(rdir, lambda r: r["variants"][k].update(status="lỗi", error=err, include=False))
            log(job, f"Kịch bản {k + 1} lỗi: {e}")
    ok = sum(v.get("status") == "chờ duyệt" for v in run_entry(rdir)["variants"])
    update_run(rdir, lambda r: r.update(status="chờ duyệt kịch bản" if ok else "lỗi", seconds=round(time.time() - t0)))
    if not ok:
        raise RuntimeError("Không viết được kịch bản nào. Xem nhật ký bên dưới.")
    log(job, f"Xong bước 1: {ok} kịch bản. Đọc, sửa rồi bấm Duyệt để tạo video.")
    return run_entry(rdir)


def job_auto_rewrite(job: dict, rdir: Path, k: int) -> dict:
    s = ai_settings()
    run = run_entry(rdir)
    engine = run["request"].get("engine") or s["engine"]
    update_run(rdir, lambda r: r["variants"][k].update(status="đang viết lại", error=""))
    try:
        v = write_variant(job, run, k, engine, s)
    except Exception as e:
        err = str(e)
        update_run(rdir, lambda r: r["variants"][k].update(status="chờ duyệt", error=err))
        raise
    update_run(rdir, lambda r: r["variants"][k].update(v))
    return run_entry(rdir)["variants"][k]


def job_auto_produce(job: dict, rdir: Path) -> dict:
    """Step 2 (+3 for slides): voice for every approved script, then clips/render."""
    t0 = time.time()
    run = update_run(rdir, lambda r: r.update(status="đang tạo video"))
    todo = [k for k, v in enumerate(run["variants"]) if v.get("include") and v.get("status") == "chờ duyệt"]
    for k in todo:
        try:
            produce_variant(job, rdir, k)
        except Exception as e:
            err = str(e)
            update_run(rdir, lambda r: r["variants"][k].update(status="lỗi", error=err))
            log(job, f"Video {k + 1} lỗi: {e}")
    vs = run_entry(rdir)["variants"]
    muse = run["request"].get("clips") == "muse"
    status = "chờ clip" if muse and any(v.get("status") == "chờ clip" for v in vs) else \
             ("xong" if any(v.get("status") == "xong" for v in vs) else "lỗi")
    update_run(rdir, lambda r: r.update(status=status, seconds=(r.get("seconds") or 0) + round(time.time() - t0)))
    log(job, "Đã có giọng đọc. Lấy clip từ Muse cho từng cảnh, rồi bấm Dựng." if muse else f"Hoàn tất sau {fmt_secs(time.time() - t0)}.")
    return run_entry(rdir)


def fmt_secs(x: float) -> str:
    x = round(x)
    return f"{x // 60} phút {x % 60} giây"


def job_render_variant(job: dict, rdir: Path, k: int) -> dict:
    update_run(rdir, lambda r: r["variants"][k].update(status="đang dựng", error=""))
    try:
        info = render_variant(job, rdir, k)

        def finish(r):   # step 3 reached once no approved video still waits for clips
            if not any(v.get("status") in ("chờ clip", "đang dựng", "đã có giọng") for v in r["variants"]):
                r["status"] = "xong"
        update_run(rdir, finish)
        return info
    except Exception as e:
        err = str(e)
        update_run(rdir, lambda r: r["variants"][k].update(status="lỗi dựng", error=err))
        raise


@app.post("/api/auto")
def create_auto(images: list[UploadFile] = File(default=[]), music: UploadFile | None = File(default=None),
                model: UploadFile | None = File(default=None), model_consent: bool = Form(False), model_talk: bool = Form(False),
                model_name: str = Form(""), clips: str = Form("slides"),
                brief: str = Form(...), duration: int = Form(30), style: str = Form("vui"), audience: str = Form(""),
                variants: int = Form(3), voice: str = Form("Hải Đăng"), myvoice: str = Form(""), takes: int = Form(3),
                speed: float = Form(1.0), aspect: str = Form("9:16"), quality: str = Form("final"), engine: str = Form(""),
                brand: str = Form(""), script_id: str = Form("")) -> dict:
    """New run. With `script_id` (a script from the 📝 Kịch bản tab) the AI writing is skipped: the run
    has one video made from that script, still stopping at step 1 for review."""
    brief = brief.strip()
    if script_id:
        src = json.loads(script_path(script_id).read_text(encoding="utf-8"))
        brief = brief or src.get("brief", "")
        variants = 1
    elif len(brief) < 10:
        raise HTTPException(400, "Hãy viết nội dung video rõ hơn (ít nhất một câu).")
    if len(images) > 10:
        raise HTTPException(400, "Tối đa 10 ảnh.")
    if myvoice:
        myvoice_dir(myvoice)
    rid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    rdir = AUTO / rid
    (rdir / "inputs").mkdir(parents=True)
    saved = []
    for i, f in enumerate(images, 1):
        ext = Path(f.filename or "").suffix.lower()
        if ext not in IMG_EXT:
            shutil.rmtree(rdir, ignore_errors=True)
            raise HTTPException(400, f"File {f.filename} không phải ảnh JPG/PNG/WEBP.")
        raw = rdir / "inputs" / f"raw{i}{ext}"
        raw.write_bytes(f.file.read())
        dst = rdir / "inputs" / f"anh-{i}.jpg"
        try:
            prep_image(raw, dst, 2400)
        except Exception:
            shutil.rmtree(rdir, ignore_errors=True)
            raise HTTPException(400, f"Không đọc được ảnh {f.filename}.")
        raw.unlink()
        saved.append(rel(dst))
    model_rel = ""
    if model is not None and model.filename:
        if not model_consent:
            shutil.rmtree(rdir, ignore_errors=True)
            raise HTTPException(400, "Hãy xác nhận bạn được phép dùng ảnh người mẫu này.")
        ext = Path(model.filename).suffix.lower()
        if ext not in IMG_EXT:
            shutil.rmtree(rdir, ignore_errors=True)
            raise HTTPException(400, "Ảnh người mẫu phải là JPG/PNG/WEBP.")
        raw = rdir / "inputs" / f"model-raw{ext}"
        raw.write_bytes(model.file.read())
        try:
            prep_image(raw, rdir / "inputs" / "nguoi-mau.jpg", 2000)
        except Exception:
            shutil.rmtree(rdir, ignore_errors=True)
            raise HTTPException(400, "Không đọc được ảnh người mẫu.")
        raw.unlink()
        model_rel = rel(rdir / "inputs" / "nguoi-mau.jpg")
    music_rel = ""
    if music is not None and music.filename:
        m = rdir / ("nhac" + (Path(music.filename).suffix.lower() or ".mp3"))
        m.write_bytes(music.file.read())
        music_rel = rel(m)
    req = {"brief": brief[:4000], "duration": min(max(int(duration), 10), 120), "style": style, "audience": audience[:300],
           "variants": min(max(int(variants), 1), 4), "voice": voice, "myvoice": myvoice, "takes": min(max(int(takes), 1), 5),
           "speed": min(max(float(speed), 0.8), 1.25), "aspect": aspect if aspect in ASPECTS else "9:16",
           "quality": "preview" if quality == "preview" else "final", "engine": engine, "brand": brand.strip()[:60],
           "model_talk": bool(model_talk and model_rel), "model_name": model_name.strip()[:40] if model_rel else "",
           "clips": "muse" if clips == "muse" else "slides"}
    save_run(rdir, {"id": rid, "created": time.time(), "status": "đang làm", "request": req, "images": saved,
                    "music": music_rel, "model": model_rel, "variants": [], "from_script": script_id})
    return {"id": rid, "job": start_auto_job(rid, "auto", job_autovideo, rdir)}


def list_auto_one(d: Path) -> dict:
    """run.json plus, for scripts still in step 1, the editable text (lines, end card, scene requests)."""
    run = run_entry(d)
    run["busy"] = auto_busy(run["id"])
    for v in run.get("variants", []):
        if v.get("script_id") and v.get("status") in ("chờ duyệt", "đang viết lại"):
            try:
                doc = json.loads(script_path(v["script_id"]).read_text(encoding="utf-8"))
            except (HTTPException, OSError, ValueError):
                continue
            sc = v.get("scene_text") or {}
            v["script"] = {"title": doc["title"], "hook": doc["hook"], "end_card": doc["end_card"],
                           "rows": [{"text": l["sub"] if l["say"] == scriptgen.to_speech(l["sub"]) else f"{l['say']} | {l['sub']}",
                                     "scene": sc.get(str(i), "")} for i, l in enumerate(doc["lines"], 1)]}
    return run


@app.get("/api/auto")
def list_auto() -> list:
    out = []
    for d in sorted(AUTO.iterdir(), reverse=True):
        if (d / "run.json").exists():
            try:
                out.append(list_auto_one(d))
            except (OSError, ValueError):
                continue
    return out


def auto_dir(rid: str) -> Path:
    d = AUTO / safe_id(rid)
    if not (d / "run.json").exists():
        raise HTTPException(404, "Không tìm thấy")
    return d


def variant_of(rdir: Path, k: int) -> dict:
    run = run_entry(rdir)
    if not 0 <= k < len(run["variants"]) or not run["variants"][k].get("voice_id"):
        raise HTTPException(400, "Video này chưa có kịch bản và giọng đọc")
    return run["variants"][k]


def store_clip(rdir: Path, k: int, line: int, src: Path | None = None, data: bytes | None = None, ext: str = ".mp4") -> dict:
    v = variant_of(rdir, k)
    if not any(sc["line"] == line for sc in v.get("scenes") or []):
        raise HTTPException(400, "Không có cảnh này")
    (rdir / "clips").mkdir(exist_ok=True)
    dst = rdir / "clips" / f"v{k + 1}-canh{line:02d}{ext}"
    for old in (rdir / "clips").glob(f"v{k + 1}-canh{line:02d}.*"):
        old.unlink()
    if src is not None:
        shutil.copy2(src, dst)
    else:
        dst.write_bytes(data or b"")
    info = probe(dst)
    if not info["has_video"]:
        dst.unlink()
        raise HTTPException(400, "File không phải video")
    run = update_run(rdir, lambda r: r["variants"][k].setdefault("clips", {}).__setitem__(str(line), rel(dst)))
    return {"file": rel(dst), "duration": info["duration"], "clips": run["variants"][k]["clips"]}


@app.post("/api/auto/{rid}/clip")
def upload_clip(rid: str, k: int = Form(...), line: int = Form(...), file: UploadFile = File(...)) -> dict:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in CLIP_EXT:
        raise HTTPException(400, "Chỉ nhận video MP4/MOV/WEBM")
    return store_clip(auto_dir(rid), k, line, data=file.file.read(), ext=ext)


@app.post("/api/auto/{rid}/grab")
def grab_clip(rid: str, body: dict = Body(...)) -> dict:
    """Newest finished video in Downloads saved after `since` (epoch seconds) → this scene's clip.
    The page calls it every few seconds after 'Chép & mở Muse'."""
    rdir = auto_dir(rid)
    k, line, since = int(body["k"]), int(body["line"]), float(body.get("since") or 0)
    if not DOWNLOADS.exists():
        return {"found": False, "error": f"Không thấy thư mục {DOWNLOADS}"}
    used = {json.dumps(x) for x in run_entry(rdir).get("grabbed", [])}
    cands = []
    for p in DOWNLOADS.iterdir():
        if p.suffix.lower() in CLIP_EXT and p.is_file():
            st = p.stat()
            key = json.dumps([p.name, round(st.st_mtime, 1)])
            if st.st_mtime >= since - 2 and st.st_size > 10_000 and key not in used:
                cands.append((st.st_mtime, p, key))
    if not cands:
        return {"found": False}
    _, p, key = max(cands)
    size = p.stat().st_size
    time.sleep(0.6)
    if p.stat().st_size != size:   # still downloading
        return {"found": False}
    out = store_clip(rdir, k, line, src=p, ext=p.suffix.lower())
    update_run(rdir, lambda r: r.setdefault("grabbed", []).append(json.loads(key)))
    return {"found": True, "name": p.name, **out}


@app.delete("/api/auto/{rid}/clip")
def remove_clip(rid: str, k: int, line: int) -> dict:
    rdir = auto_dir(rid)
    for old in (rdir / "clips").glob(f"v{k + 1}-canh{line:02d}.*"):
        old.unlink()
    run = update_run(rdir, lambda r: r["variants"][k].setdefault("clips", {}).pop(str(line), None))
    return {"clips": run["variants"][k]["clips"]}


def auto_busy(rid: str) -> bool:
    return any(j["status"] == "running" and j["kind"].startswith("auto") and rid in j.get("tag", "") for j in JOBS.values())


def start_auto_job(rid: str, kind: str, fn, *args) -> str:
    if auto_busy(rid):
        raise HTTPException(400, "Lần tạo này đang chạy một việc khác, đợi xong đã.")
    jid = start_job(kind, fn, *args)
    JOBS[jid]["tag"] = rid
    return jid


@app.put("/api/auto/{rid}/variant")
def edit_auto_variant(rid: str, body: dict = Body(...)) -> dict:
    """Step 1 edits: include/skip, title, hook, end card, and the rows (voice line + Muse scene)."""
    rdir = auto_dir(rid)
    k = int(body["k"])
    run = run_entry(rdir)
    if not 0 <= k < len(run["variants"]) or not run["variants"][k].get("script_id"):
        raise HTTPException(400, "Không có kịch bản này")
    v = run["variants"][k]
    if "include" in body:
        update_run(rdir, lambda r: r["variants"][k].update(include=bool(body["include"])))
    if any(x in body for x in ("rows", "title", "hook", "end_card")):
        if v.get("status") != "chờ duyệt":
            raise HTTPException(400, "Kịch bản đã duyệt. Bấm 'Sửa lại kịch bản' để sửa.")
        p = script_path(v["script_id"])
        doc = json.loads(p.read_text(encoding="utf-8"))
        for key in ("title", "hook", "end_card"):
            if isinstance(body.get(key), str):
                doc[key] = body[key].strip()[:80]
        scene_text = v.get("scene_text") or {}
        if isinstance(body.get("rows"), list):
            rows = [r for r in body["rows"] if isinstance(r, dict) and str(r.get("text") or "").strip()]
            if not rows:
                raise HTTPException(400, "Kịch bản cần ít nhất một câu")
            lines, scene_text = [], {}
            for i, r in enumerate(rows, 1):
                say, sep, sub = str(r["text"]).strip().partition("|")
                say, sub = say.strip(), (sub or say).strip()
                lines.append({"say": say if sep else scriptgen.to_speech(sub), "sub": sub})
                if str(r.get("scene") or "").strip():
                    scene_text[str(i)] = str(r["scene"]).strip()
            old = {sh["line"]: sh for sh in doc.get("shots", [])}
            n_img = len(run["images"])
            doc["lines"] = lines
            doc["shots"] = [{**old.get(i, {"desc": "", "prompt_en": ""}), "line": i,
                             **({"image": old.get(i, {}).get("image") or ((i - 1) % n_img) + 1} if n_img else {})}
                            for i in range(1, len(lines) + 1)]
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        update_run(rdir, lambda r: r["variants"][k].update(title=doc["title"], hook=doc["hook"], scene_text=scene_text))
    return list_auto_one(rdir)


@app.post("/api/auto/{rid}/rewrite")
def rewrite_auto_variant(rid: str, body: dict = Body(...)) -> dict:
    rdir = auto_dir(rid)
    k = int(body["k"])
    if run_entry(rdir)["variants"][k].get("status") not in ("chờ duyệt", "lỗi"):
        raise HTTPException(400, "Chỉ viết lại được kịch bản chưa duyệt")
    return {"job": start_auto_job(rid, "auto-rewrite", job_auto_rewrite, rdir, k)}


@app.post("/api/auto/{rid}/approve")
def approve_auto(rid: str) -> dict:
    rdir = auto_dir(rid)
    vs = run_entry(rdir)["variants"]
    if not any(v.get("include") and v.get("status") == "chờ duyệt" for v in vs):
        raise HTTPException(400, "Hãy chọn ít nhất một kịch bản để tạo video")
    return {"job": start_auto_job(rid, "auto-produce", job_auto_produce, rdir)}


@app.post("/api/auto/{rid}/reopen")
def reopen_auto_variant(rid: str, body: dict = Body(...)) -> dict:
    """Back to step 1 for one variant: its voice and clips are dropped (they no longer match the text)."""
    rdir = auto_dir(rid)
    k = int(body["k"])
    if auto_busy(rid):
        raise HTTPException(400, "Đang chạy, đợi xong đã.")
    for old in (rdir / "clips").glob(f"v{k + 1}-canh*.*") if (rdir / "clips").exists() else []:
        old.unlink()

    def back(r):
        v = r["variants"][k]
        for key in ("voice_id", "total", "scenes", "clips", "error"):
            v.pop(key, None)
        v.update(status="chờ duyệt", include=True)
        r["status"] = "chờ duyệt kịch bản"
    update_run(rdir, back)
    return list_auto_one(rdir)


@app.post("/api/auto/{rid}/render")
def render_auto_variant(rid: str, body: dict = Body(...)) -> dict:
    rdir = auto_dir(rid)
    k = int(body["k"])
    variant_of(rdir, k)
    return {"job": start_auto_job(rid, "auto-render", job_render_variant, rdir, k)}


@app.delete("/api/auto/{rid}")
def delete_auto(rid: str) -> dict:
    d = AUTO / safe_id(rid)
    if not (d / "run.json").exists():
        raise HTTPException(404, "Không tìm thấy")
    shutil.rmtree(d)
    return {"ok": True}


# -------- static -------------------------------------------------------------

app.mount("/files", StaticFiles(directory=str(WORK)), name="files")
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "static" / "index.html")
