# Xưởng nội dung AI local — cập nhật 09/11/2026

Đã thay phần sinh thuyết minh/quiz mô phỏng trong portal bằng API BE gọi Qwen2.5-1.5B-Instruct INT4 qua ONNX Runtime CPU. Đây là bản nháp tiếng Việt phục vụ người biên soạn; chưa xác nhận hệ thống production end-to-end.

**Cập nhật nghe trong hệ thống cùng ngày:** đã thêm nút **Tạo giọng đọc** và audio player ngay trong Xưởng AI, FE gọi BE theo hiện vật và JWT để phát văn bản đang chỉnh sửa. Xem [luồng sử dụng và kiểm tra hệ thống](AI_STUDIO_PLAYBACK_2026_11_09.md). Các file WAV của lượt kiểm thử riêng trước đó chỉ để đối chiếu.

## Nhận diện ảnh và soạn nội dung là hai bước

- Visitor chụp ảnh: CLIP so khớp ảnh với hồ sơ tham chiếu, trả ứng viên `artifactId`. Sau khi xác định hiện vật, ứng dụng lấy nội dung đã xuất bản của đúng hồ sơ. Điểm thấp/hiện vật giống nhau cần người dùng chọn hoặc quét QR.
- Museum Staff đã chọn hiện vật trong kho: biết sẵn ID, không cần nhận diện lại. BE lấy tên thật và tư liệu tiếng Việt đã xuất bản; nhân viên có thể nhập thêm thông tin bảng tên/tài liệu đã kiểm chứng.
- Qwen hiện tại chỉ nhận **chữ**. Ảnh trên Xưởng AI dùng để đối chiếu, không được truyền vào model, chưa có OCR hoặc model thị giác sinh nội dung. Chưa có tìm kiếm Internet tự động.
- Ảnh vật thể không xác minh được tên riêng, niên đại, xuất xứ hay lịch sử sử dụng. Nếu chưa có tư liệu thì cần bổ sung nguồn; không suy diễn lịch sử từ hình dáng.
- Có model ONNX nhận cả ảnh và chữ, ví dụ [Phi-3.5 Vision của Microsoft](https://huggingface.co/microsoft/Phi-3.5-vision-instruct-onnx). Chưa tích hợp hoặc benchmark model đó trong SMGS. VLM có thể hỗ trợ đọc nhãn/mô tả ảnh, vẫn cần hồ sơ bảo tàng và kiểm duyệt.

## Luồng đã nối

1. Admin hoặc Museum Staff mở **Xưởng nội dung AI**. Admin chọn bảo tàng; Museum Staff làm việc trong phạm vi được phân công.
2. Chọn hiện vật đã lưu và nhập **Tư liệu nguồn bổ sung** nếu cần. BE ghép mô tả/narration tiếng Việt đã xuất bản với tư liệu nhập thêm, tổng tối thiểu 20 ký tự. Tên hiện vật đơn thuần không được xem là nguồn lịch sử.
3. Chọn thuyết minh hoặc quiz. Model tạo JSON có đoạn trích nguồn; lỗi/bận/thiếu nguồn được hiển thị, không thay bằng nội dung demo.
4. Nhân viên kiểm tra và sửa bản nháp. Thuyết minh gửi cả `description` và `narrationText` qua luồng đệ trình hiện có, `isAiGenerated=true`, tiếng Việt. Quiz chuyển sang Ngân hàng câu hỏi để chỉnh sửa/lưu từng câu, rồi theo luồng duyệt/xuất bản hiện có.
5. Chỉ bấm sinh không ghi DB, không tự phê duyệt/xuất bản. Curator tiếp tục thẩm định trong cùng portal. Tạo văn bản chưa tạo audio; TTS là bước riêng.

Ngân hàng câu hỏi có nút **AI gợi ý câu hỏi** mở đúng hiện vật/chế độ quiz. Số câu mặc định 1; tùy chọn 3/5 tạo tuần tự, gửi câu đã tạo để hạn chế trùng. Nếu một câu lỗi, giữ các câu thành công để kiểm tra. Chưa đánh giá độ đa dạng/chất lượng bộ nhiều câu trên dữ liệu thật.

## Hợp đồng và quyền

- Browser → BE: `POST /api/artifacts/{artifactId}/ai/drafts`, JWT, role `Admin` hoặc `Museum Staff`; Visitor, Curator, System Staff không có quyền gọi endpoint sinh này.
- BE kiểm tra hiện vật/bảo tàng đang hoạt động, phân công Museum Staff và đọc nguồn trước khi gọi model. Admin có phạm vi toàn hệ thống. Tên hiện vật lấy từ DB, không tin tên/role do client gửi.
- Request: `mode` (`narration`/`quiz`), `sourceText` tối đa 6000 ký tự, `audience`, `tone`, `difficulty`, `excludeQuestions` tối đa 5. Tổng nguồn tối đa 12000 ký tự, còn chịu giới hạn token của model.
- Response: `artifactId`, `mode`, `languageCode: vi`, `isDraft: true`, `source` (ID/phiên bản đã xuất bản nếu có và toàn bộ văn bản thực sự dùng), `draft`.
- BE → AI: `POST /api/v1/studio/drafts`, `X-Service-Key`, cùng dịch vụ port 8003 với chatbot. Chỉ BE giữ key, không thêm key model vào FE.
- JSON có cấu trúc/độ dài hợp lệ, đoạn trích phải tồn tại trong nguồn, con số phải có căn cứ. Quiz cần đúng một phương án xuất hiện trong nguồn; hệ thống xác định chỉ số đáp án từ nguồn rồi hỏi model trích xuất kiểm tra lại câu hỏi. Không khớp thì từ chối. Các guard này chưa chứng minh mọi câu hỏi/diễn giải đều đúng ngữ nghĩa.

## Chạy local

Đã có model/chat environment thì dùng lại, không tải lại model hoặc tạo DB mới. Nếu process đang chạy bản cũ, dừng và khởi động lại để nạp route mới.

Terminal AI:

```powershell
cd D:\SEP409\AI-System
.\tools\start-local-chat.ps1
```

Terminal BE (cần DB/JWT/tài khoản được cấu hình sẵn):

```powershell
cd D:\SEP409\BackEnd\Smart_Museum_Guide_System
.\tools\start-api-with-local-chat.ps1
```

Terminal web:

```powershell
cd D:\SEP409\FrontEnd\smgs_web
npm run dev -- --host 127.0.0.1 --port 8090
```

`GET http://127.0.0.1:8003/ready` phải trả 200. Hướng dẫn cài model/environment ban đầu ở [AI Chat/README.md](AI%20Chat/README.md). BE dùng chung `ArtifactGuide__Enabled`, `ArtifactGuide__BaseUrl`, `ArtifactGuide__ServiceKey` với chatbot. Không sửa schema DB trong cập nhật này.

## Hiệu năng và deploy

- Chung một model/khóa inference với chatbot. Một yêu cầu tại một thời điểm; chờ 0,5 giây rồi trả 503 khi bận. Không có hàng đợi bền vững hoặc streaming; 5 người dùng đồng thời có thể phải thử lại.
- Context 2048 token, đầu ra tối đa 512 token/bản nháp. Nguồn quá dài trả 422, không âm thầm cắt. Thuyết minh có deadline 90 giây; quiz tối đa 65 giây sinh và phần còn lại trong budget 90 giây để kiểm tra đáp án.
- BE timeout 105 giây, FE 115 giây cho từng yêu cầu. Gateway/reverse proxy khi deploy cần timeout phù hợp; client hủy không dừng ngay native inference.
- Model/cache và khóa nội bộ được gitignore. Server AWS phải có model/tokenizer trên disk/volume và đủ RAM thực tế; kiểm tra tải trên máy deploy. Không chạy model trong Vercel FE. Một worker tránh tải trùng model. Chưa cung cấp Docker/benchmark AWS cho Xưởng AI.

## Kiểm thử và giới hạn bằng chứng

- Python: 16 unit test pass (chat + studio), dùng fixture để kiểm tra JSON, nguồn, số, trùng câu, đáp án và khóa inference.
- BE: bộ kiểm tra guide/provider/HTTP và kiểm tra staff source/scope/draft pass; không đọc/ghi DB nghiệp vụ, không gọi model trong bộ BE fixture.
- FE: 28 test pass, 1 skip; 16 browser test pass ở lượt toàn bộ. Ba test liên quan Studio chạy lại sau cập nhật cuối đều pass. Browser dùng BE fixture, gồm quyền hiển thị, sinh/gửi narration, bàn giao quiz và không bịa nội dung khi model lỗi. Build production và lint pass; còn cảnh báo bundle lớn và lint warnings sẵn có của portal.
- Model/API Python ASGI chạy ONNX thật trên CPU: narration máy nén khí **23,83 giây**, quiz máy nén khí **41,70 giây**; quiz van dầu **bị từ chối 502 sau 35,21 giây** do kiểm tra câu hỏi/đáp án không khớp nguồn. Không coi ca bị chặn là sinh quiz thành công.
- Giữ đầu ra lỗi ban đầu và kết quả thật tại [báo cáo model](evaluations/studio-2026-11-09/README.md). Nhãn/quan sát ảnh người dùng trong bộ thử là fixture, chưa phải hồ sơ bảo tàng được duyệt.
- Chưa test browser → BE → DB thật → model → lưu → Curator → publish trên cùng môi trường. Chưa deploy/push trong lần cập nhật này. Chưa đánh giá diện rộng tiếng Việt, chất lượng nội dung dài hoặc các hiện vật ít tư liệu.

Lệnh kiểm tra lại:

```powershell
cd 'D:\SEP409\AI-System\AI Chat'
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd D:\SEP409\AI-System
.\.venv\Scripts\python.exe tools/evaluate_staff_studio.py
cd D:\SEP409\BackEnd\Smart_Museum_Guide_System
dotnet run --project tests/SMGS.GuideChecks
cd D:\SEP409\FrontEnd\smgs_web
npm test
npm run test:e2e
npm run build
```
