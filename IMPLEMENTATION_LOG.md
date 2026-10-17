# Implementation log

## 2026-10-16 — TTS microservice MVP

- Tạo service mới tại `tts-service/` theo cấu trúc microservice của repo `AI-System`.
- Thêm API `POST /api/v1/speech`: nhận văn bản, ngôn ngữ và tốc độ; trả WAV tiếng Việt.
- Dùng `sherpa-onnx` với voice Piper `vi_VN-vais1000-medium`; model chạy trong service container, không nằm trong Flutter và không gọi nhà cung cấp AI bên ngoài trong mỗi lượt nghe.
- Tải model/eSpeak ở lần chạy đầu và giữ trong Docker volume. Cache WAV theo nội dung, voice và tốc độ đọc.
- Thêm Docker Compose, health endpoint, giới hạn đầu vào và tài liệu nối Flutter.
- Ranh giới dữ liệu: Flutter/Content Catalog lấy nội dung đã duyệt; TTS service chỉ chuyển văn bản được gửi vào thành tiếng, không truy cập database hoặc tự biên soạn nội dung.
- AI nhận diện hiện vật chưa được triển khai; Flutter chưa được nối API trong thay đổi này.

## Còn lại trước khi chạy end-to-end

- Cần môi trường Docker có quyền truy cập internet ở lần khởi chạy đầu để tải model.
- Cần Content/Catalog API thực tế để Flutter lấy nội dung theo `artifactId` và chỉ trả nội dung đã xuất bản.
- Cần cập nhật Flutter để gửi nội dung đến service và phát bytes WAV.
- Cần xác nhận voice/license và nghe thử trên thuyết minh bảo tàng trước khi chọn làm voice production.
- Runtime chưa được khởi chạy trong phiên này; vì vậy model tải thực tế, chất lượng audio và thời gian đáp ứng chưa được xác nhận.

## 2026-10-17 — Đối chiếu schema BE

- Đọc `BackEnd/project-docs/smgs_schema.dbml`.
- Xác định QR nằm ở `artifacts.qr_code`; bài thuyết minh nằm ở `narrations`; văn bản phiên bản nằm ở `narration_versions.script`.
- Bổ sung mapping theo `language_id` → `languages.code`, `length_level`, `detail_level`; chỉ chọn `narration_versions.status = published` và `is_current = true`.
- Ghi rõ TTS Service chỉ nhận script từ Content/Catalog API, không đọc DB trực tiếp; DBML tự ghi là bản đề xuất chưa chốt.
- Làm rõ `narration_versions.audio_url`: nếu có audio được duyệt thì Flutter có thể phát trực tiếp; cache WAV nội bộ hiện tại chưa tự ghi ngược URL vào DB/object storage.
