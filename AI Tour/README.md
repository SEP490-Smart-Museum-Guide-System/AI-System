# Gợi ý hành trình cá nhân — tùy chọn của Visitor

Khách có thể chọn tour đã xuất bản, tham quan tự do hoặc yêu cầu một hành trình riêng theo sở thích và thời gian. Gợi ý cá nhân không tạo giao dịch, không thay vé vào cửa, không xác minh hay thay đổi tour khách mua bên ngoài.

## Cách hoạt động

BE chọn hiện vật đang hoạt động, có nội dung tiếng Việt hiện hành đã xuất bản và khách được phép đọc. Chỉ các ứng viên đó được gửi sang service này. Bộ gợi ý dùng **TF-IDF/cosine, chủ đề và nhóm từ tiếng Việt**, rồi chọn điểm phù hợp quỹ thời gian, ưu tiên hạn chế đổi phòng/tầng. Đây là bộ gợi ý dựa trên nội dung, **không dùng LLM/ONNX, không tải model và không tự sáng tác lịch sử**.

BE kiểm tra lại ID, phiên bản nội dung, thời lượng và quyền truy cập. Bản xem trước giữ trong bộ nhớ 15 phút, mỗi khách một bản. Chỉ khi khách bấm lưu/bắt đầu, BE mới lưu hành trình riêng vào PostgreSQL. Danh sách điểm đã lưu giữ nguyên; nội dung hiện vật hiển thị theo bản xuất bản hiện hành. Nếu nội dung/quyền không còn hợp lệ, việc bắt đầu bị từ chối và đề nghị tạo lại.

Thời gian: 2 phút chuẩn bị điểm đầu; 0,5 phút khi cùng phòng; 2 phút khi đổi phòng hoặc chưa rõ tầng; 4 phút khi đổi tầng. Thời gian xem/nghe do BE ước tính theo độ dài nội dung. **Không phải khoảng cách đo thực tế, GPS trong nhà hoặc thuật toán tìm đường ngắn nhất.** Thứ tự điểm cá nhân không tự thêm node trên bản đồ; điều hướng chỉ có khi bảo tàng đã cấu hình bản đồ và các vị trí liên quan.

Không khớp sở thích: trả kết quả thay thế có nhãn rõ ràng. Thời gian không đủ: có thể trả 0 điểm, không được lưu. Service ngừng hoạt động: BE báo lỗi; tour có sẵn và tham quan tự do vẫn độc lập.

## Chạy

Từ repo AI-System, chạy cả 5 dịch vụ bằng Docker:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\start-ai.ps1
```

Hoặc chạy riêng local, không cần Docker/GPU:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r '.\AI Tour\requirements.txt'
powershell -ExecutionPolicy Bypass -File .\tools\start-local-tour.ps1
```

Launcher tạo `state/tour-service-key.txt` (Git ignored), không in khóa ra log. Dùng cùng giá trị làm `PersonalizedTours__ServiceKey` ở BE; `PersonalizedTours__BaseUrl=http://127.0.0.1:8004/`. Nếu BE và service cùng Docker network, dùng `http://tour:8004/`. Không đưa khóa vào Flutter/Vite, không mở trực tiếp port nội bộ ra Internet.

## API nội bộ

| API | Yêu cầu |
| --- | --- |
| `GET /ready`, `GET /live` | Cấu hình khóa nội bộ hợp lệ; không trả khóa |
| `POST /api/v1/tours/recommend` | Header `X-Service-Key`; ứng viên đã được BE lọc |

Giới hạn: 1–500 ứng viên, 1–8 sở thích, 5–240 phút, tối đa 30 điểm; body tối đa 2 MB. BE gọi với timeout 12 giây. Đây là cấu hình MVP cho bộ sưu tập nhỏ, chưa benchmark tải AWS.

## Kiểm thử

Từ thư mục `AI Tour`:

```powershell
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

9 ca kiểm thử thuật toán/API, bao gồm sở thích làm đổi tuyến, ngân sách thời gian, fallback, trùng/sai bảo tàng và khóa nội bộ. Kiểm thử xuyên BE/AI/DB và hướng dẫn UI xem [nhật ký triển khai](../../BackEnd/project-docs/PERSONALIZED_TOURS_2026_11_11.md).
