# Kiểm thử CLIP thật với bộ ảnh người dùng — 08/11/2026

Model: `infinilabs/pizza-clip-base-v1@f71041903f3a04f7a883b90f0126eeb4ab44fa7c/clip-vit-base-patch32-vision.onnx`; CPU ONNX Runtime `1.23.2`.

**Encoder/model và API nhận diện là code thật. Chỉ thay persistence bằng kho RAM cô lập; không ghi DB/R2, không upload ảnh người dùng ra internet.**

Dùng 14 ảnh reference cho 14 hồ sơ nháp. Ngưỡng cố định similarity=0.72, margin=0.04; không chỉnh theo kết quả.

- Holdout cùng nhóm: top-1 đúng 4/4; tự chấp nhận đúng 3/4.
- Ảnh tương tự ngoài catalog: từ chối 4/5; tự nhận nhầm 1 trường hợp.
- Một nhóm ghép tạm được thử riêng, không tính vào metric chính.

| Ảnh | Nhóm test | Kỳ vọng | Gần nhất | Similarity | Margin | Tự nhận | Kết quả |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| A04 | Cùng nhóm, giữ riêng | PHOTO-003 | PHOTO-003 | 0.929 | 0.0102 | Không | Chưa đạt |
| A09 | Cùng nhóm, giữ riêng | PHOTO-006 | PHOTO-006 | 0.8986 | 0.0841 | Có | Đạt |
| A11 | Cùng nhóm, giữ riêng | PHOTO-007 | PHOTO-007 | 0.9266 | 0.0998 | Có | Đạt |
| A15 | Cùng nhóm, giữ riêng | PHOTO-009 | PHOTO-009 | 0.9286 | 0.0587 | Có | Đạt |
| B05 | Ghép tạm, thăm dò | PHOTO-012 | PHOTO-012 | 0.8328 | 0.0304 | Không | Chưa đạt |
| WEB-01 | Tương tự nhưng ngoài catalog | Không tự gán ID | PHOTO-003 | 0.7672 | 0.0095 | Không | Đạt |
| WEB-02 | Tương tự nhưng ngoài catalog | Không tự gán ID | PHOTO-003 | 0.8239 | 0.0264 | Không | Đạt |
| WEB-03 | Tương tự nhưng ngoài catalog | Không tự gán ID | PHOTO-011 | 0.765 | 0.0089 | Không | Đạt |
| WEB-04 | Tương tự nhưng ngoài catalog | Không tự gán ID | PHOTO-007 | 0.7718 | 0.0515 | Có | Chưa đạt |
| WEB-05 | Tương tự nhưng ngoài catalog | Không tự gán ID | PHOTO-007 | 0.7226 | 0.0323 | Không | Đạt |

## Cách hiểu kết quả

- Top-1 đúng nhóm và tự nhận đúng là hai chỉ số khác nhau: khi margin thấp, API có thể yêu cầu xác nhận dù gợi ý đứng đầu đúng.
- Ảnh web cùng kiểu đèn/cân/van không chứng minh là chính hiện vật trong bảo tàng. Tự gán ID trong các ca này được tính là false accept.
- Similarity không phải xác suất nhận đúng; tập này quá nhỏ và nhiều góc gần nhau để kết luận độ chính xác production.
- Những ảnh chỉ có một view chưa có holdout độc lập; không lấy ảnh reference làm query rồi tính thành accuracy.

- Ảnh van tay quay WEB-04 bị tự nhận nhầm thành PHOTO-007 (đồng hồ). Giữ nguyên ngưỡng đã đặt trước; không điều chỉnh ngưỡng để làm đẹp kết quả trên chính bộ test này.
- Kết quả này hỗ trợ làm UI gợi ý Top 3 và khách xác nhận, chưa đủ để tự khẳng định danh tính hiện vật ở production.

## Nguồn ảnh web

- [WEB-01 — Đèn Tung Woo NOT UNDER COMMAND ở một bộ sưu tập khác](https://lannangallery.com/products/solid-copper-ship-s-lantern-by-tung-woo-of-hong-kong): Lannan Gallery — ảnh sản phẩm do bên đăng cung cấp; Chưa xác nhận giấy phép tái phân phối; chỉ lưu cache kiểm thử local, không đưa vào bộ ảnh tham chiếu hoặc bản ZIP chia sẻ.
- [WEB-02 — Đèn Tung Woo PORT ở nguồn ngoài](https://lannangallery.com/products/polished-copper-ships-port-lantern-by-tung-woo): Lannan Gallery — ảnh sản phẩm do bên đăng cung cấp; Chưa xác nhận giấy phép tái phân phối; chỉ lưu cache kiểm thử local, không đưa vào bộ ảnh tham chiếu hoặc bản ZIP chia sẻ.
- [WEB-03 — Cân ở Bucharest Municipal Museum](https://commons.wikimedia.org/wiki/File:Bucharest_Municipal_Museum_-_balance_scale_and_other_objects.jpg): Joe Mabel; CC BY-SA 4.0 — https://creativecommons.org/licenses/by-sa/4.0/
- [WEB-04 — Van có tay quay ở nguồn ngoài](https://commons.wikimedia.org/wiki/File:A-globe-valve-handwheel.JPG): Heather Smith / The Alloy Valve Stockist; phiên bản Commons đã bỏ watermark; CC BY 3.0 — https://creativecommons.org/licenses/by/3.0/
- [WEB-05 — Máy nén piston ở nguồn ngoài](https://commons.wikimedia.org/wiki/File:Piston_compressor.jpg): Yanior; Public domain theo công bố của tác giả trên trang Commons

## Tái hiện

```powershell
cd D:\SEP409\AI-System
.\.venv\Scripts\python.exe tools/evaluate_user_photo_recognition.py
```

Cần model cache và ảnh web đã tải; nguồn/checksum trong external_downloads.json. Không tự index các ảnh này vào hệ thống thật.

Giới hạn: Chỉ 4 holdout cùng nhóm quan sát; chưa có ground truth định danh bảo tàng chính thức. B05/PHOTO-012 là nhóm ghép tạm, loại khỏi metric holdout chính. Ảnh ngoài được coi là ngoài catalog, không dùng làm reference hay đếm thành positive. Không dùng A12 trùng A05; không augment ảnh để tạo holdout giả. Model và inference thật; persistence tạm trong RAM, không kiểm thử PostgreSQL/gateway/deploy.
