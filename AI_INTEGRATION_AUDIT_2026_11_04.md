# Rà soát AI-System và kết nối FE/BE — 04/11/2026

> Cập nhật sau rà soát: FE đã bổ sung playback audio thật cho Flutter, lấy bản thuyết minh published và ưu tiên audioUrl. Flutter analyze sạch, 68 test pass và 2 test Edge xác nhận phát WAV thực tế. Xem `FrontEnd/docs/TTS_REAL_AUDIO_2026_11_04.md`. Các nhận xét về player chỉ chạy timer bên dưới mô tả trạng thái trước bản sửa; gateway/deploy TTS và kiểm thử Piper thật vẫn còn cần hoàn thiện.

## Kết luận

AI-System chưa có commit remote mới hơn `be270a6` ngày 29/10/2026 sau khi chạy `git fetch origin --prune`; local `main` và `origin/main` cùng commit. Commit mới nhất bổ sung CI, không bổ sung model hoặc nghiệp vụ AI mới.

Các service TTS, Vision ONNX và 3D COLMAP đã có source, nhưng luồng sản phẩm chưa hoàn chỉnh. FE đã tiến xa hơn tài liệu AI cũ về kết nối BE; đồng thời còn lỗi hợp đồng API, thao tác nhận diện dùng ảnh mẫu, player chưa phát audio thật và thiếu gateway AI bên BE.

Đây là rà soát source hiện có trên máy và lịch sử remote AI-System, không phải xác nhận production đã chạy thành công. Không thay đổi nghiệp vụ, không tạo dữ liệu DB, không chạy training hoặc tác vụ dựng 3D trong lần rà soát này.

## Trạng thái theo tính năng

| Tính năng | Đã có | Phần còn thiếu hoặc sai |
| --- | --- | --- |
| TTS tiếng Việt | API sinh WAV, cache, client React/Flutter | Player Flutter chỉ chạy timer; chưa phát WAV. Audio tạo ở React là blob trong phiên, chưa phải audio được lưu vào nội dung published. |
| Vision | CLIP ONNX, embeddings PostgreSQL, index/xóa reference, nhận diện và ngưỡng xác nhận | Flutter còn ảnh byte mẫu hoặc service mock; parser ứng viên lệch response; thiếu gateway xác thực Visitor và quản lý phạm vi bảo tàng. |
| 3D Scan | Nhận ảnh, job PostgreSQL, worker COLMAP, bước REVIEW_REQUIRED → COMPLETED | FE cho 3 ảnh trong khi API cần ít nhất 10; preview URL và xác thực tải GLB chưa nối đúng; duyệt scan chưa xuất bản model vào BE. |
| Soạn thuyết minh/quiz | UI Xưởng AI; quiz gợi ý có thể chuyển sang ngân hàng câu hỏi để sửa/lưu | Nội dung vẫn do template và setTimeout tạo, không có API model sinh nội dung trong AI-System hiện tại. |
| Hỏi đáp Visitor | UI hỏi đáp, câu trả lời gợi ý theo dữ liệu hiện vật | AppServices vẫn dùng MockAiGuideService; chưa có service RAG/chat hoặc endpoint tương ứng. |
| Lịch sử/điểm sau nhận diện ảnh | BE có ghi nhận quét QR và lịch sử | Chưa có endpoint ghi nhận kết quả nhận diện ảnh tương ứng. Không nên giả thành một lượt quét QR để nhận điểm hoặc cập nhật tiến độ. |

## P1 — Cần sửa trước khi demo luồng AI hoàn chỉnh

### 1. Gateway BE, xác thực và cấu hình triển khai

Bằng chứng:

- React gọi `/ai-tts`, `/ai-vision`, `/ai-scan`; Vite có proxy cho chạy dev/preview.
- `FrontEnd/vercel.json` hiện chỉ cấu hình build/output/header GLB, không có rewrite các đường dẫn AI. `.env.example` của React chỉ hướng dẫn API BE.
- Flutter mặc định gọi HTTP tại host trình duyệt và các port 8000/8001/8002 nếu không truyền cấu hình build. Trên web HTTPS, cấu hình mặc định này không bảo đảm truy cập được AI đã triển khai.
- React đưa service key vào các module `visionApi.js` và `scan3dApi.js` qua biến VITE hoặc giá trị dev mặc định. Đây là mã phía trình duyệt, không phải bí mật server.
- Vision bắt buộc `X-Service-Key`, nhưng Flutter chỉ gửi nếu bên gọi cung cấp; lời gọi nhận diện hiện tại không cung cấp key.
- Source controller và đăng ký HttpClient của BE hiện chưa có gateway TTS/Vision/Scan.

Cần làm:

1. Thêm gateway BE dùng JWT của hệ thống, kiểm tra role và phạm vi bảo tàng trước khi gọi AI.
2. Giữ service key tại server. FE gọi BE; server gọi AI bằng service key.
3. Chốt địa chỉ HTTPS cho từng môi trường; cấu hình proxy hoặc URL tương ứng khi deploy. Các biến môi trường thực tế trên Vercel chưa được kiểm tra trong lần này.
4. Gateway TTS lấy nội dung published đã được phép truy cập theo artifact/version; gateway không nên tin tùy ý một văn bản do Visitor gửi lên là nội dung đã được duyệt.

