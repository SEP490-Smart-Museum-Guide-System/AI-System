"""Run the pinned real Qwen checkpoint on synthetic sources without HF redeploys.

Uses CPU 16-bit weights and the Space decoder/prompt/validators. This is not an HF GPU,
quota or production-quality guarantee. Weights must already be downloaded.
"""
import argparse
import datetime
import json
from pathlib import Path
import sys
import threading
import time


CASES = [
    ('Bình gốm DEMO', 'Bình gốm được dùng để đựng nước. Chất liệu là đất nung. Miệng bình loe rộng. Thân bình có hoa văn khắc chìm. Bình được làm bằng kỹ thuật bàn xoay. Đây là tư liệu giả lập để kiểm thử phần mềm, không phải hồ sơ hiện vật thật.'),
    ('Trống DEMO', 'Trống được dùng để báo hiệu trong lễ hội. Chất liệu là đồng. Thân trống có hình trụ. Mặt trống có họa tiết ngôi sao. Trống được làm bằng kỹ thuật đúc khuôn. Đây là tư liệu giả lập để kiểm thử phần mềm, không phải hồ sơ hiện vật thật.'),
]


def run(args):
    sys.path.insert(0, str(args.bundle.resolve()))
    import spaces  # Same import order as the deployed app; CPU has no allocation.
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from pytorch_engine import TorchQuizEngine, REVISION
    from quiz_set import generate_quiz_set
    from app.engine import ChatFailure
    torch.set_num_threads(args.threads)
    attempts = []

    class ProbeEngine(TorchQuizEngine):
        def __init__(self):
            self.device = 'cpu'
            self.lock = threading.Lock()
            self.tokenizer = AutoTokenizer.from_pretrained(args.model_folder, local_files_only=True)
            self.model = AutoModelForCausalLM.from_pretrained(args.model_folder, dtype=getattr(torch,args.dtype),
                local_files_only=True).eval()

        def generate_json(self, prompt, validator, **kwargs):
            payload = json.loads(prompt.rsplit('<|im_start|>user\n', 1)[1].split('<|im_end|>')[0])
            row = {'target': payload.get('TARGET_EVIDENCE'), 'attempt':payload.get('ATTEMPT'),
                'temperature': kwargs.get('temperature'), 'startedAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
            attempts.append(row)
            start = time.monotonic()
            def checked(text):
                row['rawModelText'] = text
                return validator(text)
            try:
                value = super().generate_json(prompt, checked, **kwargs)
                row['passedSourceValidator'] = True
                return value
            except Exception as error:
                row['error'] = str(error)
                raise
            finally:
                row['elapsedSeconds'] = round(time.monotonic()-start, 2)
                args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps({key:row.get(key) for key in ('target','attempt','elapsedSeconds','passedSourceValidator','error')}, ensure_ascii=False),flush=True)

    report = {'real_model':True,'fixture':False,'hf_gpu_tested':False,'device':'cpu','dtype':'float16',
        'modelRevision': REVISION, 'sourcesAreSynthetic':True,'cases':[], 'attempts':attempts}
    report['dtype']=args.dtype
    print(f'Loading pinned real checkpoint on CPU {args.dtype}...',flush=True)
    engine = ProbeEngine()
    print('Model loaded; starting generation.',flush=True)
    for name, source in CASES[:args.cases]:
        start=time.monotonic()
        case={'artifactName':name,'sourceText':source}
        try:
            case['result']=generate_quiz_set(engine,name,source,'easy',[],5,budget_seconds=args.budget)
        except ChatFailure as error:
            case['error']={'status':error.status,'message':str(error)}
        case['elapsedSeconds']=round(time.monotonic()-start,2)
        report['cases'].append(case)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--model-folder',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cases',type=int,choices=[1,2],default=1)
    parser.add_argument('--budget',type=int,default=240)
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--dtype',choices=['float16','bfloat16'],default='bfloat16')
    result=run(parser.parse_args())
    print(json.dumps(result,ensure_ascii=False,indent=2))
