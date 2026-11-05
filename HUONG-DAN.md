# Video Studio — hướng dẫn nhanh

Ứng dụng chạy hoàn toàn trên máy (không cần internet sau khi cài): dựng video và tạo giọng đọc tiếng Việt.

## Mở ứng dụng

Bấm đúp **Video Studio** trên màn hình Desktop. Ứng dụng chạy ẩn (không có cửa sổ cmd), vài giây sau trình duyệt tự mở, thường ở `http://127.0.0.1:8790`.

**Tắt ứng dụng:** bấm nút **⏻ Tắt ứng dụng** ở góc trên bên phải trang. Đóng tab trình duyệt thì ứng dụng vẫn chạy ngầm; bấm lại biểu tượng trên Desktop sẽ mở lại đúng trang đó.

Nhật ký chạy được ghi vào `%USERPROFILE%\VideoStudio\studio.log`. Nếu cần xem lỗi trực tiếp, chạy `start.bat` trong thư mục này (có cửa sổ cmd, đóng cửa sổ để tắt).

Ứng dụng tự chọn cổng trống trong khoảng 8790–8799 (tránh các cổng hay bị chương trình khác dùng). Nếu Video Studio đang chạy rồi mà bạn bấm mở lần nữa, nó chỉ mở lại trình duyệt chứ không chạy thêm bản thứ hai.

Dự án, video đã xuất và giọng đọc được lưu ở `%USERPROFILE%\VideoStudio`.

## Viết kịch bản

Tab **📝 Kịch bản** viết sẵn lời đọc và cảnh quay từ vài dòng mô tả.

1. Ghi **nội dung video**: video nói về gì, kèm mọi thông tin phải có (tên, sản phẩm, giá, ngày, giờ, địa chỉ, ưu đãi). AI được dặn không bịa thêm số liệu, nhưng vẫn nên đọc lại.
2. Chọn **thời lượng** (15 giây đến 2 phút), **giọng điệu** (vui, bán hàng, chuyên nghiệp, kể chuyện, hướng dẫn) và người xem nếu muốn.
3. Bấm **✍️ Viết kịch bản**. Kết quả gồm:
   - **Lời đọc** từng câu. Số, giá, ngày, giờ, số điện thoại được đổi thành chữ để máy đọc đúng (ví dụ `25.000đ` → "hai mươi lăm nghìn đồng", `30/11` → "ba mươi tháng mười một"), phụ đề vẫn giữ chữ số. Sửa thoải mái rồi bấm **Lưu chỉnh sửa**; dòng mới gõ có số cũng tự đổi.
   - **Hook, Lower third, End card**: bấm **🎬 Điền chữ vào dự án đang mở** để điền và bật các hiệu ứng này ở tab Dựng video.
   - **Danh sách cảnh quay**: mỗi câu một cảnh, có mô tả tiếng Việt và prompt tiếng Anh. Bấm **Chép** rồi dán vào công cụ tạo video AI (Google Flow, Kling, Seedance…), tải clip về và kéo vào tab Dựng video.
4. Bấm **🎙️ Tạo giọng đọc từ kịch bản này** để chuyển lời đọc sang tab Tạo giọng đọc.

**Chọn AI viết** (khung bên phải):

| AI | Chi phí | Ghi chú |
|----|---------|---------|
| **Trên máy** (Ollama + Gemma 3 4B) | Miễn phí, không cần mạng | Khoảng 1 phút một kịch bản. Lần đầu tự tải model ~3,4 GB. Văn khá ổn, đôi khi thêm chi tiết chung chung, nên đọc lại. |
| **Google Gemini** | Có lượt miễn phí mỗi ngày | Lấy khoá tại aistudio.google.com/apikey. Nhanh, văn tốt. |
| **Claude** | Trả phí theo lượt (vài trăm đến vài nghìn đồng một kịch bản) | Lấy khoá tại console.anthropic.com. Văn hay nhất. Có thể chọn Opus (hay nhất), Sonnet hoặc Haiku (rẻ nhất). |

