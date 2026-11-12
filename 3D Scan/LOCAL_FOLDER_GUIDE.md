# Dựng GLB local từ một folder ảnh

Chạy bằng Python trên Windows và Docker Desktop. Không cần artifact ID, tài khoản,
PostgreSQL hay upload từng ảnh. Dùng lại `app/reconstruction.py` và Docker image CPU
`smgs-ai-scan`; không thay contract API. Ảnh nguồn chỉ được mount read-only.

## Một lệnh

Mở Docker Desktop, đợi engine sẵn sàng, sau đó chạy PowerShell:

```powershell
python "D:\SEP409\AI-System\3D Scan\tools\scan_folder.py" "D:\3D\ceramic_vases_1\ceramic_vases_1"
```

Đổi đối số cuối sang đường dẫn folder của bộ ảnh khác. Nếu không truyền đối số,
script hỏi đường dẫn trong terminal. Nhận cả đường dẫn local `file:///D:/...`.

```powershell
python "D:\SEP409\AI-System\3D Scan\tools\scan_folder.py"
```

Script tự đọc JPG/JPEG/PNG trong folder và thư mục con. Nếu có `images/`, chỉ dùng
ảnh trong `images/`, tránh lấy texture atlas gốc làm một góc chụp. Mỗi lần chạy là
một hiện vật; không trỏ vào folder chứa nhiều hiện vật. Giới hạn local 5–1000 ảnh
là giới hạn nhận dữ liệu, không bảo đảm chất lượng hay thời gian; số ảnh lớn tốn
thêm RAM, ổ đĩa và CPU. HEIC/video/ZIP không được xử lý trực tiếp.

Mở **http://127.0.0.1:8766/** sau khi terminal in `VIEW:`. Trang theo dõi tiến độ,
hiện ảnh đầu vào, tự tải GLB khi thành công và có nút tải file. Giữ terminal mở;
Ctrl+C dừng worker đang chạy hoặc đóng server xem. Nếu cổng bị dùng, thêm `--port 8767`.
Không tự mở browser hay tự xuất bản lên bảo tàng.

Kết quả mỗi lần chạy lưu riêng tại:

```text
AI-System/3D Scan/state/local-scans/<timestamp-id>/
  config.json             bộ ảnh và chế độ được chọn
  status.json             tiến độ, lỗi, trạng thái cần kiểm tra
  worker.log              log terminal
  logs/                   log feature/matching/triangulation
  input/                  bản sao ảnh dùng trong job
  camera-audit/           chỉ ở chế độ benchmark
  colmap/                 ảnh đã undistort, sparse model
  openmvs/                dense cloud, mesh, log native
  output/model.glb        mesh và texture nhúng trong GLB
  provenance.json         nguồn gốc kết quả, giới hạn
  index.html, viewer.js   giao diện xem local
```

`model.glb` chỉ được giới thiệu trên UI khi worker trả `REVIEW_REQUIRED` sau khi
kiểm tra surface và texture. `FAILED` không được coi là mô hình đạt, kể cả còn
artifact trung gian trên đĩa. Không tự lấp lỗ hoặc lấy màu trung bình để che lỗi.
Chỉ có atlas trong GLB chưa chứng minh texture đúng trên mọi mặt; vẫn cần xem lại.

## Hai luồng tự chọn

- **photos**: chỉ cần ảnh. COLMAP tự ước lượng camera, yêu cầu ít nhất 80% ảnh
  đăng ký cùng sparse model, kiểm tra radial calibration, rồi OpenMVS CPU
  PatchMatch → mesh → refine → texture → GLB. Không dùng OBJ có sẵn để thay output.
- **benchmark**: folder LR3D-CULT2 có `metadata.json`, một OBJ và ảnh tên CAM/frame
  trong `images/`. Dùng camera positions từ metadata; hướng nhìn là giả định nhìn
  vào tâm, Y-up, zero roll. Vì metadata thiếu intrinsics, dùng silhouette OBJ gốc
  để hiệu chỉnh và kiểm tra camera. Sau đó triangulate feature tracks với camera
  cố định, rồi dựng dense/mesh/texture từ ảnh. **Đây không phải kết quả scan chỉ từ
  ảnh**; OBJ không được chép làm hình học GLB. Nếu kiểm tra camera không đạt thì
  dừng, không âm thầm lấy model nguồn làm kết quả.

Chế độ local dùng CPU PatchMatch ở `resolution-level 0`, giữ mesh khi refine,
tắt hole filling, tắt global/local seam leveling, đóng gói texture bằng byte như
bản mẫu kim loại. Các mặc định của API (SGM trước, fallback PatchMatch) không đổi.
Chất lượng một bộ ảnh khác không được bảo đảm giống bản kim loại.

Ép chạy chỉ từ ảnh, kể cả folder có OBJ/metadata:

```powershell
python "D:\SEP409\AI-System\3D Scan\tools\scan_folder.py" "D:\3D\ceramic_vases_1\ceramic_vases_1" --mode photos
```

Kiểm tra folder mà không chạy Docker; hoặc chỉ kiểm tra ảnh/calibration:

```powershell
python "D:\SEP409\AI-System\3D Scan\tools\scan_folder.py" "D:\3D\ceramic_vases_1\ceramic_vases_1" --check
python "D:\SEP409\AI-System\3D Scan\tools\scan_folder.py" "D:\3D\ceramic_vases_1\ceramic_vases_1" --prepare-only --no-serve
```

Nếu chưa có image CPU: `docker compose -f "D:\SEP409\AI-System\compose.yaml" build scan`.
Viewer dùng bundle model-viewer đã cài ở `FrontEnd/smgs_web/node_modules`; nếu thiếu,
chạy `npm install` trong thư mục đó. Worker Docker không có network khi dựng.

Mở lại một job cũ, thay đường dẫn bằng dòng `OUTPUT:` đã in:

```powershell
python -m http.server 8766 --bind 127.0.0.1 --directory "D:\SEP409\AI-System\3D Scan\state\local-scans\<timestamp-id>"
```

## Kiểm chứng 12/11/2026

- Bộ `ceramic_vases_1`: 180 PNG / 43.1 MiB, không đưa JPEG atlas vào danh sách ảnh.
- Đã chạy thật validation và calibration qua Docker bằng `--prepare-only --no-serve`:
  trạng thái `CHECKED`, bbox RMSE 0.268 px; silhouette đối chiếu camera khoảng
  98.72–99.05%. Đây là số liệu **camera với OBJ tham chiếu**, không phải chất lượng
  của một GLB mới.
- Chưa chạy toàn bộ reconstruction của bộ ceramic này: người dùng yêu cầu tự chạy.
- Chưa tích hợp local job vào BE/FE, chưa tự lưu model vào hồ sơ hiện vật. Tải GLB
  rồi upload vào chức năng model 3D hiện có sau khi kiểm tra.
