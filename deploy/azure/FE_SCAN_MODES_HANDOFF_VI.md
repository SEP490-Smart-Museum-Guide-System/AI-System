# Handoff: Hai luồng tạo mô hình 3D từ Web

Ngày ghi: 26/11/2026  
Repo FE: `FrontEnd/smgs_web`, commit `56b9d19` trên `main` (`origin/main`).

## Mục tiêu

Giao diện nhân viên có hai cách tạo mô hình 3D:

1. **Chỉ tải ảnh**: giữ quy trình dựng ảnh thông thường hiện tại.
2. **Ảnh + file tham chiếu**: nếu chọn được đủ một `metadata.json` và một `.obj`, FE tự gửi chế độ benchmark để AI dùng camera metadata/OBJ tham chiếu. OBJ chỉ hỗ trợ hiệu chỉnh camera; hình học GLB đầu ra vẫn được dựng từ ảnh.

`MTL` không cần cho luồng benchmark scan này. Nút tải mô hình 3D đã dựng sẵn vẫn chỉ nhận `.glb`.

## Hành vi FE

- Nút **Chỉ tải ảnh (quy trình thường)** chỉ nhận JPG/PNG và gửi `mode=photos`.
- Nút **Ảnh + OBJ + metadata (benchmark)** nhận JPG/PNG, `.obj`, `.json` và dùng chế độ tự động:
  - Có đúng một OBJ và file tên chính xác `metadata.json`: gửi `mode=benchmark`, kèm hai file tham chiếu.
  - Thiếu OBJ hoặc `metadata.json`: tự hạ xuống `mode=photos`; file tham chiếu lẻ không được gửi lên AI.
- Ảnh cần từ 5 đến 200 file. Giới hạn FE: mỗi ảnh 20 MiB, metadata 2 MiB, OBJ 64 MiB, tổng dữ liệu 500 MiB.
- Nếu chọn `captureOrder=ordered`, FE sắp ảnh theo tên file kiểu số tự nhiên trước khi gửi. Mặc định là `unordered`.
- Hai nút chọn file dùng multi-select; không dùng hộp chọn thư mục.

## Hợp đồng upload cần giữ

FE gửi multipart qua gateway xác thực BE tới Scan API. Các field hiện có:

| Field | Nội dung |
| --- | --- |
| `mode` | `photos` hoặc `benchmark` |
| `images` | Một field lặp cho mỗi ảnh JPG/PNG |
| `metadata` | `metadata.json`, chỉ có khi đủ cặp tham chiếu |
| `referenceObj` | Một OBJ tham chiếu, chỉ có khi đủ cặp |
| `quality` | `balanced`, `detailed` hoặc `preview` |
| `captureOrder` | `unordered` hoặc `ordered` |

Không đổi tên `metadata` / `referenceObj` khi BE chuyển multipart sang AI. Với yêu cầu ảnh thường, không cần metadata hay OBJ. Với benchmark, cần giữ nguyên tên ảnh camera/frame trong lúc upload để worker nhận đúng dataset.

## Việc phía AI-System cần xác nhận

1. Scan API và worker đang chạy trên Azure nhận `mode=photos` và `mode=benchmark`, các field multipart nêu trên.
2. Chế độ photos chạy quy trình COLMAP thông thường; bộ thiếu một file tham chiếu đã được FE chuyển thành photos.
3. Benchmark chấp nhận đúng cấu trúc `metadata.json` của bộ dữ liệu, dùng OBJ làm tham chiếu camera/calibration, không dùng OBJ nguồn làm hình học GLB đầu ra.
4. Đảm bảo gateway BE chuyển đủ các field multipart, nhất là `metadata`, `referenceObj`, `quality`, `captureOrder`.
5. Khi triển khai, giữ nguyên `.env.azure`, service keys, volume dữ liệu và job cũ; không xóa volume hoặc reset trạng thái job. Kiểm tra không có job/native worker đang chạy trước khi recreate Scan.

## Giới hạn và trạng thái triển khai

- Benchmark chỉ có thể nhanh hơn ở phần hiệu chỉnh/ước lượng camera; dựng dense mesh và texture vẫn phải xử lý ảnh. Chưa có kết quả đo thời gian mới để cam kết mức tăng tốc.
- Commit FE `56b9d19` đã nằm trên `origin/main`; đây là thay đổi giao diện/payload, không phải commit AI Scan.
- Lần kiểm tra triển khai ngày 26/11/2026, các endpoint Azure `/ready` và SSH không kết nối được. Chưa cập nhật hoặc xác nhận phiên bản Scan trên VM bằng handoff này.

## File FE liên quan

- `FrontEnd/smgs_web/src/components/artifacts/Artifact3DPanel.jsx`
- `FrontEnd/smgs_web/src/services/artifactScanApi.js`

