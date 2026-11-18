"""Offline smoke of pinned Qwen with the new Space adapter, CPU only, synthetic data."""
import argparse
import datetime
import json
from pathlib import Path
import sys
import threading
import time


def run(args):
    sys.path.insert(0, str(args.bundle.resolve()))
    import spaces  # Keep the same initialization order as the Space.
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import pytorch_engine as module
    from app.engine import ChatFailure
    torch.set_num_threads(4)
    engine = module.TorchGuideEngine.__new__(module.TorchGuideEngine)
    engine.device, engine.lock = 'cpu', threading.Lock()
    engine.deadline_seconds = args.budget
    engine.tokenizer = AutoTokenizer.from_pretrained(args.model_folder, local_files_only=True)
    engine.model = AutoModelForCausalLM.from_pretrained(args.model_folder, dtype=torch.bfloat16, local_files_only=True).eval()
    examples = json.loads((args.bundle / 'examples.json').read_text(encoding='utf-8'))
    ceramic = examples['chat']['context']
    drum = {**ceramic, 'artifactId': 2, 'artifactName': 'Trống DEMO',
            'description': 'Trống được dùng để báo hiệu trong lễ hội. Chất liệu là đồng.',
            'narrationText': 'Mặt trống có họa tiết ngôi sao. Trống được làm bằng kỹ thuật đúc khuôn.'}
    cases = [(ceramic, 'Bình gốm được làm bằng chất liệu gì?', 'đất nung'),
             (drum, 'Trống được dùng để làm gì?', 'báo hiệu'),
             (ceramic, 'Bình gốm được chế tác vào năm nào?', None)]
    report = {'real_model': True, 'fixture': False, 'hf_gpu_tested': False,
              'device': 'cpu', 'dtype': 'bfloat16', 'modelRevision': module.REVISION,
              'sourcesAreSynthetic': True, 'generationBudgetSeconds': args.budget,
              'productionGpuGenerationBudgetSeconds': 45,
              'startedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'cases': []}
    for context, question, expected in cases:
        row = {'context': context, 'question': question, 'expectedAnswerContains': expected}
        report['cases'].append(row)
        original = module.parse_answer

        def record(text):
            row['rawModelText'] = text
            return original(text)

        module.parse_answer = record
        started = time.monotonic()
        try:
            result = engine.answer(context, question, [])
            row['result'] = result
            row['passed'] = (result['supported'] and expected in result['answer'].casefold()) if expected else not result['supported']
        except ChatFailure as error:
            row['error'] = {'status': error.status, 'detail': str(error)}
            row['passed'] = False
        finally:
            module.parse_answer = original
            row['elapsedSeconds'] = round(time.monotonic() - started, 2)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(row, ensure_ascii=False), flush=True)
    return report


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--model-folder', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget', type=int, default=45)
    args = parser.parse_args()
    result = run(args)
    if not all(row.get('passed') for row in result['cases']):
        sys.exit(1)
