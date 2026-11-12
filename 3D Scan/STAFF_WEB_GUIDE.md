# Tạo 3D từ FE cho Museum Staff — 12/11/2026

## Luồng đã triển khai

Museum Staff → mở hiện vật thuộc phạm vi được phân công → tab **Xem Mô hình 3D (AR)** → chọn folder → **Tạo mô hình 3D** → theo dõi tiến độ → **Xem kết quả AI** → **Lưu vào hiện vật** hoặc **Bỏ kết quả scan**.

FE gửi multipart có JWT tới BE `api/artifacts/{artifactId}/scans`. BE kiểm tra vai trò Admin/Museum Staff và quyền trên hiện vật trước mỗi thao tác. BE gọi AI bằng khóa nội bộ; FE không cần biết khóa đó. AI dùng lại worker của `tools/scan_folder.py`: COLMAP CPU → OpenMVS CPU PatchMatch (resolution 0) → mesh/refine → texture → GLB. API cũ vẫn giữ nguyên.

Job được lưu trong `ai_3d_scan.scan_jobs`, cùng database PostgreSQL với BE. Khi bấm lưu, BE dùng dịch vụ media hiện có để ghi **bản ghi artifact_3d_models và storage key**; byte GLB nằm trong kho file/object storage đã cấu hình. Không nhét byte GLB trực tiếp vào cột DB. Thay thế/xóa model dùng cơ chế kiểm tra quyền và dọn file hiện có của BE.

## Chạy sau khi pull ba repo

Yêu cầu Docker Linux containers x64, .NET 8, Node đáp ứng Vite và PostgreSQL đã có schema BE tương thích. Trong AI-System, tạo `.env` từ `.env.example`, điền `AI_SYSTEM_DB_*` đúng DB của BE. Nếu PostgreSQL chạy trên Windows thì host từ Docker là `host.docker.internal`. Không bật thêm container PostgreSQL trên cùng cổng 5432.

Terminal 1, thư mục AI-System:

```powershell
powershell -ExecutionPolicy Bypass -File tools/start-scan.ps1
```

Terminal 2, thư mục BackEnd:

```powershell
powershell -ExecutionPolicy Bypass -File tools/start-with-scan.ps1
```

Script BE đọc cấu hình DB/khóa scan từ `.env` của repo AI-System kế bên; chỉ truyền qua environment của process. Có thể chỉ định `-AiSystemPath "D:\duong-dan\AI-System"`. Sau khi build, dùng `-NoBuild` để chạy nhanh.

Terminal 3, thư mục FrontEnd/smgs_web:

```powershell
npm ci
npm run dev -- --host 127.0.0.1
```

Mở URL Vite in ra. Đăng nhập Museum Staff đã được phân công bảo tàng/hiện vật. Hiện vật phải được lưu trước để có ID thật. Chọn folder bằng hộp chọn của trình duyệt; website không đọc tùy ý đường dẫn ổ D của khách.

## Bộ ảnh và chất lượng

- Web nhận 5–200 JPG/PNG, mỗi ảnh tối đa 20 MiB, tổng bộ tối đa 500 MiB; metadata 2 MiB, OBJ 64 MiB. Không upload ZIP/HEIC/video.
- Folder có `images/` sẽ chỉ lấy ảnh trong đó, tránh dùng atlas gốc như ảnh camera. Chọn folder **một hiện vật**, không chọn folder cha có nhiều bộ.
- Dataset LR3D như ceramic: chọn folder chứa `images/`, `metadata.json` và một OBJ. Giữ tên ảnh camera/frame. OBJ chỉ dùng hiệu chỉnh calibration vì metadata thiếu intrinsics; hướng nhìn được suy ra theo giả định look-at. Geometry đầu ra được dựng từ ảnh. Đây là benchmark có tham chiếu, không phải bằng chứng chất lượng scan chỉ từ ảnh.
- Ảnh chụp thường: chọn nhiều ảnh hoặc folder; chế độ photos chạy COLMAP ước lượng camera. Chất lượng không bảo đảm giống bộ ceramic đã có camera/tham chiếu. Thiếu góc chụp có thể để lại lỗ, không tô màu trung bình hoặc lấy OBJ nguồn thay kết quả.
- REVIEW_REQUIRED nghĩa là có GLB với image texture và cần xem lại hình dáng/màu; không chứng nhận độ chính xác bảo tàng.

