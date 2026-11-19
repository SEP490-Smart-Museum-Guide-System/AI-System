# Piper CPU: nhịp đọc — 19/11/2026

Từ D:\SEP409 chạy `AI-System\.venv\Scripts\python.exe AI-System\tools\evaluate_tts_prosody.py`.
Model tiếng Việt thật, CPU local; nguồn giả lập trong results.json, không gọi DB/VM.

- Trước sửa: 15,483 giây; khoảng yên >=100 ms tổng 0,16 giây.
- museum-v4: 17,812 giây; khoảng yên >=100 ms tổng 2,66 giây.
- 4/4 kiểm tra WAV/cache và 13 kiểm tra API/cache/segmentation đạt.
- WAV cùng thư mục được gitignore. Chưa có người nghe duyệt phát âm/tự nhiên.

Giữ dấu câu và thêm khoảng nghỉ tại ranh giới câu 320 ms, mệnh đề 140 ms, đoạn
trắng 450 ms; không chèn đầu/cuối WAV. Không cắt số 3,5 hoặc mã A.12; một số viết
tắt thông dụng được giữ liền. Heuristic vẫn cần nghe thử với nội dung thật.
API speed=1 dùng model speed=0,9, không đổi sample rate để làm giọng trầm đi.

Giả thuyết ban đầu chỉ đổi silence_scale chưa đủ; các lượt v2/v3 chỉ 3/5 kiểm tra
đạt. Giữ failed-v3.json; các mẫu đó không phải bản phát hành. Python sherpa 1.13.8
tạo GenerationConfig riêng trong overload sid/speed. Bản v4 truyền config tường
minh và đặt khoảng nghỉ câu. Không khẳng định silence_scale là nguyên nhân duy nhất.
Cache phân biệt version prosody và mọi tham số nghỉ/tốc độ.
Chưa deploy Azure hoặc kiểm chứng phát qua BE production.
