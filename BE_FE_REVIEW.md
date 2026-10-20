# Rà soát BE/FE để tích hợp TTS

Ngày rà soát: 2026-10-20. Phạm vi: source BE .NET, Flutter visitor, React curator portal, DBML và tài liệu mapping FE. Đây là ghi nhận trạng thái trong repository, không phải xác nhận hệ thống đã triển khai trên môi trường chạy thật.

## Tóm tắt kiến trúc hiện có

- BE hiện là **một ASP.NET Core Web API theo các project layer** (`API`, `Application`, `Domain`, `Infrastructure`) dùng EF Core/Npgsql/PostgreSQL. Chưa thấy nhiều backend service độc lập trong solution hiện tại. AI TTS và AI Vision hiện là các service tách riêng trong repo `AI-System`.
- FE có hai ứng dụng chính: Flutter Visitor (`FrontEnd/smgs_mobile`) và React/Vite cho nghiệp vụ nhân viên/curator (`FrontEnd/smgs_web`). Cổng React hiện chứa visitor Flutter build trong `public/visitor`.
- DBML `BackEnd/project-docs/smgs_schema.dbml` mô tả thiết kế rộng hơn nhiều so với EF entities/migrations đang có.

## BE đã có

- `api/auth/register`, `api/auth/login` cho xác thực; cấu hình JWT và Identity nằm ở Infrastructure.
- `api/museums` và `api/artifacts` có CRUD qua controller/service/repository/DTO.
- Artifact có `id` kiểu int, `museumId`, `galleryId`, `code`, `name`, `qrCode`, trường bản đồ, `accessLevel`, `isActive`, `createdAt`.
- Danh sách artifact hỗ trợ lọc museum/gallery/keyword/isActive và phân trang. Artifact có thể tìm theo QR trong `keyword`, nhưng chưa có endpoint quét QR chuyên biệt.
- Migration hiện có Identity, museums, floors, galleries, artifacts. Không thấy entity, DbSet, migration hoặc API cho `languages`, `narrations`, `narration_versions`, `media`, `artifact_contents`.

## DBML đã đề xuất nhưng BE chưa có

- Luồng script thuyết minh dự kiến theo DBML: `artifacts.qr_code` → `narrations` lọc artifact/ngôn ngữ/length/detail → `narration_versions` chọn `status = published AND is_current = true` → lấy `script`.
- Các bảng và trạng thái đó hiện **chưa được triển khai trong EF/migrations/API**. Query mẫu trong README TTS chỉ là hướng dẫn hợp đồng tương lai; không chạy được trực tiếp với schema migration hiện tại.
- DBML tự ghi rõ là đề xuất chưa chốt. Cần BE bổ sung migration/entities/endpoint trước khi FE có thể lấy narration đã duyệt từ database.

## Flutter hiện có

- Có màn chi tiết artifact và lựa chọn “Bản thuyết minh”.
- `QRScanScreen._scan()` gọi `AppServices.recognition`; cấu hình hiện tại là `MockRecognitionService`, tự trả artifact đầu tiên trong museum. Chưa dùng camera/QR decoder thật và không gọi `api/artifacts`.
- `NarrationScreen` lấy `artifact.aiGuide` từ mock data. `NarrationPlayer` chỉ tăng timer giả; không phát audio, không gọi TTS.
- `DiscoveryApiService` gọi một số API khám phá nhưng không có API artifact/narration. Base URL mặc định `http://10.0.2.2:5000`, còn launch profile BE hiện khai báo HTTP `5169` / HTTPS `7104`; cần cấu hình theo device/environment trước khi kết nối.
- `pubspec.yaml` hiện chưa có package audio player, QR scanner hoặc TTS client.

## React portal hiện có

- Artifact, audio URL và nội dung curator trong `mockData.js` là dữ liệu mô phỏng, không phải record database.
- AI Content Studio tạo bài narration giả lập trong frontend rồi gửi vào luồng curation state của FE.
- `FrontEnd/DBML_FE_MAPPING.md` đã chỉ đúng `audio_narration` → `narration_versions`, nhưng backend hiện chưa có API/bảng đó. Portal chưa thể lưu nội dung/audio đã duyệt vào BE.

