# Nâng cấp code AI-System — 04/11/2026

> Cập nhật 08/11/2026: đã bổ sung [kiểm thử CLIP thật trên ảnh người dùng và ảnh nguồn ngoài](evaluations/vision-2026-11-08/README.md). Encoder và API chạy thật, chỉ kho tham chiếu dùng RAM cô lập; có một ca nhận nhầm ảnh ngoài kho. Các mô tả bên dưới ghi lại phạm vi công việc ngày 04/11; kiểm thử mới chưa xác nhận PostgreSQL/gateway/deploy, tổng hợp TTS hoặc dựng COLMAP thật.

## Kết quả

Đã rà soát và sửa source TTS, Vision, 3D Scan cùng các adapter FE đang đọc response AI. Không thêm dữ liệu mẫu vào nghiệp vụ, không tự tải model/training, không gọi nhà cung cấp LLM, không ghi PostgreSQL/R2 thật, không commit/push/deploy.

Repo hiện có TTS tiếng Việt, nhận diện ảnh CLIP ONNX và PoC COLMAP. Chưa có service hỏi đáp/RAG hoặc sinh văn bản/quiz bằng model thật. Việc sửa độ tin cậy và vận hành dưới đây không chứng minh model nhận diện chính xác hơn trên ảnh thực tế, cũng không làm toàn bộ luồng sản phẩm thành end-to-end.

## Những lỗi đã sửa

| Phần | Trước | Sau |
| --- | --- | --- |
| Vision — `top_k=1` | Cắt bỏ ứng viên thứ hai trước khi tính margin; ảnh gần giống có thể được tự nhận là chắc chắn. | Tính margin trên toàn bộ artifact đã xếp hạng; `top_k` chỉ giới hạn response. Test xác nhận kết quả mơ hồ vẫn cần khách chọn. |
| Vision — dữ liệu vector | Byte hỏng, sai kích thước, NaN/zero có thể làm lỗi request hoặc trả điểm không hợp lệ. | Bỏ qua vector lỗi; nếu không còn reference phù hợp thì trả 503, không chọn bừa hiện vật. |
| Vision — tải ảnh và inference | Gọi encoder/DB đồng bộ trong endpoint async làm nghẽn event loop. | Route đồng bộ được FastAPI chạy trong thread pool; `/live` là async nhẹ. Test xác nhận liveness phản hồi khi encoder bị giữ. |
| Vision — quota | Đếm rồi insert ngoài cơ chế khóa có thể bị upload đồng thời vượt giới hạn. | Transaction PostgreSQL + advisory lock theo schema/model/artifact, kiểm tra quota trước insert. Có test concurrent dành cho DB kiểm thử. |
| Vision — xác thực | So sánh chuỗi thường, không fail closed nếu cấu hình key rỗng ngoài startup. | Key bắt buộc, so sánh hằng thời gian và từ chối cấu hình/header rỗng. |
| Xác thực trước upload | Dependency kiểm tra key sau khi framework đã parse body. | Middleware từ chối key sai trước khi đọc/parse body ở cả ba service; có test body lỗi vẫn trả 401 trước validation. TTS áp dụng khi đã cấu hình key. |
| Ảnh | Chỉ giới hạn byte nén; ảnh kích thước lớn có thể chiếm RAM khi giải mã. | Kiểm tra format/ảnh tĩnh/số pixel trước decode. Mặc định 20 triệu pixel. 3D còn đối chiếu đuôi JPG/PNG và decode thật để chặn ảnh hỏng. |
| TTS — cache | Không có giới hạn dung lượng; tên `.part` dùng chung giữa writer; WAV hỏng vẫn được trả. | Giới hạn 512 MiB/1.000 WAV, trim các entry cũ, temporary file riêng và atomic replace; WAV hỏng được tạo lại. |
| TTS — định danh cache | Làm tròn speed 3 chữ số, không có fingerprint model. | Speed chính xác, Unicode tiếng Việt NFC, hash nội dung model/tokens và phiên bản engine; đổi model không dùng nhầm audio cũ. |
| TTS — tải cao | Mọi request chờ khóa tổng hợp, kể cả đã có cache. | Cache hit không phải chờ slot; cache miss quá thời gian chờ mặc định 2 giây trả 503 + Retry-After. Lỗi tổng hợp không làm kẹt khóa. |
| TTS — model assets | Extract archive kiểm tra đường dẫn nhưng chưa chặn link/device; tải không timeout/bound size. | Chỉ nhận file/dir thường, dùng extraction filter, giới hạn tổng dung lượng/số entry; tải có timeout, giới hạn byte, temporary riêng và cleanup. |
| 3D — trạng thái sẵn sàng | `/health` luôn báo ok, chưa biết COLMAP/worker/DB. | `/ready` và `/health` trả `colmap_available`, `worker_ready`, `database_ready`; thiếu điều kiện trả 503. Từ chối job mới khi không có COLMAP. |
| 3D — job ID | ID sai UUID có thể phát sinh exception trong store. | Validation UUID trả 422 trước khi gọi DB. |
| 3D — upload | Persist job lỗi sau upload để lại thư mục ảnh. | Persist nằm trong vùng cleanup; lỗi DB dọn thư mục job vừa tạo, trả lỗi 503 an toàn. Metadata giới hạn 16 KiB. |
| 3D — tranh chấp worker | Nhiều worker có thể xử lý cùng job; startup reset mọi PROCESSING. | Claim atomically `QUEUED → PROCESSING`; không nhận trùng hoặc reset job của worker khác khi startup. |
| 3D — lỗi và tải GLB | RuntimeError có thể chứa đường dẫn nội bộ; kiểm tra đường dẫn đầu ra còn thiếu ràng buộc gốc. | Chỉ trả thông báo kiểm soát được; kiểm tra UUID, scan root, output directory và đuôi GLB. |

