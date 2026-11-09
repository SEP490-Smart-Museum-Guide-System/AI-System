# Chatbot hiện vật chạy local bằng ONNX Runtime

Model: `onnx-community/Qwen2.5-1.5B-Instruct`, revision `d54957e3af1be04546436e874a60fe386041b244`, graph `onnx/model_q4.onnx` (~1,79 GB). ONNX Runtime CPU 1.23.2 và tokenizer 0.22.1; không cần PyTorch, Gemini hoặc API key nhà cung cấp cloud. Model gốc: [Qwen/Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct); bản ONNX: [onnx-community](https://huggingface.co/onnx-community/Qwen2.5-1.5B-Instruct).

Đây là **model văn bản riêng**, khác CLIP nhận diện ảnh. Model chạy trên máy/server chứa AI-System; Flutter/Vercel gọi BE, BE kiểm tra JWT/premium/published rồi gọi AI Chat qua khóa nội bộ. Không chạy trực tiếp model 1,79 GB trong Vercel hoặc trình duyệt.

**09/11/2026:** cùng process/model có thêm `POST /api/v1/studio/drafts` cho Admin/Museum Staff thông qua BE. Soạn thuyết minh/quiz tiếng Việt từ nguồn, kiểm tra JSON/đoạn trích/đáp án, không phân tích ảnh hoặc tự xuất bản. Studio dùng budget tối đa 90 giây, đầu ra 512 token và cùng khóa inference với chat; các giới hạn 45 giây/384 token bên dưới áp dụng cho hỏi đáp Visitor. Xem [Xưởng nội dung AI](../AI_STUDIO_LOCAL_2026_11_09.md).

## Cài và chạy

PowerShell tại AI-System, dùng Python 3.12:

```powershell
cd D:\SEP409\AI-System
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r '.\AI Chat\requirements.txt' -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/download_chat_model.py
.\tools\start-local-chat.ps1
```

Nếu `.venv` đã tồn tại thì bỏ dòng tạo lại. Model đã được tải trên máy trong lần triển khai 08/11. Lần tải đầu cần internet; inference chỉ đọc file local. Model/cache và `state/chat-service-key.txt` được gitignore. Script tạo khóa nội bộ ngẫu nhiên trong file ignored, không in khóa. Không dùng file temp ảnh người dùng làm dữ liệu seed chatbot.

Terminal BE khác (DB/JWT/seed của BE vẫn cấu hình như trước):

```powershell
cd D:\SEP409\BackEnd\Smart_Museum_Guide_System
.\tools\start-api-with-local-chat.ps1
```

Chỉ chạy một BE ở cổng 5169. Nếu BE đang chạy, dừng terminal BE đó rồi chạy lại bằng lệnh trên để nạp cấu hình mới; không cần xóa DB hoặc đổi tài khoản. Sau đó mở Flutter Visitor qua `/visitor/`, chọn **hiện vật có nội dung tiếng Việt đã xuất bản → Hỏi hướng dẫn viên**.

`GET http://127.0.0.1:8003/ready` phải trả 200 và `CPUExecutionProvider`. Thiếu model trả 503; `/live` chỉ kiểm tra process. API `POST /api/v1/guide/answers` dành cho BE, bắt buộc `X-Service-Key`. Không bật CORS để browser gọi thẳng model. Không có key cloud cần nhập vào UI.

Thiết lập thủ công cho BE: `ArtifactGuide__Enabled=true`, `ArtifactGuide__BaseUrl=http://127.0.0.1:8003/`, `ArtifactGuide__ServiceKey` trùng `AI_CHAT_SERVICE_KEY`. Khi dùng Docker, BE container phải gọi hostname dịch vụ AI Chat trong private network, không dùng loopback của container BE. Mount đủ model/tokenizer ở `AI_CHAT_MODEL_DIR`; không tự tải model khi API khởi động.

## Cách trả lời và giới hạn

- Model nhận tên, mô tả, narration đã xuất bản và bốn cặp hội thoại gần nhất từ BE; không tự đọc DB hoặc sửa dữ liệu.
- Bản đầu dùng **hỏi đáp trích xuất**: model chọn đoạn trả lời có sẵn trong nguồn. Guard kiểm tra đáp án sau chuẩn hóa phải nằm trong tên/mô tả/narration. Nếu model bịa niên đại hoặc thêm chi tiết không có nguồn, trả `supported=false`; BE hiển thị thông báo thiếu thông tin.
- Guard không chứng minh đoạn trích luôn trả lời đúng câu hỏi. Cần đánh giá ngữ nghĩa trên nhiều hồ sơ; model 1.5B không phải hướng dẫn viên đáng tin cậy tuyệt đối.
- Context tối đa 2.048 token, đáp án tối đa 384 token, deadline 45 giây. Dữ liệu vượt budget trả 422; không âm thầm cắt nguồn. Prefill từng 128 token để hạn chế RAM cho logits.
- Một inference tại một thời điểm, chờ khóa 0,5 giây rồi trả 503 nếu bận; không dùng nhiều worker tải trùng model trên máy 16 GB. Liveness dùng route async riêng.
- Khi đóng chat/đăng xuất, FE bỏ đáp án đến muộn; inference native có thể tiếp tục tới deadline. Chưa có hủy request native, streaming, nhập giọng nói, lịch sử chat trong DB hoặc RAG nhiều hiện vật.
- Dữ liệu thật phải do BE nạp sau khi kiểm tra trạng thái/quyền. Không mở public service key cho Visitor.

## Kiểm thử

```powershell
cd 'D:\SEP409\AI-System\AI Chat'
..\.venv\Scripts\python.exe -m unittest discover -s tests -v

cd D:\SEP409\AI-System
.\.venv\Scripts\python.exe tools/evaluate_local_chat.py
```

Kiểm thử code dùng engine fixture; đánh giá trong `evaluations/chat-2026-11-08` chạy ONNX thật qua API ASGI. Giữ nguyên baseline trước source guard để thấy lỗi bịa dữ kiện, không chỉ lưu các ca thành công. Các nhãn ảnh A14/B01 là ngữ cảnh đánh giá cô lập, chưa phải bản ghi DB được kiểm duyệt.

Tài liệu runtime: [ONNX Runtime Python API](https://onnxruntime.ai/docs/api/python/api_summary.html). Không dùng API generate của CLIP: decoder văn bản quản lý attention mask, position IDs và KV cache riêng.