### 2. Player TTS Flutter chưa phát audio

`FrontEnd/smgs_mobile/lib/widgets/narration_player.dart:203–236` gọi TTS, lưu `SpeechResult`, rồi gọi `_startPlaybackTimer()`. Không có audio player phát `audioBytes`; tiến độ là số giây ước lượng. `pubspec.yaml` hiện cũng chưa có thư viện playback audio.

Cần nối WAV/audio URL với player hỗ trợ mobile và web; cập nhật play/pause/seek/tốc độ/thời lượng từ trạng thái phát thật. Kiểm tra trên browser vì Visitor hiện được xem tại `/visitor/`. Các lựa chọn độ dài/mức chi tiết cũng cần gắn nội dung thực tế hoặc thể hiện rõ giới hạn, thay vì chỉ đổi nhãn trên cùng văn bản.

### 3. Nhận diện ảnh Flutter vẫn dùng đường thử nghiệm

- `artifact_qr_scanner.dart:151–303` tạo `sampleBytes` trong code rồi gửi Vision, chưa lấy ảnh người dùng chọn/chụp.
- `qr_scan_screen.dart` ở chế độ recognition vẫn gọi `AppServices.recognition`, được khởi tạo bằng `MockRecognitionService`.

Cần thống nhất một luồng nhận ảnh thật từ camera/chọn tệp, gọi gateway, đọc artifact published từ BE, hiển thị ứng viên khi cần xác nhận và cho phép chuyển sang QR khi không khớp. Chỉ ghi lịch sử hoặc tính điểm sau khi BE xác thực kết quả. Giữ các mẫu AI/3D đã được yêu cầu trong khu vực demo riêng.

### 4. Hợp đồng Vision đang lệch

| Dữ liệu | AI thực sự trả | FE đang đọc | Hậu quả |
| --- | --- | --- | --- |
| Ứng viên | `candidates` | Flutter: `topCandidates` hoặc `top_candidates` | Bỏ mất danh sách cần xác nhận. |
| Điểm ứng viên | `similarity` | Flutter: `score` | Điểm ứng viên không đọc đúng. |
| Số ảnh reference | `reference_images` | React health: `reference_count` | UI báo 0 dù đã index ảnh. |
| Trạng thái model | Health có `model`, không có `model_ready` | React mặc định `modelReady=false` | UI có thể báo chưa sẵn sàng dù service đang hoạt động. |

Nguồn: `AI Vision/app/main.py:49–57, 119–130`; `FrontEnd/smgs_mobile/lib/services/vision_api_service.dart:12–48`; `FrontEnd/smgs_web/src/services/visionApi.js:14–30`.

Cần chuẩn hóa DTO hoặc adapter, thêm contract test với response thực tế của service, đặc biệt trường hợp `matched=false` nhưng có candidates.

### 5. Hợp đồng và preview 3D chưa đúng

- FE cho gửi từ **3 ảnh** ở `scan3dApi.js:45` và `ArtifactDetailModal.jsx:229,773`; API yêu cầu **10 đến SCAN_MAX_IMAGES**, mặc định tối đa 80 ảnh (`3D Scan/app/main.py:59`, `settings.py`). Bộ 3–9 ảnh sẽ bị từ chối.
- API trả lỗi job ở `error`; UI đọc `errorMessage`, làm mất lý do thất bại cụ thể.
- Health scan chỉ trả status/service. React đọc `colmap_available`, luôn nhận mặc định false; health hiện tại chưa kiểm tra worker/COLMAP.
- `modelUrl` là đường dẫn tương đối `/api/v1/scans/{id}/model`, bắt buộc service key. UI đưa nguyên đường dẫn vào model-viewer, không resolve về scan service/gateway và không có cơ chế tải GLB qua gateway. GET hiện tại có thể đi nhầm API của portal hoặc thiếu xác thực.

Cần đồng bộ giới hạn ảnh/dung lượng, ánh xạ lỗi đúng, tách liveness khỏi readiness worker và cung cấp luồng preview có xác thực. Khi đưa model cho Visitor, dùng media endpoint/object storage do BE quản lý.

### 6. Duyệt scan chưa đồng nghĩa xuất bản mô hình cho Visitor

`approveScanJobApi` chỉ gọi `/api/v1/scans/{id}/approve`. Service cập nhật scan job trong schema `ai_3d_scan`; chưa có thao tác tạo/cập nhật artifact asset ở BE. UI hiện báo mô hình sẵn sàng xuất bản nhưng chưa hoàn tất phần đó. Service cũng không biết JWT/role Curator của hệ thống, chỉ kiểm tra service key.

Cần luồng BE: Museum Staff tạo job theo hiện vật → Curator/Admin thẩm định theo quyền → nhập GLB vào media/object storage và lưu asset liên kết hiện vật → Visitor đọc model qua API hiện vật. BE đã có API upload/list/settings mô hình; phần còn thiếu là cầu nối từ scan output tới luồng media và thẩm định tương ứng, không phải làm lại viewer từ đầu.

