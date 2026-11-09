"""Exercise the real running Piper API and inspect its PCM audio; no DB writes.

Run tools/start-local-tts.ps1 first. This measures generation/playable-file health,
not linguistic accuracy: a human should listen to the saved WAV samples.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import wave

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')


def pcm_info(data):
    with wave.open(io.BytesIO(data), 'rb') as wav:
        info = {'channels': wav.getnchannels(), 'sample_width': wav.getsampwidth(),
                'sample_rate': wav.getframerate(), 'frames': wav.getnframes()}
        samples = wav.readframes(wav.getnframes())
    assert info['channels'] == 1 and info['sample_width'] == 2
    assert len(samples) == info['frames'] * 2 and info['frames'] > 0
    values = np.frombuffer(samples, dtype='<i2').astype(np.float64) / 32768
    info.update(duration_seconds=round(info['frames'] / info['sample_rate'], 3),
                peak=round(float(np.max(np.abs(values))), 5),
                rms=round(float(np.sqrt(np.mean(values ** 2))), 5),
                clipped_fraction=round(float(np.mean(np.abs(values) >= 0.999)), 7),
                bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    assert info['rms'] > 0.001, 'Audio is empty or effectively silent'
    return info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    out = ROOT / 'evaluations/tts-2026-11-09'
    out.mkdir(parents=True, exist_ok=True)
    studio = json.loads((ROOT / 'evaluations/studio-2026-11-09/results.json').read_text(encoding='utf-8'))
    narration = next(r['response']['narrationText'] for r in studio['results'] if r['mode'] == 'narration' and r['status'] == 200)
    cases = [
        ('compressor-ai-draft', narration, 1.0),
        ('vietnamese-names-dates', 'Trống đồng Ngọc Lũ là hiện vật tiêu biểu của văn hóa Đông Sơn. Ngày mùng hai tháng chín năm một nghìn chín trăm bốn mươi lăm.', 1.0),
        ('compressor-readable-units', 'Máy nén khí có công suất bảy phẩy năm mã lực, do Xí nghiệp thiết bị lạnh sản xuất. Thân kim loại sơn màu xanh, phía bên phải có bánh đai.', 1.0),
        ('valve-slow', 'Van mở dầu cung cấp cho lò hạ áp. Hiện vật có tay vặn và thân kim loại.', 0.75),
        ('valve-fast', 'Van mở dầu cung cấp cho lò hạ áp. Hiện vật có tay vặn và thân kim loại.', 1.25),
    ]
    report = {'date': '2026-11-09', 'scope': 'Real HTTP + Piper ONNX CPU; test text, not published DB content',
              'phonetic_accuracy_verified': False, 'cases': [], 'validation': []}
    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        health = client.get('/ready'); health.raise_for_status()
        report['ready'] = health.json()
        assert report['ready']['model_ready'] and report['ready']['language'] == 'vi-VN'
        for name, text, speed in cases:
            started = time.perf_counter()
            response = client.post('/api/v1/speech', json={'text': text, 'language': 'vi-VN', 'speed': speed})
            elapsed = time.perf_counter() - started
            response.raise_for_status()
            assert response.headers['content-type'].startswith('audio/wav')
            info = pcm_info(response.content)
            file = out / f'{name}.wav'; file.write_bytes(response.content)
            row = {'name': name, 'text': text, 'speed': speed, 'status': response.status_code,
                   'cache': response.headers.get('x-tts-cache'), 'voice': response.headers.get('x-tts-voice'),
                   'generation_seconds': round(elapsed, 3), 'file': file.name, **info}
            report['cases'].append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            cached = client.post('/api/v1/speech', json={'text': text, 'language': 'vi-VN', 'speed': speed})
            assert cached.status_code == 200 and cached.headers['x-tts-cache'] == 'HIT' and cached.content == response.content
        for body in [{'text': ' '}, {'text': 'Văn bản', 'language': 'en'}, {'text': 'Văn bản', 'speed': 3}]:
            response = client.post('/api/v1/speech', json=body)
            assert response.status_code == 422
            report['validation'].append({'request': body, 'status': response.status_code})
    slow, fast = report['cases'][-2:]
    assert slow['duration_seconds'] > fast['duration_seconds'], 'Speed setting did not affect audio duration'
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: 5 real audio samples, 5 identical server-cache hits, 3 invalid requests rejected; phonetics needs human listening.')


if __name__ == '__main__':
    main()
