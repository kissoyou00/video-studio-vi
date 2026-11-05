"""Script writer for Video Studio: turns a short brief into a Vietnamese voice-over script
(one sentence per line), on-screen texts (hook / lower third / end card) and a shot list with
English prompts for AI video tools (Flow/Veo, Kling, Seedance...).

Engines:
- "ollama": free, offline, local model (default gemma3:4b, picked after comparing qwen2.5 3b/7b,
  qwen3 4b and gemma3 4b on Vietnamese ad scripts). Needs Ollama installed.
- "claude": Anthropic API with the user's own key (paid).
- "gemini": Google Gemini API with the user's own key (has a free tier for Flash models).

Small local models get numbers wrong when asked to spell them out, so the model writes normal text
(the subtitle) and `to_speech()` spells numbers, prices, percents, dates and times as Vietnamese
words for the voice. API keys are stored only in the user's data folder, never in this repo.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "gemma3:4b"
CLAUDE_MODELS = [  # (id, label) — the user picks; cost per script is roughly a few hundred to a few thousand đồng
    ("claude-opus-5-5", "Claude Opus 5.5 (hay nhất)"),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5 (rẻ hơn một nửa)"),
    ("claude-haiku-5-5", "Claude Haiku 5.5 (rẻ nhất, nhanh)"),
]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
WORDS_PER_SECOND = 2.7   # measured pace of VieNeu "Hải Đăng" at speed 1.0, incl. short pauses

STYLES = {
    "vui": "trẻ trung, vui vẻ, gần gũi như nói với bạn bè",
    "ban-hang": "bán hàng, thuyết phục, nhấn vào lợi ích và ưu đãi, có lời kêu gọi mua rõ ràng",
    "chuyen-nghiep": "chuyên nghiệp, rõ ràng, đáng tin cậy",
    "ke-chuyen": "kể chuyện, có mở đầu, diễn biến và kết, cảm xúc",
    "huong-dan": "hướng dẫn từng bước, dễ hiểu, câu ngắn",
}

# ---------------------------------------------------------------- output schema

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hook": {"type": "string"},
        "lower_third": {"type": "string"},
        "end_card": {"type": "string"},
        "lines": {"type": "array", "items": {"type": "string"}},
        "shots": {"type": "array", "items": {
            "type": "object",
            "properties": {"line": {"type": "integer"}, "desc": {"type": "string"}, "prompt_en": {"type": "string"}},
            "required": ["line", "desc", "prompt_en"], "additionalProperties": False}},
    },
    "required": ["title", "hook", "lower_third", "end_card", "lines", "shots"],
    "additionalProperties": False,
}

SYSTEM = """Bạn là biên kịch video ngắn tiếng Việt cho TikTok, Reels, YouTube Shorts và Facebook. Bạn viết lời đọc (voice-over) bằng tiếng Việt tự nhiên, đúng ngữ pháp, như người thật đang nói chuyện, không sáo rỗng.

