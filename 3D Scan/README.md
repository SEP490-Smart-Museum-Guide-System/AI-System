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

Yêu cầu Python 3.11+, COLMAP CLI và OpenMVS CLI cài trên máy. Pipeline mặc định **không cần CUDA**: COLMAP CPU tạo poses/sparse points (dùng chung một camera calibration cho bộ ảnh); worker chọn sparse submodel có nhiều ảnh đăng ký nhất và yêu cầu ít nhất 80% ảnh upload nằm trong cùng một model. Nếu ảnh bị chia thành các nhóm rời hoặc tỷ lệ dưới ngưỡng, job `FAILED` trước dense stage. OpenMVS thử SGM CPU (`--fusion-mode -2`) trước. Nếu SGM không tạo dense points, worker chạy lại OpenMVS PatchMatch CPU (`--fusion-mode 0`, giảm ảnh một mức, 4 threads) trong workspace sạch. Nếu cả hai đều không có dense points, job chuyển `FAILED`; service không dựng mesh từ sparse points để giả làm scan hoàn chỉnh. Sau đó worker reconstruct/refine mesh, TextureMesh dùng virtual-face patches, tắt cả global/local seam leveling sau khi phép đối chứng phát hiện mảng đen do hai bước này, và đóng gói atlas vào GLB để endpoint hiện tại vẫn trả một file duy nhất. Cần các lệnh `InterfaceCOLMAP`, `DensifyPointCloud`, `ReconstructMesh`, `RefineMesh`, `TextureMesh` trong PATH, hoặc đặt `OPENMVS_BIN_DIR` trỏ đến thư mục chứa chúng. Có thể cấu hình riêng từng binary bằng biến `OPENMVS_*_COMMAND`. COLMAP dense bị tắt (`--dense 0`); feature/matching và cả hai phương án OpenMVS đều chạy CPU (`--use_gpu 0`, tối đa 4 threads).