## Xem, lưu và bỏ

Có thể chọn GLB local để xem thử trước khi upload. **Bỏ bản xem thử** chỉ bỏ preview. **Lưu vào hiện vật** ghi/thay model đã lưu, có xác nhận nếu đang có model. **Xóa model đã lưu** gọi API media BE. **Bỏ kết quả scan** chuyển job REVIEW_REQUIRED/FAILED sang DISCARDED; ảnh/log/output job vẫn giữ để chẩn đoán, chưa có chính sách xóa định kỳ. Không hủy job đang chạy.

Đóng tab không hủy worker; mở lại sẽ tải job gần nhất chưa lưu/bỏ từ DB. Server phải tiếp tục chạy.

## Triển khai server và phần còn thiếu

AI chạy trong image Linux có sẵn COLMAP/OpenMVS CPU; server không cần CUDA. BE đặt `AiScan__BaseUrl`, `AiScan__ServiceKey` trùng `SCAN_SERVICE_API_KEY`. Dùng DNS nội bộ nếu BE/AI cùng Docker network. Reverse proxy cần cho phép multipart ít nhất 550 MiB; BE đã đặt giới hạn riêng endpoint. Không mở public cổng AI có khóa cho trình duyệt.

Hiện có một worker/instance, queue trong DB và background task. Chưa có lease/heartbeat, tự phục hồi job PROCESSING sau crash, cancel, quota người dùng, dọn ảnh/log định kỳ hoặc benchmark tải đồng thời. Lưu volume `/data` bền vững. Đây là luồng demo một server; cần bổ sung các mục trên trước vận hành nhiều khách.

## Kiểm chứng

- Docker image CPU build được, bundle model-viewer độc lập tải và khớp SHA256.
- AI: 20 unit/API tests qua, gồm upload dataset/giữ tên camera, lỗi dữ liệu và cleanup, giới hạn dung lượng, discard trạng thái.
- BE: build qua; MediaChecks qua kiểm tra scope Museum Staff, chặn job khác hiện vật, chặn lưu job chưa xong và xử lý khóa AI sai, cùng các kiểm tra media/storage hiện có.
- FE: build qua; 35 tests qua, 1 test đăng nhập live bỏ qua theo cấu hình. Lint không có lỗi, còn warning của repo.
- Đã chạy thật toàn bộ FE → BE → AI → storage/DB với Museum Staff: tạo hồ sơ **DEMO-3D-20261112**, artifact ID 10, chọn folder ceramic 184 tệp (lấy 180 ảnh camera + metadata/OBJ), bấm Tạo mô hình 3D trên FE.
- Job `04473380-4377-45f0-bfef-556b95e2d6bd` hoàn tất REVIEW_REQUIRED 100%; bấm Xem kết quả AI rồi Lưu vào hiện vật thành công, trạng thái cuối COMPLETED. Đã kiểm tra SHA256 GLB tải lại qua BE trùng kết quả AI, dung lượng **8.232.748 byte**. [Bằng chứng API](WEB_SCAN_VERIFICATION_2026_11_12.json).
- Phát hiện và sửa lỗi lưu luồng HTTP không seek: gateway đệm vào file tạm có giới hạn dung lượng, tự xóa khi đóng rồi gọi bộ kiểm tra GLB hiện có. Có test regression dùng stream không seek; vẫn giữ xác thực định dạng và kiểm tra đủ byte.
- Preview/lưu GLB local từ lần PowerShell trước cũng đã chạy thật (8.294.672 byte). Xóa model được kiểm tra bằng MediaChecks với DB/storage giả lập; chưa bấm xóa bản demo đã lưu trên storage thật.
- Đây là kiểm chứng **benchmark có tham chiếu**. Chưa chứng minh ảnh chụp bất kỳ cho chất lượng tương tự, chưa kiểm thử tải đồng thời/deploy production.
