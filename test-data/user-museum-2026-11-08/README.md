# Hồ sơ ảnh nhận diện bảo tàng

Tiếp nhận: 2026-11-08. Ngày chụp và bảo tàng: chưa xác nhận.

**27 ảnh · 26 file ảnh khác nhau · 14 hồ sơ nháp.**

Ảnh ứng viên tham chiếu: 19; ảnh bảng tên: 2; ảnh trùng: 1; ảnh nhiều đối tượng/bối cảnh chờ phân loại: 5.

A01–A16 là lượt gửi thứ nhất; B01–B11 là lượt bổ sung. Ảnh được giữ nguyên byte; SHA-256 nằm trong manifest. A12 trùng A05.

## Mở và đối chiếu

- Mở [index.html](index.html) bằng trình duyệt để xem toàn bộ hồ sơ và ảnh. Không cần BE, DB hay internet.
- [dataset.json](dataset.json): hồ sơ, đặc điểm nhận biết, nhóm ảnh, checksum và trạng thái.
- [catalog_mapping.csv](catalog_mapping.csv): điền mã bảo tàng/hiện vật thật và tên đã xác nhận. Không dùng số vị trí trên nhãn làm artifact_id.
- [image_manifest.csv](image_manifest.csv): đối chiếu toàn bộ 27 ảnh với nguồn, vai trò và ảnh trùng.
- [reference_queue.json](reference_queue.json): danh sách ứng viên; mặc định disabled, chưa gửi vào service.

## Danh sách hồ sơ

| Mã nháp | Tên mô tả | Ảnh hiện vật | Hồ sơ |
| --- | --- | --- | --- |
| PHOTO-001 | Hiện vật gốm loe rộng — vị trí nhãn 12 | A01 | [Xem](profiles/PHOTO-001/README.md) |
| PHOTO-002 | Vật đựng gốm miệng vỡ — vị trí nhãn 7 | A03 | [Xem](profiles/PHOTO-002/README.md) |
| PHOTO-003 | Đèn có chữ C564 | A04, A05 | [Xem](profiles/PHOTO-003/README.md) |
| PHOTO-004 | Đèn có chữ MASTHEAD | A06 | [Xem](profiles/PHOTO-004/README.md) |
| PHOTO-005 | Đèn có chữ PORT | A07 | [Xem](profiles/PHOTO-005/README.md) |
| PHOTO-006 | Đèn cầm tay có quai lớn và khung bảo vệ | A08, A09 | [Xem](profiles/PHOTO-006/README.md) |
| PHOTO-007 | Đồng hồ kiểm tra vận tốc máy turbin khi khởi động | A10, A11 | [Xem](profiles/PHOTO-007/README.md) |
| PHOTO-008 | Van mở dầu cung cấp cho lò hạ áp | A13 | [Xem](profiles/PHOTO-008/README.md) |
| PHOTO-009 | Máy nén khí 7,5 hp | A15, A16 | [Xem](profiles/PHOTO-009/README.md) |
| PHOTO-010 | Máy công nghiệp dạng đứng — tên tạm | B02 | [Xem](profiles/PHOTO-010/README.md) |
| PHOTO-011 | Cân hai đĩa và ngăn quả cân — tên mô tả | B03 | [Xem](profiles/PHOTO-011/README.md) |
| PHOTO-012 | Hiện vật dạng lòng chảo màu sẫm — vị trí nhãn 3 | B04, B05 | [Xem](profiles/PHOTO-012/README.md) |
| PHOTO-013 | Mâm đồng — theo bảng tên trong ảnh | B06 | [Xem](profiles/PHOTO-013/README.md) |
| PHOTO-014 | Tượng nhân vật ngồi mặc trang phục xanh — tên tạm | B10 | [Xem](profiles/PHOTO-014/README.md) |

## Các ảnh chờ xác định đối tượng

- A02: Ba hiện vật gốm trong cùng khung hình. Không gán cả ba vật thành một hiện vật. Cần xác định từng vật trước khi chuẩn bị ảnh tham chiếu riêng.
- B07: Hai bộ trang phục trên hai ma-nơ-canh, một bộ màu đỏ và một bộ màu sáng. Chưa rõ bảo tàng quản lý như một bộ trưng bày hay hai hiện vật; không tự gán một artifactId cho cả ảnh.
- B08: Hai bộ trang phục màu sẫm và hồng trên hai ma-nơ-canh. Chờ xác định từng hiện vật hoặc mã bộ sưu tập trước khi chuẩn bị ảnh tham chiếu.
- B09: Toàn cảnh phòng với bàn ghế, khu thờ và trang phục. Ảnh bối cảnh trưng bày, chưa phải ảnh tham chiếu của một hiện vật cụ thể.
- B11: Toàn cảnh tủ trưng bày khu thờ và nhiều đồ vật. Không gán chung bình, lư, chân đèn và các vật khác thành một hiện vật.

## Phạm vi dữ liệu

- Tên mô tả tạm, chữ nhìn thấy và nội dung bảng tên được tách riêng khỏi thông tin chính thức.
- Không tự thêm niên đại, xuất xứ, nhân vật, danh tính tượng hay thông số kỹ thuật. Lời chép trên bảng chưa được xác minh độc lập.
- Nhóm B04/B05 và bảng tên B01 cần xác nhận cách ghép với hiện vật tương ứng.
- Chưa train, chạy inference, tạo embedding, index, tạo bản ghi hiện vật hoặc ghi DB/R2.
- Chưa chia tập đánh giá; ảnh trùng/góc gần giống không được coi là bằng chứng chất lượng nhận diện.
- Giấy phép công khai chưa xác nhận; bộ này phục vụ chuẩn bị dự án theo yêu cầu người gửi.

Nguồn phân loại thủ công: [intake.json](intake.json). Công cụ dựng hồ sơ: tools/prepare_recognition_dossiers.py.