## P2 — Hoàn thiện sau khi sửa các luồng bị đứt

### 7. Sinh thuyết minh/quiz và chat chưa là AI thật

`AIContentStudio.jsx:54–150` dùng template và setTimeout; `MockAiGuideService` trả lời theo các câu gợi ý. AI-System hiện không có API sinh text/quiz/chat.

Cần chốt phạm vi: nếu chỉ demo, gắn nhãn nội dung mẫu rõ ràng; nếu cần AI thật, bổ sung service sinh nội dung từ tư liệu hiện vật, lưu nguồn và bản nháp, đưa qua Curator duyệt. Tránh áp cùng mô tả niên đại/hoa văn/chất liệu cho mọi hiện vật như template hiện tại. Duy trì giao tiếp tiếng Việt theo yêu cầu sản phẩm.

### 8. Quản lý reference chưa bền vững ở cấp sản phẩm

Vision lưu tên ảnh và embeddings; React quản lý ảnh mới bằng state, File và object URL trong phiên. Chưa thấy luồng BE lưu metadata/storage ảnh reference và endpoint đọc lại danh sách để tiếp tục quản lý sau khi reload. Upload hoặc xóa bằng service key cũng chưa kiểm tra bảo tàng của người thao tác.

Cần BE sở hữu media/metadata, kiểm tra scope theo artifact và theo dõi trạng thái indexing. Vision sở hữu embeddings và model version. Bổ sung đồng bộ lại khi ảnh/model thay đổi, xử lý lỗi từng ảnh mà không báo tất cả đã thành công.

### 9. Test AI và bằng chứng chất lượng còn mỏng

CI hiện chạy một test PostgreSQL về cách ly embedding theo model version; TTS/3D chỉ kiểm tra cú pháp. Chưa thấy test hợp đồng FE–AI, playback, upload ảnh, xác nhận ứng viên hoặc luồng scan/review/publish.

Nhật ký 27/10 ghi nhận ba ảnh holdout của ba hiện vật cho kết quả đúng trong lần thử trước. Đây không phải benchmark đa bảo tàng hoặc kết quả kiểm thử lại ngày 04/11.

Cần ưu tiên test các hợp đồng đang lệch, rồi đánh giá ảnh điện thoại thực tế, ảnh hiện vật giống nhau/ngoài danh mục, điều kiện tủ kính và thời gian đáp ứng. Chưa có bằng chứng từ lần rà soát này để kết luận phải thay model hoặc train thêm ngay.

### 10. Tài liệu và tệp sinh tự động cần dọn

- README/BE_FE_REVIEW của AI còn mô tả FE dùng `mockData.js` và BE chưa có nội dung/media; các mô tả này đã cũ so với source hiện tại. `mockData.js` đã được bỏ khỏi FE runtime.
- Tài liệu mapping narration_versions là hướng thiết kế trước đây; khi cập nhật cần đối chiếu entities/DTO đang chạy thay vì coi đó là API hiện hành.
- Repository AI đang track `.pyc`/`__pycache__`, trong khi `.gitignore` chỉ loại `.env`. Các tệp này đổi khi chạy test và dễ gây diff/conflict không cần thiết. Nên bổ sung ignore và bỏ tracking cache trong một thay đổi riêng.

## Kiểm tra đã thực hiện

- Fetch AI-System thành công; local/remote cùng `be270a6`, working tree ban đầu sạch.
- Kiểm tra cú pháp bằng AST: **16 tệp Python, 0 lỗi**; không import/start model.
- Chạy unittest Vision với mật khẩu DB chủ động để trống nhằm không ghi vào DB thật: **1 test được phát hiện, 1 skip**. Đây không phải bằng chứng inference/DB test đã pass.
- GET read-only `/health` tại localhost:8000, 8001, 8002: cả ba timeout sau 2 giây. Chưa xác nhận được service sẵn sàng; kết quả này không chứng minh hệ thống AI ở môi trường khác đang tắt.
- Không tìm thấy lệnh COLMAP trong PATH PowerShell hiện tại; chưa kiểm tra bên trong container/worker khác.
- Các tệp cache bị Python tạo lại trong lần test đã được hoàn nguyên về nội dung trước đó.

## Thứ tự đề xuất

1. Chốt gateway, JWT/scope và địa chỉ triển khai HTTPS giữa BE và AI.
2. Sửa DTO Vision/Scan và kiểm tra trạng thái service bằng contract test.
3. Hoàn thiện ảnh đầu vào thật và playback audio thật của Flutter, kiểm tra bằng web.
4. Nối review/publish scan output vào media hiện vật và quản lý reference bền vững.
5. Tách rõ phần demo sinh nội dung; triển khai sinh text/chat thật khi đã chốt yêu cầu và nguồn dữ liệu.

Các mục trên là việc cần cập nhật được phát hiện, chưa phải các thay đổi source đã triển khai. Lần rà soát này chỉ thêm tài liệu, không commit/push.
