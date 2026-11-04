"""Score TTS takes with local Whisper: how many words differ from the text each take should say.

Used by Video Studio's "đọc 3 lần, chọn bản đúng nhất": the app writes a JSON list of
{"path": wav, "text": spoken text} and gets back, in the same order,
{"errors": int, "words": int, "heard": str, "diff": "expected→heard; …"}.

Whisper leans towards the northern accent, so southern readings (n/ng, ch/tr) count as errors
too. That bias is the same for every take of a line, so picking the take with the fewest
errors still picks the clearest one.

Usage:  python score_takes.py takes.json scores.json
"""

import difflib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from transcribe_local import _load_wav, get_model


def norm(s: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", s.lower()).split()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    items = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    model = get_model()
    out = []
    tmp = Path(tempfile.mkdtemp()) / "take16.wav"
    for it in items:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", it["path"], "-ac", "1", "-ar", "16000", str(tmp)],
                       check=True)
        segs, _ = model.transcribe(_load_wav(tmp), language="vi", vad_filter=False, beam_size=5,
                                   condition_on_previous_text=False)
        heard = " ".join(s.text.strip() for s in segs)
        a, b = norm(it["text"]), norm(heard)
        ops = [o for o in difflib.SequenceMatcher(a=a, b=b).get_opcodes() if o[0] != "equal"]
        out.append({"errors": sum(max(i2 - i1, j2 - j1) for _, i1, i2, j1, j2 in ops), "words": len(a),
                    "heard": heard,
                    "diff": "; ".join(f"{' '.join(a[i1:i2]) or '∅'}→{' '.join(b[j1:j2]) or '∅'}"
                                      for _, i1, i2, j1, j2 in ops)})
        print(f"scored {len(out)}/{len(items)}", flush=True)
    Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
