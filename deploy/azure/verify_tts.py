"""Run on VM: real HTTP/Piper checks without printing private configuration."""
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import wave

ROOT = Path(__file__).resolve().parent
TEXT = ('Bình gốm này được dùng để đựng nước. Miệng bình loe rộng, thân bình có hoa văn khắc chìm. '
        'Chất liệu của bình là đất nung; kỹ thuật chế tác là bàn xoay.\n\n'
        'Quý khách hãy quan sát phần miệng bình. Những chi tiết này giúp chúng ta tìm hiểu cách sử dụng hiện vật. '
        'Đây là nội dung giả lập để kiểm thử giọng đọc, không phải hồ sơ bảo tàng thật.')


def main():
    config = dict(line.split('=', 1) for line in (ROOT / '.env.azure').read_text().splitlines()
                  if line and not line.startswith('#') and '=' in line)
    origin = 'http://127.0.0.1:8000'

    def request(path, body=None, authorized=True):
        headers = {'Content-Type': 'application/json'}
        if authorized:
            headers['X-Service-Key'] = config['TTS_SERVICE_API_KEY']
        req = urllib.request.Request(origin + path, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as response:
            return response.code, dict(response.headers), response.read()

    status, _, ready = request('/ready')
    if status != 200:
        print(json.dumps({'ready': status}))
        raise SystemExit(1)
    payload = json.dumps({'text': TEXT, 'language': 'vi-VN', 'speed': 1.0}).encode()
    started = time.monotonic()
    status, headers, data = request('/api/v1/speech', payload)
    seconds = round(time.monotonic() - started, 3)
    if status != 200:
        print(json.dumps({'speechStatus': status}))
        raise SystemExit(1)
    headers = {key.lower(): value for key, value in headers.items()}
    with wave.open(io.BytesIO(data)) as wav:
        audio = {'channels': wav.getnchannels(), 'sampleWidth': wav.getsampwidth(),
                 'sampleRate': wav.getframerate(), 'frames': wav.getnframes(),
                 'durationSeconds': round(wav.getnframes() / wav.getframerate(), 3)}
    cached_status, cached_headers, cached = request('/api/v1/speech', payload)
    cached_headers = {key.lower(): value for key, value in cached_headers.items()}
    checks = {
        'realReady': json.loads(ready).get('model_ready') is True,
        'speech200': status == 200,
        'pcm16Mono': audio['channels'] == 1 and audio['sampleWidth'] == 2 and audio['frames'] > 0,
        'museumV4': headers.get('x-tts-prosody') == 'museum-v4',
        'baselineSpeed09': headers.get('x-tts-effective-speed') == '0.9000',
        'cacheIdentical': cached_status == 200 and cached_headers.get('x-tts-cache') == 'HIT' and data == cached,
        'missingKeyRejectedBeforeBody': request('/api/v1/speech', b'not json', authorized=False)[0] == 401,
        'invalidSpeedRejected': request('/api/v1/speech', json.dumps({'text': TEXT, 'speed': 3}).encode())[0] == 422,
    }
    report = {'realPiperCpuOnAzure': True, 'sourceSynthetic': True, 'humanListeningApproved': False,
              'scope': 'VM loopback HTTP, not public HTTPS or BE integration',
              'generationSeconds': seconds, 'ready': json.loads(ready), 'audio': audio, 'checks': checks}
    (ROOT / 'tts-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (ROOT / 'tts-museum-v4.wav').write_bytes(data)
    print(json.dumps(report, ensure_ascii=False))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
