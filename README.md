# AI System — Smart Museum Guide System

Repo chứa các microservice AI cho Smart Museum Guide System. TTS và nhận diện ảnh hiện vật có MVP độc lập trong [`TTS AI/`](TTS%20AI/README.md) và [`AI Vision/`](AI%20Vision/README.md). Dựng 3D là luồng riêng chưa triển khai.

## Mục tiêu và nguyên tắc

| Microservice | Trách nhiệm | Trạng thái |
| --- | --- | --- |
| TTS | Nhận văn bản đã duyệt, tổng hợp giọng tiếng Việt bằng Piper/sherpa-onnx và trả audio | MVP trong [`TTS AI/README.md`](TTS%20AI/README.md) |
| Nhận diện hiện vật | So khớp ảnh với ảnh tham chiếu, trả `artifactId`, similarity và ứng viên | MVP trong [`AI Vision/README.md`](AI%20Vision/README.md) |
| Dựng 3D | Hỗ trợ tạo mô hình từ bộ ảnh chụp nhiều góc bằng iPhone | Chưa triển khai |

**AI không tự viết nội dung thuyết minh cho khách tham quan.** Nội dung, tên gọi và thông tin lịch sử do người phụ trách biên soạn, kiểm duyệt và xuất bản. TTS microservice chỉ biến văn bản được ứng dụng gửi vào thành audio; service không nhận diện hiện vật và không truy cập database nội dung.

Các service dùng chung `artifactId`. Một hiện vật có thể có ảnh, mã QR, nội dung thuyết minh, audio và mô hình 3D; thiếu mô hình 3D không làm gián đoạn chức năng thuyết minh.

## Luồng 1: Dựng mô hình 3D

1. Người quản lý chọn hiện vật và chụp nhiều ảnh quanh hiện vật bằng iPhone, ở các góc và độ cao khác nhau.
2. Công cụ quét ảnh dựng mô hình. Bản thử nghiệm có thể dùng ứng dụng photogrammetry trên điện thoại để tránh vận hành GPU server.
3. Người phụ trách kiểm tra hình dạng, hoa văn, màu sắc; sửa hoặc chụp lại nếu có phần bị sai hay thiếu. Chỉ xuất bản mô hình sau khi duyệt.
4. Tối ưu dung lượng và lưu bản dùng cho web/app ở định dạng GLB; gắn `modelUrl` với `artifactId`.

Mô hình sinh từ ảnh đơn hoặc những góc chưa được chụp có thể chứa chi tiết suy đoán. Với hiện vật cần độ trung thực cao, ưu tiên ảnh nhiều góc và ghi rõ tình trạng kiểm chứng của mô hình.

## Luồng nhận diện hiện vật

```text
Camera iPhone → nhận diện → artifactId → bản ghi đã xuất bản
                                      → nội dung đã kiểm duyệt → audio/TTS → khách nghe
```

- Quét QR trên nhãn hiện vật để lấy `artifactId`; ứng dụng lấy nội dung đã xuất bản từ Content/Catalog Service.
- AI Vision so khớp ảnh camera với embedding tạo từ ảnh tham chiếu, dự đoán `artifactId` cùng similarity và các ứng viên. Chụp/index ảnh mẫu ở điều kiện trưng bày thật: nhiều góc, ánh sáng và phản chiếu tủ kính.
- Khi điểm tin cậy thấp hoặc có nhiều hiện vật giống nhau, hiển thị các kết quả để khách chọn hoặc yêu cầu quét QR. Không tự phát thuyết minh khi chưa xác định chắc hiện vật.
- Chỉ Content/Catalog Service trả nội dung có trạng thái **đã duyệt/đã xuất bản**. Nếu chưa có bản đọc, hiển thị thông báo tương ứng.

## Luồng TTS đã triển khai

```text
Flutter → Content/Catalog Service: lấy văn bản published theo artifactId
Flutter → TTS Service: POST văn bản đã duyệt
TTS Service → Flutter: audio/wav (Piper tổng hợp hoặc cache trả lại)
```

Theo schema DBML, Content/Catalog Service tra `artifacts.qr_code`, rồi lấy `narration_versions.script` qua `narrations`; chỉ chọn version `published` và `is_current = true`, theo language/length/detail mà app yêu cầu. TTS Service không truy cập database BE. Xem mapping/query và endpoint trong [`TTS AI/README.md`](TTS%20AI/README.md). Thay đổi và việc còn lại được ghi trong [`IMPLEMENTATION_LOG.md`](IMPLEMENTATION_LOG.md).

## Phân chia trách nhiệm

| Thành phần | Trách nhiệm |
| --- | --- |
| Ứng dụng Flutter | Quét QR, lấy nội dung đã xuất bản, gửi văn bản đến TTS Service và phát audio |
| TTS Service | Chạy Piper/sherpa-onnx, cache kết quả audio, trả WAV |
| AI Vision Service | So khớp ảnh và trả `artifactId`/ứng viên; không truy cập DB nghiệp vụ |
| Hệ thống quản lý hiện vật | Lưu hồ sơ, nội dung đã duyệt, `qrCode`, `audioUrl`, `modelUrl` và trạng thái xuất bản |
| Người phụ trách bảo tàng | Duyệt bản thuyết minh, audio và mô hình 3D |

Frontend hiện có dữ liệu mẫu với `qrCode`, `modelUrl` và `audioUrl` trong `FrontEnd/smgs_web/src/data/mockData.js`; đây là điểm nối dự kiến, chưa chứng minh đã có API hoặc pipeline AI hoạt động.

## Lộ trình tiếp theo

1. Nối Flutter với Content/Catalog API để lấy văn bản đã duyệt theo `artifactId`, rồi gọi TTS Service.
2. Chọn voice Piper sau khi nghe thử với tên riêng, niên đại và thuật ngữ trong bộ sưu tập thật.
3. Dùng iPhone chụp, dựng và duyệt một mô hình 3D; tối ưu GLB và gắn vào hồ sơ hiện vật.
4. Index ảnh tham chiếu tại bảo tàng, đánh giá độ chính xác AI Vision trên ảnh chưa dùng làm tham chiếu.

Audio TTS được cache theo văn bản, voice và tốc độ đọc. Khi nội dung được sửa, hash thay đổi và audio mới được tạo ở lượt gọi kế tiếp.

## Việc cần chốt trước khi nối production

- Địa chỉ Content/Catalog API và định dạng response khi trả nội dung đã duyệt.
- Cách xác thực service-to-service giữa Flutter/API Gateway và TTS Service trong môi trường triển khai.
- Bộ ảnh hiện vật có sẵn bao nhiêu và bảo tàng có cho phép chụp nhiều góc không?
- Ngưỡng chấp nhận cho nhận diện: tỷ lệ nhận đúng, tỷ lệ phải xác nhận thủ công và thời gian phản hồi trên thiết bị thử nghiệm.
