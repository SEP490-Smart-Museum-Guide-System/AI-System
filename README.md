# AI System — Smart Museum Guide System

Repo chứa các microservice AI cho Smart Museum Guide System. TTS, nhận diện ảnh hiện vật và 3D Scan có các PoC độc lập; xem README từng service để biết giới hạn và cách chạy.

**Cập nhật 04/11/2026:** đã sửa lỗi độ tin cậy Vision khi `top_k=1`, giới hạn ảnh/cache, readiness, cleanup/claim job 3D và adapter FE. Có 26 test AI pass, 2 test PostgreSQL chủ động skip khi chạy local. Xem [thay đổi code và các phần còn thiếu](AI_CODE_UPGRADE_2026_11_04.md). Đây chưa phải xác nhận pipeline AI production end-to-end.

AI Vision và 3D Scan dùng **cùng PostgreSQL database của BE**, mỗi service có schema riêng để lưu embedding dẫn xuất hoặc scan-job metadata; không cần deploy thêm database. Cấu hình cùng `AI_SYSTEM_DB_HOST`, `AI_SYSTEM_DB_PORT`, `AI_SYSTEM_DB_NAME`, `AI_SYSTEM_DB_USER`, `AI_SYSTEM_DB_PASSWORD` như BE. TTS không cần DB. Media 3D hiện còn ở local disk và cần shared/object storage nếu chạy nhiều replica.

## Cấu trúc thư mục

```text
AI-System/
├── AI Vision/                 # Microservice nhận diện hiện vật từ ảnh
│   ├── app/                   # API, CLIP ONNX embeddings và kho ảnh tham chiếu
│   ├── Dockerfile
│   ├── compose.yaml
│   ├── requirements.txt
│   └── README.md
├── 3D Scan/                   # Nhận ảnh, điều phối COLMAP và xuất GLB
│   ├── app/                   # API job và worker tái tạo
│   ├── requirements.txt
│   └── README.md
├── TTS AI/                    # Microservice chuyển văn bản thành giọng nói
│   ├── app/                   # API, tổng hợp Piper/sherpa-onnx và cache audio
│   ├── Dockerfile
│   ├── compose.yaml
│   ├── requirements.txt
│   └── README.md
├── state/                     # Thư mục dành cho dữ liệu trạng thái cục bộ
├── BE_FE_REVIEW.md            # Ghi chú rà soát backend và frontend
├── IMPLEMENTATION_LOG.md      # Nhật ký triển khai
└── README.md                  # Tổng quan kiến trúc và luồng AI
```

## Mục tiêu và nguyên tắc

| Microservice | Trách nhiệm | Trạng thái |
| --- | --- | --- |
| TTS | Nhận văn bản đã duyệt, tổng hợp giọng tiếng Việt bằng Piper/sherpa-onnx và trả audio | MVP trong [`TTS AI/README.md`](TTS%20AI/README.md) |
| Nhận diện hiện vật | So khớp CLIP ONNX embeddings với ảnh tham chiếu, trả `artifactId`, similarity và ứng viên | MVP ONNX trong [`AI Vision/README.md`](AI%20Vision/README.md) |
| Dựng 3D | Nhận bộ ảnh, chạy COLMAP, xuất GLB và chờ curator review | PoC; chưa nối Backend/web/Flutter end-to-end |

**AI không tự viết nội dung thuyết minh cho khách tham quan.** Nội dung, tên gọi và thông tin lịch sử do người phụ trách biên soạn, kiểm duyệt và xuất bản. TTS microservice chỉ biến văn bản được ứng dụng gửi vào thành audio; service không nhận diện hiện vật và không truy cập database nội dung.

Các service dùng chung `artifactId`. Một hiện vật có thể có ảnh, mã QR, nội dung thuyết minh, audio và mô hình 3D; thiếu mô hình 3D không làm gián đoạn chức năng thuyết minh.

## Luồng 1: Dựng mô hình 3D

1. Người quản lý chụp nhiều ảnh quanh hiện vật bằng iPhone, ở các góc và độ cao khác nhau; trang capture Safari và API Backend chưa nối.
2. PoC `3D Scan` nhận bộ ảnh theo job, chạy COLMAP trên máy cài COLMAP CLI và tạo mesh/GLB.
3. Job chuyển sang `REVIEW_REQUIRED`; curator kiểm tra hình dạng, hoa văn, màu sắc. Chỉ Backend sau khi được nối mới có thể xuất bản `modelUrl`.
4. Flutter viewer hiện nhận `modelUrl` theo artifact nếu có, còn không sẽ dùng GLB mẫu cục bộ.

Mô hình sinh từ ảnh đơn hoặc những góc chưa được chụp có thể chứa chi tiết suy đoán. Với hiện vật cần độ trung thực cao, ưu tiên ảnh nhiều góc và ghi rõ tình trạng kiểm chứng của mô hình.

## Luồng nhận diện hiện vật

```text
Camera iPhone → nhận diện → artifactId → bản ghi đã xuất bản
                                      → nội dung đã kiểm duyệt → audio/TTS → khách nghe
```