## Hợp đồng tích hợp khuyến nghị

1. Flutter quét QR thật để lấy chuỗi QR; gọi BE `GET /api/artifacts/by-qr/{qrCode}/narrations?language=vi&lengthLevel=medium&detailLevel=basic` (đề xuất route, chưa tồn tại).
2. BE trả artifact summary cùng `narrationId`, `narrationVersionId`, `script`, enum status, `audioUrl` nếu có. BE chỉ expose `published/current`, kiểm tra artifact active và quyền free/premium.
3. Nếu `audioUrl` có audio curator đã duyệt thì Flutter phát URL. Nếu không có, Flutter gửi **script** đến `POST /api/v1/speech` ở TTS service và phát bytes `audio/wav`.
4. TTS service giữ stateless với database nghiệp vụ; không nhận QR/artifact ID làm nguồn nội dung và không tự tạo/biên tập script. Cache WAV hiện tại là cache nội bộ của service, chưa được lưu thành `narration_versions.audio_url`.
5. Để không gửi lại text tốn băng thông mỗi lần, Flutter có thể giữ audio URL/cache cục bộ; hoặc BE dùng một internal worker gọi TTS khi narration version được publish, upload WAV lên object storage, rồi cập nhật `audio_url`. Đây là lựa chọn vận hành cần nhóm quyết định.

## Thứ tự triển khai để có end-to-end

1. Chốt DBML và thêm entity/config/migration cho `languages`, `narrations`, `narration_versions` (và media/storage nếu dùng audio URL).
2. Thêm endpoint public read-only theo QR, ngôn ngữ, độ dài, chi tiết; chỉ trả bản current/published.
3. Nối Flutter QR scanner và API client; thay mock narration bằng DTO BE.
4. Thêm Flutter audio playback và gọi TTS service khi không có audio URL.
5. Đặt TTS phía sau API gateway hoặc private network, xác thực request, giới hạn rate/text, cấu hình HTTPS/CORS nếu target web, và kiểm tra license model voice.
6. Nối React curation endpoints để nội dung duyệt thực sự cập nhật `narration_versions`; chỉ khi đó luồng curator → visitor mới end-to-end.

## Các điểm cần xử lý trước khi mở môi trường dùng thật

- Artifact POST/PUT/DELETE đang đánh dấu `[AllowAnonymous]`; cần khôi phục authorization cho role nhân viên/admin trước khi dùng production.
- `appsettings.Development.json` có JWT signing key và thông tin kết nối development được đặt trực tiếp trong file cấu hình. Không đưa các giá trị này ra log hoặc commit mới; chuyển secrets sang User Secrets/environment variables và thay key nếu giá trị đã được chia sẻ công khai.
- URL BE trong Flutter không khớp launch profile hiện tại; tránh hard-code một URL cho emulator, thiết bị vật lý và web.

## Kết luận riêng cho TTS

TTS service đã có API riêng nhận `{text, language, speed}` và trả WAV. Service có thể chạy độc lập, nhưng **chưa kết nối end-to-end** vì BE chưa phục vụ `narration_versions.script`, Flutter đang dùng QR/narration/player giả lập, và React curation đang giữ state mock. Nút thắt đầu tiên là API/domain narration trong BE; không nên tích hợp dựa trên bảng DBML như thể migration đã có.

## Cập nhật sau khi tạo AI Vision MVP

- `AI-System/AI Vision/` nay có service so khớp embeddings ảnh OpenCLIP với reference images đã index theo `artifactId`; đây là MVP mới trong repo, chưa có dữ liệu tham chiếu thật hoặc kiểm định accuracy.
- Endpoint nhận diện cần BE/API Gateway proxy vì dùng service key nội bộ; không đưa key vào Flutter.
- Kết nối BE/Flutter vẫn chưa có: BE chưa đồng bộ `artifact_reference_images` vào service, còn Flutter recognition vẫn mock.
