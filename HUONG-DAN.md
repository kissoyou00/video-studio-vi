# Video Studio — hướng dẫn nhanh

Ứng dụng chạy hoàn toàn trên máy (không cần internet sau khi cài): dựng video và tạo giọng đọc tiếng Việt.

## Mở ứng dụng

Bấm đúp **Video Studio** trên màn hình Desktop. Ứng dụng chạy ẩn (không có cửa sổ cmd), vài giây sau trình duyệt tự mở, thường ở `http://127.0.0.1:8790`.

**Tắt ứng dụng:** bấm nút **⏻ Tắt ứng dụng** ở góc trên bên phải trang. Đóng tab trình duyệt thì ứng dụng vẫn chạy ngầm; bấm lại biểu tượng trên Desktop sẽ mở lại đúng trang đó.

Nhật ký chạy được ghi vào `%USERPROFILE%\VideoStudio\studio.log`. Nếu cần xem lỗi trực tiếp, chạy `start.bat` trong thư mục này (có cửa sổ cmd, đóng cửa sổ để tắt).

Ứng dụng tự chọn cổng trống trong khoảng 8790–8799 (tránh các cổng hay bị chương trình khác dùng). Nếu Video Studio đang chạy rồi mà bạn bấm mở lần nữa, nó chỉ mở lại trình duyệt chứ không chạy thêm bản thứ hai.

Dự án, video đã xuất và giọng đọc được lưu ở `%USERPROFILE%\VideoStudio`.

## Video tự động

Tab **⚡ Video tự động**: đưa ảnh + vài dòng gợi ý, ra 2–4 video hoàn chỉnh (giọng đọc, phụ đề, Hook, End card, nhạc), mỗi video một hướng kịch bản khác nhau để thử xem bản nào hiệu quả hơn. Làm theo 3 bước: **1. Hoàn thiện kịch bản → 2. Tạo video → 3. Dựng hoàn thiện** (thanh bước hiện ở mỗi lần tạo).

1. Kéo thả **ảnh sản phẩm** (không bắt buộc, tối đa 10 ảnh). Không có ảnh thì video dùng nền màu chuyển động.
2. **Người mẫu** (không bắt buộc): chọn ảnh một người, chụp rõ, mặt nhìn thẳng. Ứng dụng tự tách nền, cho người mẫu trượt vào và đứng giới thiệu ở góc dưới (mỗi video một bên), ảnh sản phẩm thu nhỏ sang phía còn lại; lời thoại viết theo kiểu người mẫu nói với người xem. Tick **Người mẫu nhép miệng** để mặt người mẫu tự nói theo giọng đọc (cần cài thêm, xem dưới; chậm: mỗi video 30 giây lâu thêm khoảng 5–6 phút trên card 4 GB). Bắt buộc tick xác nhận được người trong ảnh cho phép dùng hình ảnh. Giọng đọc nên chọn hợp với người mẫu (nam/nữ) hoặc dùng giọng đã clone của chính người đó.
3. Viết **gợi ý nội dung**: sản phẩm là gì, ưu điểm, giá, ưu đãi, khách hàng tiêu biểu, số điện thoại…
4. Chọn thời lượng, giọng điệu, số video (2–4), giọng đọc (có sẵn hoặc giọng đã clone), khung hình, nhạc nền nếu có.
   **Đã có kịch bản ở tab 📝 Kịch bản?** Mở kịch bản đó, bấm **⚡ Tạo video từ kịch bản này** (hoặc chọn nó ở ô **Kịch bản** của tab Video tự động). Ứng dụng dùng nguyên lời thoại và cảnh quay của kịch bản đó (1 video, bản sao nên sửa ở đây không đổi bản gốc), bỏ qua bước AI viết; cảnh nào thiếu mô tả thì AI viết thêm cho Muse.
