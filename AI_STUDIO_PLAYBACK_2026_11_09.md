# Nghe thuyết minh trực tiếp trong Xưởng AI — 09/11/2026

Đã thêm trình phát vào giao diện sản phẩm của Admin/Museum Staff. Người dùng không phải lưu hoặc mở file WAV thủ công.

## Cách sử dụng

**Xưởng nội dung AI → Thuyết minh âm thanh → Sinh nội dung bằng AI → sửa Nội dung bản nháp → Tạo giọng đọc → Phát bản đọc.**

Cũng có thể nhập bản thuyết minh trực tiếp vào **Nội dung bản nháp** rồi nghe, không cần model sinh văn bản thành công trước. Lần kiểm tra với nguồn seed đã gặp Qwen trả 502 do guard từ chối bản nháp; lỗi đó không được thay bằng nội dung mẫu và không nên khóa chức năng TTS của văn bản do nhân viên nhập.

Khối **Nghe bản thuyết minh** nằm ngay dưới ô chỉnh sửa. Có phát/tạm dừng, thanh tua và âm lượng của trình duyệt, tốc độ 0,75×/1×/1,25×. Piper tổng hợp ở 1×, tốc độ trong UI điều chỉnh playback, không nhân tốc độ hai lần.

Audio đọc văn bản hiện đang chỉnh sửa. Khi đổi văn bản hoặc hiện vật, hệ thống dừng/bỏ bản đọc cũ; phải tạo lại để nghe nội dung mới. Chuyển màn hình sẽ hủy yêu cầu FE đang chờ, dừng phát và thu hồi blob URL. Native inference có thể tiếp tục tới timeout dù FE đã hủy.

Tạo bản nghe không đệ trình, không duyệt/xuất bản và không ghi `audioUrl` vào DB. Nội dung vẫn theo luồng Museum Staff gửi → Curator thẩm định → xuất bản. Cache WAV nội bộ của TTS là tối ưu vận hành; người dùng nghe HTTP response ngay trong audio player. File mẫu ở lượt kiểm thử trước chỉ phục vụ đối chiếu.

## Luồng kỹ thuật

```text
Nút Tạo giọng đọc trong Xưởng AI
    → FE gửi JWT + artifactId + văn bản đang sửa
    → POST /api/artifacts/{id}/ai/speech-preview
    → BE kiểm tra Admin/Museum Staff và phân công hiện vật
    → Piper tiếng Việt qua khóa nội bộ
    → BE trả audio/wav
    → audio player trên giao diện phát trực tiếp
```

- FE không nhận service key và không gọi `/ai-tts` cho bản nghe của Xưởng AI. Dùng chung API base với các nghiệp vụ BE, phù hợp khi FE và BE ở máy khác nhau.
- Request `{"text":"Bản thuyết minh đang chỉnh sửa..."}`, tối đa 12000 ký tự. Chưa đăng nhập trả 401, sai role/phạm vi trả 403; không gọi model khi bị từ chối.
- BE cấu hình `ArtifactSpeech:Enabled`, `ArtifactSpeech:BaseUrl`, `ArtifactSpeech:ServiceKey`; typed HttpClient timeout 65 giây, response tối đa 32 MiB, không theo redirect hoặc ghi service key vào HTTP logs.
- FE timeout 70 giây, kiểm tra content type và WAV header trước khi tạo player. Model tắt/lỗi trả thông báo và nút thử lại, không phát file mẫu thay thế.
- Visitor hiện có `NarrationPlayer` trong màn thuyết minh và nghe câu trả lời AI. Transport Visitor hiện vẫn dùng `TTS_BASE_URL`/proxy `/ai-tts` cũ; cập nhật này chưa chuyển Visitor sang gateway speech-preview dành cho staff.

## Chạy local

Ba terminal dịch vụ:

```powershell
# 1. Piper tiếng Việt
cd D:\SEP409\AI-System
.\tools\start-local-tts.ps1

# 2. Model soạn văn bản
cd D:\SEP409\AI-System
.\tools\start-local-chat.ps1

# 3. BE bật cả model văn bản và giọng đọc
cd D:\SEP409\BackEnd\Smart_Museum_Guide_System
.\tools\start-api-with-local-chat.ps1
```

