"""Real ONNX/ASGI evaluation for staff drafts. No business DB writes or external inference."""
import json
import os
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
os.environ['AI_CHAT_SERVICE_KEY'] = secrets.token_urlsafe(32)
sys.path.insert(0, str(ROOT / 'AI Chat'))
from app.engine import OnnxChat
from app.main import app, DEFAULT_MODEL, REVISION
import app.studio as studio
from fastapi.testclient import TestClient

raw = []
original = studio.validate_draft
def capture(text, source, mode, excluded):
    raw.append({'mode': mode, 'raw': text})
    return original(text, source, mode, excluded)
studio.validate_draft = capture
engine = OnnxChat(DEFAULT_MODEL)
app.state.engine, app.state.model_ready = engine, True
compressor = 'Máy nén khí có công suất 7,5hp, do Xí nghiệp thiết bị lạnh sản xuất. Thân kim loại sơn màu xanh, phía bên phải có bánh đai.'
valve = 'Van mở dầu cung cấp cho lò hạ áp. Hiện vật có tay vặn và thân kim loại.'
cases = [('narration', 'Máy nén khí', compressor), ('quiz', 'Máy nén khí', compressor), ('quiz', 'Van mở dầu', valve)]
rows = []
client = TestClient(app, raise_server_exceptions=True)
try:
    # Model is loaded once; the production DB is never initialized.
    for mode, name, source in cases:
        start = time.perf_counter()
        response = client.post('/api/v1/studio/drafts', headers={'X-Service-Key': os.environ['AI_CHAT_SERVICE_KEY']}, json={
            'artifactId': 17, 'artifactName': name, 'sourceText': source, 'mode': mode,
            'audience': 'general', 'tone': 'vivid', 'difficulty': 'easy', 'excludeQuestions': []})
        result = {'mode': mode, 'artifact': name, 'source': source, 'status': response.status_code,
                  'seconds': round(time.perf_counter() - start, 2), 'response': response.json()}
        rows.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
finally:
    client.close()
out = ROOT / 'evaluations/studio-2026-11-09'
out.mkdir(parents=True, exist_ok=True)
report = {'date': '2026-11-09', 'model': engine.model_name, 'revision': REVISION, 'runtime': engine.runtime,
          'providers': engine.providers, 'production_db': False, 'image_inference': False,
          'source_note': 'Nhãn ảnh A14/B01 và quan sát ảnh người dùng, chưa là bản ghi được bảo tàng duyệt.',
          'results': rows, 'raw_for_validation_audit': raw}
(out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
lines = ['# Kiểm thử Xưởng AI ONNX thật — 09/11/2026', '',
         'Qwen2.5-1.5B-Instruct INT4, CPU ONNX Runtime. API ASGI/model chạy thật, không ghi DB nghiệp vụ, không phân tích ảnh.', '',
         '| Chế độ | Hiện vật | HTTP | Giây |', '| --- | --- | ---: | ---: |']
for row in rows: lines.append(f"| {row['mode']} | {row['artifact']} | {row['status']} | {row['seconds']} |")
lines += ['', 'Hai đầu ra máy nén khí được chấp nhận. Quiz van dầu bị từ chối: model hỏi loại lò nhưng các phương án lại là nước/đất/điện/dầu; bước hỏi đáp trích xuất độc lập không xác nhận đáp án. Đây là một ca chặn đầu ra sai, không phải sinh quiz thành công. Baseline trước bước kiểm tra này nằm trong before-answer-consistency-check.json.', '',
          'Response và đầu ra model trước kiểm tra nằm trong results.json. Model từng sai chỉ số đáp án (đếm từ 1); validator hiện xác định lại đáp án duy nhất có trong nguồn, không tin chỉ số model. Kiểm tra đoạn trích/con số không chứng minh mọi diễn giải hoặc câu hỏi đúng ngữ nghĩa; Curator vẫn phải duyệt.', '',
          'Giữ các probe thất bại ban đầu để đối chiếu: initial-probe.json, raw-validation-probe.json, prefill-probe.json và fewshot-quiz-probe.json. Không tính bộ thử nhỏ này thành độ chính xác production.', '']
(out / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
print(json.dumps({'successes': sum(r['status'] == 200 for r in rows), 'total': len(rows)}, ensure_ascii=False))
