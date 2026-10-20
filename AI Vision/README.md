# AI Vision — Artifact Recognition Service

Microservice nhận ảnh hiện vật và tìm artifact gần giống nhất trong bộ ảnh tham chiếu đã index. MVP dùng image embeddings từ OpenCLIP (`ViT-B-32`, checkpoint `laion2b_s34b_b79k`) chạy CPU; không huấn luyện model riêng. Ảnh tham chiếu được gắn với `artifactId`, tương ứng ý tưởng bảng `artifact_reference_images` trong DBML.

Service không kết nối trực tiếp database BE. BE hoặc công cụ quản trị nội bộ cần đẩy ảnh tham chiếu vào service. Với mỗi ảnh khách gửi, service trả ứng viên và độ tương đồng; nếu điểm/margin chưa đủ thì `matched=false` và cần khách xác nhận hoặc quét QR.

## Chạy local bằng Docker Compose

Cần Docker Desktop/Compose, internet ở lần chạy đầu và RAM đủ để tải model PyTorch/CLIP. Lần đầu có thể lâu do tải dependencies và pretrained weights; cache được giữ trong volume.

```powershell
cd 'D:\SEP409\AI-System\AI Vision'
$env:AI_SERVICE_API_KEY = 'replace-with-a-local-secret'
docker compose up --build
```

Service nghe tại `http://localhost:8001`, OpenAPI tại `/docs`, health tại `/health`. Health trả số lượng ảnh tham chiếu hiện được index; service chưa có dữ liệu thì detect sẽ trả `503`.

## Index ảnh tham chiếu

BE quản lý record artifact/reference image. Sau khi kiểm tra ảnh thuộc artifact active, BE gọi endpoint nội bộ sau cho từng ảnh:

```powershell
curl.exe -X POST 'http://localhost:8001/api/v1/references?artifact_id=123' `
  -H "X-Service-Key: $env:AI_SERVICE_API_KEY" `
  -F 'image=@D:\data\artifact-123-front.jpg'
```

Giới hạn mặc định 20 ảnh tham chiếu mỗi artifact. Ảnh không được lưu; service lưu vector embedding cùng artifact ID trong SQLite volume. Xóa ảnh tham chiếu của artifact sau khi artifact bị xóa/vô hiệu hóa hoặc ảnh tham chiếu cần thay thế:

```powershell
curl.exe -X DELETE 'http://localhost:8001/api/v1/references/123' `
  -H "X-Service-Key: $env:AI_SERVICE_API_KEY"
```

## Nhận diện ảnh

```powershell
curl.exe -X POST 'http://localhost:8001/api/v1/recognitions?top_k=3' `
  -H "X-Service-Key: $env:AI_SERVICE_API_KEY" `
  -F 'image=@D:\data\museum-photo.jpg'
```

Response ví dụ:

```json
{
  "matched": true,
  "artifactId": 123,
  "similarity": 0.84,
  "margin": 0.12,
  "requiresConfirmation": false,
  "candidates": [
    { "artifactId": 123, "similarity": 0.84 },
    { "artifactId": 456, "similarity": 0.72 }
  ],
  "model": "ViT-B-32:laion2b_s34b_b79k"
}
```

Similarity là cosine similarity giữa vector ảnh query và ảnh tham chiếu gần nhất của mỗi artifact; đây **không phải xác suất đã hiệu chuẩn**. Ngưỡng mặc định (`MIN_SIMILARITY=0.72`, `MIN_MARGIN=0.04`) chỉ để khởi đầu, cần hiệu chỉnh trên ảnh chụp thật của bảo tàng. Ứng dụng nên luôn hiển thị xác nhận khi `requiresConfirmation=true`; không tự phát narration dựa vào match yếu.

## Luồng nối SMGS

```text
Flutter/Visitor → BE/API Gateway → Vision Service → artifactId + candidates
                               BE → artifact + published narration theo artifactId
                               Flutter → TTS Service với script đã duyệt
```

Vision service chỉ trả ID; BE vẫn là nguồn chân lý để kiểm tra artifact active, museum scope, quyền truy cập và narration `published/current`. Service không trả nội dung, không tự viết bài thuyết minh.

Để đồng bộ DBML, BE đọc `artifact_reference_images.image_url` rồi index lại embeddings vào service. `embedding_ref` có thể lưu ID trả bởi service nếu cần xóa/cập nhật riêng từng ảnh; bản MVP hiện xóa theo toàn bộ artifact ID.

## Giới hạn MVP

- Chất lượng phụ thuộc vào ảnh tham chiếu; cần ảnh nhiều góc/ánh sáng, và ảnh test phải khác ảnh index.
- CLIP là model ảnh tổng quát; ảnh hiện vật giống nhau, tủ kính phản chiếu hoặc góc chụp khác mạnh có thể nhầm. QR vẫn là fallback tin cậy.
- OpenCLIP/PyTorch tốn disk/RAM hơn service TTS. Đây là service CPU demo, chưa benchmark tải và chưa phù hợp public internet nếu chưa có gateway/auth/rate limiting.
- Model weights/cache và embeddings được giữ trong Docker volumes. Backup volume nếu cần bảo toàn index.
- `X-Service-Key` dùng cho gọi service-to-service; không nhúng secret này vào Flutter app. Đặt Vision Service trong private network và để BE/API Gateway proxy request.