Ảnh tham chiếu vẫn phải được BE xác minh thuộc bảo tàng/hiện vật đúng quyền. Service key là xác thực nội bộ, không thay thế quyền của Visitor/Museum Staff/Curator.

## Hợp đồng API và FE

Giữ tên endpoint/các trường response hiện hành; bổ sung readiness và xử lý đúng các trường FE đọc lệch:

- Vision trả `candidates` với `{artifactId, similarity}`. Flutter giờ đọc trường này, giữ các alias cũ để tương thích; trường hợp `matched=false` không làm mất danh sách cần xác nhận.
- Vision health trả `reference_images` và `model_ready`; web hiển thị đúng số ảnh.
- Scan trả `error`; web ánh xạ thành `errorMessage` cho UI hiện có.
- Theo cập nhật yêu cầu, web và API nhận từ **5 ảnh JPG/PNG của cùng một hiện vật**; 80 chỉ là giới hạn trên. Không còn yêu cầu chụp 10–15 ảnh trở lên. Số ảnh ít có thể khiến COLMAP thất bại hoặc thiếu chi tiết; giao diện ghi rõ giới hạn này.
- Thông báo sau approve nói rõ phải lưu mô hình vào hồ sơ hiện vật để xuất bản; không báo scan đã tự hoàn tất bước lưu BE/R2.
- Lỗi polling scan được hiển thị thay vì dừng im lặng.
- Bản Flutter `/visitor/` đã build lại để chứa adapter mới.

BE hiện có API nội dung published `GET /api/artifacts/{id}/contents/published?languageCode=vi` và DTO `narrationText`/`audioUrl`. TTS không tự tra schema DBML hoặc kiểm tra quyền xuất bản. Tài liệu mapping `narration_versions` cũ được ghi chú là thiết kế tham khảo.

## Cấu hình mới

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `TTS_CACHE_MAX_BYTES` | 536870912 | Ngân sách WAV cache 512 MiB. |
| `TTS_CACHE_MAX_FILES` | 1000 | Số WAV tối đa. |
| `TTS_QUEUE_TIMEOUT_SECONDS` | 2 | Thời gian chờ slot tổng hợp; tối đa cấu hình 30 giây. |
| `TTS_SERVICE_API_KEY` | Rỗng cho tương thích local | Nếu đặt thì POST speech bắt buộc X-Service-Key. Khi triển khai, key thuộc gateway server. |
| `MAX_IMAGE_PIXELS` | 20000000 | Giới hạn ảnh Vision trước decode. |
| `SCAN_MAX_IMAGE_PIXELS` | 20000000 | Giới hạn ảnh 3D trước decode. |
| `SCAN_MAX_METADATA_BYTES` | 16384 | Giới hạn capture_metadata. |
| `AI_RUN_DB_TESTS` | Không bật khi chạy local | Bật `1` chỉ khi chạy test trên DB kiểm thử. |

Compose Vision không còn dùng service key mặc định công khai. Cần cấu hình `AI_SERVICE_API_KEY`. Các biến mẫu chỉ là placeholder, không chứa secret thật. Không đưa key vào VITE_* hoặc Flutter; FE hiện vẫn có cơ chế key PoC cũ, cần thay bằng gateway BE trước production.

Ba service cùng pin FastAPI 0.119.1/Uvicorn 0.38.0; Vision và 3D dùng Pillow 12.0.0/NumPy 2.2.6 để tránh lệch môi trường kiểm thử.

## CI, file sinh tự động và lệnh test

