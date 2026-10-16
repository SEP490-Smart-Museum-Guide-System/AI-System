# SMGS TTS Service

Microservice tạo audio tiếng Việt từ **văn bản thuyết minh đã được nhân viên bảo tàng duyệt**. Service dùng Piper qua `sherpa-onnx`, tổng hợp trên CPU và trả WAV cho ứng dụng Flutter. Service không nhận diện hiện vật và không tự viết nội dung.

## Luồng tích hợp

```text
Flutter quét QR → Content/Catalog Service trả bản thuyết minh đã xuất bản
                 → Flutter gọi TTS Service với văn bản đó
                 → Piper trả audio/wav → Flutter phát audio
```

Content/Catalog Service vẫn là nguồn dữ liệu chuẩn và kiểm soát trạng thái duyệt. TTS Service chỉ nhận văn bản đã xuất bản; nó không truy cập database của các service khác. Kết quả WAV được cache theo nội dung, voice và tốc độ đọc để tái sử dụng.

## Chạy bằng Docker Compose

Cần Docker Desktop với Docker Compose. Lần khởi động đầu tải voice `vi_VN-vais1000-medium` và dữ liệu eSpeak vào volume; các lần sau tái sử dụng model đã tải.

```powershell
cd D:\SEP409\AI-System\tts-service
docker compose up --build
```

Service mặc định lắng nghe ở `http://localhost:8000`. Tài liệu API tại `http://localhost:8000/docs`; kiểm tra trạng thái tại `http://localhost:8000/health`.

## API

### `POST /api/v1/speech`

Request JSON:

```json
{
  "text": "Bản thuyết minh đã được bảo tàng kiểm duyệt...",
  "language": "vi-VN",
  "speed": 1.0
}
```

Response: `audio/wav` (mono PCM 16-bit). Giới hạn mặc định 12.000 ký tự; tốc độ đọc từ `0.75` đến `1.25`. Header `X-TTS-Cache` cho biết kết quả là `HIT` hay vừa tổng hợp `MISS`.

Ví dụ gọi API và lưu file:

```powershell
$body = @{
  text = 'Trống đồng Ngọc Lũ là hiện vật tiêu biểu của văn hóa Đông Sơn.'
  language = 'vi-VN'
  speed = 1.0
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri http://localhost:8000/api/v1/speech `
  -Method Post `
  -ContentType 'application/json' `
  -Body $body `
  -OutFile .\sample.wav
```

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| Voice model | `vi_VN-vais1000-medium` | Voice Piper tiếng Việt cố định trong MVP; model được tải một lần vào volume |
| `TTS_MODEL_DIR` | `/models` | Thư mục model; được giữ qua volume Compose |
| `TTS_CACHE_DIR` | `/data/audio-cache` | Thư mục WAV đã tổng hợp để cache |
| `TTS_NUM_THREADS` | `2` | Số CPU threads chạy model |
| `TTS_MAX_TEXT_CHARS` | `12000` | Số ký tự tối đa mỗi request |

## Nối từ Flutter

1. Flutter đọc `artifactId` từ kết quả quét QR.
2. Flutter lấy văn bản thuyết minh trạng thái `published` từ Content/Catalog API.
3. Flutter gửi `{text, language, speed}` đến `POST /api/v1/speech`.
4. Phát response bytes bằng audio player trên Flutter.

Ở production, đặt service sau API gateway hoặc private network, bật HTTPS và xác thực service-to-service. Không mở endpoint công khai không giới hạn vì việc tạo audio dùng CPU. Bản MVP hiện không thêm nguồn phát sinh nội dung hay công cụ nhận diện.

## Ghi chú model và giấy phép

`sherpa-onnx` phát hành theo Apache-2.0. Voice Piper là model riêng; phải kiểm tra giấy phép của đúng voice và tuân theo điều kiện sử dụng/phân phối của nó trước khi triển khai ngoài đồ án. Dùng mẫu thuyết minh bảo tàng thật để đánh giá phát âm tên riêng, niên đại và thuật ngữ trước khi chọn voice cuối.
