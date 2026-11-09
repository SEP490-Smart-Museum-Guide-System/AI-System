# Kiểm thử Xưởng AI ONNX thật — 09/11/2026

Qwen2.5-1.5B-Instruct INT4, CPU ONNX Runtime. API ASGI/model chạy thật, không ghi DB nghiệp vụ, không phân tích ảnh.

| Chế độ | Hiện vật | HTTP | Giây |
| --- | --- | ---: | ---: |
| narration | Máy nén khí | 200 | 23.83 |
| quiz | Máy nén khí | 200 | 41.7 |
| quiz | Van mở dầu | 502 | 35.21 |

Hai đầu ra máy nén khí được chấp nhận. Quiz van dầu bị từ chối: model hỏi loại lò nhưng các phương án lại là nước/đất/điện/dầu; bước hỏi đáp trích xuất độc lập không xác nhận đáp án. Đây là một ca chặn đầu ra sai, không phải sinh quiz thành công. Baseline trước bước kiểm tra này nằm trong before-answer-consistency-check.json.

Response và đầu ra model trước kiểm tra nằm trong results.json. Model từng sai chỉ số đáp án (đếm từ 1); validator hiện xác định lại đáp án duy nhất có trong nguồn, không tin chỉ số model. Kiểm tra đoạn trích/con số không chứng minh mọi diễn giải hoặc câu hỏi đúng ngữ nghĩa; Curator vẫn phải duyệt.

Giữ các probe thất bại ban đầu để đối chiếu: initial-probe.json, raw-validation-probe.json, prefill-probe.json và fewshot-quiz-probe.json. Không tính bộ thử nhỏ này thành độ chính xác production.
