"""Start Video Studio on a free local port and open the browser.

The Desktop shortcut runs this with pythonw.exe, so there is no console window: output goes to
~/VideoStudio/studio.log, startup problems show as a message box, and the app is closed from the
"Tắt ứng dụng" button in the web page. start.bat runs it with a visible console for debugging.

Other local tools often sit on common ports, so the app doesn't assume one: it reuses a running
Video Studio if there is one, otherwise it takes the first free port in PORTS.
"""

import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

PORTS = range(8790, 8800)
HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get("STUDIO_HOME", Path.home() / "VideoStudio"))
WINDOWLESS = sys.stdout is None   # pythonw

if WINDOWLESS:
    WORK.mkdir(parents=True, exist_ok=True)
    _log = open(WORK / "studio.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log
    print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} start =====")

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
_links = Path.home() / "AppData/Local/Microsoft/WinGet/Links"   # winget's ffmpeg
if _links.exists() and str(_links) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = str(_links) + os.pathsep + os.environ.get("PATH", "")
os.chdir(HERE)
sys.path.insert(0, str(HERE))


def alert(msg: str) -> None:
    print(msg)
    if WINDOWLESS:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "Video Studio", 0x10)


def is_studio(port: int) -> bool:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/info")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never via a proxy
        with opener.open(req, timeout=1) as r:
            return "voices" in json.loads(r.read())
    except Exception:
        return False


def is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def open_when_ready(url: str, port: int) -> None:
    for _ in range(120):
        if is_studio(port):
            webbrowser.open(url)
            return
        time.sleep(0.5)
    alert(f"Video Studio khởi động quá lâu. Xem nhật ký tại {WORK / 'studio.log'}")


def main() -> None:
    for port in PORTS:
        if is_studio(port):
            url = f"http://127.0.0.1:{port}"
            print(f"Video Studio dang chay san o {url}, mo trinh duyet.")
            webbrowser.open(url)
            return
    port = next((p for p in PORTS if is_free(p)), None)
    if port is None:
        alert(f"Không còn cổng trống trong khoảng {PORTS.start}-{PORTS.stop - 1}. Hãy tắt bớt ứng dụng khác rồi thử lại.")
        return
    url = f"http://127.0.0.1:{port}"
    print(f"Video Studio: {url}")
    if not WINDOWLESS:
        print("Trinh duyet se tu mo khi san sang. Dong cua so nay de tat ung dung.")
    threading.Thread(target=open_when_ready, args=(url, port), daemon=True).start()
    try:
        import uvicorn
        uvicorn.run("app:app", host="127.0.0.1", port=port)
    except Exception as e:
        alert(f"Video Studio không khởi động được: {e}\n\nXem nhật ký tại {WORK / 'studio.log'}")
        raise


if __name__ == "__main__":
    main()
