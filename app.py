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
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
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
        chain += drawtext_lines(fx_lines(edit, "lower", s["fx_lower"], fs, int(w * 0.8)), font_bold, fs, int(h * 0.54),
                                f"fontcolor=white:box=1:boxcolor={ACCENT}@0.92:boxborderw={pad}:"
                                f"enable='between(t,1,{b})':alpha='{fade_alpha(1, b)}'", x=str(int(w * 0.06) + pad))
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


def job_voice(job: dict, req: dict) -> dict:
    lines = parse_script(req.get("text", ""))
    if not lines:
        raise RuntimeError("Chưa có lời thoại")
    title = (req.get("title") or lines[0][1])[:60]
    vid = time.strftime("%Y%m%d-%H%M%S") + "-" + slug(title, "giong-doc")
    d = VOICES / vid
    d.mkdir(parents=True)
    ref = req.get("ref") or ""
    who = {"ref_audio": str(REFS / Path(ref).name)} if ref else {"voice": req.get("voice") or "Hải Đăng"}
    temp, top_k = float(req.get("temperature", 0.3)), int(req.get("top_k", 10))
    speed, gap = float(req.get("speed", 1.0)), float(req.get("gap", 0.4))
    with GPU:
        model = TTS.get(job)
        for i, (say, _) in enumerate(lines, 1):
            log(job, f"Câu {i}/{len(lines)}: {say[:70]}")
            audio = np.asarray(model.infer(say, **who, temperature=temp, top_k=top_k), dtype=np.float32)
            wav = d / f"line{i:02d}.wav"
            sf.write(str(wav), audio, SR)
            if abs(speed - 1.0) > 1e-3:   # atempo keeps the pitch
                tmp = d / f"line{i:02d}.tmp.wav"
                ffmpeg("-i", wav, "-af", f"atempo={speed}", "-ar", str(SR), tmp)
                os.replace(tmp, wav)
            ffmpeg("-i", wav, "-c:a", "libmp3lame", "-b:a", "192k", d / f"line{i:02d}.mp3")
    gap_s = np.zeros(int(round(gap * SR)), dtype=np.float32)
    parts, meta, srt, t = [], [], [], 0.0
    for i, (say, sub) in enumerate(lines, 1):
        audio, _ = sf.read(str(d / f"line{i:02d}.wav"), dtype="float32")
        dur = len(audio) / SR
        parts.append(audio)
        meta.append({"file": f"line{i:02d}.mp3", "say": say, "sub": sub, "start": round(t, 3), "end": round(t + dur, 3),
                     "duration": round(dur, 3)})
        srt.append(f"{i}\n{srt_stamp(t)} --> {srt_stamp(t + dur)}\n{sub}\n")
        t += dur
        if len(gap_s) and i < len(lines):
            parts.append(gap_s)
            t += len(gap_s) / SR
    sf.write(str(d / "voice_full.wav"), np.concatenate(parts), SR)
    ffmpeg("-i", d / "voice_full.wav", "-c:a", "libmp3lame", "-b:a", "192k", d / "voice_full.mp3")
    (d / "subtitles.srt").write_text("\n".join(srt), encoding="utf-8")
    info = {"id": vid, "title": title, "voice": ("nhái: " + Path(ref).stem) if ref else who["voice"],
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


@app.get("/api/refs")
def list_refs() -> list:
    return [{"name": f.name, "url": rel(f)} for f in sorted(REFS.glob("*.wav"))]


@app.post("/api/refs")
def upload_ref(file: UploadFile = File(...)) -> dict:
    raw = unique(REFS / f"_upload{Path(file.filename or '.wav').suffix.lower()}")
    with raw.open("wb") as out:
        shutil.copyfileobj(file.file, out, 1 << 20)
    dest = unique(REFS / f"{slug(Path(file.filename or 'giong').stem, 'giong')}.wav")
    try:   # mono 24 kHz, first 8 s (VieNeu clones from 3-8 s)
        ffmpeg("-i", raw, "-t", "8", "-ac", "1", "-ar", "24000", dest)
    finally:
        raw.unlink(missing_ok=True)
    return {"name": dest.name, "url": rel(dest), "duration": probe(dest)["duration"]}


# -------- static -------------------------------------------------------------

app.mount("/files", StaticFiles(directory=str(WORK)), name="files")
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "static" / "index.html")