Dockerfile tải OpenMVS CPU Linux v2.4.0 từ release chính thức, xác minh SHA-256 trước khi cài và giữ license trong image/repo. Base image dùng Ubuntu 24.04 vì binary yêu cầu runtime mới hơn Debian Bookworm. Upstream ghi SGM CPU qua `--fusion-mode -2`; `TextureMesh` hỗ trợ texturing và export GLB. OpenMVS công bố giấy phép AGPL-3.0; nhóm cần xem điều kiện phân phối image/sản phẩm. Xem [OpenMVS Usage](https://github.com/cdcseacave/openMVS/blob/develop/docs/wiki/Usage.md), [Building](https://github.com/cdcseacave/openMVS/blob/develop/docs/wiki/Building.md), [license](https://github.com/cdcseacave/openMVS/blob/v2.4.0/LICENSE).

Có thể khởi động cùng các AI khác bằng [một lệnh Docker Compose](../RUN_ALL_AI.md). Image Scan mặc định chứa COLMAP CPU và OpenMVS CPU, không tích hợp CUDA/GPU passthrough. Readiness kiểm tra COLMAP, đủ bộ OpenMVS CPU, DB và worker; `/ready` không thay thế việc kiểm tra chất lượng mesh từng job.

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
uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Job records được lưu trong PostgreSQL chung; khi service khởi động lần đầu, nó tạo schema/table `ai_3d_scan.scan_jobs` nếu role DB có quyền. File job vẫn nằm ở `state/scan-jobs/<scanJobId>/`; đặt `SCAN_DATA_DIR` để chuyển nơi lưu. Muốn chạy nhiều instance hoặc giữ file qua redeploy, cần shared/object storage cho ảnh và GLB. Hệ thống nhận từ **5 ảnh của cùng một hiện vật**; 80 ảnh chỉ là giới hạn trên, không phải số lượng phải chụp. Mỗi ảnh tối đa 20 MiB, tổng job tối đa 500 MiB; cấu hình qua `SCAN_MAX_IMAGES`, `SCAN_MAX_IMAGE_BYTES`, `SCAN_MAX_TOTAL_BYTES`.

Chụp 5 ảnh rõ nét ở các góc khác nhau nhưng có nhiều chi tiết chung giữa ảnh liền kề. Đây là điều kiện nhận bộ ảnh, không bảo đảm dựng được mesh đầy đủ: COLMAP vẫn có thể thất bại hoặc thiếu mặt/chi tiết. Giám tuyển phải kiểm tra bản dựng; không sinh mô hình mẫu thay thế khi dựng thất bại. Tham khảo [hướng dẫn chụp của COLMAP](https://colmap.github.io/tutorial.html).

Bản sửa 04/11/2026 giới hạn thêm `SCAN_MAX_IMAGE_PIXELS` (20 triệu pixel) và `SCAN_MAX_METADATA_BYTES` (16 KiB); giải mã thật ảnh, kiểm tra đuôi/định dạng và dọn thư mục upload khi persist job lỗi. Job ID không đúng UUID trả 422. `/live` dành cho process; `/ready` và `/health` kiểm tra COLMAP, OpenMVS CPU, trạng thái worker và DB; trả 503 nếu thiếu bất kỳ thành phần cần thiết nào.

Worker claim `QUEUED → PROCESSING` bằng một UPDATE có điều kiện để tránh nhận trùng. Startup không còn reset hàng loạt `PROCESSING` thành `QUEUED`, tránh cướp job đang chạy ở worker khác. Sau crash, job `PROCESSING` cần operator xác minh toàn bộ worker đã dừng trước khi phục hồi; chưa có lease/heartbeat hoặc tự phục hồi an toàn. Với storage local, vẫn chỉ triển khai một instance. Thay đổi này không biến BackgroundTasks thành hàng đợi phân tán production.

## API

`SCAN_COLMAP_CAMERA_MODEL` mặc định `SIMPLE_RADIAL` cho bộ ảnh chụp cùng camera. Có thể đặt `PINHOLE` cho bộ ảnh render/camera đã hiệu chỉnh không có lens distortion; đây là cấu hình server, không đổi contract API. Worker kiểm tra SIMPLE_RADIAL để từ chối calibration có radial mapping bị gập trước khi undistort. 40/40 ảnh đăng ký hoặc reprojection error thấp chưa bảo đảm calibration đúng. Phép kiểm tra radial này chưa bao phủ các camera model khác.

Mọi endpoint scan yêu cầu header `X-Service-Key`. Tích hợp thực tế phải gọi service từ Backend, không gọi trực tiếp từ trình duyệt.

```http
POST /api/v1/scans
Content-Type: multipart/form-data
X-Service-Key: <server-side-key>

artifact_id: 123
capture_metadata: {"device":"iPhone Safari"}
images: <5..80 JPG/PNG files; 5 photos are accepted>
```

Trả `202 Accepted` với `scanJobId`, `artifactId`, `status=QUEUED`. Dùng `GET /api/v1/scans/{scanJobId}` để xem `QUEUED`, `PROCESSING`, `REVIEW_REQUIRED` hoặc `FAILED`. Model chỉ được phục vụ sau khi tạo thành công. `POST /api/v1/scans/{scanJobId}/approve` chuyển job từ `REVIEW_REQUIRED` sang `COMPLETED`; đây hiện là endpoint nội bộ PoC, chưa kiểm tra role curator. Backend cần thay thế bước duyệt nội bộ này bằng quyền đăng nhập và audit log của SMGS.

## Giới hạn PoC

Kết quả audit toàn bộ 180 ảnh, camera priors và nguyên nhân thiếu đáy lòng được ghi tại [`DATASET_CAMERA_AUDIT_2026-11-11.md`](DATASET_CAMERA_AUDIT_2026-11-11.md). Thử nghiệm camera priors là công cụ benchmark riêng, chưa thêm endpoint upload pose vào API. Worker hiện tắt automatic hole filling/tower mode, giữ lưới khi refine, và lưu stdout/stderr từng lệnh vào thư mục `logs` trong workspace tương ứng. GLB đóng gói atlas theo byte, giữ nguyên UV/material và extension unlit. `REVIEW_REQUIRED` vẫn đòi hỏi người duyệt chất lượng; service không thể tự chứng nhận đầy đủ các bề mặt bị che khuất chỉ từ số lượng dense points.

- PostgreSQL chung lưu job metadata; file scan/GLB vẫn nằm ở ổ đĩa local. Chưa có object storage, queue phân tán, cleanup policy hoặc nhiều worker.
- API key bảo vệ service; Backend JWT/role chưa được nối vào.
- Pipeline CPU có thể tốn RAM và thời gian; một worker xử lý một job tại một thời điểm. Bộ test 40 ảnh Blender mất khoảng 5 phút 17 giây ở PatchMatch CPU trên 4 threads; ảnh hiện vật thật chưa benchmark.
- **Hiệu chỉnh kết quả ngày 11/11/2026:** job `6d9f771a-acb1-4a57-a483-6741ae41a56e` từng được báo nhầm là dense mesh hoàn chỉnh. Log thực tế ghi OpenMVS SGM `0 points`; mesh/GLB 6.327 đỉnh, 9.812 mặt được tạo từ sparse points. Atlas có nhiều vùng chưa texture, nên kết quả đó không chứng minh scan 3D trung thực. API verification sau khi bật PatchMatch cũng cho thấy COLMAP chỉ đăng ký 25/40 ảnh trong submodel lớn nhất và tạo 6 model rời; GLB này không được coi là scan đạt. Worker mới chọn sparse submodel tốt nhất, yêu cầu ít nhất 80% ảnh đăng ký, kiểm tra dense PLY, rồi thử PatchMatch CPU nếu cần. Tham khảo [`PIPELINE_AUDIT_2026-11-11.md`](PIPELINE_AUDIT_2026-11-11.md) và [`IMPLEMENTATION_LOG.md`](../IMPLEMENTATION_LOG.md).
- Bộ sample hiện có là 40 ảnh render Blender của một ly/chân đế kim loại, không phải ảnh camera của bình gốm trong hội thoại hoặc ảnh chụp hiện vật; nó không chứng minh chất lượng scan bảo tàng.
- Curator review hiện chỉ là state transition nội bộ; Backend chưa lưu `modelUrl`.
- Chưa có trang Safari chụp/upload. Browser capture và Backend job gateway là bước kế tiếp.

Tham khảo pipeline/CLI chính thức: [COLMAP CLI](https://github.com/colmap/colmap/blob/main/doc/cli.rst), [COLMAP tutorial](https://github.com/colmap/colmap/blob/main/doc/tutorial.rst), [OpenMVS SGM/mesh/texture/GLB pipeline](https://github.com/cdcseacave/openMVS/blob/develop/docs/wiki/Usage.md).