Khoá API chỉ lưu trên máy (`%APPDATA%\VideoStudio\ai-settings.json`), ngoài thư mục dữ liệu, và trang web chỉ hiện 4 ký tự cuối. Kịch bản đã viết lưu ở `%USERPROFILE%\VideoStudio\scripts`.

AI trên máy dùng cả card đồ hoạ, nên viết kịch bản, tạo giọng và chuyển chữ chạy lần lượt, không cùng lúc.

## Dựng video

1. Tạo dự án, kéo thả các clip vào.
2. Bấm **Chuyển giọng nói thành chữ** (Whisper, chạy trên máy).
3. Mỗi clip chọn:
   - **Cắt theo lời nói**: chỉ giữ những đoạn có nói, bấm vào chữ để cắt đoạn đó (Shift + bấm để chọn cả khoảng, bấm đúp để nghe).
   - **Giữ nguyên cả clip**: cho clip không có lời (nhạc, cảnh quay đẹp…), có thể bỏ bớt vài giây đầu/cuối.
4. Thiết lập khung hình (9:16 TikTok…), màu, phụ đề, cắt khoảng lặng.
5. **Hiệu ứng dựng video**: tick những hiệu ứng muốn dùng (bảng dưới).
6. Âm thanh: chỉnh tiếng gốc, thêm giọng đọc AI (tạo ở tab bên cạnh), thêm nhạc nền (tự nhỏ lại khi có tiếng nói).
7. **Xem thử nhanh** (nửa độ phân giải) rồi **Xuất bản hoàn chỉnh** (1080p, âm lượng chuẩn mạng xã hội).

### Các hiệu ứng có thể tick

| Nhóm | Thuật ngữ | Làm gì |
|------|-----------|--------|
| Cắt ghép | **Fade in / Fade out** | Hiện dần ở đầu, tối dần ở cuối (hình và tiếng) |
| | **Transition** | Chuyển giữa hai clip: cắt thẳng, Dip to black (nháy đen) hoặc Flash (nháy trắng) |
| | **Jump cut zoom** | Phóng to/thu nhỏ xen kẽ ở mỗi chỗ cắt trong cùng clip để giấu vết cắt |
| | **Ken Burns** | Phóng to chậm ở clip "giữ nguyên cả clip" |
| | **Freeze frame** | Dừng hình cuối thêm 2 giây |
| Chữ & đồ hoạ | **Hook** | Tiêu đề lớn 3 giây đầu |
| | **Lower third** | Thanh tên ở giây 1–5 |
| | **End card / Outro** | Lời kết ở 2,5 giây cuối |
| | **Watermark** | Tên kênh mờ ở góc trên phải |
| | **Progress bar** | Thanh tiến trình ở mép trên |
| Hình ảnh | **Letterbox** | Viền đen trên dưới kiểu điện ảnh |
| | **Vignette** | Tối nhẹ 4 góc |
| | **Sharpen** | Làm nét |
| Âm thanh | **Noise reduction** | Giảm tiếng ồn nền của tiếng gốc |
| | **SFX whoosh** | Tiếng vút ở chỗ chuyển giữa hai clip |

Chuyển cảnh và whoosh chỉ xảy ra ở chỗ chuyển giữa **hai clip khác nhau**, không ở mỗi lần cắt chữ trong một clip (để không bị nháy liên tục). Phụ đề luôn được in sau cùng nên không bị hiệu ứng che. Chữ hiệu ứng không hiện được emoji (tự bỏ).

## Tạo giọng đọc