Trả về JSON với các trường:
- "lines": lời đọc, mỗi phần tử là MỘT câu ngắn (8 đến 18 từ), đọc thành tiếng phải trôi chảy. Câu 1 gây tò mò hoặc nêu vấn đề ngay. Câu cuối là lời kêu gọi hành động phù hợp. Giữ đúng mọi thông tin người dùng đưa (tên, ngày, giá, phần trăm, địa chỉ); không bịa thêm số liệu, giá, địa chỉ hay tính năng không có trong yêu cầu. Số, giá, ngày viết bình thường bằng chữ số (ví dụ 299.000đ, 30%, 15/11). Không emoji, không hashtag, không gạch đầu dòng, không ghi chú trong ngoặc.
- "hook": chữ lớn hiện 3 giây đầu video, 3 đến 6 từ, gây tò mò.
- "lower_third": tên thương hiệu, người nói hoặc chủ đề, tối đa 6 từ.
- "end_card": lời kết hiện ở cuối video, 2 đến 6 từ.
- "title": tên ngắn cho kịch bản.
- "shots": danh sách cảnh, MỖI câu trong lines có đúng một cảnh, theo thứ tự. "line" là số thứ tự câu (bắt đầu từ 1). "desc" mô tả bằng tiếng Việt cần quay hoặc dựng gì. "prompt_en" là prompt tiếng Anh chi tiết để tạo video bằng AI: chủ thể, hành động, bối cảnh, góc máy, chuyển động máy, ánh sáng, phong cách; không yêu cầu chữ trên hình."""


def user_prompt(brief: str, duration: int, style: str, audience: str = "") -> tuple[str, int]:
    words = round(duration * WORDS_PER_SECOND)
    n = max(3, round(words / 11))
    tone = STYLES.get(style, style or STYLES["vui"])
    text = (f"Viết kịch bản cho video dài khoảng {duration} giây: khoảng {n} câu, tổng khoảng {words} từ.\n"
            f"Giọng điệu: {tone}.\n" + (f"Người xem: {audience.strip()}.\n" if audience.strip() else "")
            + f"Nội dung và thông tin cần có:\n{brief.strip()}")
    return text, n


# ---------------------------------------------------------------- numbers → Vietnamese words

DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
SCALES = ["", "nghìn", "triệu", "tỷ"]


def _three(n: int, full: bool) -> list[str]:
    """Read 0-999. `full` = not the leading group, so 5 reads 'không trăm linh năm'."""
    h, t, u = n // 100, n // 10 % 10, n % 10
    out: list[str] = []
    if h or full:
        out += [DIGITS[h], "trăm"]
    if t == 0:
        if u and out:
            out += ["linh", DIGITS[u]]
        elif u:
            out.append(DIGITS[u])
    elif t == 1:
        out.append("mười")
        if u:
            out.append("lăm" if u == 5 else DIGITS[u])
    else:
        out += [DIGITS[t], "mươi"]
        if u:
            out.append({1: "mốt", 4: "tư", 5: "lăm"}.get(u, DIGITS[u]))
    return out


def read_int(n: int) -> str:
    if n == 0:
        return "không"
    if n < 0:
        return "âm " + read_int(-n)
    groups = []
    while n:
        groups.append(n % 1000)
        n //= 1000
    words: list[str] = []
    top = len(groups) - 1
    for i in range(top, -1, -1):
        g = groups[i]
        if not g:
            continue
        scale = SCALES[i % 3] if i % 3 else ""
        words += _three(g, full=i != top)
        if i % 3:
            words.append(scale)
        if i and i % 3 == 0:   # 1e9, 1e18 …
            words.append("tỷ")
    return " ".join(words)


def read_digits(s: str) -> str:
    return " ".join(DIGITS[int(c)] for c in s if c.isdigit())


def read_number(tok: str) -> str:
    """'299.000' → thousands; '1,5' or '3.5' → decimal ('phẩy'); '2026' → plain."""
    tok = tok.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", tok) or re.fullmatch(r"\d{1,3}(,\d{3}){2,}", tok):
        return read_int(int(re.sub(r"[.,]", "", tok)))
    m = re.fullmatch(r"(\d+)[.,](\d+)", tok)
    if m:
        frac = m.group(2)
        frac_words = read_int(int(frac)) if len(frac) <= 2 and not frac.startswith("0") else read_digits(frac)
        return f"{read_int(int(m.group(1)))} phẩy {frac_words}"
    return read_int(int(re.sub(r"\D", "", tok) or 0))


UNITS = {"km": "ki lô mét", "kg": "ki lô gam", "cm": "xen ti mét", "mm": "mi li mét", "m2": "mét vuông",
         "m²": "mét vuông", "m3": "mét khối", "ml": "mi li lít", "gb": "gi ga bai", "mb": "mê ga bai",
         "mbps": "mê ga bít trên giây", "h": "giờ", "p": "phút", "s": "giây", "m": "mét", "l": "lít", "g": "gam"}
MONEY = {"k": "nghìn", "nghìn": "nghìn", "ngàn": "nghìn", "tr": "triệu", "triệu": "triệu", "tỷ": "tỷ", "tỉ": "tỷ"}
CURRENCY = {"đ": "đồng", "₫": "đồng", "vnđ": "đồng", "vnd": "đồng", "đồng": "đồng", "usd": "đô la", "$": "đô la"}
NUM = r"\d+(?:[.,]\d+)*"
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")


def to_speech(text: str) -> str:
    """Spell out numbers and symbols so VieNeu reads them correctly; text otherwise unchanged."""
    s = EMOJI.sub("", text)
    s = re.sub(r"#(\w+)", r"\1", s)

    def phone(m):   # 0901234567 / 0901 234 567 → digit by digit
        return read_digits(m.group(0))
    s = re.sub(r"(?<![\d.,])(?:\+?84|0)\d{2,3}[ .]?\d{3}[ .]?\d{3,4}(?!\d|[.,]\d)", phone, s)

    def time_(m):
        h, mi = int(m.group(1)), m.group(2)
        out = f"{read_int(h)} giờ"
        if mi and int(mi):
            out += " rưỡi" if int(mi) == 30 and not m.group(3) else f" {read_int(int(mi))} phút" if m.group(3) else f" {read_int(int(mi))}"
        return out
    s = re.sub(r"\b(\d{1,2})(?:h|g|:)(\d{2})?(p|')?(?![\d])", lambda m: time_(m) if int(m.group(1)) < 25 else m.group(0), s)

    def date(m):
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            return m.group(0)
        out = f"{read_int(d)} tháng {'tư' if mo == 4 else read_int(mo)}"
        return out + (f" năm {read_int(int(y) + (2000 if len(y) == 2 else 0))}" if y else "")
    s = re.sub(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}|\d{2}))?\b", date, s)

    def money(num: str, mult: str | None, rest: str | None, cur: str | None) -> str:
        words = read_number(num)
        mult, cur = (mult or "").lower(), (cur or "").lower()
        if mult:
            words += " " + MONEY[mult]
            if rest and mult in ("tr", "triệu"):   # 2tr5 → hai triệu năm trăm nghìn
                words += f" {read_int(int(rest.ljust(3, '0')[:3]))} nghìn"
        if cur:
            words += " " + CURRENCY[cur]
        return words
    s = re.sub(rf"({NUM})\s*(k|nghìn|ngàn|tr|triệu|tỷ|tỉ)?(\d{{1,3}})?\s*(đồng|vnđ|vnd|đ|₫|usd)(?!\w)",
               lambda m: money(*m.groups()), s, flags=re.I)
    s = re.sub(rf"({NUM})\s*(k|tr)(\d{{1,3}})?(?!\w)", lambda m: money(*m.groups(), None), s, flags=re.I)
    s = re.sub(rf"\$\s*({NUM})", lambda m: read_number(m.group(1)) + " đô la", s)
    s = re.sub(rf"({NUM})\s*%", lambda m: read_number(m.group(1)) + " phần trăm", s)
    s = re.sub(rf"({NUM})\s*(km|kg|cm|mm|m2|m²|m3|ml|gb|mb|mbps)(?!\w)",
               lambda m: read_number(m.group(1)) + " " + UNITS[m.group(2).lower()], s, flags=re.I)
    s = re.sub(rf"({NUM})\s*[-–]\s*({NUM})", lambda m: f"{read_number(m.group(1))} đến {read_number(m.group(2))}", s)
    s = re.sub(r"\b[xX](\d+)\b", lambda m: "nhân " + read_int(int(m.group(1))), s)
    s = re.sub(rf"({NUM})(?=[^\W\d_])", r"\1 ", s)   # 12A → 12 A, so the letter isn't glued to the word
    s = re.sub(NUM, lambda m: read_number(m.group(0)), s)
    s = s.replace("&", " và ").replace("+", " cộng ").replace("@", " a còng ")
    s = re.sub(r"[\"“”*_~<>\[\]{}]", "", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- engines

class ScriptError(RuntimeError):
    pass


def _http_json(url: str, body: dict | None = None, headers: dict | None = None, timeout: float = 600):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data, {"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def ollama_exe() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    cand = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(cand) if cand.exists() else None


def ollama_up() -> bool:
    try:
        _http_json(OLLAMA_URL + "/api/version", timeout=2)
        return True
    except Exception:
        return False


def ensure_ollama(log) -> None:
    if ollama_up():
        return
    exe = ollama_exe()
    if not exe:
        raise ScriptError("Chưa cài Ollama (AI viết chữ chạy trên máy). Cài bằng lệnh: winget install Ollama.Ollama, "
                          "hoặc chọn Claude / Gemini và dán khoá API.")
    log("Đang khởi động Ollama…")
    subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
    for _ in range(40):
        time.sleep(0.5)
        if ollama_up():
            return
    raise ScriptError("Không khởi động được Ollama. Thử mở ứng dụng Ollama rồi bấm tạo lại.")


def ollama_models() -> list[str]:
    try:
        return sorted(m["name"] for m in _http_json(OLLAMA_URL + "/api/tags", timeout=3).get("models", []))
    except Exception:
        return []


def ollama_pull(model: str, log) -> None:
    log(f"Đang tải model {model} lần đầu (vài GB, chỉ tải một lần)…")
    req = urllib.request.Request(OLLAMA_URL + "/api/pull", json.dumps({"model": model}).encode(),
                                 {"Content-Type": "application/json"})
    last = -10
    with urllib.request.urlopen(req, timeout=3600) as r:
        for raw in r:
            ev = json.loads(raw or b"{}")
            if ev.get("error"):
                raise ScriptError("Tải model lỗi: " + ev["error"])
            if ev.get("total") and ev.get("completed"):
                pct = int(ev["completed"] * 100 / ev["total"])
                if pct >= last + 10:
                    log(f"  đã tải {pct}%")
                    last = pct
    log("Tải model xong.")


def run_ollama(model: str, system: str, prompt: str, log) -> dict:
    ensure_ollama(log)
    if model not in ollama_models():
        ollama_pull(model, log)
    log(f"AI trên máy ({model}) đang viết… thường mất 30–90 giây.")
    body = {"model": model, "stream": True, "format": SCHEMA, "keep_alive": 0,   # free the 4 GB card right after
            "options": {"temperature": 0.7, "num_ctx": 4096},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
    if model.startswith("qwen3"):
        body["think"] = False
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    out, n, t0 = [], 0, time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            for raw in r:
                ev = json.loads(raw or b"{}")
                if ev.get("error"):
                    raise ScriptError("Ollama lỗi: " + ev["error"])
                out.append(ev.get("message", {}).get("content", ""))
                n += 1
                if n % 150 == 0:
                    log(f"  vẫn đang viết… ({time.time() - t0:.0f} giây)")
    except urllib.error.URLError as e:
        raise ScriptError(f"Không gọi được Ollama: {e}")
    return parse_json("".join(out))


def run_claude(key: str, model: str, system: str, prompt: str, log) -> dict:
    import anthropic
    if not key:
        raise ScriptError("Chưa có khoá API Claude. Dán khoá ở mục Cài đặt AI.")
    client = anthropic.Anthropic(api_key=key, timeout=300)
    log(f"Đang gọi {model}…")
    kwargs = dict(model=model, max_tokens=16000, system=system,
                  messages=[{"role": "user", "content": prompt}],
                  output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
    try:
        if model.startswith("claude-haiku"):
            resp = client.messages.create(**kwargs)
        else:   # if a safety classifier declines, the API retries on a fallback model in the same call
            resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    except anthropic.AuthenticationError:
        raise ScriptError("Khoá API Claude không đúng hoặc đã bị thu hồi.")
    except anthropic.PermissionDeniedError:
        raise ScriptError("Khoá API Claude không có quyền dùng model này.")
    except anthropic.NotFoundError:
        raise ScriptError(f"Không tìm thấy model {model}.")
    except anthropic.RateLimitError:
        raise ScriptError("Claude báo gọi quá nhiều hoặc hết hạn mức. Đợi một lúc rồi thử lại, hoặc kiểm tra số dư tài khoản.")
    except anthropic.BadRequestError as e:
        msg = str(e)
        if "credit" in msg.lower() or "balance" in msg.lower():
            raise ScriptError("Tài khoản Claude hết tiền (credit). Nạp thêm ở console.anthropic.com.")
        raise ScriptError("Claude từ chối yêu cầu: " + msg[-300:])
    except anthropic.APIStatusError as e:
        raise ScriptError(f"Claude lỗi máy chủ ({e.status_code}). Thử lại sau.")
    except anthropic.APIConnectionError:
        raise ScriptError("Không kết nối được tới Claude. Kiểm tra internet.")
    if resp.stop_reason == "refusal":
        raise ScriptError("Claude từ chối viết nội dung này.")
    if resp.stop_reason == "max_tokens":
        raise ScriptError("Kịch bản quá dài, bị cắt giữa chừng. Hãy giảm thời lượng.")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    u = resp.usage
    log(f"Claude dùng {u.input_tokens} token vào, {u.output_tokens} token ra.")
    return parse_json(text)


def gemini_models(key: str) -> list[str]:
    """Text models this key may call, best Flash first (model names change often, so ask the API)."""
    data = _http_json(f"{GEMINI_URL}/models?pageSize=200", headers={"x-goog-api-key": key}, timeout=20)
    names = [m["name"].split("/", 1)[-1] for m in data.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    names = [n for n in names if n.startswith("gemini") and not re.search(r"image|tts|audio|live|embedding|vision|robotics|computer", n)]

    def rank(n: str):
        ver = [float(x) for x in re.findall(r"gemini-(\d+(?:\.\d+)?)", n)] or [0]
        return (("flash" in n) and ("lite" not in n), "lite" not in n, "preview" not in n and "exp" not in n, ver[0], n)
    return sorted(set(names), key=rank, reverse=True)


def run_gemini(key: str, model: str, system: str, prompt: str, log) -> dict:
    if not key:
        raise ScriptError("Chưa có khoá API Gemini. Dán khoá ở mục Cài đặt AI.")
    if not model:
        models = gemini_models(key)
        if not models:
            raise ScriptError("Khoá Gemini không gọi được model viết chữ nào.")
        model = models[0]
    log(f"Đang gọi {model}…")
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "responseMimeType": "application/json", "responseJsonSchema": SCHEMA}}
    url = f"{GEMINI_URL}/models/{model}:generateContent"
    try:
        try:
            data = _http_json(url, body, {"x-goog-api-key": key}, timeout=300)
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            if "API key not valid" in e.read().decode("utf-8", "replace"):
                raise ScriptError("Khoá API Gemini không đúng.")
            body["generationConfig"].pop("responseJsonSchema")   # older models: JSON mode + schema in the prompt
            body["contents"][0]["parts"][0]["text"] += "\n\nCấu trúc JSON bắt buộc:\n" + json.dumps(SCHEMA, ensure_ascii=False)
            data = _http_json(url, body, {"x-goog-api-key": key}, timeout=300)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        m = re.search(r'"message":\s*"([^"]+)"', detail)
        detail = m.group(1) if m else detail[-300:]
        if e.code in (401, 403) or "API key not valid" in detail:
            raise ScriptError("Khoá API Gemini không đúng hoặc không có quyền.")
        if e.code == 429:
            raise ScriptError("Gemini báo hết lượt miễn phí (theo phút hoặc theo ngày). Đợi rồi thử lại.")
        raise ScriptError(f"Gemini lỗi {e.code}: {detail}")
    except urllib.error.URLError:
        raise ScriptError("Không kết nối được tới Gemini. Kiểm tra internet.")
    cands = data.get("candidates") or []
    if not cands:
        raise ScriptError("Gemini không trả lời (có thể nội dung bị chặn).")
    text = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))
    return parse_json(text)


def parse_json(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise ScriptError("AI trả về kết quả không đúng định dạng. Bấm tạo lại.")


# ---------------------------------------------------------------- tidy the result

def _clean(s) -> str:
    s = EMOJI.sub("", str(s or ""))
    s = re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", s)   # list markers the model sometimes adds
    return re.sub(r"\s+", " ", s).strip().strip('"“”')


def tidy(raw: dict) -> dict:
    lines = [_clean(x) for x in raw.get("lines") or [] if _clean(x)]
    if not lines:
        raise ScriptError("AI không viết được câu nào. Hãy ghi rõ nội dung hơn rồi tạo lại.")
    shots, seen = [], set()
    for s in raw.get("shots") or []:
        if not isinstance(s, dict):
            continue
        try:
            i = int(s.get("line"))
        except (TypeError, ValueError):
            continue
        if 1 <= i <= len(lines) and i not in seen:
            seen.add(i)
            shots.append({"line": i, "desc": _clean(s.get("desc")), "prompt_en": _clean(s.get("prompt_en"))})
    for i in range(1, len(lines) + 1):   # every line gets a shot, even if the model skipped one
        if i not in seen:
            shots.append({"line": i, "desc": "", "prompt_en": ""})
    shots.sort(key=lambda s: s["line"])
    return {
        "title": _clean(raw.get("title"))[:80] or lines[0][:60],
        "hook": _clean(raw.get("hook"))[:60],
        "lower_third": _clean(raw.get("lower_third"))[:60],
        "end_card": _clean(raw.get("end_card"))[:60],
        "lines": [{"sub": l, "say": to_speech(l)} for l in lines],
        "shots": shots,
    }


def voice_text(lines: list[dict]) -> str:
    """Script in the voice tab's format: 'say | sub' when the subtitle differs from what is read."""
    return "\n".join(l["say"] if l["say"] == l["sub"] else f"{l['say']} | {l['sub']}" for l in lines)
