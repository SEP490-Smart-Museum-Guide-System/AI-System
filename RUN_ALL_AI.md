# Chạy toàn bộ AI-System cho thành viên

## Một lệnh chạy

Mở PowerShell tại thư mục **AI-System** vừa clone/pull:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\start-ai.ps1
```

Không cần đường dẫn `D:\SEP409`, không cần tạo `.venv` hoặc cài Python trên máy host. Cần Docker Desktop đang chạy ở chế độ Linux containers và Internet cho lần tải image/model đầu. Trên máy dùng PowerShell 7 có thể dùng `pwsh -File ./tools/start-ai.ps1`.

## Chuẩn bị một lần trên mỗi máy

1. Cài và mở Docker Desktop/Compose.
2. Có PostgreSQL của hệ thống BE đang hoạt động. Lệnh này chạy các dịch vụ AI; PostgreSQL/BE/FE được quản lý riêng.
3. Lần đầu script tự copy `.env.example` thành `.env`, sinh khóa nội bộ rồi báo điền kết nối DB nếu còn placeholder. Mở `.env`, sửa `AI_SYSTEM_DB_HOST`, `AI_SYSTEM_DB_PORT`, `AI_SYSTEM_DB_NAME`, `AI_SYSTEM_DB_USER`, `AI_SYSTEM_DB_PASSWORD` theo database BE và chạy lại cùng lệnh.

Nếu PostgreSQL chạy trên máy Windows host hoặc container được publish ra host port 5432, giữ `AI_SYSTEM_DB_HOST=host.docker.internal`. Nếu DB ở server khác, điền hostname/IP thực tế mà container truy cập được. Không đặt `localhost`: bên trong container đó là chính container AI. Role DB cần quyền tạo schema/bảng dẫn xuất cho Vision và Scan; các dịch vụ không migrate bảng nghiệp vụ BE.

Với password chứa `$`, `#` hoặc khoảng trắng, dùng dấu nháy đơn trong `.env`, ví dụ `AI_SYSTEM_DB_PASSWORD='your actual password'`. Không commit hoặc gửi `.env` có mật khẩu/khóa cho cả nhóm; mỗi thành viên tự cấu hình.

Script không tự tạo lại database, không xóa dữ liệu, không tự tắt tiến trình đang chiếm port. Nếu đang chạy riêng `start-local-chat.ps1`/`start-local-tts.ps1`, dừng terminal đó trước, hoặc đổi `AI_*_PORT` trong `.env`.

## Các dịch vụ được chạy

| Dịch vụ | Port mặc định trên máy host | Kiểm tra sẵn sàng | Chức năng |
| --- | ---: | --- | --- |
| TTS Piper tiếng Việt | 8000 | `http://127.0.0.1:8000/ready` | Văn bản → WAV |
| Vision CLIP ONNX | 8001 | `http://127.0.0.1:8001/ready` | Ảnh → ứng viên hiện vật |
| 3D Scan API/worker | 8002 | `http://127.0.0.1:8002/ready` | Nhận bộ ảnh, quản lý job COLMAP |
| Chat/Xưởng AI Qwen ONNX | 8003 | `http://127.0.0.1:8003/ready` | Hỏi đáp, soạn thuyết minh/quiz |

Compose còn có `chat-model`: đây là bước tải graph/tokenizer Qwen đã pin revision, chạy xong rồi thoát **Exited (0)** là bình thường. Chat chỉ khởi động sau khi bước tải thành công. Model Chat khoảng 1,79 GB, các model khác được tải khi khởi động lần đầu. Lần đầu chậm hơn; các lần sau giữ cache/model. Chat chạy 1 worker để tránh nhân bản model trong RAM. Cần đủ RAM/dung lượng cho Docker và model; chưa benchmark cấu hình máy của từng thành viên.

Script chỉ báo thành công khi cả bốn `/ready` pass, tối đa mặc định 20 phút chờ readiness sau giai đoạn build. Vision ready với `reference_images=0` là hợp lệ cho service mới nhưng chưa nhận diện được hiện vật: cần index ảnh tham chiếu thật. Không tự nạp ảnh demo vào DB.

### Giới hạn 3D cần phân biệt

