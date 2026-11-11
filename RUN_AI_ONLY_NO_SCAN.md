# Máy mới: chỉ chạy AI-System, không chạy 3D Scan

Hướng dẫn PowerShell cho member phụ trách AI. Không cài/chạy/migrate/seed BE, FE hoặc DB. Cần **Git, Docker Desktop đang chạy ở chế độ Linux containers** và thông tin PostgreSQL do member BE cung cấp. Không cần cài Python, Flutter, Node, .NET hay CUDA trên máy host cho cách chạy này.

## 1. Clone và cấu hình một lần

```powershell
git clone https://github.com/SEP490-Smart-Museum-Guide-System/AI-System.git
cd AI-System

if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Điền đúng 5 dòng kết nối DB hiện có của BE:

```dotenv
AI_SYSTEM_DB_HOST=host.docker.internal
AI_SYSTEM_DB_PORT=5432
AI_SYSTEM_DB_NAME=smgs_db
AI_SYSTEM_DB_USER=postgres
AI_SYSTEM_DB_PASSWORD='replace-with-the-existing-be-db-password'
```

- DB cùng máy Windows, AI trong Docker: host là `host.docker.internal`.
- DB ở máy/server khác: thay host bằng IP/hostname **do member BE cung cấp**, cùng port/user/password thật. Member BE cần bảo đảm DB cho phép máy AI kết nối. Không dùng `localhost` trong container để chỉ DB trên host.
- Giữ nguyên các dòng khác nếu dùng port mặc định. Launcher tự tạo khóa nội bộ và đồng bộ file khóa; không cần tự nghĩ key cloud hoặc tải model thủ công.
- Không commit `.env` hoặc thư mục khóa/model. Clone repo không mang theo DB, bộ embedding/ảnh tham chiếu hay cache model của máy cũ.

## 2. Chạy AI, bỏ Scan

Từ thư mục `AI-System`, bộ lệnh tương thích với repo hiện có (không cần cờ mới):

```powershell
# Chuẩn bị khóa nội bộ từ .env đã điền, không in khóa ra màn hình
powershell -ExecutionPolicy Bypass -Command ". .\tools\AiStackConfig.ps1; Initialize-AiStackEnv (Get-Location).Path | Out-Null"

# Chỉ chọn 4 API và bước tải model; không chọn scan
docker compose up --build --detach --wait --wait-timeout 1200 tts vision chat-model chat tour
```

Nếu nhóm đã pull bản launcher có cờ `-SkipScan`, hai lệnh trên có thể thay bằng một lệnh:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\start-ai.ps1 -SkipScan
```

Lần đầu cần Internet để Docker tải image/dependency/model. Model Qwen khoảng 1,79 GB; thời gian khởi động phụ thuộc đường truyền và máy. Script chờ readiness; chỉ báo thành công sau khi các API đã sẵn sàng. Nếu DB chưa kết nối được, Vision không ready và launcher báo lỗi cụ thể.

| Service | URL trên máy AI | Chức năng |
| --- | --- | --- |
| TTS | `http://127.0.0.1:8000` | Giọng đọc tiếng Việt |
| Vision | `http://127.0.0.1:8001` | Nhận diện ảnh hiện vật bằng CLIP ONNX |
| Chat / Xưởng AI | `http://127.0.0.1:8003` | Chatbot, soạn thuyết minh và câu hỏi |
| Tour | `http://127.0.0.1:8004` | Gợi ý hành trình cá nhân |

`chat-model` là bước tải model, kết thúc **Exited (0)** là đúng. Chỉ có 4 API chạy lâu dài. Cờ `-SkipScan` không build/start/restart Scan, không kiểm tra port 8002. Nó không tự dừng container Scan cũ đang chạy; công việc fix Scan hiện có vẫn được giữ nguyên.

Các lần sau, dùng lại image/model từ thư mục `AI-System`:

```powershell
docker compose up --detach --wait --wait-timeout 1200 tts vision chat-model chat tour

# Hoặc, khi đã có launcher mới
powershell -ExecutionPolicy Bypass -File .\tools\start-ai.ps1 -SkipScan -NoBuild
```

Sau khi pull thay đổi Dockerfile/requirements/code, chạy lại **không có `-NoBuild`** để cập nhật image.

## 3. Kiểm tra, xem log, dừng

```powershell
# Các URL phải trả HTTP 200 khi ready
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:8001/ready
Invoke-RestMethod http://127.0.0.1:8003/ready
Invoke-RestMethod http://127.0.0.1:8004/ready

# Trạng thái, gồm bước tải model đã hoàn thành
docker compose ps -a tts vision chat-model chat tour

# Log khi lỗi hoặc tải model lâu
docker compose logs --tail 100 tts vision chat-model chat tour

# Chỉ dừng 4 API đang phụ trách, giữ cache/model và không dừng Scan
docker compose stop tts vision chat tour
```

Vision mới có thể ready với `reference_images=0`; khi đó chưa nhận diện được hiện vật. Cần index ảnh tham chiếu đúng ID hiện vật của DB hiện tại theo [`AI Vision/README.md`](AI%20Vision/README.md). Chạy service không tự nạp bộ ảnh của máy cũ; cũng không tự hoàn thiện gateway/khóa ở adapter FE.

## 4. Bàn giao cấu hình cho member BE

Các API mặc định chỉ publish lên loopback; BE chạy cùng máy dùng các URL trong bảng trên. BE ở máy khác cần cấu hình mạng/proxy riêng; chỉ đổi URL sang IP máy AI chưa đủ với binding hiện tại.

Khóa sinh trên từng máy nằm trong `.env` và các file **Git ignored**:

- `state/chat-service-key.txt`: cho chatbot và tạo nội dung.
- `state/tts-service-key.txt`: cho gateway TTS của BE; `TTS_SERVICE_API_KEY` mặc định rỗng để tương thích proxy local Visitor hiện có.
- `state/tour-service-key.txt`: cho gợi ý tour.
- Vision dùng `AI_SERVICE_API_KEY` trong `.env`.

Member BE nối các URL/key này qua cấu hình server. Không đặt service key vào `VITE_*`, Flutter hoặc mã nguồn public. Hướng dẫn này chỉ chạy AI; không khẳng định toàn bộ FE → BE → AI đã nối và chạy end-to-end trên máy mới.

## Kiểm chứng thay đổi launcher

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\test-ai-launcher.ps1
powershell -ExecutionPolicy Bypass -File .\tools\test-ai-skip-scan.ps1
```

Đã kiểm tra sinh/giữ khóa, danh sách service và lệnh Compose bằng Docker giả lập: đúng 4 API + `chat-model`, bỏ Scan/recovery/port Scan, giữ cờ `NoBuild`. Đã kiểm tra cấu hình Compose; chưa dựng lại toàn bộ image trên một máy sạch trong lượt thay đổi này.

Các file launcher vừa sửa và tài liệu này cần được commit/push vào repo trước khi member clone để dùng cờ mới. Bộ lệnh chọn service trực tiếp phía trên dùng helper cấu hình đã có, không phụ thuộc cờ mới. Không có thao tác push trong lượt viết hướng dẫn.
