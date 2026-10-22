# AI Vision — Artifact Recognition Service

Microservice nhận ảnh hiện vật và tìm artifact gần giống nhất trong bộ ảnh tham chiếu đã index. Service dùng image encoder CLIP ViT-B/32 đã đóng gói ở định dạng ONNX, chạy bằng ONNX Runtime CPU; không huấn luyện model riêng. Model mặc định là [`infinilabs/pizza-clip-base-v1`](https://huggingface.co/infinilabs/pizza-clip-base-v1), cung cấp embedding ảnh 512 chiều dành cho image retrieval. Ảnh tham chiếu gắn với `artifactId`, theo ý tưởng bảng `artifact_reference_images` trong DBML.

Service không kết nối trực tiếp database BE. BE hoặc công cụ quản trị nội bộ cần đẩy ảnh tham chiếu vào service. Với mỗi ảnh khách gửi, service trả ứng viên và độ tương đồng; nếu điểm/margin chưa đủ thì `matched=false` và cần khách xác nhận hoặc quét QR.

## Chạy local bằng Docker Compose

Cần Docker Desktop/Compose và internet ở lần chạy đầu để cài ONNX Runtime, tải model ONNX cùng external weights. File model được giữ trong volume `vision-models`; các lần chạy sau dùng cache. ONNX Runtime Python CPU là lựa chọn mặc định theo hướng dẫn cài đặt chính thức của ONNX Runtime.

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
  "model": "infinilabs/pizza-clip-base-v1@<resolved-commit>/clip-vit-base-patch32-vision.onnx"
}
```

Similarity là cosine similarity giữa vector ảnh query và ảnh tham chiếu gần nhất của mỗi artifact; đây **không phải xác suất đã hiệu chuẩn**. Ngưỡng mặc định (`MIN_SIMILARITY=0.72`, `MIN_MARGIN=0.04`) chỉ để khởi đầu, cần hiệu chỉnh trên ảnh chụp thật của bảo tàng. Ứng dụng nên luôn hiển thị xác nhận khi `requiresConfirmation=true`; không tự phát narration dựa vào match yếu.

### Model và index ảnh

- Default model source: `infinilabs/pizza-clip-base-v1`, file `clip-vit-base-patch32-vision.onnx`. The response/store model id includes the resolved immutable Hub commit hash, even when configured revision is `main`.
- Model nhận ảnh RGB 224×224, tiền xử lý CLIP và trả vector L2-normalized 512 chiều.
- Có thể đổi `CLIP_ONNX_REPO_ID`, `CLIP_ONNX_REVISION` và `CLIP_ONNX_FILENAME`; nên pin revision bất biến trước khi deploy production.
- Đổi model/revision nghĩa là embedding không còn cùng không gian vector. SQLite giữ cột `model_id`; recognition chỉ so với ảnh tham chiếu được index bằng đúng model hiện hành. Embedding OpenCLIP cũ được giữ lại nhưng không được dùng; cần index lại ảnh tham chiếu.
- Model pretrained là model ảnh tổng quát, không được fine-tune trên bộ hiện vật SMGS. Chưa có benchmark độ chính xác trên ảnh bảo tàng; chưa thể kết luận threshold phù hợp.

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
- ONNX Runtime CPU bỏ PyTorch khỏi image AI Vision nhưng model vision vẫn cần tải từ Hugging Face khi khởi động lần đầu. Chưa đo dung lượng image encoder thực tế, RAM, tốc độ hoặc độ chính xác trong repo này.
- CLIP ONNX đang được cung cấp bởi model repository bên thứ ba; cần pin revision, xác minh artifact/hash sau khi tải và rà điều khoản model trước khi production.
- Model weights/cache và embeddings được giữ trong Docker volumes. Backup volume nếu cần bảo toàn index.
- `X-Service-Key` dùng cho gọi service-to-service; không nhúng secret này vào Flutter app. Đặt Vision Service trong private network và để BE/API Gateway proxy request.