Image mặc định cài COLMAP từ Debian, phục vụ API/DB/job và kiểm tra binary. Đây không phải image CUDA. `scan` healthy **không chứng minh dựng được GLB**: bước dense reconstruction của pipeline hiện tại cần bản COLMAP có CUDA và NVIDIA GPU; chỉ cài binary/khởi động API chưa đáp ứng điều đó. Xem [COLMAP FAQ](https://colmap.github.io/legacy/3.12/faq.html) và [hướng dẫn cài COLMAP](https://colmap.github.io/install.html).

Máy không có GPU phù hợp vẫn chạy được TTS, Vision, Chat và API quản lý 3D. Job dựng dense mesh có thể thất bại; chưa thêm pipeline dense CPU hoặc cấu hình passthrough GPU vào bản Compose này. Không tạo GLB mẫu để che lỗi. Phần 3D vẫn là PoC, chưa phải luồng dựng mesh end-to-end đã được xác nhận.

## Cấu hình BE

Khi BE chạy trực tiếp trên cùng máy host, dùng:

```text
ArtifactGuide__Enabled=true
ArtifactGuide__BaseUrl=http://127.0.0.1:8003/
ArtifactGuide__ServiceKey=<AI_CHAT_SERVICE_KEY trong .env>
ArtifactSpeech__Enabled=true
ArtifactSpeech__BaseUrl=http://127.0.0.1:8000/
ArtifactSpeech__ServiceKey=<khóa trong state/tts-service-key.txt>
```

Launcher tự đồng bộ `.env` → `state/chat-service-key.txt` và `state/tts-service-key.txt` (ignored), nên các script BE `start-api-with-local-chat.ps1` và `start-api-with-local-tts.ps1` hiện có dùng lại được nếu các repo nằm theo cấu trúc thư mục chung. Không in khóa ra terminal, không đưa khóa vào `VITE_*`/Flutter.

TTS mặc định giữ key rỗng ở service để tương thích proxy Visitor local hiện tại; BE vẫn có key file riêng để cấu hình gateway. Nếu đặt `TTS_SERVICE_API_KEY` trong `.env`, script đồng bộ giá trị đó sang key file và TTS bắt buộc key. Khi đó client Visitor/proxy cũ phải đi qua gateway giữ key; không đặt secret vào FE. Vision và Scan luôn yêu cầu key nội bộ, chưa tự nối các gateway còn thiếu bằng việc chạy Compose.

Nếu BE cũng chạy Docker trong cùng network, dùng tên service `chat:8003`, `tts:8000`, `vision:8001`, `scan:8002`, không dùng localhost của container BE. Root stack mặc định chỉ publish lên `127.0.0.1`; chưa mở các API ra LAN/Internet.

## Dừng, xem log và kiểm tra

Từ thư mục AI-System:

```powershell
# Dừng cả nhóm, giữ cache/model/file job
powershell -ExecutionPolicy Bypass -File .\tools\stop-ai.ps1

# Trạng thái và log
docker compose ps
docker compose logs --tail 80 chat
docker compose logs --tail 80 vision
docker compose logs --tail 80 scan
docker compose logs --tail 80 tts

# Kiểm tra config mà chưa khởi động
powershell -ExecutionPolicy Bypass -File .\tools\start-ai.ps1 -CheckOnly

# Lần sau dùng image đã build
powershell -ExecutionPolicy Bypass -File .\tools\start-ai.ps1 -NoBuild
```

`docker compose down` giữ các volume. Không thêm `-v` nếu cần giữ model/cache/job. Dữ liệu embedding/job metadata nằm trong PostgreSQL BE, còn model Qwen ở `state/models/chat`, model TTS/Vision và file job ở Docker volumes. Clone Git không mang theo những dữ liệu này; máy mới sẽ tải model và cần dùng DB/index đúng của nhóm.

## Kiểm tra launcher

```powershell
.\tools\test-ai-launcher.ps1
```

Bộ kiểm tra dùng thư mục tạm: tạo config mới, giữ password có ký tự đặc biệt, không ghi đè cấu hình khác, khóa tách biệt, đồng bộ BE, chạy lại không đổi khóa và giữ tương thích TTS local. Không dùng hoặc in mật khẩu DB thật.

## Kết quả chạy thật ngày 09/11/2026

- Đã build và khởi động toàn bộ root Compose: TTS, Vision, Scan, Chat đều `healthy`; `chat-model` kết thúc exit 0. Cả bốn URL `/ready` từ máy host trả HTTP 200.
- Chạy lại `start-ai.ps1 -NoBuild` thành công, dùng lại model/cache. Đã kiểm tra chức năng chặn port bị process ngoài stack chiếm.
- TTS trong container tạo WAV thật 153132 byte, mono 22050 Hz, dài khoảng 3,47 giây với câu kiểm tra tiếng Việt. Đây là kiểm tra service, không đo chất lượng phát âm hoặc toàn bộ FE/BE.
- Khi DB local đang tắt, Vision/Scan không ready và launcher báo thất bại đúng; sau khi bật PostgreSQL dùng chung, các service kết nối được.
- Đã sửa lỗi SQL khởi tạo Scan: ký hiệu JSON mặc định `{}` bị `psycopg.sql.format` hiểu nhầm thành placeholder thứ hai. Escape thành `{{}}` trong template, SQL thực thi vẫn là `'{}'::jsonb`; 10 test Scan pass, gồm ca hồi quy mới. Không đổi cấu trúc bảng nghiệp vụ BE.
- Chưa kiểm thử job dựng mesh/GLB, cấu hình GPU, nhận diện trên bộ ảnh mới hoặc tải đồng thời trên máy thành viên. Các giới hạn 3D và yêu cầu index ảnh vẫn áp dụng.