5. **Bước 1, kịch bản:** bấm **✍️ Bước 1: Viết kịch bản** (hoặc **Dùng kịch bản đã chọn**). AI xem ảnh (bấm "AI thấy gì trong ảnh" để xem lại) và viết mỗi video một kịch bản theo một hướng: nêu vấn đề → giải pháp; lợi ích nổi bật trước; câu hỏi gây tò mò; bằng chứng thật. Mỗi bản khoảng 1 phút. Sau đó ứng dụng **dừng lại chờ bạn duyệt**: sửa tên, Hook, End card, từng câu thoại (số, giá, ngày cứ viết bằng chữ số, máy tự đọc đúng), thêm/bỏ câu, và với chế độ Muse thì sửa cả cảnh tương ứng mỗi câu. Bấm **Lưu**. Bản chưa ưng thì bấm **✍️ AI viết lại bản này**; bản không dùng thì bỏ tick.
6. **Bước 2, tạo video:** bấm **✅ Duyệt … kịch bản & tạo video**. Lúc này mới đọc giọng. Chế độ ảnh chuyển động thì tự dựng luôn (mỗi câu một cảnh, ảnh phóng chậm trên nền mờ hoặc lia dọc ảnh, tiếng vút ở chỗ đổi ảnh, mỗi video một kiểu chuyển cảnh). Chế độ Muse thì hiện danh sách cảnh để lấy clip (xem dưới).
7. **Bước 3, dựng hoàn thiện:** xem, tải MP4. Muốn sửa lời một video đã làm thì bấm **↩ Sửa lại kịch bản** (giọng đọc và clip của video đó sẽ làm lại).

### Clip AI từ Muse (muse.ai)

Ở mục **Hình cho từng cảnh**, chọn **Clip AI từ Muse**. Ở bước 1, mỗi câu thoại có thêm một ô "cảnh cho Muse" (AI viết sẵn, bạn sửa; AI trên máy đôi khi vẫn nhắc logo hay chữ trên màn hình, nên xoá các chi tiết đó). Sau khi duyệt và đọc giọng, ứng dụng hiện danh sách cảnh, mỗi cảnh có sẵn một yêu cầu tạo video viết cho Muse (ví dụ "Tạo một video dọc 9:16 dài 5 giây: một nhân viên kỹ thuật đang lắp màn hình quảng cáo trên tường…, máy quay tiến chậm…"), vẫn sửa được ngay trong ô.

Với mỗi cảnh:
1. Bấm **Chép & mở Muse**: yêu cầu được chép sẵn, trang muse.ai mở ra (đăng nhập tài khoản của bạn).
2. Trong ô chat Muse: Ctrl+V, Enter. Muse tạo video 5 giây trong khoảng 30 giây.
3. Bấm "…" ở video → **Download**. Ứng dụng tự nhận file vừa tải về thư mục Downloads (trong 10 phút) và gán vào đúng cảnh. Hoặc bấm **Chọn file** để chọn tay.

Có clip cho các cảnh muốn dùng (không cần đủ hết) thì bấm **🎬 Dựng video**: cảnh có clip dùng clip AI (cắt hoặc kéo chậm cho khớp lời), cảnh chưa có dùng ảnh chuyển động; người mẫu, phụ đề, Hook, nhạc vẫn ghép như thường. Thêm clip rồi bấm **Dựng lại** bao nhiêu lần cũng được. Muse không có API công khai nên bước tạo clip phải làm trên trang Muse; mỗi clip dùng một lượt trong tài khoản của bạn.

**Cài phần người mẫu nhép miệng** (một lần, tải khoảng 4 GB): mở PowerShell trong thư mục ứng dụng, chạy
`powershell -ExecutionPolicy Bypass -File install_talker.ps1`, rồi tắt và mở lại Video Studio. Phần này dùng SadTalker chạy trên máy: chỉ khuôn mặt cử động (miệng, mắt), người và tay đứng yên.

Với AI trên máy, 3 video 30 giây mất khoảng 6–10 phút (chọn "Đọc 3 lần" thì lâu hơn). Video lưu ở `%USERPROFILE%\VideoStudio\auto`. Chữ AI chép từ ảnh đôi khi sai dấu; ứng dụng không in chữ đó lên video, nhưng hãy đọc lại lời thoại trước khi đăng.

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
| **Google Gemini** | Miễn phí với khoá tạo ở Google AI Studio (không cần thẻ), có giới hạn lượt mỗi phút/ngày | Lấy khoá tại aistudio.google.com/apikey. Khoảng 30 giây một kịch bản, văn tốt hơn AI trên máy, xem ảnh tốt hơn. Để "Tự chọn model Flash": các model mới hay báo quá tải, ứng dụng tự chuyển sang model khác. Với gói miễn phí, Google có thể dùng nội dung gửi lên để cải thiện sản phẩm, nên đừng gửi thông tin nhạy cảm. |
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
