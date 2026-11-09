# Kiểm thử TTS tiếng Việt bằng model thật — 09/11/2026

Đã tải model Piper `vi_VN-vais1000-medium`, nạp bằng `sherpa-onnx 1.13.8` trên CPU Windows và gọi HTTP thật `POST /api/v1/speech`. Metadata ONNX xác nhận `language=Vietnamese`, `voice=vi`, sample rate 22050 Hz. Không dùng bộ tổng hợp giả lập trong các ca dưới đây.

**Cập nhật nghe trong sản phẩm:** đã có nút Tạo giọng đọc và audio player ngay trong Xưởng AI. Bài thử đăng nhập/JWT, BE, PostgreSQL schema riêng và Piper thật đã pass: phát/tạm dừng/tua/đổi tốc độ và bỏ audio khi sửa văn bản. Không mở WAV mẫu trong bài này. Xem [system-ui.json](system-ui.json) và [luồng sử dụng, giới hạn DB local](../../AI_STUDIO_PLAYBACK_2026_11_09.md).

| Mẫu | Tốc độ | Thời gian tạo lần đầu | Độ dài WAV | Kết quả |
| --- | ---: | ---: | ---: | --- |
| Thuyết minh máy nén khí do Qwen vừa soạn, giữ nguyên `7,5hp` | 1,0 | 3,796 giây | 7,639 giây | HTTP 200 |
| Tên riêng Ngọc Lũ, Đông Sơn và ngày tháng viết thành chữ | 1,0 | 0,581 giây | 5,503 giây | HTTP 200 |
| Máy nén khí, viết đơn vị thành “bảy phẩy năm mã lực” | 1,0 | 0,811 giây | 6,885 giây | HTTP 200 |
| Van mở dầu — chậm | 0,75 | 0,458 giây | 4,005 giây | HTTP 200 |
| Van mở dầu — nhanh | 1,25 | 0,338 giây | 3,390 giây | HTTP 200 |

Đây là thời gian quan sát trên máy local, không phải benchmark tải đồng thời/AWS. Các đoạn văn là dữ liệu kiểm thử, không phải nội dung đã được bảo tàng xuất bản.

## Đã kiểm tra

- Năm response là WAV PCM mono 16-bit, 22050 Hz, dữ liệu đầy đủ, không rỗng/không im lặng; tỷ lệ mẫu chạm biên clipping bằng 0 trong bộ thử này.
- Gọi lại mỗi mẫu trả server cache `HIT`, byte giống hoàn toàn lần đầu. Cùng nội dung nhưng speed khác sinh file/độ dài khác nhau.
- Request trống, ngôn ngữ ngoài tiếng Việt và speed ngoài khoảng đều bị từ chối 422.
- Browser Edge headless dùng **module FE thật** `ttsApi.js` → proxy Vite `/ai-tts` → TTS đang chạy. Ba mẫu đầu decode thành công, `currentTime` tiến khi phát, chạy đến `ended` không báo lỗi media. Cache FE trả lại cùng blob URL.
- Chín unit test TTS cũ vẫn pass; đó là lớp kiểm tra fixture riêng, không tính thay cho inference thật.

Kết quả máy đọc được: [results.json](results.json), [browser-playback.json](browser-playback.json). Có thể mở [trang nghe năm mẫu](listen.html) sau khi chạy script tạo WAV.

## Giới hạn

Browser phát được và WAV có tín hiệu chưa chứng minh phát âm chính xác từng từ. Chưa có người nghe chấm hoặc ASR độc lập xác nhận; chưa xác nhận tên riêng, niên đại hay viết tắt `hp` đọc đúng. Có bản nguyên văn và bản viết đơn vị thành chữ để nghe so sánh; không tự thay dữ kiện trong DB.

Chưa kiểm thử luồng Flutter widget → nội dung published trong DB thật → TTS trên cùng môi trường, chưa kiểm tra loa/thiết bị di động hoặc deploy. Kiểm thử mẫu WAV trong bảng bên trên là lượt riêng; nút nghe trong Xưởng AI và kiểm thử sản phẩm đã được thêm sau đó theo tài liệu liên kết ở đầu trang. TTS endpoint tự nó không xác minh trạng thái published; production cần gateway kiểm soát quyền/nội dung và giữ key nội bộ.

## Chạy lại

Đã có model tại `state/models/tts` (ignored). Nếu chưa có `.venv`, xem `TTS AI/README.md` để cài dependencies; script startup tải voice ở lần đầu có Internet.

Terminal TTS (local loopback; để trống `TTS_SERVICE_API_KEY` cho phép thử này):

```powershell
cd D:\SEP409\AI-System
.\tools\start-local-tts.ps1
```

Terminal kiểm thử API:

```powershell
cd D:\SEP409\AI-System
.\.venv\Scripts\python.exe tools/evaluate_local_tts.py
```

Terminal Vite:

```powershell
cd D:\SEP409\FrontEnd\smgs_web
npm run dev -- --host 127.0.0.1 --port 4173 --strictPort
```

Terminal kiểm thử browser:

```powershell
cd D:\SEP409\FrontEnd\smgs_web
node tools/check-real-tts.mjs
```

WAV/cache/model được gitignore để tránh đẩy file phát sinh lên Git. Script giữ báo cáo JSON; chạy lại khi cache đã có sẽ đo cache hit thay vì thời gian tạo mới.