- Quét QR trên nhãn hiện vật để lấy `artifactId`; ứng dụng lấy nội dung đã xuất bản từ Content/Catalog Service.
- AI Vision so khớp ảnh camera với embedding tạo từ ảnh tham chiếu, dự đoán `artifactId` cùng similarity và các ứng viên. Chụp/index ảnh mẫu ở điều kiện trưng bày thật: nhiều góc, ánh sáng và phản chiếu tủ kính.
- Khi điểm tin cậy thấp hoặc có nhiều hiện vật giống nhau, hiển thị các kết quả để khách chọn hoặc yêu cầu quét QR. Không tự phát thuyết minh khi chưa xác định chắc hiện vật.
- Chỉ Content/Catalog Service trả nội dung có trạng thái **đã duyệt/đã xuất bản**. Nếu chưa có bản đọc, hiển thị thông báo tương ứng.

## Luồng TTS đã triển khai

```text
Flutter → Content/Catalog Service: lấy văn bản published theo artifactId
Flutter → TTS Service: POST văn bản đã duyệt
TTS Service → Flutter: audio/wav (Piper tổng hợp hoặc cache trả lại)
```

BE hiện có `GET /api/artifacts/{id}/contents/published?languageCode=vi`, trả bản `ArtifactContent` đã xuất bản, gồm `narrationText`/`audioUrl`. Flutter đã lấy nội dung này và phát audio thật. TTS không truy cập DB hoặc tự xác nhận trạng thái xuất bản: gateway BE vẫn phải kiểm soát quyền/nội dung. Mapping `narration_versions` trong tài liệu thiết kế cũ không phải hợp đồng API hiện hành.

## Phân chia trách nhiệm

| Thành phần | Trách nhiệm |
| --- | --- |
| Ứng dụng Flutter | Quét QR, lấy nội dung đã xuất bản, gửi văn bản đến TTS Service và phát audio |
| TTS Service | Chạy Piper/sherpa-onnx, cache kết quả audio, trả WAV |
| AI Vision Service | So khớp ảnh và trả `artifactId`/ứng viên; lưu embedding dẫn xuất trong schema `ai_vision` của PostgreSQL dùng chung với BE |
| 3D Scan Service | Nhận bộ ảnh, chạy COLMAP ở nền, tạo GLB và chờ duyệt; lưu scan-job metadata trong schema `ai_3d_scan` của PostgreSQL dùng chung với BE; ảnh/GLB vẫn ở storage local trong PoC |
| Hệ thống quản lý hiện vật | Lưu hồ sơ, nội dung đã duyệt, `qrCode`, `audioUrl`, `modelUrl` và trạng thái xuất bản |
| Người phụ trách bảo tàng | Duyệt bản thuyết minh, audio và mô hình 3D |

Frontend hiện lấy dữ liệu nghiệp vụ từ BE; dữ liệu demo AI/3D vẫn được giữ riêng theo phạm vi sản phẩm. Playback TTS thật đã có. Hỏi đáp và sinh nội dung/quiz vẫn chưa có model service thật trong AI-System; không nên đánh đồng giao diện demo với tích hợp AI đã hoàn tất.

## Lộ trình tiếp theo

1. Hoàn thiện gateway AI phía BE: JWT, role/phạm vi bảo tàng, quyền nội dung published và địa chỉ HTTPS. Không đưa service key vào browser/Flutter.
2. Chọn voice Piper sau khi nghe thử với tên riêng, niên đại và thuật ngữ trong bộ sưu tập thật.
3. Nối Backend làm job gateway có xác thực, trạng thái bền vững, lưu trữ model và bước curator duyệt; sau đó làm trang scan Safari.
4. Dùng iPhone chụp, dựng và duyệt một mô hình 3D; tối ưu GLB và gắn vào hồ sơ hiện vật.
5. Index ảnh tham chiếu tại bảo tàng, đánh giá độ chính xác AI Vision trên ảnh chưa dùng làm tham chiếu.

Audio TTS được cache theo văn bản tiếng Việt đã chuẩn hóa Unicode, voice/model và tốc độ chính xác. Cache mặc định giới hạn 512 MiB/1.000 tệp; thay model sẽ không dùng nhầm audio cũ. `/live` dành cho liveness; `/ready` và `/health` phản ánh trạng thái sẵn sàng thực tế và có thể trả 503.

## Kiểm thử code

Python 3.12; cài dependency từng service cùng `requirements-dev.txt`, sau đó chạy:

```powershell
cd D:\SEP409\AI-System
.\tools\test-ai.ps1
```

Script ưu tiên `.venv\Scripts\python.exe`, có thể truyền `-Python` để chọn interpreter khác. Mặc định không chạy test DB thật, không tải model hoặc chạy COLMAP. CI kiểm thử TTS/Vision/3D; riêng Vision có PostgreSQL test container và bật `AI_RUN_DB_TESTS=1`. Chỉ dùng `-IncludeDatabaseTests` khi đã cấu hình DB kiểm thử riêng.

## Việc cần chốt trước khi nối production

- Địa chỉ Content/Catalog API và định dạng response khi trả nội dung đã duyệt.
- Cách xác thực service-to-service giữa Flutter/API Gateway và TTS Service trong môi trường triển khai.
- Bộ ảnh hiện vật có sẵn bao nhiêu và bảo tàng có cho phép chụp nhiều góc không?
- Ngưỡng chấp nhận cho nhận diện: tỷ lệ nhận đúng, tỷ lệ phải xác nhận thủ công và thời gian phản hồi trên thiết bị thử nghiệm.
