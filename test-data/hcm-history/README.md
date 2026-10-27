# Multi-artifact AI Vision test set

Dữ liệu thử lấy từ ảnh hiện vật tại Bảo tàng Lịch sử TP.HCM, Wikimedia Commons. Các file đã tải về ở kích thước thumbnail 960px; ảnh gốc và giấy phép xem qua từng liên kết trong `manifest.csv`.

## Cấu hình test

- Model: `infinilabs/pizza-clip-base-v1` chạy ONNX Runtime; **không fine-tune/train lại**.
- Mỗi artifact có 2 ảnh để index và 1 ảnh holdout không đưa vào embeddings.
- PostgreSQL dùng chung DB Backend. Bản ghi museum test ID `2`; các artifact test IDs `1`–`3` có code `AI-TEST-*`.
- Embeddings được lưu ở schema `ai_vision`; ảnh vẫn là file trong thư mục này.

| Artifact ID | Nhãn test | Reference | Holdout | Similarity | Margin | Kết quả |
|---:|---|---|---|---:|---:|---|
| 1 | Trống đồng Đông Sơn khoảng năm 500 | 2 | `bronze-drum-500ad/Bronze_drum,_c._500_AD_(9980411594).jpg` | 0.9133 | 0.1040 | Đúng ID |
| 2 | Ấm đồng triều Lê thế kỷ 18 | 2 | `kettle-le18c/Kettle_DSC06003.jpg` | 0.9358 | 0.2032 | Đúng ID |
| 3 | Chuông đồng văn hóa Đông Sơn | 2 | `dong-son-bell/Dong_Son_Bell_03.jpg` | 0.9227 | 0.1370 | Đúng ID |

Các kết quả cho thấy ba holdout được xếp đúng trong tập nhỏ này. Đây **chưa phải benchmark đại diện**: chỉ có 3 lớp, ảnh Commons chụp trong điều kiện khác với camera khách, và các holdout đến từ cùng các bộ ảnh nhiều góc. Cần thêm ảnh điện thoại tự chụp, ánh sáng/tủ kính khác nhau, vật thể gây nhầm, và nhiều mẫu cho mỗi hiện vật trước khi đặt ngưỡng production.

## Nguồn và giấy phép

Xem `manifest.csv` để biết creator, URL, license và vai trò từng file. Trống đồng và ấm đồng do Daderot/Gary Todd phát hành CC0; chuông đồng do HappyMidnight phát hành CC BY-SA 3.0 nên giữ attribution/license trong manifest khi tái phân phối.

## Download

`download_commons_extra.py` tải bộ ấm đồng và chuông đồng qua Wikimedia Commons. Chạy trong container AI Vision để dùng mạng Docker nếu DNS/network của Windows shell bị giới hạn. Script chờ giữa các request và retry HTTP 429.
