# Implementation log

## 2026-10-26 — Dùng PostgreSQL chung với Backend

- AI Vision thay SQLite bằng PostgreSQL client `psycopg`; embeddings nằm trong schema `ai_vision` của cùng DB/instance đã cấu hình cho BE. Compose không còn volume/database riêng cho dữ liệu Vision; chỉ giữ volume cache model.
- 3D Scan thay SQLite job store bằng PostgreSQL, lưu job metadata trong schema `ai_3d_scan` của cùng DB. Ảnh scan và GLB vẫn nằm trên disk local trong PoC.
- Thêm cấu hình `AI_SYSTEM_DB_*`, `.env.example` (không chứa secret thật), yêu cầu Compose password và hướng dẫn khớp cấu hình BE. TTS không cần DB.
- Chưa nối metadata upload ảnh tham chiếu của portal vào BE API; AI Vision hiện giữ embeddings, còn BE cần sở hữu `artifact_reference_images`/media và gọi service.
- Runtime chưa xác minh kết nối DB vì PostgreSQL ở `127.0.0.1:5432` không lắng nghe trong môi trường hiện tại. Cần cấu hình `AI-System/.env` theo BE và chạy migration/khởi động PostgreSQL BE trước khi start AI Vision/3D Scan.
- `python -m compileall` cho AI Vision/3D Scan và `docker compose config --quiet` đạt. `python -m unittest discover -s tests -v` bỏ qua integration test vì máy chưa cài psycopg và chưa có DB test. Chưa build lại container: Docker Desktop Engine pipe hiện không khả dụng; host PostgreSQL cũng không lắng nghe ở `127.0.0.1:5432`, nên chưa kiểm tra kết nối/runtime.

## 2026-10-22 — Chuyển AI Vision sang CLIP ONNX

- Thay OpenCLIP/PyTorch image encoder bằng ONNX Runtime CPU trong `AI Vision/`; dùng pretrained CLIP ViT-B/32 ONNX image encoder từ `infinilabs/pizza-clip-base-v1`.
- Bổ sung tải model vào cache `/models` khi khởi động, preprocessing CLIP RGB 224×224, vector 512 chiều chuẩn hóa L2; giữ nguyên API index references và recognition.
- Bổ sung `model_id` cho từng embedding. Vector OpenCLIP đã có trong SQLite được giữ lại nhưng không đem so với ONNX vì cùng 512 chiều không đồng nghĩa cùng không gian vector. Ảnh tham chiếu cần index lại.
- Bỏ cài PyTorch/torchvision khỏi Docker image AI Vision; thêm `onnxruntime` và `huggingface_hub`.
- Chưa train/fine-tune model: pretrained CLIP là baseline tổng quát; chưa có benchmark trên bộ ảnh hiện vật SMGS.
- Chưa chạy inference do dependencies ONNX/FastAPI chưa cài trong môi trường. Docker image build bị sandbox chặn quyền truy cập Buildx lock; `docker compose config` vẫn đạt. Chưa xác minh tải artifact, output graph, preprocessing parity, dung lượng/RAM, tốc độ hoặc độ chính xác. Cần pin revision và kiểm tra license/hash trước production.
- `python -m unittest discover -s tests -v` (migration SQLite/cách ly embedding theo model commit), `python -m compileall` và `docker compose config` đạt.

## 2026-10-21 — 3D Scan PoC và Flutter model URL

- Thêm `3D Scan/` như microservice riêng trong `AI-System`, nhận nhiều ảnh JPG/PNG, giới hạn dung lượng, lưu job SQLite và đưa tái tạo COLMAP vào background.
- Dùng pipeline COLMAP tự động, tìm mesh Poisson/Delaunay, thử tạo texture atlas rồi xuất GLB; job dừng ở `REVIEW_REQUIRED` để không tự xuất bản model chưa duyệt.
- Bảo vệ API bằng `X-Service-Key`; endpoint chỉ dành cho gọi server-to-server. Chưa nối service key vào web/mobile.
- Flutter `Artifact` nhận thêm `modelUrl` tùy chọn; màn hình 3D dùng URL của artifact và vẫn fallback sang GLB mẫu khi chưa có URL.
- Rà `smgs_schema.dbml`: bảng `artifacts` chưa có `model_url`, và Backend hiện chưa có scan-job/model-review API. Vì vậy chưa nối upload iPhone Safari, BE gateway, database, storage hay curator role.
- COLMAP CLI chưa được cài/xác minh trong môi trường hiện tại; PoC mới kiểm tra tĩnh. Cần cài COLMAP và thử bộ ảnh thật để xác nhận pipeline, texture, chất lượng GLB, thời gian và tài nguyên.
- `python -m compileall` và `git diff --check` thành công. FastAPI chưa cài trong môi trường nên chưa chạy endpoint; COLMAP executable và .NET SDK cũng chưa có, do đó chưa kiểm thử runtime/BE build. Web build hiện có thành công; Flutter analyze không trả kết quả trong phiên kiểm tra và đã dừng.

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

## 2026-10-20 — Rà soát source BE/FE để xác định tích hợp TTS

- Rà solution .NET, EF entities/migrations, API controllers, Flutter visitor, React portal, DBML và tài liệu mapping.
- Xác nhận BE hiện là một ASP.NET Core API chia project layer; migration hiện chưa có các bảng narration trong DBML.
- Xác nhận Flutter đang mock QR recognition, nội dung narration lấy từ mock `artifact.aiGuide`, player dùng timer và chưa có playback/TTS client.
- Xác nhận React curation cũng dùng state/mock data; mapping FE đến `narration_versions` chưa có endpoint/backend persistence thực tế.
- Ghi hợp đồng nối phù hợp và thứ tự công việc trong `BE_FE_REVIEW.md`.
- Nêu các điểm môi trường cần giải quyết: base URL Flutter lệch launch profile BE và các endpoint ghi artifact đang allow anonymous. Giá trị secrets không được sao chép vào log.

## 2026-10-20 — Sắp xếp TTS và tạo AI Vision MVP

- Chuyển nội dung service TTS vào folder `TTS AI/` theo cấu trúc người dùng đưa.
- Tạo microservice `AI Vision/` dùng OpenCLIP embeddings để so khớp ảnh query với ảnh tham chiếu được index theo `artifactId`.
- Thêm API có xác thực service key để index/xóa ảnh tham chiếu và nhận diện ảnh; kết quả có similarity, top candidates và ngưỡng yêu cầu xác nhận.
- Embedding lưu trong SQLite volume; ảnh query không được lưu. Service không truy cập database BE.
- Cập nhật README cấp repo và README từng service để mô tả luồng hai service, cách chạy, nạp ảnh và giới hạn.
- `compileall` và `docker compose config` cho cả hai service đều thành công.
- Docker build AI Vision đã thử nhưng Docker Desktop Linux engine hiện không chạy (`dockerDesktopLinuxEngine` pipe không tồn tại), nên chưa xác minh được dependency install/model download/inference.
- Cần xác nhận tải model, dependencies, RAM, ngưỡng similarity và độ chính xác trên bộ ảnh thật khi Docker engine sẵn sàng.