- Mỗi dòng là một câu. Viết số bằng chữ khi đọc; muốn phụ đề khác lời đọc thì dùng `|`, ví dụ: `Chỉ hai trăm chín mươi chín nghìn đồng thôi! | Chỉ 299.000đ thôi!`
- Giọng mặc định **Hải Đăng**, phong cách "Rõ chữ" (cài đặt đã được chọn sau khi so sánh nhiều model). Có 25 giọng Bắc / Nam / Trung.
- **Kiểm tra đọc sai** (mặc định bật): mỗi câu được đọc 3 lần, Whisper nghe lại và giữ bản đúng chữ nhất. Chậm hơn khoảng 5–7 lần so với đọc 1 lần (đoạn 13 câu mất khoảng 2,5 phút), nhưng chữ đọc sai giảm khoảng một nửa. Câu nào Whisper vẫn nghe khác được đánh dấu ⚠ trong "Từng câu": nghe lại, nếu sai thật thì sửa lời (ví dụ viết số bằng chữ) rồi tạo lại. Với giọng miền Nam, Whisper (quen giọng Bắc) hay tính n/ng, ch/tr, au/âu là "khác" dù đọc đúng giọng Nam.
- Viết số và ký hiệu bằng chữ khi có thể ("chương ba, câu một đến chín" thay cho "3, 1–9") để máy đọc tự nhiên hơn.
- Tải MP3/WAV/phụ đề .srt, hoặc bấm **Dùng cho dự án đang mở** để ghép vào video.
- VieNeu-TTS v3 được dùng thương mại; âm thanh có watermark AI không nghe thấy.

### Clone giọng và lưu lại ("Giọng của tôi")

1. Ở mục **🧬 Clone giọng mới**, đặt **tên giọng** (ví dụ "Giọng anh Tuấn").
2. Bấm **🎙 Ghi âm** rồi đọc to đoạn văn gợi ý, hoặc **📁 Chọn file** ghi âm / video có sẵn. Nên dài **45–60 giây** (ít nhất 15 giây): nói rõ, tự nhiên, ít tiếng ồn, chỉ một người nói. Thanh tiến trình có vạch xanh ở 45 giây; ghi âm tự dừng ở 60 giây. File dài hơn 60 giây chỉ dùng 60 giây đầu. Lần đầu ghi âm, trình duyệt sẽ hỏi quyền dùng micro.
3. Tick xác nhận đây là giọng của bạn hoặc bạn được phép dùng, bấm **Lưu giọng**. Ứng dụng phân tích giọng một lần (khoảng 20–30 giây với đoạn 60 giây) và đọc thử một câu để bạn nghe ngay.
4. Giọng đã lưu nằm trong danh sách **Giọng của tôi**: nghe thử, nghe đoạn ghi âm gốc, **Dùng giọng này**, **Đổi tên**, **Xoá**. Chọn "Giọng của tôi" ở mục **2. Giọng** khi tạo giọng đọc.

**Vì sao nên ghi dài?** Model giọng chỉ nhận đoạn mẫu ngắn (khoảng 7 giây), nên ứng dụng cắt đoạn dài thành nhiều đoạn ~7 giây ở chỗ ngắt nghỉ, phân tích từng đoạn rồi **lấy trung bình "dấu vân giọng"** của tất cả (bỏ đoạn lạc giọng như có tiếng ồn, người khác nói). Càng nhiều đoạn, giọng clone càng ổn định và giống hơn. Danh sách "Giọng của tôi" ghi rõ đã gộp bao nhiêu đoạn.

Giọng đã lưu ở `%USERPROFILE%\VideoStudio\refs`. Tên giọng không được trùng nhau. Xoá một giọng không xoá các bản giọng đọc đã tạo bằng giọng đó.

## Giới hạn hiện tại

- Clip không có âm thanh chưa dựng được (hãy thêm tiếng trước).
- Whisper đôi khi nghe nhầm hoặc "bịa" câu trong lúc có nhạc; ứng dụng tự lọc các câu kiểu "đăng ký kênh…", nhưng nên xem lại bản chữ.
- Phụ đề từ giọng đọc chia theo số chữ, đôi khi tách đôi một từ ghép ("GIỚI / THIỆU").
- Card đồ hoạ 4 GB: tạo giọng và chuyển chữ chạy lần lượt, không cùng lúc.

## Kỹ thuật (cho người sửa code)

- `app.py`: FastAPI, chạy trong `.venv` (cùng VieNeu). Chuyển chữ và dựng video gọi `helpers/transcribe.py` / `helpers/render.py` bằng `.venv-whisper` (đặt `STUDIO_WHISPER_PYTHON` để dùng Python khác).
- `static/index.html`: giao diện, không cần build.
- `launch.py`: chọn cổng, mở trình duyệt, ghi nhật ký khi chạy ẩn.
