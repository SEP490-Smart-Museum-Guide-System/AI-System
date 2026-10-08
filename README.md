# AI System — Smart Museum Guide System

Tài liệu định hướng cho hai luồng xử lý liên quan đến hiện vật bảo tàng. Repo này hiện là điểm khởi đầu; các thành phần bên dưới là **đề xuất triển khai**, chưa phải tính năng đã hoàn thành.

## Mục tiêu và nguyên tắc

| Luồng | AI làm gì? | Đầu ra |
| --- | --- | --- |
| Dựng 3D | Hỗ trợ tái dựng mô hình từ ảnh chụp nhiều góc bằng iPhone | Mô hình 3D để xem trên web/app sau khi được duyệt |
| Nhận diện và thuyết minh | Nhận diện hiện vật trong ảnh camera, trả về `artifactId` | Ứng dụng lấy đúng bản thuyết minh do con người kiểm duyệt và phát cho khách nghe |

**AI không tự viết nội dung thuyết minh cho khách tham quan.** Nội dung, tên gọi và thông tin lịch sử do người phụ trách biên soạn, kiểm duyệt và xuất bản. Việc đọc có thể dùng file audio thu sẵn, file tạo bằng text-to-speech (TTS) từ bản đã duyệt, hoặc TTS trên thiết bị. AI nhận diện chỉ tìm đúng bản ghi.

Hai luồng dùng chung `artifactId`. Một hiện vật có thể có ảnh, mã QR, nội dung thuyết minh, audio và mô hình 3D; thiếu mô hình 3D không làm gián đoạn chức năng thuyết minh.

## Luồng 1: Dựng mô hình 3D

1. Người quản lý chọn hiện vật và chụp nhiều ảnh quanh hiện vật bằng iPhone, ở các góc và độ cao khác nhau.
2. Công cụ quét ảnh dựng mô hình. Bản thử nghiệm có thể dùng ứng dụng photogrammetry trên điện thoại để tránh vận hành GPU server.
3. Người phụ trách kiểm tra hình dạng, hoa văn, màu sắc; sửa hoặc chụp lại nếu có phần bị sai hay thiếu. Chỉ xuất bản mô hình sau khi duyệt.
4. Tối ưu dung lượng và lưu bản dùng cho web/app ở định dạng GLB; gắn `modelUrl` với `artifactId`.

Mô hình sinh từ ảnh đơn hoặc những góc chưa được chụp có thể chứa chi tiết suy đoán. Với hiện vật cần độ trung thực cao, ưu tiên ảnh nhiều góc và ghi rõ tình trạng kiểm chứng của mô hình.

## Luồng 2: Nhận diện hiện vật và đọc thuyết minh

```text
Camera iPhone → nhận diện → artifactId → bản ghi đã xuất bản
                                      → nội dung đã kiểm duyệt → audio/TTS → khách nghe
```

- **Bản đầu tiên:** quét QR trên nhãn hiện vật để lấy `artifactId`, sau đó phát bản thuyết minh tương ứng. Đây là đường dự phòng đáng tin cậy ngay cả khi nhận diện ảnh chưa tốt.
- **Bản có AI:** huấn luyện mô hình nhận diện gọn cho tập hiện vật của bảo tàng, chạy trên thiết bị nếu phù hợp. Chụp ảnh mẫu ở điều kiện trưng bày thật: nhiều góc, ánh sáng và phản chiếu tủ kính.
- Khi điểm tin cậy thấp hoặc có nhiều hiện vật giống nhau, hiển thị các kết quả để khách chọn hoặc yêu cầu quét QR. Không tự phát thuyết minh khi chưa xác định chắc hiện vật.
- Chỉ lấy nội dung có trạng thái **đã duyệt/đã xuất bản**. Nếu chưa có bản đọc, hiển thị thông báo tương ứng; không để AI tự điền nội dung.

## Phân chia trách nhiệm

| Thành phần | Trách nhiệm |
| --- | --- |
| Ứng dụng iPhone/web | Chụp hoặc quét QR, hiển thị ứng viên nhận diện, phát audio/TTS, xem mô hình 3D |
| AI System | Xử lý/tích hợp quy trình dựng 3D; cung cấp mô hình nhận diện và kết quả `artifactId` kèm độ tin cậy |
| Hệ thống quản lý hiện vật | Lưu hồ sơ, nội dung đã duyệt, `qrCode`, `audioUrl`, `modelUrl` và trạng thái xuất bản |
| Người phụ trách bảo tàng | Duyệt bản thuyết minh, audio và mô hình 3D |

Frontend hiện có dữ liệu mẫu với `qrCode`, `modelUrl` và `audioUrl` trong `FrontEnd/smgs_web/src/data/mockData.js`; đây là điểm nối dự kiến, chưa chứng minh đã có API hoặc pipeline AI hoạt động.

## Lộ trình đề xuất theo chi phí thấp

1. **MVP:** chọn 3–5 hiện vật; tạo QR và bản thuyết minh đã duyệt; dùng audio thu sẵn hoặc TTS từ đúng văn bản đó. Quét QR để nghe.
2. **3D:** dùng iPhone chụp, dựng và duyệt một mô hình mẫu; tối ưu GLB, gắn vào hồ sơ hiện vật.
3. **Nhận diện ảnh:** thu ảnh mẫu tại bảo tàng, đánh giá độ chính xác trên ảnh chưa dùng để huấn luyện; thêm xác nhận của khách và đường dự phòng QR.
4. **Mở rộng:** chỉ cân nhắc tự vận hành pipeline 3D hoặc dịch vụ TTS khi số lượng hiện vật và nhu cầu thực tế đủ lớn.

Mỗi hiện vật chỉ cần dựng 3D và tạo file audio khi tư liệu thay đổi. Khi khách tham quan, hệ thống chủ yếu tra cứu, tải và phát các tài nguyên đã xuất bản; không cần gọi dịch vụ AI tạo mới cho mỗi lượt.

## Việc cần chốt trước khi viết code

- Ứng dụng khách tham quan là web, iOS native hay cả hai? Điều này quyết định cách tích hợp model nhận diện và TTS trên thiết bị.
- Bộ ảnh hiện vật có sẵn bao nhiêu và bảo tàng có cho phép chụp nhiều góc không?
- Bản ghi nội dung thuyết minh đã duyệt nằm ở đâu, và ai có quyền đổi trạng thái xuất bản?
- Ngưỡng chấp nhận cho nhận diện: tỷ lệ nhận đúng, tỷ lệ phải xác nhận thủ công và thời gian phản hồi trên thiết bị thử nghiệm.
