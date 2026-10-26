# 3D Scan Service

Microservice PoC nhận ảnh nhiều góc, chạy COLMAP ở nền, chuyển mesh sang GLB và giữ kết quả ở trạng thái curator review. Job metadata được lưu trong schema riêng `ai_3d_scan.scan_jobs` của **cùng PostgreSQL database với BE**, cấu hình qua `AI_SYSTEM_DB_*`. Service không tạo database riêng và chưa tự cập nhật `modelUrl` trong Backend. Ảnh đầu vào và GLB hiện vẫn lưu trên ổ đĩa theo `SCAN_DATA_DIR`.

## Luồng hiện tại

```text
iPhone/web client → POST ảnh → 3D Scan Service → COLMAP → GLB
                                                ↓
                                         REVIEW_REQUIRED
                                                ↓ curator duyệt
Flutter ← modelUrl do Backend lưu sau khi duyệt
```

Backend cần làm gateway xác thực giữa giao diện scan và service này. Không nhúng `SCAN_SERVICE_API_KEY` vào JavaScript frontend hoặc ứng dụng Flutter.

## Chạy local

Yêu cầu Python 3.11+, COLMAP CLI cài trên máy và truy cập được qua PATH (hoặc cấu hình `COLMAP_COMMAND`). Bản COLMAP phải có các lệnh `automatic_reconstructor`, `poisson_mesher` và `mesh_texturer`. CPU chạy được nhưng chậm; COLMAP dùng CUDA khi máy hỗ trợ.

```powershell
cd "AI-System/3D Scan"
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SCAN_SERVICE_API_KEY = "dev-only-change-this-key"
$env:AI_SYSTEM_DB_HOST = "localhost"
$env:AI_SYSTEM_DB_NAME = "smgs_db"
$env:AI_SYSTEM_DB_USER = "postgres"
$env:AI_SYSTEM_DB_PASSWORD = "<same secret configured for BE PostgreSQL>"
uvicorn app.main:app --host 127.0.0.1 --port 8012
```

Job records được lưu trong PostgreSQL chung; khi service khởi động lần đầu, nó tạo schema/table `ai_3d_scan.scan_jobs` nếu role DB có quyền. File job vẫn nằm ở `state/scan-jobs/<scanJobId>/`; đặt `SCAN_DATA_DIR` để chuyển nơi lưu. Muốn chạy nhiều instance hoặc giữ file qua redeploy, cần shared/object storage cho ảnh và GLB. Giới hạn mặc định: 10–80 ảnh, tối đa 20 MiB/ảnh và 500 MiB/job; có thể cấu hình qua `SCAN_MAX_IMAGES`, `SCAN_MAX_IMAGE_BYTES`, `SCAN_MAX_TOTAL_BYTES`.

## API

Mọi endpoint scan yêu cầu header `X-Service-Key`. Tích hợp thực tế phải gọi service từ Backend, không gọi trực tiếp từ trình duyệt.

```http
POST /api/v1/scans
Content-Type: multipart/form-data
X-Service-Key: <server-side-key>

artifact_id: 123
capture_metadata: {"device":"iPhone Safari"}
images: <10..80 JPG/PNG files>
```

Trả `202 Accepted` với `scanJobId`, `artifactId`, `status=QUEUED`. Dùng `GET /api/v1/scans/{scanJobId}` để xem `QUEUED`, `PROCESSING`, `REVIEW_REQUIRED` hoặc `FAILED`. Model chỉ được phục vụ sau khi tạo thành công. `POST /api/v1/scans/{scanJobId}/approve` chuyển job từ `REVIEW_REQUIRED` sang `COMPLETED`; đây hiện là endpoint nội bộ PoC, chưa kiểm tra role curator. Backend cần thay thế bước duyệt nội bộ này bằng quyền đăng nhập và audit log của SMGS.

## Giới hạn PoC

- PostgreSQL chung lưu job metadata; file scan/GLB vẫn nằm ở ổ đĩa local. Chưa có object storage, queue phân tán, cleanup policy hoặc nhiều worker.
- API key bảo vệ service; Backend JWT/role chưa được nối vào.
- `automatic_reconstructor` có thể tốn CPU, RAM, dung lượng và thời gian. Một worker xử lý một job tại một thời điểm.
- COLMAP tạo mesh và texture atlas; chuyển đổi GLB cần được kiểm tra bằng bộ ảnh thật vì material/texture có thể không được giữ đồng nhất ở mọi bản build.
- Curator review hiện chỉ là state transition nội bộ; Backend chưa lưu `modelUrl`.
- Chưa có trang Safari chụp/upload. Browser capture và Backend job gateway là bước kế tiếp.

Tham khảo pipeline/CLI chính thức: [COLMAP CLI](https://github.com/colmap/colmap/blob/main/doc/cli.rst), [COLMAP tutorial](https://github.com/colmap/colmap/blob/main/doc/tutorial.rst).
