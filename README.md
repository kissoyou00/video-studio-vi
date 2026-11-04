# Video Studio (tiếng Việt)

Ứng dụng web chạy **hoàn toàn trên máy** (Windows): dựng video theo lời nói và tạo giọng đọc tiếng Việt bằng AI. Không cần tài khoản, không cần internet sau khi cài, không tốn phí API.

- **Dựng video:** chuyển giọng nói thành chữ (Whisper offline), bấm vào chữ để cắt, tự cắt khoảng lặng, khung 9:16 / 16:9 / 1:1 / 4:5, chỉnh màu, phụ đề in lên video, 15 hiệu ứng tick chọn (Fade, Dip to black, Jump cut zoom, Ken Burns, Hook, Lower third, End card…), giọng đọc AI và nhạc nền tự nhỏ lại khi có tiếng nói, xuất chuẩn âm lượng mạng xã hội (-14 LUFS).
- **Tạo giọng đọc:** VieNeu-TTS v3, 25 giọng Bắc/Nam/Trung, hoặc **clone giọng** từ ghi âm micro / file 3–12 giây rồi **lưu lại và đặt tên** (thư viện "Giọng của tôi"), xuất MP3/WAV + phụ đề .srt. Giọng mặc định *Hải Đăng*, phong cách "rõ chữ". Được dùng thương mại (Apache-2.0).

Hướng dẫn sử dụng chi tiết: [HUONG-DAN.md](HUONG-DAN.md).

## Yêu cầu

- Windows 10/11, Python 3.10–3.12 (`winget install Python.Python.3.12`)
- Card NVIDIA (đã thử trên RTX 3050 4 GB). Không có card vẫn chạy được với `-CpuOnly`, nhưng chậm.
- Khoảng 10 GB trống (thư viện + model Whisper large-v3 ~3 GB, VieNeu ~260 MB)

## Cài đặt

```powershell
git clone https://github.com/<tai-khoan>/video-studio-vi.git
cd video-studio-vi
powershell -ExecutionPolicy Bypass -File install.ps1
```

Trình cài đặt tạo hai môi trường Python (`.venv` cho ứng dụng và giọng đọc, `.venv-whisper` cho chuyển chữ), cài ffmpeg nếu thiếu, và tạo biểu tượng **Video Studio** trên Desktop. Model tự tải ở lần dùng đầu.

## Chạy

- Bấm đúp **Video Studio** trên Desktop: chạy ẩn, trình duyệt tự mở (thường `http://127.0.0.1:8790`). Tắt bằng nút **⏻ Tắt ứng dụng** trong trang.
- `start.bat`: chạy có cửa sổ cmd để xem lỗi.
- Dữ liệu (dự án, video xuất, giọng đọc) lưu ở `%USERPROFILE%\VideoStudio`, nhật ký ở `%USERPROFILE%\VideoStudio\studio.log`.

## Cấu trúc

| Đường dẫn | Nội dung |
|-----------|----------|
| `app.py` | Máy chủ FastAPI: dự án, chuyển chữ, dựng video, hiệu ứng, trộn âm thanh, giọng đọc |
| `static/index.html` | Giao diện (một trang, không cần build) |
| `launch.py` | Chọn cổng trống 8790–8799, mở trình duyệt, chạy ẩn |
| `helpers/` | Script cắt/ghép/chuyển chữ lấy từ [browser-use/video-use](https://github.com/browser-use/video-use) (MIT), đã sửa cho Windows và Whisper offline |
| `skills/giong-mc-viet/` | Skill cho Claude Code: tạo giọng MC tiếng Việt từ kịch bản (VieNeu offline hoặc edge-tts) |
| `install.ps1`, `requirements-*.txt` | Cài đặt |

## Skill giọng MC cho Claude Code

Chép thư mục `skills/giong-mc-viet` vào `%USERPROFILE%\.claude\skills\`. Script offline cần Python có `vieneu`. Sau khi cài app có thể dùng `.venv\Scripts\python.exe` trong thư mục này thay cho đường dẫn ghi trong SKILL.md.

## Giấy phép

Mã của bên thứ ba và model: xem [THIRD-PARTY.md](THIRD-PARTY.md).