Portal:

```powershell
cd D:\SEP409\FrontEnd\smgs_web
npm run dev -- --host 127.0.0.1 --port 8090
```

Nếu chỉ cần BE với TTS, dùng `tools/start-api-with-local-tts.ps1`. Chỉ chạy một API ở port 5169. Khóa TTS local nằm tại `AI-System/state/tts-service-key.txt`, được gitignore. Script TTS mặc định giữ tương thích proxy FE/Flutter loopback hiện có; `-GatewayOnly` bật bắt buộc khóa nội bộ, chỉ dùng khi các client đều đi qua gateway có khóa. Các client Visitor/proxy cũ chưa truyền khóa nên không dùng cờ đó cho toàn hệ thống hiện tại.

Deploy: cấu hình ba giá trị `ArtifactSpeech__*` trên BE, URL trỏ tới TTS trong mạng server, cấu hình HTTPS/CORS API như các nghiệp vụ khác. Không dùng localhost của Vercel để gọi máy chứa model. Chưa deploy hoặc push trong lượt cập nhật này.

## Môi trường DB và kiểm chứng

DB local cũ trong container `smgs-postgres` khởi động được nhưng ứng dụng hiện báo `42703: column u.IsActive does not exist`. Chưa thay đổi schema/dữ liệu cũ để sửa lỗi này. Cần đồng bộ DB với phiên bản BE trước khi dùng ứng dụng chính ở port 5169.

Bộ kiểm tra `tests/SMGS.SpeechLiveChecks` tạo schema PostgreSQL riêng bằng EF model hiện hành, chạy API sản phẩm thật và Vite thật, đăng nhập tài khoản seed qua JWT, bấm các nút Xưởng AI bằng Edge rồi dọn schema thử sau khi kết thúc. Không dùng interceptor/mock response hoặc file WAV mẫu cho luồng này. Các seed chỉ nằm trong schema thử; không ghi vào schema ứng dụng hiện có.

```powershell
# Sau khi PostgreSQL, TTS và AI Chat đang chạy
cd D:\SEP409\BackEnd\Smart_Museum_Guide_System
dotnet run --project tests/SMGS.SpeechLiveChecks
```

Báo cáo thành công được ghi tại `evaluations/tts-2026-11-09/system-ui.json`, ảnh chụp trình phát ở `FrontEnd/smgs_web/test-results/studio-real-speech.png`. Nếu lần kiểm tra thất bại, xem lỗi lệnh chạy và ảnh `studio-real-speech-failed.png`; không coi việc có file báo cáo cũ là lần mới đã pass.

Các kiểm tra riêng đã pass: 30 test Node + 1 skip, BE guide/speech provider và HTTP role/phạm vi, 6 test Flutter playback/retry/tua/tốc độ/dọn request, browser test lỗi TTS trong Xưởng AI. Build web pass; còn cảnh báo bundle lớn và lint warnings sẵn có. Chất lượng phát âm vẫn cần người nghe chấm; browser phát được không chứng minh mọi tên riêng/đơn vị đọc đúng.

**Kết quả kiểm tra sản phẩm đã pass:** đăng nhập JWT thật, đọc danh sách hiện vật từ PostgreSQL schema thử, nhập/sửa nội dung trực tiếp trong Xưởng AI, bấm Tạo giọng đọc và nhận HTTP 200 từ BE/Piper thật. Trình phát chạy đến hết (6,885 giây), tạm dừng được, tua tới giây thứ 2, đổi tốc độ 1,25×; sửa văn bản xóa player/audio cũ. Không có lỗi JavaScript. Bài này dùng văn bản do người dùng nhập, không tính là Qwen đã sinh thành công; thử Qwen trước đó trả 502 và được ghi nhận là hạn chế riêng. Schema thử và các API/Vite process thử đã được dọn sau khi chạy.
