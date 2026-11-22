# Tối ưu Scan CPU — chuẩn bị cục bộ ngày 22/11/2026

Trạng thái: chưa triển khai, chưa benchmark trên Azure. VM đang được người dùng
tắt; không tự bật VM, không chạy lại job đang có và không đổi cấu hình job cũ.

## Thay đổi

| Tùy chọn `quality` | Tính độ sâu | Tinh chỉnh mesh | Texture tối đa |
| --- | --- | --- | --- |
| `detailed` | resolution-level 0, min-resolution 640; giữ mức cũ | Có | 4096 |
| `balanced` | resolution-level 1, min-resolution 320 | Có | 4096 |
| `preview` | resolution-level 2, min-resolution 256 | Bỏ RefineMesh | 2048 |

Web và yêu cầu dataset mới mặc định `balanced`. Config đã lưu thiếu `quality`
vẫn chạy `detailed`. CLI cũ giữ mặc định `detailed`, có thể truyền
`--quality balanced` hoặc `--quality preview`. Thông số min-resolution được
truyền cùng resolution-level, tránh ngưỡng mặc định 640 chặn việc giảm ảnh.
Chế độ nhẹ hơn có thể làm mất chi tiết hình học nhỏ. Không giảm số ảnh đầu vào,
không tắt kiểm tra mesh/texture, không dùng sparse points thay mesh.

`captureOrder=unordered` là mặc định trên Web/BE (`capture_order` ở AI).
Chỉ bật `ordered` khi tên file theo đúng thứ tự chụp vòng quanh hiện vật.
FE sắp tên theo thứ tự số tự nhiên trước upload. Với 180 ảnh, bộ chọn tạo
3.330 cặp ứng viên thay vì 16.110 cặp đầy đủ, gồm ảnh lân cận, đóng vòng và
các mốc trải đều để nối các vòng chụp. Tất cả ảnh vẫn tham gia.
Không suy ra tỷ lệ giảm thời gian từ tỷ lệ giảm số cặp.

COLMAP vẫn xác minh hình học của các cặp. Nếu khớp/mapping nhanh lỗi hoặc
đăng ký dưới 80% ảnh, thử exhaustive matching với feature database đã có và
mapping trong thư mục mới. Nếu vẫn không đủ, trả FAILED như trước.
Dataset benchmark giữ luồng camera priors đã kiểm định, không thay bằng
luồng khớp ảnh chụp có thứ tự.

Mỗi job lưu `performance.json` ghi preset, cách matching, số cặp và fallback;
log command ghi `ELAPSED_SECONDS` để đo từng bước ở lượt benchmark tới.
Thông số chất lượng cũng được lưu trong metadata job và provenance.

## Áp dụng khi người dùng bật Azure trở lại

1. Xác nhận không có job QUEUED/PROCESSING/FINALIZING và không còn tiến trình
   COLMAP/OpenMVS đang chạy. Không restart worker đang xử lý job.
2. Triển khai phần `3D Scan/app` và `3D Scan/tools`, rebuild/recreate riêng
   `scan` và `scan-status` trong Compose project hiện có. Giữ nguyên env,
   keys, volumes và dữ liệu job; không dùng `down -v`.
3. BE cần deploy `SMGS.API/Controllers/ArtifactScanController.cs` mới.
   Multipart nhận `quality`, `captureOrder`; chuyển sang AI thành
   `quality`, `capture_order`. Không cần key, quyền DB hoặc migration mới.
4. Sau AI và BE mới deploy FE gồm `Artifact3DPanel.jsx`, `artifactScanApi.js`.
   BE/AI cũ có thể bỏ qua các trường mới nên không được tuyên bố preset đã áp
   dụng nếu chỉ redeploy FE.
5. Đo một job mới bằng bộ ảnh cũ, cùng VM/ảnh/thứ tự để so sánh. Kiểm tra
   ảnh đăng ký, dense points, hình dạng, chi tiết hoa văn, texture và hướng.
   Thử `balanced` trước; `ordered` chỉ khi biết thứ tự ảnh chính xác.
   Không hứa mức 15–20 phút trước khi có kết quả đo.

## Hướng mô hình

Pipeline cũng có bản sửa hướng GLB dựa trên hướng lên trung bình của camera,
chỉ thêm rotation vào scene, giữ nguyên mesh/UV/texture bytes. Từ chối tự chỉnh
khi camera không thống nhất hoặc exporter có transform không rõ ràng.
File đã kiểm tra cục bộ:
`D:\SEP409\tmp\scan-orientation-20261121\upright.glb`.
Chưa thay file trên Azure hoặc bản asset BE đã lưu. Các mảnh mesh rời vẫn
được giữ nguyên; sửa hướng không phải sửa chất lượng tái dựng.

## Kiểm thử cục bộ

- AI: `python -m unittest discover -s tests -v` từ `3D Scan` (virtualenv AI).
- FE: `node --test tests/artifactScan.test.js`, `npm run build` từ `FrontEnd/smgs_web`.
- BE: `dotnet run --project tests/SMGS.MediaChecks --no-restore`.
- Fixture UI: `/tests/scanProgress.html?mode=upload` trên Vite cục bộ;
  toàn bộ API giả, không gửi job thật. Fixture không nằm trong entry build production.
