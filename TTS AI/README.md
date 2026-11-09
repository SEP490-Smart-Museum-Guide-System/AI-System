# SMGS TTS Service

Microservice tạo audio tiếng Việt từ **văn bản thuyết minh đã được nhân viên bảo tàng duyệt**. Service dùng Piper qua `sherpa-onnx`, tổng hợp trên CPU và trả WAV cho ứng dụng Flutter. Service không nhận diện hiện vật và không tự viết nội dung.

**Kiểm thử model thật 09/11/2026:** đã tổng hợp 5 mẫu WAV bằng Piper tiếng Việt trên CPU, kiểm tra PCM/cache/speed và phát hết 3 mẫu qua module FE thật + proxy Vite + Edge headless. Chưa chấm phát âm từng từ hoặc xác nhận toàn luồng Flutter/DB/deploy. Xem [báo cáo, file nghe và lệnh chạy](../evaluations/tts-2026-11-09/README.md). Chạy Windows không cần Docker: `D:\SEP409\AI-System\tools\start-local-tts.ps1`; model/cache nằm trong `state` được gitignore.

**Nghe ngay trên UI:** Xưởng AI gọi gateway BE `POST /api/artifacts/{id}/ai/speech-preview`, có JWT/phạm vi Admin/Museum Staff, rồi phát response bằng audio player trong trang. Bài kiểm tra UI/JWT/PostgreSQL riêng/BE/Piper thật đã pass. [Hướng dẫn và tình trạng DB local](../AI_STUDIO_PLAYBACK_2026_11_09.md).

**Code hiện tại 04/11/2026:** BE trả nội dung qua `/api/artifacts/{id}/contents/published?languageCode=vi` (`narrationText`, `audioUrl`); Flutter đã phát WAV/audio thật. Phần DBML/query dưới đây là thiết kế tham khảo trước đây, không thay thế entity/DTO BE hiện hành. Xem [nhật ký nâng cấp](../AI_CODE_UPGRADE_2026_11_04.md).

## Luồng tích hợp

```text
Flutter quét QR → Content/Catalog Service trả bản thuyết minh đã xuất bản
                 → Flutter gọi TTS Service với văn bản đó
                 → Piper trả audio/wav → Flutter phát audio
```

Content/Catalog Service vẫn là nguồn dữ liệu chuẩn và kiểm soát trạng thái duyệt. Theo DBML hiện tại, nội dung để đọc nằm trong `narration_versions.script`, gắn với `narrations` theo hiện vật/ngôn ngữ/độ dài/mức chi tiết. TTS Service chỉ nhận văn bản đã xuất bản; nó không truy cập database của các service khác. Kết quả WAV được cache theo nội dung, voice và tốc độ đọc để tái sử dụng.

### Tra nội dung theo DBML

Khi QR chứa `artifacts.qr_code`, backend tra bản thuyết minh tiếng Việt hiện hành tương đương truy vấn sau (tên enum/alias cần đối chiếu với migration và entity BE thực tế):

```sql
SELECT
  a.id AS artifact_id,
  a.name AS artifact_name,
  n.id AS narration_id,
  nv.id AS narration_version_id,
  nv.version_no,
  nv.script,
  nv.audio_url
FROM artifacts AS a
JOIN narrations AS n
  ON n.artifact_id = a.id
JOIN languages AS l
  ON l.id = n.language_id
JOIN narration_versions AS nv
  ON nv.narration_id = n.id
WHERE a.qr_code = :qr_code
  AND a.is_active = TRUE
  AND l.code = :language_code
  AND n.length_level = :length_level
  AND n.detail_level = :detail_level
  AND nv.status = 'published'
  AND nv.is_current = TRUE;
```

`narrations` có unique key `(artifact_id, language_id, length_level, detail_level)`. Vì app hiện chưa có quy tắc chọn mặc định, backend nên nhận `language_code`, `length_level`, `detail_level` rõ ràng (ví dụ `vi`, `medium`, `basic`) hoặc thống nhất giá trị mặc định với team BE. Nếu không có bản phù hợp, trả not found thay vì gửi nội dung chưa duyệt sang TTS.

DBML ghi chú đây là **đề xuất thiết kế, chưa phải ERD đã chốt**. Enum PostgreSQL/EF mapping và tên bảng/cột cuối cùng phải được xác nhận với migration/backend trước khi dùng query này trực tiếp.

## Chạy bằng Docker Compose

Cần Docker Desktop với Docker Compose. Lần khởi động đầu tải voice `vi_VN-vais1000-medium` và dữ liệu eSpeak vào volume; các lần sau tái sử dụng model đã tải.

```powershell
cd 'D:\SEP409\AI-System\TTS AI'
docker compose up --build
```

Service mặc định lắng nghe ở `http://localhost:8000`. Tài liệu API tại `/docs`; `/live` kiểm tra process, `/health` và `/ready` chỉ trả 200 sau khi model đã nạp. Lỗi/bận trả 503 với `Retry-After`.

Cache mặc định 512 MiB/1.000 WAV, ghi atomic, tự loại WAV hỏng và không dùng chung audio giữa các tốc độ/model khác nhau. Cấu hình `TTS_CACHE_MAX_BYTES`, `TTS_CACHE_MAX_FILES`, `TTS_QUEUE_TIMEOUT_SECONDS` (mặc định 2 giây chờ slot tổng hợp). Cache hit vẫn có thể được trả khi slot đang bận.

Nếu đặt `TTS_SERVICE_API_KEY`, POST speech yêu cầu `X-Service-Key`. Để trống chỉ nhằm tương thích proxy local hiện có; khi triển khai cần gateway BE giữ key và kiểm tra quyền/nội dung. Không đặt key trong `VITE_*` hoặc Flutter. Voice vẫn là tiếng Việt `vi_VN-vais1000-medium`.

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

1. Flutter đọc mã QR; Content/Catalog API tìm `artifacts.qr_code` và trả hồ sơ hiện vật.
2. Flutter yêu cầu narration theo `language_code`, `length_level`, `detail_level`; backend chỉ trả `narration_versions.script` với `status = published` và `is_current = true`.
3. Flutter gửi `narration_versions.script` (không gửi summary hay nội dung draft) cùng `{language, speed}` đến `POST /api/v1/speech`.
4. Phát response bytes bằng audio player trên Flutter.

Nếu `narration_versions.audio_url` đã có audio được duyệt/thu sẵn, Content/Catalog API có thể trả URL để Flutter phát trực tiếp và bỏ qua TTS. Nếu `audio_url` rỗng, Flutter gửi script sang TTS Service. Trong schema hiện tại chưa có cột quản lý WAV cache được TTS tạo; cache MVP lưu file ở volume nội bộ và trả bytes trực tiếp. Muốn lưu audio tổng hợp lâu dài và dùng `audio_url`, cần backend/object storage quản lý URL và trạng thái duyệt tương ứng.

Ở production, đặt service sau API gateway hoặc private network, bật HTTPS và xác thực service-to-service. Không mở endpoint công khai không giới hạn vì việc tạo audio dùng CPU. Bản MVP hiện không thêm nguồn phát sinh nội dung hay công cụ nhận diện.

## Ghi chú model và giấy phép

`sherpa-onnx` phát hành theo Apache-2.0. Voice Piper là model riêng; phải kiểm tra giấy phép của đúng voice và tuân theo điều kiện sử dụng/phân phối của nó trước khi triển khai ngoài đồ án. Dùng mẫu thuyết minh bảo tàng thật để đánh giá phát âm tên riêng, niên đại và thuật ngữ trước khi chọn voice cuối.