- Bổ sung test API/cache/validation/worker cho cả ba service; CI TTS/3D chạy test thay vì chỉ compile syntax.
- CI Vision dùng PostgreSQL container kiểm thử, bật rõ `AI_RUN_DB_TESTS=1`; có test cách ly model version và quota upload đồng thời.
- Bỏ Git tracking 12 file `.pyc`, ignore `__pycache__`, `.venv`, log và output test. File cache trên máy vẫn giữ, không xóa source.
- Thêm `tools/test-ai.ps1`, mặc định ép tắt live DB tests và khôi phục flag môi trường sau khi chạy.

Tạo môi trường test chung với Python 3.12:

```powershell
cd D:\SEP409\AI-System
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r 'TTS AI/requirements.txt' -r 'AI Vision/requirements.txt' -r '3D Scan/requirements.txt' -r requirements-dev.txt
.\tools\test-ai.ps1
```

Khi đã cấu hình DB kiểm thử riêng, có thể chạy `./tools/test-ai.ps1 -IncludeDatabaseTests`. Script không tự tạo database; không dùng cấu hình production cho việc kiểm thử. Service startup có tạo schema/table riêng như trước, nhưng không được gọi với DB thật trong lần sửa này.

## Bằng chứng kiểm thử local

| Kiểm tra | Kết quả |
| --- | --- |
| TTS API, WAV thật dạng PCM, cache hỏng/budget/speed/model, khóa, archive và download failure | 9 pass. Engine/model được thay bằng fixture. |
| Vision API, ambiguity top_k, reference cùng artifact, corrupt vector, key/limits/DB failure, event loop và ảnh decode | 8 pass. Inference/store fixture. |
| Vision PostgreSQL model isolation + concurrent quota | 2 skip local có chủ đích; workflow CI đã cấu hình chạy với DB kiểm thử, chưa có kết quả CI remote trong lần này. |
| 3D API ảnh thật/DB fixture, UUID/path, COLMAP/readiness, cleanup/claim/error | 9 pass. Không chạy COLMAP thật. |
| Parse source/test Python + YAML workflow | 22 tệp Python hợp lệ; có job test Vision/PostgreSQL và matrix TTS/3D. |
| Node tests FE | Sau cập nhật bộ 5 ảnh: 26 pass, 1 live test skip; 4 contract test AI. |
| Flutter analyze + toàn bộ test | Sạch; 73 pass, 1 live test skip. |
| Playwright Edge hồi quy web | 14/14 pass; nghiệp vụ dùng API fixture. |
| Build | Flutter release và React production build; bundle /visitor/ được cập nhật. |

Chưa xác nhận giọng Piper thật bằng nghe thử, CLIP inference với trọng số thật, chất lượng mô hình từ ảnh, camera thiết bị thật hoặc end-to-end với PostgreSQL/R2/BE JWT thật. Similarity là độ tương đồng, không phải xác suất nhận đúng.

## Các phần còn cần triển khai để toàn diện ở cấp sản phẩm

1. **Gateway BE cho TTS/Vision/Scan:** JWT, đúng role/phạm vi bảo tàng, nội dung published và quyền free/premium; service key giữ tại server, HTTPS/proxy cho production. TTS nhận raw text nên không thể tự chứng minh văn bản đã được duyệt.
2. **Nguồn ảnh thực và đồng bộ reference:** hoàn thiện luồng ảnh camera/chọn file của Visitor, BE sở hữu media/reference metadata, list/re-index/delete theo model và artifact active. Chưa thêm filter bảo tàng vào Vision; BE phải bảo đảm phạm vi trước khi hiển thị kết quả.
3. **3D preview và publish:** tải binary GLB qua gateway có xác thực, nhập vào media/R2 và gắn artifact asset theo quyền; approve trong scan store không tự xuất bản cho Visitor. URL model tương đối/key hiện có không thể coi là URL công khai đưa thẳng vào viewer production.
4. **Worker 3D bền vững:** storage hiện còn local; cần queue ngoài process, lease/heartbeat, retry và cleanup/orphan reconciliation. Bản sửa không tự phục hồi job PROCESSING sau crash; operator phải kiểm tra các worker đã dừng trước khi requeue. Tránh bật nhiều instance khi chưa có shared storage/fencing.
5. **AI Guide/RAG và sinh narration/quiz:** chưa có API/model thật trong repo; cần chốt nguồn tư liệu đã duyệt, kiểm soát câu trả lời theo nguồn, lưu bản nháp và đưa qua Curator review/publish. Giữ nhãn demo ở FE cho tới khi có pipeline thật.
6. **Đánh giá model:** benchmark ảnh chưa index, hiện vật giống nhau/ngoài danh mục, ánh sáng/tủ kính; nghe thử tiếng Việt với tên riêng/niên đại. Không tự thay ngưỡng hoặc train model khi chưa có bộ dữ liệu đánh giá.

Tham khảo cách triển khai thread pool và giải nén: [FastAPI async/sync](https://fastapi.tiangolo.com/async/), [Python tarfile extraction filters](https://docs.python.org/3.12/library/tarfile.html#extraction-filters).
