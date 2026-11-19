"""Real Piper CPU comparison for pacing; synthetic narration, no DB or VM required."""
import io
import json
import os
from pathlib import Path
import sys
import time
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'TTS AI'))
os.environ['TTS_MODEL_DIR'] = str(ROOT / 'state/models/tts')
OUT = ROOT / 'evaluations/tts-2026-11-19'
os.environ['TTS_CACHE_DIR'] = str(ROOT / 'state/tts-prosody-evaluation-cache')
from app.config import get_settings
from app.synthesizer import PiperSynthesizer

TEXT = ('Bình gốm này được dùng để đựng nước. Miệng bình loe rộng, thân bình có hoa văn khắc chìm. '
        'Chất liệu của bình là đất nung; kỹ thuật chế tác là bàn xoay.\n\n'
        'Quý khách hãy quan sát phần miệng bình. Những chi tiết này giúp chúng ta tìm hiểu cách sử dụng hiện vật. '
        'Đây là nội dung giả lập để kiểm thử giọng đọc, không phải hồ sơ bảo tàng thật.')


def inspect_audio(data):
    with wave.open(io.BytesIO(data)) as wav:
        rate, count = wav.getframerate(), wav.getnframes()
        assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
        samples = np.frombuffer(wav.readframes(count), dtype='<i2').astype(np.float64) / 32768
    window = max(1, round(rate * 0.02))
    blocks = samples[:len(samples) // window * window].reshape(-1, window)
    quiet = np.sqrt(np.mean(blocks * blocks, axis=1)) < 0.005
    runs = []
    start = None
    for i, is_quiet in enumerate([*quiet, False]):
        if is_quiet and start is None:
            start = i
        elif not is_quiet and start is not None:
            duration = (i - start) * window / rate
            if duration >= 0.1:
                runs.append({'startSeconds': round(start * window / rate, 3), 'durationSeconds': round(duration, 3)})
            start = None
    return {'sampleRate': rate, 'durationSeconds': round(count / rate, 3), 'frames': count,
            'peak': round(float(np.max(np.abs(samples))), 5), 'rms': round(float(np.sqrt(np.mean(samples * samples))), 5),
            'quietRunsAtLeast100ms': runs, 'quietSecondsInRuns': round(sum(r['durationSeconds'] for r in runs), 3)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'realPiperCpu': True, 'syntheticSource': True, 'humanListeningApproved': False,
              'text': TEXT, 'cases': [], 'checks': []}
    variants = [
        ('before-compressed-pauses', '1.0', '0.2', '0', '0', '0', ' '.join(TEXT.split()), 1.0),
        ('native-pauses', '1.0', '1.0', '0', '0', '0', ' '.join(TEXT.split()), 1.0),
        ('museum-v4', '0.9', '1.0', '450', '320', '140', TEXT, 1.0),
    ]
    for name, factor, silence, paragraph_pause, sentence_pause, clause_pause, text, speed in variants:
        os.environ.update(TTS_SPEED_FACTOR=factor, TTS_SILENCE_SCALE=silence, TTS_PARAGRAPH_PAUSE_MS=paragraph_pause,
                          TTS_SENTENCE_PAUSE_MS=sentence_pause, TTS_CLAUSE_PAUSE_MS=clause_pause)
        get_settings.cache_clear()
        engine = PiperSynthesizer()
        start = time.monotonic()
        audio, hit = engine.generate(text, speed)
        row = {'name': name, 'speed': speed, 'speedFactor': float(factor), 'silenceScale': float(silence),
               'paragraphPauseMs': int(paragraph_pause), 'sentencePauseMs': int(sentence_pause),
               'clausePauseMs': int(clause_pause), 'cacheHit': hit, 'file': name + '.wav',
               'generationSeconds': round(time.monotonic() - start, 3), **inspect_audio(audio)}
        (OUT / row['file']).write_bytes(audio)
        cached, cache_hit = engine.generate(text, speed)
        row['cacheRoundTripIdentical'] = cache_hit and cached == audio
        report['cases'].append(row)
        (OUT / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({key: row[key] for key in ('name', 'durationSeconds', 'quietSecondsInRuns', 'generationSeconds', 'cacheRoundTripIdentical')}, ensure_ascii=False), flush=True)
        del engine
    before, native, after = report['cases']
    report['checks'] = [
        {'name': 'museum rendering longer than baseline', 'passed': after['durationSeconds'] > before['durationSeconds'] * 1.1},
        {'name': 'museum pause duration increased', 'passed': after['quietSecondsInRuns'] > before['quietSecondsInRuns']},
        {'name': 'all files non-silent mono PCM', 'passed': all(row['rms'] > 0.001 and row['frames'] > 0 for row in report['cases'])},
        {'name': 'cache returns identical generated WAV', 'passed': all(row['cacheRoundTripIdentical'] for row in report['cases'])},
    ]
    (OUT / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'checksPassed': sum(row['passed'] for row in report['checks']), 'totalChecks': len(report['checks'])}))
    if not all(row['passed'] for row in report['checks']):
        raise SystemExit(1)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
